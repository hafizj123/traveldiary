from __future__ import annotations

import hashlib
import json
from typing import Optional


def extract_geometry(payload) -> list[list[float]]:
    if isinstance(payload, list):
        geometry = payload
    elif isinstance(payload, dict):
        geometry = payload.get("geometry")
    else:
        geometry = None

    if not isinstance(geometry, list):
        return []

    points: list[list[float]] = []
    for point in geometry:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            points.append([float(point[0]), float(point[1])])
        except (TypeError, ValueError):
            continue
    return points


def normalize_countries(countries: Optional[list[str]]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for country in countries or []:
        value = " ".join(str(country or "").strip().split())
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    normalized.sort(key=str.casefold)
    return normalized


def geometry_signature(geometry: list[list[float]]) -> str:
    digest_source = json.dumps(
        [
            [round(float(lat), 5), round(float(lon), 5)]
            for lat, lon in geometry
        ],
        separators=(",", ":"),
    )
    return hashlib.sha1(digest_source.encode("utf-8")).hexdigest()


def build_route_cache_metadata(payload, *, countries: Optional[list[str]] = None) -> dict:
    geometry = extract_geometry(payload)
    normalized_countries = normalize_countries(
        countries if countries is not None else (payload.get("countries") if isinstance(payload, dict) else None)
    )
    provider = payload.get("provider") if isinstance(payload, dict) else None
    return {
        "provider": str(provider).strip() if provider else None,
        "point_count": len(geometry),
        "countries": normalized_countries,
        "geometry_signature": geometry_signature(geometry) if len(geometry) >= 2 else None,
    }

