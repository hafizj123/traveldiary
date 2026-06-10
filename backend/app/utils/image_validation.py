from typing import Optional


def detect_image_content_type(image_bytes: bytes) -> Optional[str]:
    if len(image_bytes) < 12:
        return None

    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"

    # HEIC/HEIF files are ISO BMFF containers with an ftyp brand near the start.
    if image_bytes[4:8] == b"ftyp":
        brand = image_bytes[8:12]
        if brand in {b"heic", b"heix", b"hevc", b"hevx"}:
            return "image/heic"
        if brand in {b"mif1", b"msf1", b"heif"}:
            return "image/heif"

    return None
