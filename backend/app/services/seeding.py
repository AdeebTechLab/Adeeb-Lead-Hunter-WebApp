from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import mongo
from app.core.security import hash_password
from app.models import normalize_cnic
from app.services.dedupe import make_dedupe_key, make_identity_keys


def _migrate_legacy_roles_and_pipeline() -> None:
    """Keep existing production data compatible with the two-role and five-stage workflow."""
    now = datetime.now(timezone.utc)
    mongo.db.users.update_many(
        {"role": {"$in": ["manager", "salesperson"]}},
        {"$set": {"role": "user", "updated_at": now}},
    )

    # Previous releases used a generic Closed state. Preserve won deals as Completed
    # and move every other closed record to Cancel. Backfill creator metadata and
    # dedupe keys without failing startup if historical duplicate records already exist.
    existing_keys = {
        item.get("dedupe_key")
        for item in mongo.db.leads.find()
        if item.get("dedupe_key")
    }
    for lead in mongo.db.leads.find():
        changes = {}
        if lead.get("status") == "Closed":
            if lead.get("deal_status") == "Won":
                changes.update({"status": "Completed", "deal_status": "Won"})
            else:
                changes.update({"status": "Cancel", "deal_status": "Lost"})
        identity_keys = make_identity_keys(lead)
        if identity_keys != (lead.get("dedupe_aliases") or []):
            changes["dedupe_aliases"] = identity_keys
        if not lead.get("dedupe_key"):
            dedupe_key = make_dedupe_key(lead)
            if dedupe_key not in existing_keys:
                changes["dedupe_key"] = dedupe_key
                existing_keys.add(dedupe_key)
        if not lead.get("created_by_name") and lead.get("created_by"):
            creator = mongo.db.users.find_one({"_id": lead.get("created_by")})
            changes["created_by_name"] = creator.get("name") if creator else "Former user"
            changes["created_by_email"] = creator.get("email", "") if creator else ""
        if changes:
            changes["updated_at"] = now
            mongo.db.leads.update_one({"_id": lead["_id"]}, {"$set": changes})


def seed_database() -> None:
    """Create the configured administrator and apply safe data migrations."""
    _migrate_legacy_roles_and_pipeline()

    admin_email = settings.default_admin_email.lower().strip()
    existing = mongo.db.users.find_one({"email": admin_email})
    if existing:
        if existing.get("role") != "admin":
            raise RuntimeError("DEFAULT_ADMIN_EMAIL already belongs to a non-admin account")
        missing = {}
        if not existing.get("cnic"):
            missing["cnic"] = normalize_cnic(settings.default_admin_cnic)
        if not existing.get("city"):
            missing["city"] = settings.default_admin_city.strip()
        if existing.get("must_change_password") is None:
            missing["must_change_password"] = False
        if missing:
            missing["updated_at"] = datetime.now(timezone.utc)
            mongo.db.users.update_one({"_id": existing["_id"]}, {"$set": missing})
        return

    now = datetime.now(timezone.utc)
    mongo.db.users.insert_one(
        {
            "name": settings.default_admin_name.strip(),
            "email": admin_email,
            "password_hash": hash_password(settings.default_admin_password),
            "cnic": normalize_cnic(settings.default_admin_cnic),
            "city": settings.default_admin_city.strip(),
            "role": "admin",
            "active": True,
            "must_change_password": False,
            "created_at": now,
            "updated_at": now,
        }
    )
