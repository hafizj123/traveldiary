from __future__ import annotations

import json
import logging
import threading
import unicodedata
from pathlib import Path
from typing import Optional

from ..config import settings
from .egypt_route_service import is_egypt_coordinate

logger = logging.getLogger(__name__)

_dataset_lock = threading.Lock()
_dataset_cache: Optional[list[dict]] = None


def _normalize_text(value: str) -> str:
    text = " ".join((value or "").strip().lower().split())
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("ascii")


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    radius = 6371000.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * radius * asin(sqrt(a))


def _preferred_station_name(properties: dict) -> str:
    return (
        str(properties.get("name:en") or "").strip()
        or str(properties.get("int_name") or "").strip()
        or str(properties.get("alt_name") or "").strip()
        or str(properties.get("name") or "").strip()
        or "Egypt Train Station"
    )


def _station_aliases(properties: dict) -> list[str]:
    aliases = []
    for key in ("name:en", "int_name", "alt_name", "name", "name:ar"):
        value = str(properties.get(key) or "").strip()
        if value:
            aliases.append(value)
    deduped: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        normalized = _normalize_text(alias)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(alias)
    return deduped


def _resolve_dataset_path() -> Optional[Path]:
    configured_path = settings.EGYPT_STATION_GEOJSON_PATH.strip()
    if not configured_path:
        return None
    path = Path(configured_path)
    if not path.is_absolute():
        path = (Path(__file__).resolve().parents[3] / path).resolve()
    if not path.exists():
        logger.warning("egypt_station_geojson: configured file not found at %s", path)
        return None
    return path


def _load_dataset() -> list[dict]:
    global _dataset_cache
    if _dataset_cache is not None:
        return _dataset_cache

    with _dataset_lock:
        if _dataset_cache is not None:
            return _dataset_cache

        path = _resolve_dataset_path()
        if not path:
            _dataset_cache = []
            return _dataset_cache

        data = json.loads(path.read_text(encoding="utf-8"))
        stations: list[dict] = []
        for feature in data.get("features") or []:
            geometry = feature.get("geometry") or {}
            if geometry.get("type") != "Point":
                continue
            coordinates = geometry.get("coordinates") or []
            if len(coordinates) < 2:
                continue
            properties = feature.get("properties") or {}
            railway_type = str(properties.get("station") or properties.get("railway") or "").strip().lower()
            if railway_type not in {"station", "subway"} and str(properties.get("train") or "").strip().lower() != "yes":
                continue
            lon = float(coordinates[0])
            lat = float(coordinates[1])
            stations.append(
                {
                    "name": _preferred_station_name(properties),
                    "aliases": _station_aliases(properties),
                    "latitude": lat,
                    "longitude": lon,
                    "city": "Egypt",
                    "country": "Egypt",
                    "railway_type": railway_type or "station",
                    "tags": properties,
                    "osm_id": str(properties.get("@id") or ""),
                }
            )

        _dataset_cache = stations
        logger.info("egypt_station_geojson: loaded %s station candidates", len(stations))
        return _dataset_cache


def lookup_nearest_station_from_egypt_geojson(lat: float, lon: float) -> Optional[dict]:
    if not is_egypt_coordinate(lat, lon):
        return None
    stations = _load_dataset()
    if not stations:
        return None
    best_station = None
    best_distance = None
    for station in stations:
        distance = _haversine_meters(lat, lon, station["latitude"], station["longitude"])
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_station = station
    if not best_station or best_distance is None:
        return None
    return {
        "name": best_station["name"],
        "latitude": best_station["latitude"],
        "longitude": best_station["longitude"],
        "distance_meters": round(best_distance, 1),
        "city": best_station["city"],
        "country": best_station["country"],
        "railway_type": best_station["railway_type"],
        "source": "egypt_station_geojson",
        "tags": best_station["tags"],
        "osm_id": best_station["osm_id"],
    }


def search_stations_from_egypt_geojson(query: str, limit: int = 10) -> list[dict]:
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return []
    ranked: list[tuple[int, dict]] = []
    for station in _load_dataset():
        best_score = None
        for alias in station.get("aliases") or [station["name"]]:
            normalized_alias = _normalize_text(alias)
            if not normalized_alias:
                continue
            if normalized_alias == normalized_query:
                score = 400
            elif normalized_alias.startswith(normalized_query):
                score = 300
            elif normalized_query in normalized_alias:
                score = 200
            else:
                continue
            if best_score is None or score > best_score:
                best_score = score
        if best_score is None:
            continue
        ranked.append(
            (
                best_score,
                {
                    "id": station.get("osm_id") or f"egypt-{station['latitude']:.6f}-{station['longitude']:.6f}",
                    "place_name": station["name"],
                    "city": station["city"],
                    "country": station["country"],
                    "latitude": station["latitude"],
                    "longitude": station["longitude"],
                    "subtitle": f"{station['country']}",
                    "source": "egypt_station_geojson",
                },
            )
        )
    ranked.sort(key=lambda item: (-item[0], item[1]["place_name"]))
    results: list[dict] = []
    seen_names: set[str] = set()
    for _, result in ranked:
        key = _normalize_text(result["place_name"])
        if key in seen_names:
            continue
        seen_names.add(key)
        results.append(result)
        if len(results) >= limit:
            break
    return results
