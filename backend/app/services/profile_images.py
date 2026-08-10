from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _configure_cloudinary():
    if not settings.cloudinary_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Profile image service is not configured",
        )
    import cloudinary

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )


async def upload_profile_image(file: UploadFile | None, identity: str) -> dict:
    if not file or not file.filename:
        return {}
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Profile photo must be JPEG, PNG or WebP")

    raw = await file.read(settings.profile_image_max_bytes + 1)
    if len(raw) > settings.profile_image_max_bytes:
        raise HTTPException(status_code=413, detail="Profile photo must be 1 MB or smaller")

    try:
        image = Image.open(BytesIO(raw))
        image.verify()
        image = Image.open(BytesIO(raw))
        image = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(status_code=422, detail="Profile photo is not a valid image")

    if image.width * image.height > 20_000_000:
        raise HTTPException(status_code=422, detail="Profile photo dimensions are too large")

    # The frontend supplies a square crop. The server still normalizes dimensions,
    # strips metadata and guarantees a compact JPEG before Cloudinary upload.
    side = min(image.size)
    left = max(0, (image.width - side) // 2)
    top = max(0, (image.height - side) // 2)
    image = image.crop((left, top, left + side, top + side)).resize((512, 512), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="JPEG", quality=86, optimize=True)
    output.seek(0)

    _configure_cloudinary()
    import cloudinary.uploader

    safe_identity = "".join(ch for ch in identity.lower() if ch.isalnum())[:32] or "user"
    public_id = f"{safe_identity}-{uuid4().hex[:12]}"
    try:
        result = cloudinary.uploader.upload(
            output,
            folder=settings.cloudinary_profile_folder,
            public_id=public_id,
            resource_type="image",
            format="jpg",
            overwrite=False,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Profile photo upload failed") from exc

    return {
        "profile_image_url": result.get("secure_url"),
        "profile_image_public_id": result.get("public_id"),
    }


def delete_profile_image(public_id: str | None) -> None:
    if not public_id or not settings.cloudinary_configured:
        return
    try:
        _configure_cloudinary()
        import cloudinary.uploader

        cloudinary.uploader.destroy(public_id, invalidate=True, resource_type="image")
    except Exception:
        # Cleanup failure must not hide the original database error.
        return
