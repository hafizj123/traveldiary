"""
Shared train-route logic: Google Routes API transit fetch + DB cache.
Used by both the /routes/train endpoint and the segment creation hook.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import unicodedata
from datetime import datetime, time, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .country_route_policy_service import (
    GOOGLE_TRAIN_COUNTRIES,
    TRAIN_MODE_GEOJSON_OSM,
    TRAIN_MODE_GOOGLE_OSM,
    TRAIN_MODE_OSM_ONLY,
    country_key_from_name,
    get_effective_train_mode_for_country,
)
from .geojson_transport_service import (
    _country_bbox,
    _europe_country_bbox,
    build_train_route_from_geojson,
    lookup_nearest_transport_place_from_geojson,
    match_geojson_dataset_for_route,
    search_transport_places_from_geojson,
)
from .route_cache_service import build_route_cache_metadata
from .shanghai_route_service import build_route_from_shanghai_geojson, is_shanghai_coordinate
from ..config import settings
from ..models.route_cache import RouteCache
from ..models.train_station import TrainStation
from ..models.train_station_cache import TrainStationCache
logger = logging.getLogger(__name__)

GOOGLE_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_FALLBACK_URLS = [
    OVERPASS_URL,
    "https://overpass.private.coffee/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
GOOGLE_FIELD_MASK = ",".join([
    "routes.polyline.encodedPolyline",
    "routes.legs.steps.polyline.encodedPolyline",
    "routes.legs.steps.transitDetails.transitLine.vehicle.type",
])
CACHE_PREFIX = "google_transit_train"
NEARBY_REUSE_RADIUS_METERS = 10
STATION_SEARCH_RADIUS_METERS = 1500
STATION_SEARCH_RADIUS_METERS_EXPANDED = 5000
SEARCH_PADDING_DEGREES = 0.35
TERMINAL_MATCH_RADIUS_DEGREES = 0.12
MAX_OSM_ROUTE_LENGTH_RATIO = 4.0
GRAPH_NODE_SNAP_RADIUS_DEGREES = 0.05
GRAPH_NODE_LINK_RADIUS_METERS = 180
GRAPH_NODE_CANDIDATE_LIMIT = 6
GRAPH_NODE_STITCH_RADIUS_METERS = 45
OVERPASS_MAX_ATTEMPTS = 1
OVERPASS_RETRY_BASE_SECONDS = 0.75
STATION_CACHE_REUSE_RADIUS_METERS = 10
MASTER_STATION_SEARCH_RADIUS_METERS = STATION_SEARCH_RADIUS_METERS_EXPANDED
USER_TRAIN_SNAP_MAX_DISTANCE_METERS = 1000
ROUTE_TRAIN_STATION_MAX_DISTANCE_METERS = 1000
_station_snap_cache: dict[str, Optional[dict]] = {}

RAIL_VEHICLE_TYPES = {
    "COMMUTER_TRAIN",
    "HEAVY_RAIL",
    "HIGH_SPEED_TRAIN",
    "LONG_DISTANCE_TRAIN",
    "METRO_RAIL",
    "MONORAIL",
    "RAIL",
    "SUBWAY",
    "TRAM",
}

BUS_VEHICLE_TYPES = {
    "BUS",
    "INTERCITY_BUS",
    "SHARE_TAXI",
    "TROLLEYBUS",
}


def _preferred_english_name(tags: dict, fallback: str) -> str:
    return (
        tags.get("name:en")
        or tags.get("official_name:en")
        or tags.get("alt_name:en")
        or tags.get("short_name:en")
        or tags.get("int_name")
        or tags.get("official_name")
        or tags.get("uic_name")
        or tags.get("short_name")
        or tags.get("name")
        or fallback
    )


def _contains_non_ascii(value: str) -> bool:
    return any(ord(char) > 127 for char in value)


async def _fetch_nearest_station_from_geoapify(lat: float, lon: float) -> Optional[dict]:
    api_key = settings.GEOAPIFY_API_KEY.strip()
    if not api_key:
        return None

    category_sets = [
        "public_transport.train",
        "public_transport.train,public_transport.light_rail,public_transport.subway,public_transport.tram,public_transport.monorail",
    ]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for categories in category_sets:
                resp = await client.get(
                    GEOAPIFY_PLACES_URL,
                    params={
                        "categories": categories,
                        "filter": f"circle:{lon},{lat},{STATION_SEARCH_RADIUS_METERS_EXPANDED}",
                        "bias": f"proximity:{lon},{lat}",
                        "limit": 10,
                        "lang": "en",
                        "apiKey": api_key,
                    },
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "traveldiary/1.0",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                features = data.get("features") or []
                if not features:
                    continue

                best_station = None
                best_distance = None
                for feature in features:
                    geometry = feature.get("geometry") or {}
                    coords = geometry.get("coordinates") or []
                    if len(coords) < 2:
                        continue
                    station_lon = float(coords[0])
                    station_lat = float(coords[1])
                    props = feature.get("properties") or {}
                    distance = _haversine_meters(lat, lon, station_lat, station_lon)
                    if best_distance is None or distance < best_distance:
                        best_distance = distance
                        best_station = {
                            "name": props.get("name") or props.get("formatted") or "Train station",
                            "latitude": station_lat,
                            "longitude": station_lon,
                            "distance_meters": round(distance, 1),
                            "city": props.get("city") or "",
                            "country": props.get("country") or "",
                        }

                if best_station:
                    logger.info(
                        "train_route: Geoapify nearest station matched %.5f,%.5f -> %s",
                        lat,
                        lon,
                        best_station["name"],
                    )
                    return best_station
    except Exception as exc:
        logger.warning("train_route: Geoapify nearest station lookup failed: %s", exc)

    return None


async def _post_overpass(
    query: str,
    timeout: float,
    context: str,
    *,
    endpoints: Optional[list[str]] = None,
    max_attempts: Optional[int] = None,
) -> Optional[dict]:
    last_exc: Optional[Exception] = None
    endpoint_list = endpoints or OVERPASS_FALLBACK_URLS
    attempts = max_attempts or OVERPASS_MAX_ATTEMPTS

    for endpoint_index, endpoint in enumerate(endpoint_list):
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        endpoint,
                        data={"data": query},
                        headers={
                            "Accept": "application/json",
                            "User-Agent": "traveldiary/1.0",
                        },
                    )
                    resp.raise_for_status()
                    if endpoint_index > 0 or attempt > 1:
                        logger.info(
                            "train_route: Overpass %s succeeded via %s on attempt %s",
                            context,
                            endpoint,
                            attempt,
                        )
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status_code = exc.response.status_code
                should_retry = status_code in {429, 500, 502, 503, 504}
                logger.warning(
                    "train_route: Overpass %s failed via %s with status %s on attempt %s",
                    context,
                    endpoint,
                    status_code,
                    attempt,
                )
                if not should_retry:
                    break
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "train_route: Overpass %s failed via %s on attempt %s: %s",
                    context,
                    endpoint,
                    attempt,
                    exc,
                )

            if attempt < attempts:
                await asyncio.sleep(OVERPASS_RETRY_BASE_SECONDS * attempt)

    if last_exc:
        logger.warning("train_route: Overpass %s exhausted: %s", context, last_exc)
    return None


def make_cache_key(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> str:
    """Round to 5 dp so identical geometry lookups share one cached entry."""
    return f"{CACHE_PREFIX}|{lat1:.5f},{lon1:.5f}|{lat2:.5f},{lon2:.5f}"


def _station_cache_key(lat: float, lon: float) -> str:
    return f"{lat:.5f},{lon:.5f}"


def _station_lookup_db_key(lat: float, lon: float) -> str:
    return f"{lat:.5f},{lon:.5f}"


def _normalize_country_name(country: Optional[str]) -> str:
    if not country:
        return ""
    return " ".join(country.strip().lower().split())


def _normalize_search_text(value: str) -> str:
    text = " ".join((value or "").strip().lower().split())
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("ascii")


def _is_china_country(country: Optional[str]) -> bool:
    normalized = _normalize_country_name(country)
    return normalized in {"china", "people's republic of china", "pr china", "prc"}


def _is_china_route_candidate(country: Optional[str], lat: float, lon: float) -> bool:
    normalized = _normalize_country_name(country)
    if normalized:
        return _is_china_country(country)
    china_bbox = _country_bbox("china")
    if not china_bbox:
        return False
    return (
        china_bbox["south"] <= lat <= china_bbox["north"]
        and china_bbox["west"] <= lon <= china_bbox["east"]
    )


def _points_are_close(a: list[float], b: list[float], max_meters: float = 25.0) -> bool:
    return _haversine_meters(float(a[0]), float(a[1]), float(b[0]), float(b[1])) <= max_meters


def _stitch_train_geometry_to_stations(
    payload: Optional[dict],
    start_station: dict,
    end_station: dict,
) -> Optional[dict]:
    if not payload:
        return payload

    geometry = payload.get("geometry")
    if not isinstance(geometry, list) or len(geometry) < 2:
        payload["anchor_start"] = [start_station["latitude"], start_station["longitude"]]
        payload["anchor_end"] = [end_station["latitude"], end_station["longitude"]]
        return payload

    stitched = [list(point) for point in geometry]
    start_point = [float(start_station["latitude"]), float(start_station["longitude"])]
    end_point = [float(end_station["latitude"]), float(end_station["longitude"])]

    if not _points_are_close(stitched[0], start_point):
        stitched.insert(0, start_point)
    else:
        stitched[0] = start_point

    if not _points_are_close(stitched[-1], end_point):
        stitched.append(end_point)
    else:
        stitched[-1] = end_point

    payload["geometry"] = stitched
    payload["anchor_start"] = start_point
    payload["anchor_end"] = end_point
    return payload


def _should_use_google_for_train(from_country: Optional[str], to_country: Optional[str]) -> bool:
    if not from_country or not to_country:
        return True
    if _is_china_country(from_country) and _is_china_country(to_country):
        return False
    normalized_from = _normalize_country_name(from_country)
    normalized_to = _normalize_country_name(to_country)
    return (
        normalized_from in GOOGLE_TRAIN_COUNTRIES
        and normalized_to in GOOGLE_TRAIN_COUNTRIES
    )


def _should_try_google_for_train_by_policy(
    db: Session,
    from_country: Optional[str],
    to_country: Optional[str],
) -> bool:
    if not _should_use_google_for_train(from_country, to_country):
        return False
    if from_country and get_effective_train_mode_for_country(db, from_country) != TRAIN_MODE_GOOGLE_OSM:
        return False
    if to_country and get_effective_train_mode_for_country(db, to_country) != TRAIN_MODE_GOOGLE_OSM:
        return False
    return True


def _provider_family(provider: Optional[str]) -> str:
    normalized = str(provider or "").strip().lower()
    if not normalized:
        return ""
    if normalized == "google":
        return "google"
    if normalized == "fallback":
        return "fallback"
    if normalized == "osm" or normalized.startswith("osm"):
        return "osm"
    if "geojson" in normalized:
        return "geojson"
    return normalized


def _is_cached_provider_compatible(
    db: Session,
    provider: Optional[str],
    from_country: Optional[str],
    to_country: Optional[str],
) -> bool:
    family = _provider_family(provider)
    if not family:
        return False

    if family == "osm":
        return True

    # Never lock train routing onto an old straight-line fallback cache.
    # If policy or data changed, we want to retry and replace it.
    if family == "fallback":
        return False

    same_country_name = _same_non_china_country(from_country, to_country)
    if same_country_name:
        mode = get_effective_train_mode_for_country(db, same_country_name)
        if mode == TRAIN_MODE_GOOGLE_OSM:
            return family == "google"
        if mode == TRAIN_MODE_GEOJSON_OSM:
            return family == "geojson"
        return False

    if (
        _is_china_route_candidate(from_country, 0.0, 0.0)  # country-name-only fast path
        and _is_china_route_candidate(to_country, 0.0, 0.0)
    ):
        return family in {"geojson", "osm"}

    if family == "google":
        return _should_try_google_for_train_by_policy(db, from_country, to_country)

    return False


def _same_non_china_country(from_country: Optional[str], to_country: Optional[str]) -> Optional[str]:
    from_key = country_key_from_name(from_country)
    to_key = country_key_from_name(to_country)
    if not from_key or from_key != to_key:
        return None
    if _is_china_country(from_country) or _is_china_country(to_country):
        return None
    return from_country or to_country


def _geojson_hint_from_dataset(dataset_match: Optional[dict]) -> Optional[str]:
    if not dataset_match:
        return None
    return dataset_match.get("city") or dataset_match.get("key")


async def _resolve_china_city_policy_payload(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> tuple[Optional[dict], bool]:
    dataset_match = match_geojson_dataset_for_route(lat1, lon1, lat2, lon2)
    if not dataset_match or _normalize_country_name(dataset_match.get("country")) != "china":
        return None, False

    mode = get_effective_train_mode_for_country(db, dataset_match.get("key"))
    if mode == TRAIN_MODE_GEOJSON_OSM:
        payload = await _fetch_from_generic_geojson_with_timeout(
            lat1,
            lon1,
            lat2,
            lon2,
            country_hint=_geojson_hint_from_dataset(dataset_match),
        )
        if payload:
            payload["provider"] = payload.get("provider") or "geojson"
        return payload, True

    if mode == TRAIN_MODE_OSM_ONLY:
        return None, True

    return None, True


async def _resolve_train_payload_for_country_mode(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    country_name: str,
) -> Optional[dict]:
    mode = get_effective_train_mode_for_country(db, country_name)

    if mode == TRAIN_MODE_GOOGLE_OSM:
        payload = await _fetch_from_google_routes(lat1, lon1, lat2, lon2)
        if payload:
            payload["provider"] = "google"
            return payload
        payload = await _fetch_from_osm_railway(lat1, lon1, lat2, lon2)
        if payload:
            payload["provider"] = "osm"
        return payload

    if mode == TRAIN_MODE_GEOJSON_OSM:
        payload = await _fetch_from_generic_geojson_with_timeout(
            lat1,
            lon1,
            lat2,
            lon2,
            country_hint=country_name,
        )
        if payload:
            payload["provider"] = payload.get("provider") or "geojson"
            return payload
        payload = await _fetch_from_osm_railway(lat1, lon1, lat2, lon2)
        if payload:
            payload["provider"] = "osm"
        return payload

    payload = await _fetch_from_osm_railway(lat1, lon1, lat2, lon2)
    if payload:
        payload["provider"] = "osm"
    return payload


async def _fetch_from_shanghai_geojson_with_timeout(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Optional[dict]:
    timeout_seconds = max(0.1, float(settings.GEOJSON_ROUTE_TIMEOUT_SECONDS))
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(build_route_from_shanghai_geojson, lat1, lon1, lat2, lon2),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.info(
            "train_route: shanghai_geojson timed out for %.5f,%.5f -> %.5f,%.5f after %.1fs",
            lat1,
            lon1,
            lat2,
            lon2,
            timeout_seconds,
        )
        return None
    except Exception:
        logger.exception(
            "train_route: shanghai_geojson failed for %.5f,%.5f -> %.5f,%.5f",
            lat1,
            lon1,
            lat2,
            lon2,
        )
        return None


async def _fetch_from_generic_geojson_with_timeout(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    country_hint: Optional[str] = None,
) -> Optional[dict]:
    timeout_seconds = max(0.1, float(settings.GEOJSON_ROUTE_TIMEOUT_SECONDS))
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(build_train_route_from_geojson, lat1, lon1, lat2, lon2, country_hint=country_hint),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.info(
            "train_route: generic_geojson timed out for %.5f,%.5f -> %.5f,%.5f after %.1fs",
            lat1,
            lon1,
            lat2,
            lon2,
            timeout_seconds,
        )
        return None
    except Exception:
        logger.exception(
            "train_route: generic_geojson failed for %.5f,%.5f -> %.5f,%.5f",
            lat1,
            lon1,
            lat2,
            lon2,
        )
        return None


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


def _polyline_length(points: list[list[float]]) -> float:
    total = 0.0
    for index in range(len(points) - 1):
        total += math.sqrt(
            (points[index + 1][0] - points[index][0]) ** 2
            + (points[index + 1][1] - points[index][1]) ** 2
        )
    return total


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius_m * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _extract_route_geometry(route: dict) -> Optional[list[list[float]]]:
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


def _score_route(route: dict) -> tuple[int, int, int]:
    rail_steps = 0
    bus_steps = 0
    transit_steps = 0

    for leg in route.get("legs") or []:
        for step in leg.get("steps") or []:
            transit_details = step.get("transitDetails") or {}
            vehicle_type = (
                ((transit_details.get("transitLine") or {}).get("vehicle") or {}).get("type")
            )
            if not vehicle_type:
                continue
            transit_steps += 1
            if vehicle_type in RAIL_VEHICLE_TYPES:
                rail_steps += 1
            elif vehicle_type in BUS_VEHICLE_TYPES:
                bus_steps += 1

    # Prefer routes with more rail, fewer bus segments, then more transit detail overall.
    return rail_steps, -bus_steps, transit_steps


def _build_route_payload(route: dict) -> Optional[dict]:
    geometry = _extract_route_geometry(route)
    if not geometry:
        return None

    transit_step_geometries: list[list[list[float]]] = []
    for leg in route.get("legs") or []:
        for step in leg.get("steps") or []:
            if not step.get("transitDetails"):
                continue
            step_encoded = ((step.get("polyline") or {}).get("encodedPolyline"))
            if not step_encoded:
                continue
            step_points = _dedupe_points(_decode_polyline(step_encoded))
            if step_points:
                transit_step_geometries.append(step_points)

    if transit_step_geometries:
        core_geometry: list[list[float]] = []
        for points in transit_step_geometries:
            core_geometry.extend(points)
        core_geometry = _dedupe_points(core_geometry)
        anchor_start = transit_step_geometries[0][0]
        anchor_end = transit_step_geometries[-1][-1]
        if core_geometry:
            return {
                "geometry": core_geometry,
                "anchor_start": anchor_start,
                "anchor_end": anchor_end,
            }

    return {
        "geometry": geometry,
        "anchor_start": geometry[0],
        "anchor_end": geometry[-1],
    }


def _extract_route_payload(data: dict) -> Optional[dict]:
    routes = data.get("routes") or []
    if not routes:
        return None

    best_route = max(routes, key=_score_route)
    payload = _build_route_payload(best_route)
    if payload:
        return payload

    for route in routes:
        payload = _build_route_payload(route)
        if payload:
            return payload

    return None


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
        "computeAlternativeRoutes": True,
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

    payload = _extract_route_payload(data)
    if not payload:
        logger.info("train_route: Google Routes returned no usable transit geometry")
        return None
    return payload


def _geometry_from_way(element: dict) -> list[list[float]]:
    return _dedupe_points([
        [point["lat"], point["lon"]]
        for point in (element.get("geometry") or [])
        if "lat" in point and "lon" in point
    ])


def _distance_sq(a: list[float], b: list[float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _graph_node_key(point: list[float]) -> str:
    return f"{point[0]:.6f},{point[1]:.6f}"


def _nearest_graph_node(
    graph_nodes: dict[str, list[float]],
    target: list[float],
) -> tuple[Optional[str], Optional[list[float]], Optional[float]]:
    best_key = None
    best_point = None
    best_dist = None

    for key, point in graph_nodes.items():
        dist = _distance_sq(point, target)
        if best_dist is None or dist < best_dist:
            best_key = key
            best_point = point
            best_dist = dist

    if best_key is None or best_point is None or best_dist is None:
        return None, None, None
    return best_key, best_point, best_dist


def _nearest_graph_candidates(
    graph_nodes: dict[str, list[float]],
    target: list[float],
    limit: int = GRAPH_NODE_CANDIDATE_LIMIT,
) -> list[tuple[str, list[float], float]]:
    candidates: list[tuple[str, list[float], float]] = []
    for key, point in graph_nodes.items():
        dist = _distance_sq(point, target)
        candidates.append((key, point, dist))
    candidates.sort(key=lambda item: item[2])
    return candidates[:limit]


def _connect_terminal_nodes(
    adjacency: dict[str, list[tuple[str, float]]],
    graph_nodes: dict[str, list[float]],
    terminal_keys: set[str],
) -> None:
    if len(terminal_keys) < 2:
        return

    threshold_m = GRAPH_NODE_LINK_RADIUS_METERS
    cell_size_deg = threshold_m / 111320
    buckets: dict[tuple[int, int], list[str]] = {}

    for key in terminal_keys:
        point = graph_nodes.get(key)
        if not point:
            continue
        bucket = (
            int(point[0] / cell_size_deg),
            int(point[1] / cell_size_deg),
        )
        buckets.setdefault(bucket, []).append(key)

    for key in terminal_keys:
        point = graph_nodes.get(key)
        if not point:
            continue
        bucket = (
            int(point[0] / cell_size_deg),
            int(point[1] / cell_size_deg),
        )
        for lat_offset in (-1, 0, 1):
            for lon_offset in (-1, 0, 1):
                neighbor_bucket = (bucket[0] + lat_offset, bucket[1] + lon_offset)
                for other_key in buckets.get(neighbor_bucket, []):
                    if other_key <= key:
                        continue
                    other_point = graph_nodes.get(other_key)
                    if not other_point:
                        continue
                    distance_m = _haversine_meters(
                        point[0],
                        point[1],
                        other_point[0],
                        other_point[1],
                    )
                    if distance_m > threshold_m:
                        continue
                    weight = math.sqrt(_distance_sq(point, other_point))
                    adjacency.setdefault(key, []).append((other_key, weight))
                    adjacency.setdefault(other_key, []).append((key, weight))


def _connect_nearby_graph_nodes(
    adjacency: dict[str, list[tuple[str, float]]],
    graph_nodes: dict[str, list[float]],
) -> None:
    if len(graph_nodes) < 2:
        return

    threshold_m = GRAPH_NODE_STITCH_RADIUS_METERS
    cell_size_deg = threshold_m / 111320
    buckets: dict[tuple[int, int], list[str]] = {}

    for key, point in graph_nodes.items():
        bucket = (
            int(point[0] / cell_size_deg),
            int(point[1] / cell_size_deg),
        )
        buckets.setdefault(bucket, []).append(key)

    existing_edges = {
        tuple(sorted((source_key, target_key)))
        for source_key, neighbors in adjacency.items()
        for target_key, _ in neighbors
    }

    for key, point in graph_nodes.items():
        bucket = (
            int(point[0] / cell_size_deg),
            int(point[1] / cell_size_deg),
        )
        for lat_offset in (-1, 0, 1):
            for lon_offset in (-1, 0, 1):
                neighbor_bucket = (bucket[0] + lat_offset, bucket[1] + lon_offset)
                for other_key in buckets.get(neighbor_bucket, []):
                    if other_key <= key:
                        continue
                    edge_key = tuple(sorted((key, other_key)))
                    if edge_key in existing_edges:
                        continue
                    other_point = graph_nodes.get(other_key)
                    if not other_point:
                        continue
                    distance_m = _haversine_meters(
                        point[0],
                        point[1],
                        other_point[0],
                        other_point[1],
                    )
                    if distance_m > threshold_m:
                        continue
                    weight = math.sqrt(_distance_sq(point, other_point))
                    adjacency.setdefault(key, []).append((other_key, weight))
                    adjacency.setdefault(other_key, []).append((key, weight))
                    existing_edges.add(edge_key)


def _shortest_graph_path(
    adjacency: dict[str, list[tuple[str, float]]],
    graph_nodes: dict[str, list[float]],
    start_key: str,
    end_key: str,
) -> Optional[list[list[float]]]:
    import heapq

    distances: dict[str, float] = {start_key: 0.0}
    previous: dict[str, Optional[str]] = {start_key: None}
    queue: list[tuple[float, str]] = [(0.0, start_key)]

    while queue:
        current_distance, current_key = heapq.heappop(queue)
        if current_key == end_key:
            break
        if current_distance > distances.get(current_key, float("inf")):
            continue

        for next_key, edge_weight in adjacency.get(current_key, []):
            next_distance = current_distance + edge_weight
            if next_distance >= distances.get(next_key, float("inf")):
                continue
            distances[next_key] = next_distance
            previous[next_key] = current_key
            heapq.heappush(queue, (next_distance, next_key))

    if end_key not in previous:
        return None

    keys: list[str] = []
    current_key: Optional[str] = end_key
    while current_key is not None:
        keys.append(current_key)
        current_key = previous.get(current_key)
    keys.reverse()

    return [graph_nodes[key] for key in keys if key in graph_nodes]


async def _fetch_from_osm_railway(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Optional[dict]:
    south = min(lat1, lat2) - SEARCH_PADDING_DEGREES
    north = max(lat1, lat2) + SEARCH_PADDING_DEGREES
    west = min(lon1, lon2) - SEARCH_PADDING_DEGREES
    east = max(lon1, lon2) + SEARCH_PADDING_DEGREES

    query = f"""
    [out:json][timeout:25];
    (
      way["railway"~"rail|light_rail|subway|tram|narrow_gauge|monorail"]({south},{west},{north},{east});
    );
    out geom;
    """

    data = await _post_overpass(query, timeout=30.0, context="railway lookup")
    if not data:
        return None

    start = [lat1, lon1]
    end = [lat2, lon2]
    elements = data.get("elements") or []
    logger.info(
        "train_route: OSM railway lookup returned %s elements for %.5f,%.5f -> %.5f,%.5f",
        len(elements),
        lat1,
        lon1,
        lat2,
        lon2,
    )
    graph_nodes: dict[str, list[float]] = {}
    adjacency: dict[str, list[tuple[str, float]]] = {}
    terminal_keys: set[str] = set()
    segment_count = 0

    for element in elements:
        if element.get("type") != "way":
            continue

        geometry = _geometry_from_way(element)
        if len(geometry) < 2:
            continue

        terminal_keys.add(_graph_node_key(geometry[0]))
        terminal_keys.add(_graph_node_key(geometry[-1]))
        segment_count += len(geometry) - 1

        for index in range(len(geometry) - 1):
            point_a = geometry[index]
            point_b = geometry[index + 1]
            key_a = _graph_node_key(point_a)
            key_b = _graph_node_key(point_b)
            graph_nodes[key_a] = point_a
            graph_nodes[key_b] = point_b
            weight = math.sqrt(_distance_sq(point_a, point_b))
            adjacency.setdefault(key_a, []).append((key_b, weight))
            adjacency.setdefault(key_b, []).append((key_a, weight))

    if not graph_nodes:
        logger.info(
            "train_route: OSM railway graph empty for %.5f,%.5f -> %.5f,%.5f",
            lat1,
            lon1,
            lat2,
            lon2,
        )
        return None

    _connect_terminal_nodes(adjacency, graph_nodes, terminal_keys)
    _connect_nearby_graph_nodes(adjacency, graph_nodes)
    edge_count = sum(len(neighbors) for neighbors in adjacency.values()) // 2
    logger.info(
        "train_route: OSM railway graph built with %s nodes, %s edges, %s raw segments",
        len(graph_nodes),
        edge_count,
        segment_count,
    )

    start_key, start_point, start_dist = _nearest_graph_node(graph_nodes, start)
    end_key, end_point, end_dist = _nearest_graph_node(graph_nodes, end)
    if (
        not start_key
        or not end_key
        or start_point is None
        or end_point is None
        or start_dist is None
        or end_dist is None
    ):
        logger.info("train_route: OSM railway nearest-node lookup failed")
        return None

    logger.info(
        "train_route: OSM railway nearest nodes start_dist=%.6f end_dist=%.6f",
        start_dist,
        end_dist,
    )
    if (
        start_dist > GRAPH_NODE_SNAP_RADIUS_DEGREES ** 2
        or end_dist > GRAPH_NODE_SNAP_RADIUS_DEGREES ** 2
    ):
        logger.info(
            "train_route: OSM railway nearest nodes outside snap radius %.6f",
            GRAPH_NODE_SNAP_RADIUS_DEGREES ** 2,
        )
        return None

    start_candidates = [
        candidate
        for candidate in _nearest_graph_candidates(graph_nodes, start)
        if candidate[2] <= GRAPH_NODE_SNAP_RADIUS_DEGREES ** 2
    ]
    end_candidates = [
        candidate
        for candidate in _nearest_graph_candidates(graph_nodes, end)
        if candidate[2] <= GRAPH_NODE_SNAP_RADIUS_DEGREES ** 2
    ]
    if not start_candidates or not end_candidates:
        logger.info(
            "train_route: OSM railway candidate search failed start=%s end=%s",
            len(start_candidates),
            len(end_candidates),
        )
        return None

    best_geometry = None
    best_start_point = start_point
    best_end_point = end_point
    best_score = None
    attempted_paths = 0
    for candidate_start_key, candidate_start_point, candidate_start_dist in start_candidates:
        for candidate_end_key, candidate_end_point, candidate_end_dist in end_candidates:
            attempted_paths += 1
            candidate_geometry = _shortest_graph_path(
                adjacency,
                graph_nodes,
                candidate_start_key,
                candidate_end_key,
            )
            if not candidate_geometry or len(candidate_geometry) < 2:
                continue
            route_length = _polyline_length(candidate_geometry)
            score = route_length + candidate_start_dist + candidate_end_dist
            if best_score is None or score < best_score:
                best_geometry = candidate_geometry
                best_start_point = candidate_start_point
                best_end_point = candidate_end_point
                best_score = score

    if not best_geometry or len(best_geometry) < 2:
        logger.info(
            "train_route: OSM railway graph had no connected path after %s attempts",
            attempted_paths,
        )
        return None

    direct_length = math.sqrt(_distance_sq(start, end))
    route_length = _polyline_length(best_geometry)
    if direct_length > 0 and route_length > direct_length * MAX_OSM_ROUTE_LENGTH_RATIO:
        logger.info(
            "train_route: OSM railway route rejected by ratio route=%.6f direct=%.6f max_ratio=%.2f",
            route_length,
            direct_length,
            MAX_OSM_ROUTE_LENGTH_RATIO,
        )
        return None

    logger.info(
        "train_route: OSM railway route accepted with %s points after %s attempts",
        len(best_geometry),
        attempted_paths,
    )
    return {
        "geometry": best_geometry,
        "anchor_start": best_start_point,
        "anchor_end": best_end_point,
    }


async def _reverse_geocode_station(lat: float, lon: float) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                NOMINATIM_REVERSE_URL,
                params={
                    "lat": lat,
                    "lon": lon,
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "namedetails": 1,
                    "accept-language": "en",
                },
                headers={
                    "Accept": "application/json",
                    "User-Agent": "traveldiary/1.0",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("train_route: reverse geocode failed: %s", exc)
        return {}

    addr = data.get("address") or {}
    namedetails = data.get("namedetails") or {}
    place_name = (
        namedetails.get("name:en")
        or namedetails.get("official_name:en")
        or namedetails.get("alt_name:en")
        or namedetails.get("short_name:en")
        or namedetails.get("int_name")
        or data.get("name")
        or data.get("display_name", "").split(",")[0].strip()
        or ""
    )
    return {
        "place_name": place_name,
        "city": addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("suburb")
        or addr.get("county")
        or "",
        "country": addr.get("country") or "",
    }


def _normalize_station_payload(payload: Optional[dict]) -> Optional[dict]:
    if not payload:
        return None
    try:
        return {
            "name": payload["name"],
            "latitude": float(payload["latitude"]),
            "longitude": float(payload["longitude"]),
            "distance_meters": round(float(payload.get("distance_meters") or 0), 1),
            "city": payload.get("city") or "",
            "country": payload.get("country") or "",
        }
    except (KeyError, TypeError, ValueError):
        return None


def _station_payload_from_row(row: TrainStationCache, query_lat: float, query_lon: float) -> dict:
    return {
        "name": row.station_name,
        "latitude": float(row.station_latitude),
        "longitude": float(row.station_longitude),
        "distance_meters": round(
            _haversine_meters(query_lat, query_lon, row.station_latitude, row.station_longitude),
            1,
        ),
        "city": row.city or "",
        "country": row.country or "",
    }


def _station_payload_from_master_row(row: TrainStation, query_lat: float, query_lon: float) -> dict:
    return {
        "name": row.name,
        "latitude": float(row.latitude),
        "longitude": float(row.longitude),
        "distance_meters": round(
            _haversine_meters(query_lat, query_lon, row.latitude, row.longitude),
            1,
        ),
        "city": row.city or "",
        "country": row.country or "",
    }


def _get_cached_station_from_db(db: Session, lat: float, lon: float) -> Optional[dict]:
    lookup_key = _station_lookup_db_key(lat, lon)
    exact = db.query(TrainStationCache).filter(TrainStationCache.lookup_key == lookup_key).first()
    if exact:
        return _station_payload_from_row(exact, lat, lon)

    max_delta = STATION_CACHE_REUSE_RADIUS_METERS / 111320
    candidates = (
        db.query(TrainStationCache)
        .filter(TrainStationCache.query_latitude.between(lat - max_delta, lat + max_delta))
        .filter(TrainStationCache.query_longitude.between(lon - max_delta, lon + max_delta))
        .all()
    )

    best_row = None
    best_distance = None
    for row in candidates:
        distance = _haversine_meters(lat, lon, row.query_latitude, row.query_longitude)
        if distance > STATION_CACHE_REUSE_RADIUS_METERS:
            continue
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_row = row

    if best_row:
        return _station_payload_from_row(best_row, lat, lon)
    return None


def _get_master_station_from_db(
    db: Session,
    lat: float,
    lon: float,
    radius_meters: int = MASTER_STATION_SEARCH_RADIUS_METERS,
) -> Optional[dict]:
    max_delta = radius_meters / 111320
    candidates = (
        db.query(TrainStation)
        .filter(TrainStation.latitude.between(lat - max_delta, lat + max_delta))
        .filter(TrainStation.longitude.between(lon - max_delta, lon + max_delta))
        .all()
    )

    best_row = None
    best_distance = None
    for row in candidates:
        distance = _haversine_meters(lat, lon, row.latitude, row.longitude)
        if distance > radius_meters:
            continue
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_row = row

    if best_row:
        return _station_payload_from_master_row(best_row, lat, lon)
    return None


def _save_station_cache(db: Session, lat: float, lon: float, station: dict) -> None:
    normalized = _normalize_station_payload(station)
    if not normalized:
        return

    lookup_key = _station_lookup_db_key(lat, lon)
    row = db.query(TrainStationCache).filter(TrainStationCache.lookup_key == lookup_key).first()
    if not row:
        row = TrainStationCache(lookup_key=lookup_key)
        db.add(row)

    row.query_latitude = lat
    row.query_longitude = lon
    row.station_name = normalized["name"]
    row.station_latitude = normalized["latitude"]
    row.station_longitude = normalized["longitude"]
    row.distance_meters = normalized["distance_meters"]
    row.city = normalized["city"]
    row.country = normalized["country"]

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(TrainStationCache).filter(TrainStationCache.lookup_key == lookup_key).first()
        if not existing:
            logger.exception("train_route.save_station_cache: duplicate key but row missing key=%s", lookup_key)
            return
        existing.query_latitude = lat
        existing.query_longitude = lon
        existing.station_name = normalized["name"]
        existing.station_latitude = normalized["latitude"]
        existing.station_longitude = normalized["longitude"]
        existing.distance_meters = normalized["distance_meters"]
        existing.city = normalized["city"]
        existing.country = normalized["country"]
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("train_route.save_station_cache: recovery commit failed key=%s", lookup_key)
    except Exception:
        db.rollback()
        logger.exception("train_route.save_station_cache: commit failed key=%s", lookup_key)


def _save_master_station(
    db: Session,
    station: dict,
    *,
    osm_type: Optional[str] = None,
    osm_id: Optional[str] = None,
    tags: Optional[dict] = None,
) -> None:
    normalized = _normalize_station_payload(station)
    if not normalized:
        return

    tags = tags or {}
    provider = tags.get("provider") or "osm_live_lookup"
    osm_key = None
    if osm_type and osm_id:
        osm_key = f"osm_{osm_type}_{osm_id}"

    row = None
    if osm_key:
        row = db.query(TrainStation).filter(TrainStation.osm_key == osm_key).first()
    if not row:
        row = (
            db.query(TrainStation)
            .filter(TrainStation.name == normalized["name"])
            .filter(TrainStation.latitude == normalized["latitude"])
            .filter(TrainStation.longitude == normalized["longitude"])
            .first()
        )
    if not row:
        row = TrainStation(osm_key=osm_key or f"manual_{normalized['latitude']:.6f}_{normalized['longitude']:.6f}")
        db.add(row)

    row.osm_type = osm_type or row.osm_type or "manual"
    row.osm_id = str(osm_id or row.osm_id or "")
    row.name = normalized["name"]
    row.latitude = normalized["latitude"]
    row.longitude = normalized["longitude"]
    row.city = normalized["city"]
    row.country = normalized["country"]
    row.railway_type = tags.get("railway") or tags.get("station") or tags.get("public_transport") or row.railway_type or ""
    row.source = provider
    row.tags_json = json.dumps(tags, ensure_ascii=True)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if not osm_key:
            logger.exception("train_route.save_master_station: duplicate without osm key for %s", normalized["name"])
            return
        existing = db.query(TrainStation).filter(TrainStation.osm_key == osm_key).first()
        if not existing:
            logger.exception("train_route.save_master_station: duplicate key but row missing key=%s", osm_key)
            return
        existing.osm_type = osm_type or existing.osm_type or "manual"
        existing.osm_id = str(osm_id or existing.osm_id or "")
        existing.name = normalized["name"]
        existing.latitude = normalized["latitude"]
        existing.longitude = normalized["longitude"]
        existing.city = normalized["city"]
        existing.country = normalized["country"]
        existing.railway_type = tags.get("railway") or tags.get("station") or tags.get("public_transport") or existing.railway_type or ""
        existing.source = provider
        existing.tags_json = json.dumps(tags, ensure_ascii=True)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("train_route.save_master_station: recovery commit failed key=%s", osm_key)
    except Exception:
        db.rollback()
        logger.exception("train_route.save_master_station: commit failed for %s", normalized["name"])


async def _fetch_nearest_station(db: Session, lat: float, lon: float, *, country_hint: Optional[str] = None) -> Optional[dict]:
    cache_key = _station_cache_key(lat, lon)
    is_shanghai_lookup = is_shanghai_coordinate(lat, lon)

    # Only use the coordinate-only cache when no country filter is active.
    # With a country hint we always do a fresh search so the bbox filter is applied.
    if not country_hint and not is_shanghai_lookup and cache_key in _station_snap_cache:
        cached = _station_snap_cache[cache_key]
        if cached:
            logger.info(
                "train_route: station source=memory_cache for %.5f,%.5f -> %s",
                lat,
                lon,
                cached["name"],
            )
        else:
            logger.info(
                "train_route: station source=memory_cache for %.5f,%.5f -> none",
                lat,
                lon,
        )
        return _station_snap_cache[cache_key]

    geojson_station = lookup_nearest_transport_place_from_geojson(
        lat,
        lon,
        "train",
        country_hint=country_hint,
        max_distance_meters=STATION_SEARCH_RADIUS_METERS_EXPANDED,
    )
    if geojson_station:
        # Only store in the coordinate-only cache for unfiltered lookups.
        if not country_hint:
            _station_snap_cache[cache_key] = geojson_station
        logger.info(
            "train_route: station source=%s for %.5f,%.5f -> %s",
            geojson_station.get("source"),
            lat,
            lon,
            geojson_station["name"],
        )
        _save_master_station(
            db,
            geojson_station,
            osm_type="node",
            osm_id=geojson_station.get("osm_id"),
            tags={
                **(geojson_station.get("tags") or {}),
                "provider": geojson_station.get("source") or "geojson",
            },
        )
        _save_station_cache(db, lat, lon, geojson_station)
        return geojson_station

    # When a country filter is active, don't fall through to the DB / Overpass
    # fallbacks because those have no spatial filter and would happily return
    # a station from a neighbouring country.
    if country_hint:
        return None

    cached_station = _get_cached_station_from_db(db, lat, lon)
    if cached_station:
        _station_snap_cache[cache_key] = cached_station
        logger.info(
            "train_route: station source=train_station_cache for %.5f,%.5f -> %s",
            lat,
            lon,
            cached_station["name"],
        )
        return cached_station

    master_station = _get_master_station_from_db(db, lat, lon)
    if master_station:
        _station_snap_cache[cache_key] = master_station
        _save_station_cache(db, lat, lon, master_station)
        logger.info(
            "train_route: station source=train_stations for %.5f,%.5f -> %s",
            lat,
            lon,
            master_station["name"],
        )
        return master_station

    def build_query(radius: int) -> str:
        return f"""
    [out:json][timeout:15];
    (
      node(around:{radius},{lat},{lon})["railway"~"station|halt|tram_stop|subway_entrance"];
      node(around:{radius},{lat},{lon})["railway"="stop"];
      node(around:{radius},{lat},{lon})["station"];
      node(around:{radius},{lat},{lon})["public_transport"="station"];
      node(around:{radius},{lat},{lon})["public_transport"="platform"];
      node(around:{radius},{lat},{lon})["public_transport"="stop_position"];
      node(around:{radius},{lat},{lon})["subway"="yes"];
      node(around:{radius},{lat},{lon})["monorail"="yes"];
      way(around:{radius},{lat},{lon})["railway"~"station|halt|tram_stop|subway_entrance"];
      way(around:{radius},{lat},{lon})["railway"="stop"];
      way(around:{radius},{lat},{lon})["station"];
      way(around:{radius},{lat},{lon})["public_transport"="station"];
      way(around:{radius},{lat},{lon})["public_transport"="platform"];
      way(around:{radius},{lat},{lon})["public_transport"="stop_position"];
      way(around:{radius},{lat},{lon})["subway"="yes"];
      way(around:{radius},{lat},{lon})["monorail"="yes"];
      relation(around:{radius},{lat},{lon})["railway"~"station|halt|tram_stop|subway_entrance"];
      relation(around:{radius},{lat},{lon})["railway"="stop"];
      relation(around:{radius},{lat},{lon})["station"];
      relation(around:{radius},{lat},{lon})["public_transport"="station"];
      relation(around:{radius},{lat},{lon})["public_transport"="platform"];
      relation(around:{radius},{lat},{lon})["public_transport"="stop_position"];
      relation(around:{radius},{lat},{lon})["subway"="yes"];
      relation(around:{radius},{lat},{lon})["monorail"="yes"];
    );
    out center tags;
    """

    data = None
    for radius in (STATION_SEARCH_RADIUS_METERS, STATION_SEARCH_RADIUS_METERS_EXPANDED):
        data = await _post_overpass(
            build_query(radius),
            timeout=20.0,
            context=f"nearest station radius={radius}",
            endpoints=[OVERPASS_URL],
            max_attempts=1,
        )
        if data and data.get("elements"):
            break
    if not data:
        _station_snap_cache[cache_key] = None
        return None

    best_station = None
    best_distance = None
    best_station_tags = None
    best_station_osm_type = None
    best_station_osm_id = None
    for element in data.get("elements") or []:
        station_lat = element.get("lat") or (element.get("center") or {}).get("lat")
        station_lon = element.get("lon") or (element.get("center") or {}).get("lon")
        if station_lat is None or station_lon is None:
            continue
        distance = _haversine_meters(lat, lon, float(station_lat), float(station_lon))
        if best_distance is None or distance < best_distance:
            best_distance = distance
            tags = element.get("tags") or {}
            best_station = {
                "name": _preferred_english_name(tags, "Train station"),
                "latitude": float(station_lat),
                "longitude": float(station_lon),
                "distance_meters": round(distance, 1),
                "city": tags.get("addr:city") or tags.get("is_in:city") or "",
                "country": tags.get("addr:country") or tags.get("is_in:country") or "",
            }
            best_station_tags = tags
            best_station_osm_type = element.get("type")
            best_station_osm_id = str(element.get("id") or "")

    if best_station:
        # Normalize ISO country codes (e.g. "CN" → full name via reverse geocode)
        country_raw = best_station["country"]
        country_is_iso = bool(country_raw) and len(country_raw) <= 3 and country_raw.isupper()
        if not best_station["city"] or not country_raw or country_is_iso:
            reverse = await _reverse_geocode_station(best_station["latitude"], best_station["longitude"])
            if reverse:
                best_station["city"] = best_station["city"] or reverse.get("city", "")
                if not country_raw or country_is_iso:
                    best_station["country"] = reverse.get("country", country_raw)
                if _contains_non_ascii(best_station["name"]):
                    reverse_name = reverse.get("place_name") or ""
                    if reverse_name and not _contains_non_ascii(reverse_name):
                        best_station["name"] = reverse_name

    if best_station:
        _station_snap_cache[cache_key] = best_station
        logger.info(
            "train_route: station source=overpass for %.5f,%.5f -> %s",
            lat,
            lon,
            best_station["name"],
        )
        _save_master_station(
            db,
            best_station,
            osm_type=best_station_osm_type,
            osm_id=best_station_osm_id,
            tags=best_station_tags,
        )
        _save_station_cache(db, lat, lon, best_station)
        return best_station

    geoapify_station = await _fetch_nearest_station_from_geoapify(lat, lon)
    if geoapify_station:
        _station_snap_cache[cache_key] = geoapify_station
        logger.info(
            "train_route: station source=geoapify for %.5f,%.5f -> %s",
            lat,
            lon,
            geoapify_station["name"],
        )
        _save_master_station(db, geoapify_station, tags={"provider": "geoapify"})
        _save_station_cache(db, lat, lon, geoapify_station)
        return geoapify_station

    _station_snap_cache[cache_key] = None
    logger.info(
        "train_route: station source=none for %.5f,%.5f",
        lat,
        lon,
    )
    return None


async def lookup_nearest_train_station(db: Session, lat: float, lon: float, *, country_hint: Optional[str] = None) -> Optional[dict]:
    station = await _fetch_nearest_station(db, lat, lon, country_hint=country_hint)
    if not station:
        return None
    if float(station.get("distance_meters") or 0) > USER_TRAIN_SNAP_MAX_DISTANCE_METERS:
        logger.info(
            "train_route: station snap rejected for %.5f,%.5f -> %s distance=%.1fm max=%sm",
            lat,
            lon,
            station.get("name"),
            float(station.get("distance_meters") or 0),
            USER_TRAIN_SNAP_MAX_DISTANCE_METERS,
        )
        return None
    return station


async def _fetch_nearest_station_for_route(db: Session, lat: float, lon: float) -> Optional[dict]:
    station = await _fetch_nearest_station(db, lat, lon)
    if not station:
        return None
    if float(station.get("distance_meters") or 0) > ROUTE_TRAIN_STATION_MAX_DISTANCE_METERS:
        logger.info(
            "train_route: route station anchor rejected for %.5f,%.5f -> %s distance=%.1fm max=%sm",
            lat,
            lon,
            station.get("name"),
            float(station.get("distance_meters") or 0),
            ROUTE_TRAIN_STATION_MAX_DISTANCE_METERS,
        )
        return None
    return station


def _normalize_cached_payload(value) -> Optional[dict]:
    if isinstance(value, list):
        if not value:
            return {"geometry": [], "anchor_start": None, "anchor_end": None, "provider": None}
        return {
            "geometry": value,
            "anchor_start": value[0],
            "anchor_end": value[-1],
            "provider": None,
        }
    if isinstance(value, dict):
        geometry = value.get("geometry")
        if not isinstance(geometry, list):
            return None
        anchor_start = value.get("anchor_start") or (geometry[0] if geometry else None)
        anchor_end = value.get("anchor_end") or (geometry[-1] if geometry else None)
        return {
            "geometry": geometry,
            "anchor_start": anchor_start,
            "anchor_end": anchor_end,
            "provider": value.get("provider"),
        }
    return None


def search_train_stations(
    db: Session,
    query: str,
    limit: int = 10,
    country: Optional[str] = None,
    include_eu_international: bool = False,
) -> list[dict]:
    normalized_query = _normalize_search_text(query)
    if len(normalized_query) < 2:
        return []

    ranked_results: list[tuple[int, dict]] = []
    seen_ids: set[str] = set()

    for station in search_transport_places_from_geojson(
        query,
        "train",
        country_hint=country,
        limit=limit,
        include_eu_international=include_eu_international,
    ):
        station_id = str(station.get("id") or "")
        if station_id in seen_ids:
            continue
        seen_ids.add(station_id)
        ranked_results.append((500, station))

    ascii_query = _normalize_search_text(query.strip())
    db_query = db.query(TrainStation).filter(
        TrainStation.name.ilike(f"%{query.strip()}%")
        | TrainStation.name.ilike(f"%{ascii_query}%")
    )
    if country:
        db_query = db_query.filter(TrainStation.country.ilike(country.strip()))
    db_rows = db_query.limit(max(limit * 4, 20)).all()
    for row in db_rows:
        normalized_name = _normalize_search_text(row.name or "")
        if not normalized_name:
            continue
        if normalized_name == normalized_query:
            score = 400
        elif normalized_name.startswith(normalized_query):
            score = 300
        elif normalized_query in normalized_name:
            score = 200
        else:
            continue

        station_id = row.osm_key or f"db-{row.id}"
        if station_id in seen_ids:
            continue
        seen_ids.add(station_id)
        ranked_results.append(
            (
                score,
                {
                    "id": station_id,
                    "place_name": row.name,
                    "city": row.city or "",
                    "country": row.country or "",
                    "latitude": float(row.latitude),
                    "longitude": float(row.longitude),
                    "subtitle": ", ".join(part for part in [row.city or "", row.country or ""] if part),
                    "source": row.source or "train_stations",
                },
            )
        )

    ranked_results.sort(key=lambda item: (-item[0], item[1]["place_name"]))

    results: list[dict] = []
    seen_names: set[str] = set()
    for _, station in ranked_results:
        key = _normalize_search_text(station["place_name"])
        if key in seen_names:
            continue
        seen_names.add(key)
        results.append(station)
        if len(results) >= limit:
            break

    return results


def get_cached_geometry(db: Session, key: str) -> Optional[dict]:
    row = db.query(RouteCache).filter(RouteCache.cache_key == key).first()
    if row is None:
        return None
    payload = _normalize_cached_payload(json.loads(row.geometry_json))
    if payload is not None and not payload.get("provider") and row.provider:
        payload["provider"] = row.provider
    return payload

def save_geometry(db: Session, key: str, payload: dict, *, countries: Optional[list[str]] = None) -> None:
    row = db.query(RouteCache).filter(RouteCache.cache_key == key).first()
    serialized = json.dumps(payload)
    metadata = build_route_cache_metadata(payload, countries=countries)
    if row:
        row.geometry_json = serialized
        row.provider = metadata["provider"]
        row.point_count = metadata["point_count"]
        row.countries_json = json.dumps(metadata["countries"])
        row.geometry_signature = metadata["geometry_signature"]
    else:
        db.add(RouteCache(
            cache_key=key,
            geometry_json=serialized,
            provider=metadata["provider"],
            point_count=metadata["point_count"],
            countries_json=json.dumps(metadata["countries"]),
            geometry_signature=metadata["geometry_signature"],
        ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(RouteCache).filter(RouteCache.cache_key == key).first()
        if not existing:
            logger.exception("train_route.save_geometry: duplicate key but row missing key=%s", key)
            return
        existing.geometry_json = serialized
        existing.provider = metadata["provider"]
        existing.point_count = metadata["point_count"]
        existing.countries_json = json.dumps(metadata["countries"])
        existing.geometry_signature = metadata["geometry_signature"]
        try:
            db.commit()
            logger.info("train_route.save_geometry: recovered duplicate insert for key=%s", key)
        except Exception:
            db.rollback()
            logger.exception("train_route.save_geometry: recovery commit failed key=%s", key)
    except Exception:
        db.rollback()
        logger.exception("train_route.save_geometry: commit failed key=%s", key)


def _find_nearby_cached_payload(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Optional[dict]:
    rows = db.query(RouteCache).filter(RouteCache.cache_key.like(f"{CACHE_PREFIX}|%")).all()
    best_match = None
    best_score = None

    for row in rows:
        payload = _normalize_cached_payload(json.loads(row.geometry_json))
        if not payload or not payload.get("geometry"):
            continue
        if not payload.get("provider") and row.provider:
            payload["provider"] = row.provider
        anchor_start = payload.get("anchor_start")
        anchor_end = payload.get("anchor_end")
        if not anchor_start or not anchor_end:
            continue

        start_dist = _haversine_meters(lat1, lon1, anchor_start[0], anchor_start[1])
        end_dist = _haversine_meters(lat2, lon2, anchor_end[0], anchor_end[1])
        if start_dist > NEARBY_REUSE_RADIUS_METERS or end_dist > NEARBY_REUSE_RADIUS_METERS:
            continue

        score = start_dist + end_dist
        if best_score is None or score < best_score:
            best_score = score
            best_match = payload

    return best_match


def get_cached_train_geometry(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    from_country: Optional[str] = None,
    to_country: Optional[str] = None,
) -> Optional[dict]:
    exact = get_cached_geometry(db, make_cache_key(lat1, lon1, lat2, lon2))
    if exact is not None and _is_cached_provider_compatible(db, exact.get("provider"), from_country, to_country):
        return exact
    nearby = _find_nearby_cached_payload(db, lat1, lon1, lat2, lon2)
    if nearby is not None and _is_cached_provider_compatible(db, nearby.get("provider"), from_country, to_country):
        return nearby
    return None


def get_train_route_state(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    from_country: Optional[str] = None,
    to_country: Optional[str] = None,
) -> tuple[Optional[list], str, Optional[list[float]], Optional[list[float]]]:
    cached = get_cached_train_geometry(db, lat1, lon1, lat2, lon2, from_country, to_country)
    if cached is None:
        return None, "pending", None, None

    geometry = cached.get("geometry") or []
    anchor_start = cached.get("anchor_start")
    anchor_end = cached.get("anchor_end")
    if geometry:
        return geometry, "ready", anchor_start, anchor_end
    return None, "unavailable", anchor_start, anchor_end


def get_train_route_provider(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    from_country: Optional[str] = None,
    to_country: Optional[str] = None,
) -> Optional[str]:
    cached = get_cached_train_geometry(db, lat1, lon1, lat2, lon2, from_country, to_country)
    if cached is None:
        return None
    return cached.get("provider")


async def resolve_train_route(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> tuple[Optional[list], str, Optional[list[float]], Optional[list[float]]]:
    geometry, status, anchor_start, anchor_end = get_train_route_state(db, lat1, lon1, lat2, lon2)
    if geometry or status == "unavailable":
        return geometry, status, anchor_start, anchor_end

    start_station = await _fetch_nearest_station_for_route(db, lat1, lon1)
    end_station = await _fetch_nearest_station_for_route(db, lat2, lon2)
    if not start_station or not end_station:
        return geometry, status, anchor_start, anchor_end

    geometry, status, anchor_start, anchor_end = get_train_route_state(
        db,
        start_station["latitude"],
        start_station["longitude"],
        end_station["latitude"],
        end_station["longitude"],
    )
    if anchor_start is None:
        anchor_start = [start_station["latitude"], start_station["longitude"]]
    if anchor_end is None:
        anchor_end = [end_station["latitude"], end_station["longitude"]]
    return geometry, status, anchor_start, anchor_end


async def fetch_and_cache(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    from_country: Optional[str] = None,
    to_country: Optional[str] = None,
) -> Optional[list]:
    """
    Check DB cache first. If missing, fetch from Google Routes, store result,
    and return geometry (or None when no usable transit path is found).
    """
    key = make_cache_key(lat1, lon1, lat2, lon2)
    cached = get_cached_geometry(db, key)
    if cached is not None and _is_cached_provider_compatible(db, cached.get("provider"), from_country, to_country):
        geometry = cached.get("geometry") or []
        logger.info(
            "train_route: route source=route_cache key=%s provider=%s points=%s",
            key,
            cached.get("provider"),
            len(geometry),
        )
        return geometry or None
    if cached is not None:
        logger.info(
            "train_route: route_cache ignored due to policy key=%s provider=%s from=%r to=%r",
            key,
            cached.get("provider"),
            from_country,
            to_country,
        )

    start_station = await _fetch_nearest_station_for_route(db, lat1, lon1)
    end_station = await _fetch_nearest_station_for_route(db, lat2, lon2)

    if start_station and end_station:
        same_country_name = _same_non_china_country(
            start_station.get("country"),
            end_station.get("country"),
        )
        is_china_station_pair = (
            (
                _is_china_route_candidate(
                    start_station.get("country"),
                    start_station["latitude"],
                    start_station["longitude"],
                )
                and _is_china_route_candidate(
                    end_station.get("country"),
                    end_station["latitude"],
                    end_station["longitude"],
                )
            ) or (
                not _normalize_country_name(start_station.get("country"))
                and not _normalize_country_name(end_station.get("country"))
                and _is_china_route_candidate(None, start_station["latitude"], start_station["longitude"])
                and _is_china_route_candidate(None, end_station["latitude"], end_station["longitude"])
            )
        )
        station_key = make_cache_key(
            start_station["latitude"],
            start_station["longitude"],
            end_station["latitude"],
            end_station["longitude"],
        )
        station_cached = get_cached_geometry(db, station_key)
        if station_cached is not None and _is_cached_provider_compatible(
            db,
            station_cached.get("provider"),
            start_station.get("country"),
            end_station.get("country"),
        ):
            save_geometry(
                db,
                key,
                {
                    "geometry": station_cached.get("geometry") or [],
                    "anchor_start": station_cached.get("anchor_start") or [start_station["latitude"], start_station["longitude"]],
                    "anchor_end": station_cached.get("anchor_end") or [end_station["latitude"], end_station["longitude"]],
                    "provider": station_cached.get("provider"),
                },
            )
            geometry = station_cached.get("geometry") or []
            logger.info(
                "train_route: route source=station_route_cache key=%s provider=%s points=%s",
                station_key,
                station_cached.get("provider"),
                len(geometry),
            )
            return geometry or None
        if station_cached is not None:
            logger.info(
                "train_route: station_route_cache ignored due to policy key=%s provider=%s from=%r to=%r",
                station_key,
                station_cached.get("provider"),
                start_station.get("country"),
                end_station.get("country"),
            )

        nearby = _find_nearby_cached_payload(
            db,
            start_station["latitude"],
            start_station["longitude"],
            end_station["latitude"],
            end_station["longitude"],
        )
        if nearby is not None and _is_cached_provider_compatible(
            db,
            nearby.get("provider"),
            start_station.get("country"),
            end_station.get("country"),
        ):
            save_geometry(
                db,
                key,
                {
                    "geometry": nearby.get("geometry") or [],
                    "anchor_start": nearby.get("anchor_start") or [start_station["latitude"], start_station["longitude"]],
                    "anchor_end": nearby.get("anchor_end") or [end_station["latitude"], end_station["longitude"]],
                    "provider": nearby.get("provider"),
                },
            )
            geometry = nearby.get("geometry") or []
            logger.info(
                "train_route: route source=nearby_cache provider=%s points=%s",
                nearby.get("provider"),
                len(geometry),
            )
            return geometry or None
        if nearby is not None:
            logger.info(
                "train_route: nearby_cache ignored due to policy provider=%s from=%r to=%r",
                nearby.get("provider"),
                start_station.get("country"),
                end_station.get("country"),
            )

        provider_payload = None
        if same_country_name:
            provider_payload = await _resolve_train_payload_for_country_mode(
                db,
                start_station["latitude"],
                start_station["longitude"],
                end_station["latitude"],
                end_station["longitude"],
                same_country_name,
            )
        elif is_china_station_pair:
            china_city_payload, china_city_policy_applied = await _resolve_china_city_policy_payload(
                db,
                start_station["latitude"],
                start_station["longitude"],
                end_station["latitude"],
                end_station["longitude"],
            )
            provider_payload = china_city_payload
            if provider_payload:
                provider_payload["provider"] = provider_payload.get("provider") or "geojson"
            if not provider_payload and not china_city_policy_applied:
                if (
                    is_shanghai_coordinate(start_station["latitude"], start_station["longitude"])
                    and is_shanghai_coordinate(end_station["latitude"], end_station["longitude"])
                ):
                    provider_payload = await _fetch_from_shanghai_geojson_with_timeout(
                        start_station["latitude"],
                        start_station["longitude"],
                        end_station["latitude"],
                        end_station["longitude"],
                    )
                    if provider_payload:
                        provider_payload["provider"] = "shanghai_geojson"
        elif _should_try_google_for_train_by_policy(
            db,
            start_station.get("country") or from_country,
            end_station.get("country") or to_country,
        ):
            provider_payload = await _fetch_from_google_routes(
                start_station["latitude"],
                start_station["longitude"],
                end_station["latitude"],
                end_station["longitude"],
            )
            if provider_payload:
                provider_payload["provider"] = "google"
        if not provider_payload:
            provider_payload = await _fetch_from_osm_railway(
                start_station["latitude"],
                start_station["longitude"],
                end_station["latitude"],
                end_station["longitude"],
            )
            if provider_payload:
                provider_payload["provider"] = "osm"
        provider_payload = _stitch_train_geometry_to_stations(provider_payload, start_station, end_station)
        countries = [
            country
            for country in [start_station.get("country"), end_station.get("country")]
            if country
        ]
        payload = provider_payload or {
            "geometry": [
                [start_station["latitude"], start_station["longitude"]],
                [end_station["latitude"], end_station["longitude"]],
            ],
            "anchor_start": [start_station["latitude"], start_station["longitude"]],
            "anchor_end": [end_station["latitude"], end_station["longitude"]],
            "provider": "fallback",
        }
        if payload:
            payload = _stitch_train_geometry_to_stations(payload, start_station, end_station)
        save_geometry(
            db,
            station_key,
            payload,
            countries=countries,
        )
        save_geometry(
            db,
            key,
            payload,
            countries=countries,
        )
        geometry = payload.get("geometry") if payload else None
        logger.info(
            "train_route: route source=%s key=%s points=%s",
            (payload or {}).get("provider"),
            station_key,
            len(geometry or []),
        )
        return geometry if geometry else None

    nearby = _find_nearby_cached_payload(db, lat1, lon1, lat2, lon2)
    if nearby is not None and _is_cached_provider_compatible(db, nearby.get("provider"), from_country, to_country):
        save_geometry(
            db,
            key,
            {
                "geometry": nearby.get("geometry") or [],
                "anchor_start": nearby.get("anchor_start"),
                "anchor_end": nearby.get("anchor_end"),
                "provider": nearby.get("provider"),
            },
        )
        geometry = nearby.get("geometry") or []
        logger.info(
            "train_route: route source=nearby_cache provider=%s points=%s",
            nearby.get("provider"),
            len(geometry),
        )
        return geometry or None
    if nearby is not None:
        logger.info(
            "train_route: nearby_cache ignored due to policy provider=%s from=%r to=%r",
            nearby.get("provider"),
            from_country,
            to_country,
        )

    same_country_name = _same_non_china_country(from_country, to_country)
    payload = None
    if same_country_name:
        payload = await _resolve_train_payload_for_country_mode(
            db,
            lat1,
            lon1,
            lat2,
            lon2,
            same_country_name,
        )
    elif _is_china_route_candidate(from_country, lat1, lon1) and _is_china_route_candidate(to_country, lat2, lon2):
        china_city_payload, china_city_policy_applied = await _resolve_china_city_policy_payload(
            db,
            lat1,
            lon1,
            lat2,
            lon2,
        )
        payload = china_city_payload
        if payload:
            payload["provider"] = payload.get("provider") or "geojson"
        if not payload and not china_city_policy_applied:
            if is_shanghai_coordinate(lat1, lon1) and is_shanghai_coordinate(lat2, lon2):
                payload = await _fetch_from_shanghai_geojson_with_timeout(lat1, lon1, lat2, lon2)
                if payload:
                    payload["provider"] = "shanghai_geojson"
    elif _should_try_google_for_train_by_policy(db, from_country, to_country):
        payload = await _fetch_from_google_routes(lat1, lon1, lat2, lon2)
        if payload:
            payload["provider"] = "google"
    if not payload:
        payload = await _fetch_from_osm_railway(lat1, lon1, lat2, lon2)
        if payload:
            payload["provider"] = "osm"
    payload = payload or {
        "geometry": [[lat1, lon1], [lat2, lon2]],
        "anchor_start": [lat1, lon1],
        "anchor_end": [lat2, lon2],
        "provider": "fallback",
    }
    save_geometry(
        db,
        key,
        payload,
        countries=[country for country in [from_country, to_country] if country],
    )
    geometry = payload.get("geometry") if payload else None
    logger.info(
        "train_route: route source=%s key=%s points=%s",
        (payload or {}).get("provider"),
        key,
        len(geometry or []),
    )
    return geometry if geometry else None
