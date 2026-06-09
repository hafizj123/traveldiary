import uuid
import os
import boto3
from botocore.config import Config
from ..config import settings


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


async def upload_image(file_bytes: bytes, original_filename: str, content_type: str) -> str:
    ext = os.path.splitext(original_filename)[1].lower() or ".jpg"
    key = f"photos/{uuid.uuid4()}{ext}"

    client = _r2_client()
    client.put_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )

    return f"{settings.R2_PUBLIC_URL}/{key}"


async def delete_image(url: str) -> None:
    """Best-effort deletion given a public URL."""
    try:
        prefix = settings.R2_PUBLIC_URL.rstrip("/") + "/"
        if url.startswith(prefix):
            key = url[len(prefix):]
            _r2_client().delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
    except Exception as exc:
        print(f"[r2] delete failed: {exc}")
