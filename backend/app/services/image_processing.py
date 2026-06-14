import io
import os
from typing import Tuple

from PIL import Image

try:
    from pillow_heif import register_heif_opener
except ImportError:  # pragma: no cover - optional dependency until installed
    register_heif_opener = None

if register_heif_opener:
    register_heif_opener()


def normalize_uploaded_image(image_bytes: bytes, original_filename: str, content_type: str) -> Tuple[bytes, str, str]:
    normalized_type = (content_type or "").lower()
    if normalized_type not in {"image/heic", "image/heif"}:
        return image_bytes, original_filename, content_type

    if not register_heif_opener:
        raise ValueError("HEIC support is not installed on the server")

    with Image.open(io.BytesIO(image_bytes)) as image:
        exif_bytes = image.info.get("exif")
        converted = image.convert("RGB")
        output = io.BytesIO()
        save_kwargs = {"format": "JPEG", "quality": 90}
        if exif_bytes:
            save_kwargs["exif"] = exif_bytes
        converted.save(output, **save_kwargs)

    base_name = os.path.splitext(original_filename or "upload")[0] or "upload"
    return output.getvalue(), f"{base_name}.jpg", "image/jpeg"
