import hashlib
import secrets
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

from fastapi import Request
from sqlalchemy.orm import Session

from ..config import settings
from ..models.trip import Trip
from ..models.trip_public_view import TripPublicView


def normalize_trip_visibility(value: Optional[str]) -> str:
    normalized = " ".join(str(value or "private").strip().lower().split())
    if normalized not in {"private", "unlisted", "public"}:
        return "private"
    return normalized


def create_share_slug() -> str:
    return secrets.token_urlsafe(9).replace("-", "").replace("_", "")


def ensure_trip_share_state(trip: Trip) -> None:
    trip.visibility = normalize_trip_visibility(trip.visibility)
    if trip.visibility in {"unlisted", "public"}:
        if not trip.share_slug:
            trip.share_slug = create_share_slug()
        if not trip.shared_at:
            trip.shared_at = datetime.utcnow()
    else:
        trip.share_slug = None
        trip.shared_at = None


def regenerate_trip_share_slug(db: Session, trip: Trip) -> Trip:
    trip.shared_at = datetime.utcnow()
    slug = create_share_slug()
    while db.query(Trip.id).filter(Trip.share_slug == slug, Trip.id != trip.id).first():
        slug = create_share_slug()
    trip.share_slug = slug
    db.flush()
    return trip


def build_public_share_url(share_slug: Optional[str]) -> Optional[str]:
    if not share_slug:
        return None
    base_url = str(settings.APP_PUBLIC_BASE_URL or "").strip().rstrip("/")
    if not base_url:
        return None
    return urljoin(f"{base_url}/", f"shared/{share_slug}")


def _request_ip(request: Request) -> str:
    forwarded = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return str(request.client.host if request.client else "unknown").strip() or "unknown"


def build_public_viewer_hash(request: Request) -> str:
    ip = _request_ip(request)
    user_agent = str(request.headers.get("user-agent") or "").strip()
    raw = f"{ip}|{user_agent}|{settings.SECRET_KEY}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def record_trip_public_view(db: Session, trip: Trip, request: Request) -> bool:
    today = date.today()
    viewer_hash = build_public_viewer_hash(request)
    exists = (
        db.query(TripPublicView.id)
        .filter(
            TripPublicView.trip_id == trip.id,
            TripPublicView.viewer_hash == viewer_hash,
            TripPublicView.view_date == today,
        )
        .first()
    )
    if exists:
        return False

    db.add(
        TripPublicView(
            trip_id=trip.id,
            viewer_hash=viewer_hash,
            view_date=today,
            viewed_at=datetime.utcnow(),
            user_agent=str(request.headers.get("user-agent") or "").strip()[:255] or None,
        )
    )
    db.flush()
    return True


def get_trip_public_stats(db: Session, trip_id: int) -> dict:
    today = date.today()
    seven_days_ago = today - timedelta(days=6)
    thirty_days_ago = today - timedelta(days=29)

    rows = (
        db.query(TripPublicView.view_date)
        .filter(TripPublicView.trip_id == trip_id)
        .all()
    )
    total = len(rows)
    unique_7d = sum(1 for (view_date,) in rows if view_date and view_date >= seven_days_ago)
    unique_30d = sum(1 for (view_date,) in rows if view_date and view_date >= thirty_days_ago)
    return {
        "unique_views_total": total,
        "unique_views_7d": unique_7d,
        "unique_views_30d": unique_30d,
    }
