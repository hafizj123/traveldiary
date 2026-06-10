"""
Shared train-route logic: Google Routes API transit fetch + DB cache.
Used by both the /routes/train endpoint and the segment creation hook.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, time, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models.route_cache import RouteCache

logger = logging.getLogger(__name__)

GOOGLE_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
GOOGLE_FIELD_MASK = ",".join([
    "routes.polyline.encodedPolyline",
    "routes.legs.steps.polyline.encodedPolyline",
    "routes.legs.steps.transitDetails.transitLine.vehicle.type",
])
CACHE_PREFIX = "google_transit_train"
NEARBY_REUSE_RADIUS_METERS = 1000
STATION_SEARCH_RADIUS_METERS = 1500
STATION_SEARCH_RADIUS_METERS_EXPANDED = 5000
SEARCH_PADDING_DEGREES = 0.35
TERMINAL_MATCH_RADIUS_DEGREES = 0.12
MAX_OSM_ROUTE_LENGTH_RATIO = 4.0
_station_snap_cache: dict[str, Optional[dict]] = {}

GOOGLE_TRAIN_COUNTRIES = {
    "argentina",
    "australia",
    "austria",
    "belgium",
    "brazil",
    "canada",
    "chile",
    "colombia",
    "czechia",
    "czech republic",
    "denmark",
    "finland",
    "france",
    "germany",
    "greece",
    "hungary",
    "india",
    "indonesia",
    "ireland",
    "israel",
    "italy",
    "japan",
    "luxembourg",
    "malaysia",
    "mexico",
    "netherlands",
    "new zealand",
    "norway",
    "poland",
    "portugal",
    "puerto rico",
    "qatar",
    "romania",
    "singapore",
    "slovakia",
    "spain",
    "sweden",
    "switzerland",
    "taiwan",
    "thailand",
    "turkey",
    "united kingdom",
    "uk",
    "united states",
    "usa",
}

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


def make_cache_key(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> str:
    """Round to 5 dp so identical geometry lookups share one cached entry."""
    return f"{CACHE_PREFIX}|{lat1:.5f},{lon1:.5f}|{lat2:.5f},{lon2:.5f}"


def _station_cache_key(lat: float, lon: float) -> str:
    return f"{lat:.4f},{lon:.4f}"


def _normalize_country_name(country: Optional[str]) -> str:
    if not country:
        return ""
    return " ".join(country.strip().lower().split())


def _should_use_google_for_train(from_country: Optional[str], to_country: Optional[str]) -> bool:
    if not from_country or not to_country:
        return True
    normalized_from = _normalize_country_name(from_country)
    normalized_to = _normalize_country_name(to_country)
    return (
        normalized_from in GOOGLE_TRAIN_COUNTRIES
        and normalized_to in GOOGLE_TRAIN_COUNTRIES
    )


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


def _geometry_from_relation(element: dict) -> list[list[float]]:
    points: list[list[float]] = []
    for member in element.get("members") or []:
        for point in member.get("geometry") or []:
            if "lat" in point and "lon" in point:
                points.append([point["lat"], point["lon"]])
    return _dedupe_points(points)


def _distance_sq(a: list[float], b: list[float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _extract_osm_route_segment(
    geometry: list[list[float]],
    start: list[float],
    end: list[float],
) -> Optional[list[list[float]]]:
    if len(geometry) < 2:
        return None

    start_index = min(range(len(geometry)), key=lambda idx: _distance_sq(geometry[idx], start))
    end_index = min(range(len(geometry)), key=lambda idx: _distance_sq(geometry[idx], end))
    start_gap = _distance_sq(geometry[start_index], start)
    end_gap = _distance_sq(geometry[end_index], end)

    if start_gap > TERMINAL_MATCH_RADIUS_DEGREES ** 2 or end_gap > TERMINAL_MATCH_RADIUS_DEGREES ** 2:
        return None

    if start_index <= end_index:
        segment = geometry[start_index:end_index + 1]
    else:
        segment = list(reversed(geometry[end_index:start_index + 1]))

    if len(segment) < 2:
        return None

    direct_length = math.sqrt(_distance_sq(start, end))
    route_length = _polyline_length(segment)
    if direct_length > 0 and route_length > direct_length * MAX_OSM_ROUTE_LENGTH_RATIO:
        return None

    return _dedupe_points(segment)


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
      relation["route"~"train|subway|light_rail|tram|railway"]({south},{west},{north},{east});
    );
    out geom;
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OVERPASS_URL,
                data={"data": query},
                headers={
                    "Accept": "application/json",
                    "User-Agent": "traveldiary/1.0",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("train_route: OSM railway lookup failed: %s", exc)
        return None

    start = [lat1, lon1]
    end = [lat2, lon2]
    best_geometry = None
    best_score = None

    for element in data.get("elements") or []:
        if element.get("type") == "way":
            geometry = _geometry_from_way(element)
        elif element.get("type") == "relation":
            geometry = _geometry_from_relation(element)
        else:
            continue

        normalized = _extract_osm_route_segment(geometry, start, end)
        if not normalized:
            continue

        score = _distance_sq(normalized[0], start) + _distance_sq(normalized[-1], end)
        if best_score is None or score < best_score:
            best_score = score
            best_geometry = normalized

    if not best_geometry:
        return None

    return {
        "geometry": best_geometry,
        "anchor_start": best_geometry[0],
        "anchor_end": best_geometry[-1],
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
    return {
        "city": addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("suburb")
        or addr.get("county")
        or "",
        "country": addr.get("country") or "",
    }


async def _fetch_nearest_station(lat: float, lon: float) -> Optional[dict]:
    cache_key = _station_cache_key(lat, lon)
    if cache_key in _station_snap_cache:
        return _station_snap_cache[cache_key]

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
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            for radius in (STATION_SEARCH_RADIUS_METERS, STATION_SEARCH_RADIUS_METERS_EXPANDED):
                resp = await client.post(
                    OVERPASS_URL,
                    data={"data": build_query(radius)},
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "traveldiary/1.0",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("elements"):
                    break
    except Exception as exc:
        logger.warning("train_route: nearest station lookup failed: %s", exc)
        _station_snap_cache[cache_key] = None
        return None

    best_station = None
    best_distance = None
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

    if best_station and (not best_station["city"] or not best_station["country"]):
        reverse = await _reverse_geocode_station(best_station["latitude"], best_station["longitude"])
        if reverse:
            best_station["city"] = best_station["city"] or reverse.get("city", "")
            best_station["country"] = best_station["country"] or reverse.get("country", "")

    _station_snap_cache[cache_key] = best_station
    return best_station


async def lookup_nearest_train_station(lat: float, lon: float) -> Optional[dict]:
    return await _fetch_nearest_station(lat, lon)


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


def get_cached_geometry(db: Session, key: str) -> Optional[dict]:
    row = db.query(RouteCache).filter(RouteCache.cache_key == key).first()
    if row is None:
        return None
    return _normalize_cached_payload(json.loads(row.geometry_json))

def save_geometry(db: Session, key: str, payload: dict) -> None:
    row = db.query(RouteCache).filter(RouteCache.cache_key == key).first()
    serialized = json.dumps(payload)
    if row:
        row.geometry_json = serialized
    else:
        db.add(RouteCache(cache_key=key, geometry_json=serialized))
    try:
        db.commit()
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
) -> Optional[dict]:
    exact = get_cached_geometry(db, make_cache_key(lat1, lon1, lat2, lon2))
    if exact is not None:
        return exact
    return _find_nearby_cached_payload(db, lat1, lon1, lat2, lon2)


def get_train_route_state(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> tuple[Optional[list], str, Optional[list[float]], Optional[list[float]]]:
    cached = get_cached_train_geometry(db, lat1, lon1, lat2, lon2)
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
) -> Optional[str]:
    cached = get_cached_train_geometry(db, lat1, lon1, lat2, lon2)
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

    start_station = await _fetch_nearest_station(lat1, lon1)
    end_station = await _fetch_nearest_station(lat2, lon2)
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
    if cached is not None:
        geometry = cached.get("geometry") or []
        return geometry or None

    start_station = await _fetch_nearest_station(lat1, lon1)
    end_station = await _fetch_nearest_station(lat2, lon2)

    if start_station and end_station:
        station_key = make_cache_key(
            start_station["latitude"],
            start_station["longitude"],
            end_station["latitude"],
            end_station["longitude"],
        )
        station_cached = get_cached_geometry(db, station_key)
        if station_cached is not None:
            save_geometry(
                db,
                key,
                {
                    "geometry": station_cached.get("geometry") or [],
                    "anchor_start": station_cached.get("anchor_start") or [start_station["latitude"], start_station["longitude"]],
                    "anchor_end": station_cached.get("anchor_end") or [end_station["latitude"], end_station["longitude"]],
                },
            )
            geometry = station_cached.get("geometry") or []
            return geometry or None

        nearby = _find_nearby_cached_payload(
            db,
            start_station["latitude"],
            start_station["longitude"],
            end_station["latitude"],
            end_station["longitude"],
        )
        if nearby is not None:
            save_geometry(
                db,
                key,
                {
                    "geometry": nearby.get("geometry") or [],
                    "anchor_start": nearby.get("anchor_start") or [start_station["latitude"], start_station["longitude"]],
                    "anchor_end": nearby.get("anchor_end") or [end_station["latitude"], end_station["longitude"]],
                },
            )
            geometry = nearby.get("geometry") or []
            return geometry or None

        provider_payload = None
        used_google_provider = False
        if _should_use_google_for_train(from_country, to_country):
            provider_payload = await _fetch_from_google_routes(
                start_station["latitude"],
                start_station["longitude"],
                end_station["latitude"],
                end_station["longitude"],
            )
            used_google_provider = provider_payload is not None
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
        payload = provider_payload or {
            "geometry": [
                [start_station["latitude"], start_station["longitude"]],
                [end_station["latitude"], end_station["longitude"]],
            ],
            "anchor_start": [start_station["latitude"], start_station["longitude"]],
            "anchor_end": [end_station["latitude"], end_station["longitude"]],
            "provider": "fallback",
        }
        if payload and used_google_provider:
            payload["anchor_start"] = [start_station["latitude"], start_station["longitude"]]
            payload["anchor_end"] = [end_station["latitude"], end_station["longitude"]]
        save_geometry(
            db,
            station_key,
            payload,
        )
        save_geometry(
            db,
            key,
            payload,
        )
        geometry = payload.get("geometry") if payload else None
        return geometry if geometry else None

    nearby = _find_nearby_cached_payload(db, lat1, lon1, lat2, lon2)
    if nearby is not None:
        save_geometry(
            db,
            key,
            {
                "geometry": nearby.get("geometry") or [],
                "anchor_start": nearby.get("anchor_start"),
                "anchor_end": nearby.get("anchor_end"),
            },
        )
        geometry = nearby.get("geometry") or []
        return geometry or None

    payload = None
    if _should_use_google_for_train(from_country, to_country):
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
    )
    geometry = payload.get("geometry") if payload else None
    return geometry if geometry else None
