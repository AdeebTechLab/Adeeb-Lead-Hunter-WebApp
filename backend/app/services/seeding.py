from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import mongo
from app.core.security import hash_password
from app.models import normalize_cnic


def seed_database() -> None:
    """Create the configured administrator if it does not already exist."""
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
            "created_at": now,
            "updated_at": now,
        }
    )
