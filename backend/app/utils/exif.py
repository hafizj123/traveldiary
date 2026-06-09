from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from typing import Optional, Tuple
import io


def extract_gps_from_image(
    image_bytes: bytes,
) -> Optional[Tuple[float, float, Optional[str]]]:
    """Return (latitude, longitude, date_taken) from EXIF data, or None."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        exif_raw = img._getexif()
        if not exif_raw:
            return None

        gps_info: dict = {}
        date_taken: Optional[str] = None

        for tag_id, value in exif_raw.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                for gps_tag_id, gps_value in value.items():
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_info[gps_tag] = gps_value
            elif tag == "DateTimeOriginal":
                date_taken = str(value)

        if not gps_info:
            return None

        lat = _dms_to_decimal(gps_info.get("GPSLatitude"))
        lon = _dms_to_decimal(gps_info.get("GPSLongitude"))

        if lat is None or lon is None:
            return None

        if gps_info.get("GPSLatitudeRef") == "S":
            lat = -lat
        if gps_info.get("GPSLongitudeRef") == "W":
            lon = -lon

        return lat, lon, date_taken
    except Exception:
        return None


def _dms_to_decimal(value) -> Optional[float]:
    if not value or len(value) != 3:
        return None
    d, m, s = value
    return float(d) + float(m) / 60 + float(s) / 3600
