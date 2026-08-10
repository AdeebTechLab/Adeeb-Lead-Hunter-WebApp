from datetime import date, datetime
from typing import Any

from app.core.objectid import ObjectId

_PRIVATE_FIELDS = {"password_hash", "profile_image_public_id"}


def serialize_value(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize_value(val) for key, val in value.items() if key not in _PRIVATE_FIELDS}
    return value


def serialize_doc(doc: dict | None) -> dict | None:
    if not doc:
        return None
    result = {key: serialize_value(value) for key, value in doc.items() if key not in _PRIVATE_FIELDS}
    if "_id" in result:
        result["id"] = result.pop("_id")
    return result
