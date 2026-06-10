from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from ..services.r2_service import upload_image, delete_image
from ..utils.deps import get_current_user
from ..utils.exif import extract_gps_from_image
from ..utils.image_validation import detect_image_content_type
from ..models.user import User

router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
MAX_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("/image")
async def upload_image_endpoint(
    file: UploadFile = File(...),
    _user: User = Depends(get_current_user),
):
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(400, "File too large (max 20 MB)")

    detected_type = detect_image_content_type(contents)
    content_type = detected_type or file.content_type
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Only JPEG, PNG, WebP, and HEIC images are allowed")

    exif_result = extract_gps_from_image(contents)
    url = await upload_image(contents, file.filename or "upload.jpg", content_type)

    response: dict = {"url": url}
    if exif_result:
        lat, lon, date_taken = exif_result
        response["exif"] = {
            "latitude": lat,
            "longitude": lon,
            "date_taken": date_taken,
        }

    return response


class DeleteImageRequest(BaseModel):
    url: str


@router.delete("/image")
async def delete_image_endpoint(
    body: DeleteImageRequest,
    _user: User = Depends(get_current_user),
):
    """Delete an image that was uploaded but never attached to a point (cancelled form)."""
    await delete_image(body.url)
    return {"ok": True}
