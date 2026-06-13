from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.route_cache import RouteCache
from .geojson_transport_service import build_excursion_route_from_geojson
from .route_cache_service import build_route_cache_metadata

CACHE_PREFIX = "geojson_excursion"
ENDPOINT_TOLERANCE_DEGREES = 0.002


def make_cache_key(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    return f"{CACHE_PREFIX}|{lat1:.5f},{lon1:.5f}|{lat2:.5f},{lon2:.5f}"


def _points_close(a: list[float], b: list[float], tolerance: float = ENDPOINT_TOLERANCE_DEGREES) -> bool:
    return abs(a[0] - b[0]) <= tolerance and abs(a[1] - b[1]) <= tolerance


def _dedupe_points(points: list[list[float]]) -> list[list[float]]:
    deduped: list[list[float]] = []
    for point in points:
        if len(point) < 2:
            continue
        lat = float(point[0])
        lon = float(point[1])
        if not deduped or deduped[-1][0] != lat or deduped[-1][1] != lon:
            deduped.append([lat, lon])
    return deduped


def _compose_full_geometry(
    geometry: Optional[list[list[float]]],
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Optional[list[list[float]]]:
    if not isinstance(geometry, list) or len(geometry) < 2:
        return geometry
    return _dedupe_points([[lat1, lon1], *geometry, [lat2, lon2]])


def _is_full_route_geometry(
    geometry: Optional[list[list[float]]],
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> bool:
    if not isinstance(geometry, list) or len(geometry) < 2:
        return False
    start = [float(lat1), float(lon1)]
    end = [float(lat2), float(lon2)]
    first = geometry[0]
    last = geometry[-1]
    return (
        _points_close(first, start) and _points_close(last, end)
    ) or (
        _points_close(first, end) and _points_close(last, start)
    )


def get_cached_geometry(db: Session, key: str) -> Optional[dict]:
    row = db.query(RouteCache).filter(RouteCache.cache_key == key).first()
    if not row:
        return None
    try:
        payload = json.loads(row.geometry_json)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def set_cached_geometry(db: Session, key: str, payload: dict, *, countries: Optional[list[str]] = None) -> None:
    serialized = json.dumps(payload)
    metadata = build_route_cache_metadata(payload, countries=countries)
    row = db.query(RouteCache).filter(RouteCache.cache_key == key).first()
    if row:
        row.geometry_json = serialized
        row.provider = metadata["provider"]
        row.point_count = metadata["point_count"]
        row.countries_json = json.dumps(metadata["countries"])
        row.geometry_signature = metadata["geometry_signature"]
        db.commit()
        return
    try:
        db.add(RouteCache(
            cache_key=key,
            geometry_json=serialized,
            provider=metadata["provider"],
            point_count=metadata["point_count"],
            countries_json=json.dumps(metadata["countries"]),
            geometry_signature=metadata["geometry_signature"],
        ))
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.query(RouteCache).filter(RouteCache.cache_key == key).first()
        if row:
            row.geometry_json = serialized
            row.provider = metadata["provider"]
            row.point_count = metadata["point_count"]
            row.countries_json = json.dumps(metadata["countries"])
            row.geometry_signature = metadata["geometry_signature"]
            db.commit()


def _lookup_cached_route(db: Session, lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[dict]:
    return (
        get_cached_geometry(db, make_cache_key(lat1, lon1, lat2, lon2))
        or get_cached_geometry(db, make_cache_key(lat2, lon2, lat1, lon1))
    )


def get_excursion_route_state(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
):
    cached = _lookup_cached_route(db, lat1, lon1, lat2, lon2)
    if not cached or not _is_full_route_geometry(cached.get("geometry"), lat1, lon1, lat2, lon2):
        return None, "pending", None, None
    return (
        cached.get("geometry"),
        "ready" if cached.get("geometry") else "unavailable",
        cached.get("anchor_start"),
        cached.get("anchor_end"),
    )


def get_excursion_route_provider(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Optional[str]:
    cached = _lookup_cached_route(db, lat1, lon1, lat2, lon2)
    return cached.get("provider") if cached else None


async def fetch_and_cache_excursion_route(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    country: Optional[str] = None,
):
    key = make_cache_key(lat1, lon1, lat2, lon2)
    cached = get_cached_geometry(db, key)
    if cached and _is_full_route_geometry(cached.get("geometry"), lat1, lon1, lat2, lon2):
        return cached.get("geometry")

    route = build_excursion_route_from_geojson(lat1, lon1, lat2, lon2, country_hint=country)
    geometry = _compose_full_geometry(route.get("geometry") if route else None, lat1, lon1, lat2, lon2)
    payload = {
        "geometry": geometry,
        "anchor_start": route.get("anchor_start") if route else None,
        "anchor_end": route.get("anchor_end") if route else None,
        "provider": route.get("provider") if route else "excursion_straight",
    }
    set_cached_geometry(db, key, payload, countries=[country] if country else None)
    return payload["geometry"]
