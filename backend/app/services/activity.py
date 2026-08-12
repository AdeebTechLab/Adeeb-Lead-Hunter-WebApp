from datetime import datetime, timezone
from typing import Optional

from app.core.objectid import ObjectId
from app.core.database import mongo


def log_activity(user: dict, action: str, entity: str, entity_id: Optional[str] = None, detail: str = "") -> None:
    """Internal audit trail. The activity page is intentionally not exposed in the UI."""
    mongo.db.activity_logs.insert_one(
        {
            "user_id": user.get("_id"),
            "user_name": user.get("name", "System"),
            "action": action,
            "entity": entity,
            "entity_id": ObjectId(entity_id) if entity_id and ObjectId.is_valid(entity_id) else entity_id,
            "detail": detail,
            "created_at": datetime.now(timezone.utc),
        }
    )


def create_notification(title: str, message: str, kind: str = "info", user_id=None, link: str = "/notifications") -> None:
    mongo.db.notifications.insert_one(
        {
            "title": title,
            "message": message,
            "kind": kind,
            "user_id": user_id,
            "link": link,
            "read": False,
            "created_at": datetime.now(timezone.utc),
        }
    )


def create_admin_notification(title: str, message: str, kind: str = "info", link: str = "/notifications") -> None:
    """Send a private copy of an operational notification to every active administrator."""
    for admin in mongo.db.users.find({"role": "admin", "active": True}):
        create_notification(title, message, kind, admin.get("_id"), link)
