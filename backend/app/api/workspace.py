from datetime import datetime, timezone
from typing import Annotated

from app.core.objectid import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import ValidationError
from app.core.db_compat import is_duplicate_key_error

from app.core.database import mongo
from app.core.dependencies import get_current_user, require_roles
from app.core.security import hash_password
from app.core.serializers import serialize_doc
from app.models import NotificationUpdateRequest, UserCreateRequest, UserUpdateRequest
from app.services.activity import log_activity
from app.services.profile_images import delete_profile_image, upload_profile_image

router = APIRouter(tags=["Workspace"])


@router.get("/activity")
def activity(limit: int = Query(default=50, ge=1, le=200), user: dict = Depends(get_current_user)):
    return {"items": [serialize_doc(item) for item in mongo.db.activity_logs.find().sort("created_at", -1).limit(limit)]}


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
def users(user: dict = Depends(require_roles("admin", "manager"))):
    return {"items": [serialize_doc(item) for item in mongo.db.users.find().sort("created_at", -1)]}


@router.post("/users")
async def create_user(
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    cnic: Annotated[str, Form()],
    city: Annotated[str, Form()],
    role: Annotated[str, Form()] = "salesperson",
    profile_image: Annotated[UploadFile | None, File()] = None,
    current_user: dict = Depends(require_roles("admin")),
):
    try:
        payload = UserCreateRequest(name=name, email=email, password=password, cnic=cnic, city=city, role=role)
    except ValidationError as exc:
        message = exc.errors()[0].get("msg", "Invalid account details") if exc.errors() else "Invalid account details"
        raise HTTPException(status_code=422, detail=message.replace("Value error, ", "")) from exc

    image_data = await upload_profile_image(profile_image, str(payload.email)) if profile_image else {}
    now = datetime.now(timezone.utc)
    document = {
        "name": payload.name,
        "email": payload.email.lower(),
        "password_hash": hash_password(payload.password),
        "cnic": payload.cnic,
        "city": payload.city,
        "role": payload.role,
        "active": True,
        **image_data,
        "created_at": now,
        "updated_at": now,
    }
    try:
        document["_id"] = mongo.db.users.insert_one(document).inserted_id
    except Exception as exc:
        delete_profile_image(image_data.get("profile_image_public_id"))
        if not is_duplicate_key_error(exc):
            raise
        if "cnic" in str(exc).lower():
            raise HTTPException(status_code=409, detail="A user with this CNIC already exists") from exc
        raise HTTPException(status_code=409, detail="A user with this email already exists") from exc

    log_activity(current_user, "Created", "User", str(document["_id"]), payload.email)
    return serialize_doc(document)


@router.patch("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdateRequest, user: dict = Depends(require_roles("admin"))):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        changes["name"] = " ".join(changes["name"].strip().split())
    if "city" in changes:
        changes["city"] = " ".join(changes["city"].strip().split())
    changes["updated_at"] = datetime.now(timezone.utc)
    result = mongo.db.users.update_one({"_id": ObjectId(user_id)}, {"$set": changes})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="User not found")
    log_activity(user, "Updated", "User", user_id, ", ".join(changes.keys()))
    return serialize_doc(mongo.db.users.find_one({"_id": ObjectId(user_id)}))
