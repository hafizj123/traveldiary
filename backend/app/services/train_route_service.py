"""
Shared train-route logic: Google Routes API transit fetch + DB cache.
Used by both the /routes/train endpoint and the segment creation hook.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, time, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models.route_cache import RouteCache

logger = logging.getLogger(__name__)

GOOGLE_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
GOOGLE_FIELD_MASK = ",".join([
    "routes.polyline.encodedPolyline",
    "routes.legs.steps.polyline.encodedPolyline",
])
CACHE_PREFIX = "google_transit_train"


def make_cache_key(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> str:
    """Round to 5 dp so identical geometry lookups share one cached entry."""
    return f"{CACHE_PREFIX}|{lat1:.5f},{lon1:.5f}|{lat2:.5f},{lon2:.5f}"


def _approximate_timezone_offset_hours(lon: float) -> int:
    """
    Approximate local timezone from longitude when no timezone dataset is available.
    This keeps schedule-based transit lookups much closer to local morning service.
    """
    return max(-12, min(14, round(lon / 15)))


def _departure_time_utc(origin_lon: float) -> str:
    offset_hours = _approximate_timezone_offset_hours(origin_lon)
    local_tz = timezone(timedelta(hours=offset_hours))
    local_now = datetime.now(timezone.utc).astimezone(local_tz)
    local_date = local_now.date() + timedelta(days=1)
    local_dt = datetime.combine(local_date, time(hour=8, minute=0), tzinfo=local_tz)
    return local_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _decode_polyline(encoded: str) -> list[list[float]]:
    """Decode a Google encoded polyline into [lat, lon] pairs."""
    points: list[list[float]] = []
    index = 0
    lat = 0
    lon = 0

    while index < len(encoded):
        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lon += dlng

        points.append([lat / 1e5, lon / 1e5])

    return points


def _dedupe_points(points: list[list[float]]) -> list[list[float]]:
    deduped: list[list[float]] = []
    for lat, lon in points:
        if not deduped or deduped[-1][0] != lat or deduped[-1][1] != lon:
            deduped.append([lat, lon])
    return deduped


def _extract_geometry(data: dict) -> Optional[list[list[float]]]:
    routes = data.get("routes") or []
    if not routes:
        return None

    route = routes[0]
    encoded = ((route.get("polyline") or {}).get("encodedPolyline"))
    if encoded:
        return _dedupe_points(_decode_polyline(encoded))

    points: list[list[float]] = []
    for leg in route.get("legs") or []:
        for step in leg.get("steps") or []:
            step_encoded = ((step.get("polyline") or {}).get("encodedPolyline"))
            if step_encoded:
                points.extend(_decode_polyline(step_encoded))

    return _dedupe_points(points) if points else None


async def _fetch_from_google_routes(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Optional[list[list[float]]]:
    api_key = settings.GOOGLE_MAPS_API_KEY.strip()
    if not api_key:
        logger.warning("train_route: GOOGLE_MAPS_API_KEY is not configured")
        return None

    body = {
        "origin": {
            "location": {
                "latLng": {"latitude": lat1, "longitude": lon1}
            }
        },
        "destination": {
            "location": {
                "latLng": {"latitude": lat2, "longitude": lon2}
            }
        },
        "travelMode": "TRANSIT",
        "computeAlternativeRoutes": False,
        "transitPreferences": {
            "allowedTravelModes": ["TRAIN", "LIGHT_RAIL", "RAIL", "SUBWAY", "BUS"],
            "routingPreference": "FEWER_TRANSFERS",
        },
        "languageCode": "en",
        "units": "METRIC",
    }
    body["departureTime"] = _departure_time_utc(lon1)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                GOOGLE_ROUTES_URL,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": GOOGLE_FIELD_MASK,
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("train_route: Google Routes request failed: %s", exc)
        return None

    geometry = _extract_geometry(data)
    if not geometry:
        logger.info("train_route: Google Routes returned no usable transit geometry")
        return None
    return geometry


def get_cached_geometry(db: Session, key: str) -> Optional[list]:
    row = db.query(RouteCache).filter(RouteCache.cache_key == key).first()
    if row is None:
        return None
    return json.loads(row.geometry_json)


def save_geometry(db: Session, key: str, geometry: list) -> None:
    row = db.query(RouteCache).filter(RouteCache.cache_key == key).first()
    payload = json.dumps(geometry)
    if row:
        row.geometry_json = payload
    else:
        db.add(RouteCache(cache_key=key, geometry_json=payload))
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("train_route.save_geometry: commit failed key=%s", key)


def get_cached_train_geometry(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Optional[list]:
    return get_cached_geometry(db, make_cache_key(lat1, lon1, lat2, lon2))


def get_train_route_state(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> tuple[Optional[list], str]:
    cached = get_cached_train_geometry(db, lat1, lon1, lat2, lon2)
    if cached is None:
        return None, "pending"
    if isinstance(cached, list):
        if cached:
            return cached, "ready"
        return None, "unavailable"
    return None, "pending"


async def fetch_and_cache(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Optional[list]:
    """
    Check DB cache first. If missing, fetch from Google Routes, store result,
    and return geometry (or None when no usable transit path is found).
    """
    key = make_cache_key(lat1, lon1, lat2, lon2)
    cached = get_cached_geometry(db, key)
    if cached is not None:
        return cached or None

    geometry = await _fetch_from_google_routes(lat1, lon1, lat2, lon2)
    save_geometry(db, key, geometry or [])
    return geometry if geometry else None
