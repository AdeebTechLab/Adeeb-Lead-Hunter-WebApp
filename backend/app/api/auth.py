from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from app.core.db_compat import is_duplicate_key_error

from app.core.config import settings
from app.core.database import mongo
from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.core.serializers import serialize_doc
from app.models import LoginRequest, SignupRequest
from app.services.activity import log_activity
from app.services.profile_images import delete_profile_image, upload_profile_image

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _form_payload(name: str, email: str, password: str, cnic: str, city: str) -> SignupRequest:
    try:
        return SignupRequest(name=name, email=email, password=password, cnic=cnic, city=city)
    except ValidationError as exc:
        message = exc.errors()[0].get("msg", "Invalid account details") if exc.errors() else "Invalid account details"
        raise HTTPException(status_code=422, detail=message.replace("Value error, ", "")) from exc


@router.post("/signup")
async def signup(
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    cnic: Annotated[str, Form()],
    city: Annotated[str, Form()],
    profile_image: Annotated[UploadFile | None, File()] = None,
):
    if not settings.allow_public_signup:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account registration is disabled")

    payload = _form_payload(name, email, password, cnic, city)
    image_data = await upload_profile_image(profile_image, str(payload.email)) if profile_image else {}
    now = datetime.now(timezone.utc)
    user = {
        "name": payload.name,
        "email": payload.email.lower(),
        "password_hash": hash_password(payload.password),
        "cnic": payload.cnic,
        "city": payload.city,
        "role": "salesperson",
        "active": True,
        **image_data,
        "created_at": now,
        "updated_at": now,
    }
    try:
        user["_id"] = mongo.db.users.insert_one(user).inserted_id
    except Exception as exc:
        delete_profile_image(image_data.get("profile_image_public_id"))
        if not is_duplicate_key_error(exc):
            raise
        if "cnic" in str(exc).lower():
            raise HTTPException(status_code=409, detail="An account with this CNIC already exists") from exc
        raise HTTPException(status_code=409, detail="An account with this email already exists") from exc

    log_activity(user, "Created", "Account", str(user["_id"]), "Account registration")
    token = create_access_token(str(user["_id"]), {"role": user["role"]})
    return {"access_token": token, "token_type": "bearer", "user": serialize_doc(user)}


@router.post("/login")
def login(payload: LoginRequest):
    user = mongo.db.users.find_one({"email": payload.email.lower()})
    if not user or not user.get("active") or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    log_activity(user, "Signed in", "Account", str(user["_id"]))
    token = create_access_token(str(user["_id"]), {"role": user["role"]})
    return {"access_token": token, "token_type": "bearer", "user": serialize_doc(user)}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return serialize_doc(user)
