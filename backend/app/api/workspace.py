from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import ValidationError

from app.core.database import mongo
from app.core.db_compat import is_duplicate_key_error
from app.core.dependencies import get_current_user, require_roles
from app.core.objectid import ObjectId
from app.core.security import hash_password
from app.core.serializers import serialize_doc
from app.models import NotificationUpdateRequest, PasswordResetRequest, UserUpdateRequest
from app.services.activity import create_admin_notification, log_activity
from app.services.profile_images import delete_profile_image, upload_profile_image

router = APIRouter(tags=["Workspace"])


def _user_or_404(user_id: str) -> dict:
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    target = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    return target


def _user_with_stats(target: dict) -> dict:
    result = serialize_doc(target)
    creator_query = {"created_by": target["_id"]}
    result["lead_count"] = mongo.db.leads.count_documents(creator_query)
    result["completed_count"] = mongo.db.leads.count_documents({**creator_query, "status": "Completed"})
    result["contacted_count"] = mongo.db.leads.count_documents(
        {**creator_query, "status": {"$in": ["Contacted", "Follow-up", "Cancel", "Completed"]}}
    )
    return result


def _ensure_regular_user(target: dict) -> None:
    if target.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Administrator accounts are protected")


@router.get("/notifications")
def notifications(user: dict = Depends(get_current_user)):
    query = {"$or": [{"user_id": user["_id"]}, {"user_id": None}]}
    items = [serialize_doc(item) for item in mongo.db.notifications.find(query).sort("created_at", -1).limit(100)]
    unread = mongo.db.notifications.count_documents({**query, "read": False})
    return {"items": items, "unread": unread}


@router.patch("/notifications/{notification_id}")
def update_notification(notification_id: str, payload: NotificationUpdateRequest, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    result = mongo.db.notifications.update_one(
        {"_id": ObjectId(notification_id), "$or": [{"user_id": user["_id"]}, {"user_id": None}]},
        {"$set": {"read": payload.read}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.post("/notifications/read-all")
def read_all_notifications(user: dict = Depends(get_current_user)):
    mongo.db.notifications.update_many({"$or": [{"user_id": user["_id"]}, {"user_id": None}]}, {"$set": {"read": True}})
    return {"ok": True}


@router.get("/users")
def users(user: dict = Depends(require_roles("admin"))):
    return {"items": [_user_with_stats(item) for item in mongo.db.users.find().sort("created_at", -1)]}


@router.get("/users/{user_id}")
def user_detail(user_id: str, user: dict = Depends(require_roles("admin"))):
    return _user_with_stats(_user_or_404(user_id))


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    name: Annotated[str | None, Form()] = None,
    email: Annotated[str | None, Form()] = None,
    cnic: Annotated[str | None, Form()] = None,
    city: Annotated[str | None, Form()] = None,
    profile_image: Annotated[UploadFile | None, File()] = None,
    current_user: dict = Depends(require_roles("admin")),
):
    target = _user_or_404(user_id)
    raw_changes = {key: value for key, value in {"name": name, "email": email, "cnic": cnic, "city": city}.items() if value is not None}
    try:
        payload = UserUpdateRequest(**raw_changes)
    except ValidationError as exc:
        message = exc.errors()[0].get("msg", "Invalid user details") if exc.errors() else "Invalid user details"
        raise HTTPException(status_code=422, detail=message.replace("Value error, ", "")) from exc

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "email" in changes:
        changes["email"] = str(changes["email"]).lower()

    image_data = await upload_profile_image(profile_image, changes.get("email") or target.get("email") or user_id) if profile_image else {}
    changes.update(image_data)
    if not changes:
        return _user_with_stats(target)

    changes["updated_at"] = datetime.now(timezone.utc)
    try:
        result = mongo.db.users.update_one({"_id": target["_id"]}, {"$set": changes})
    except Exception as exc:
        delete_profile_image(image_data.get("profile_image_public_id"))
        if not is_duplicate_key_error(exc):
            raise
        if "cnic" in str(exc).lower():
            raise HTTPException(status_code=409, detail="A user with this CNIC already exists") from exc
        raise HTTPException(status_code=409, detail="A user with this email already exists") from exc

    if not result.matched_count:
        delete_profile_image(image_data.get("profile_image_public_id"))
        raise HTTPException(status_code=404, detail="User not found")

    if image_data and target.get("profile_image_public_id"):
        delete_profile_image(target.get("profile_image_public_id"))

    updated = mongo.db.users.find_one({"_id": target["_id"]})
    log_activity(current_user, "Updated", "User", user_id, ", ".join(key for key in changes if key != "updated_at"))
    return _user_with_stats(updated)


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: str,
    payload: PasswordResetRequest,
    current_user: dict = Depends(require_roles("admin")),
):
    target = _user_or_404(user_id)
    _ensure_regular_user(target)
    mongo.db.users.update_one(
        {"_id": target["_id"]},
        {
            "$set": {
                "password_hash": hash_password(payload.temporary_password),
                "must_change_password": True,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    log_activity(current_user, "Reset", "User password", user_id, target.get("email", ""))
    return {"ok": True}


@router.post("/users/{user_id}/suspend")
def suspend_user(user_id: str, current_user: dict = Depends(require_roles("admin"))):
    target = _user_or_404(user_id)
    _ensure_regular_user(target)
    mongo.db.users.update_one(
        {"_id": target["_id"]},
        {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}},
    )
    log_activity(current_user, "Suspended", "User", user_id, target.get("email", ""))
    return {"ok": True}


@router.post("/users/{user_id}/activate")
def activate_user(user_id: str, current_user: dict = Depends(require_roles("admin"))):
    target = _user_or_404(user_id)
    _ensure_regular_user(target)
    mongo.db.users.update_one(
        {"_id": target["_id"]},
        {"$set": {"active": True, "updated_at": datetime.now(timezone.utc)}},
    )
    log_activity(current_user, "Activated", "User", user_id, target.get("email", ""))
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, current_user: dict = Depends(require_roles("admin"))):
    target = _user_or_404(user_id)
    _ensure_regular_user(target)

    mongo.db.users.delete_one({"_id": target["_id"]})
    mongo.db.notifications.delete_many({"user_id": target["_id"]})
    mongo.db.lead_lists.delete_many({"created_by": target["_id"]})
    delete_profile_image(target.get("profile_image_public_id"))
    log_activity(current_user, "Deleted", "User", user_id, target.get("email", ""))
    create_admin_notification(
        "User account deleted",
        f"{target.get('name', 'A user')} was removed by {current_user.get('name', 'an administrator')}.",
        "account",
        "/team",
    )
    return {"ok": True}
