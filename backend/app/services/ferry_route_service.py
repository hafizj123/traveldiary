from __future__ import annotations

import json
import logging
import math
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..services.place_lookup_service import lookup_nearest_transport_place
from ..services.train_route_service import get_cached_geometry, save_geometry

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_FALLBACK_URLS = [
    OVERPASS_URL,
    "https://overpass.private.coffee/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
CACHE_PREFIX = "osm_ferry_route"
SEARCH_PADDING_DEGREES = 0.35
TERMINAL_MATCH_RADIUS_DEGREES = 0.12
MAX_ROUTE_LENGTH_RATIO = 3.0
MIN_FERRY_BEND_DEGREES = 0.006
WATER_CORRIDOR_RATIO = 0.35


def make_cache_key(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    return f"{CACHE_PREFIX}|{lat1:.5f},{lon1:.5f}|{lat2:.5f},{lon2:.5f}"


def _dedupe_points(points: list[list[float]]) -> list[list[float]]:
    deduped: list[list[float]] = []
    for lat, lon in points:
        if not deduped or deduped[-1][0] != lat or deduped[-1][1] != lon:
            deduped.append([lat, lon])
    return deduped


def _geometry_from_way(element: dict) -> list[list[float]]:
    return _dedupe_points([
        [point["lat"], point["lon"]]
        for point in (element.get("geometry") or [])
        if "lat" in point and "lon" in point
    ])


def _geometry_from_relation(element: dict) -> list[list[float]]:
    points: list[list[float]] = []
    for member in element.get("members") or []:
        geometry = member.get("geometry") or []
        for point in geometry:
            if "lat" in point and "lon" in point:
                points.append([point["lat"], point["lon"]])
    return _dedupe_points(points)


def _distance_sq(a: list[float], b: list[float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _polyline_length(points: list[list[float]]) -> float:
    total = 0.0
    for index in range(len(points) - 1):
        total += math.sqrt(_distance_sq(points[index], points[index + 1]))
    return total


def _build_curve_through_control(
    start: list[float],
    end: list[float],
    control: list[float],
    n: int = 48,
) -> list[list[float]]:
    # Nudge the visible water segment a little offshore from each terminal
    # so the fallback does not scrape along the shoreline.
    eased_start = [
        start[0] + (control[0] - start[0]) * 0.12,
        start[1] + (control[1] - start[1]) * 0.12,
    ]
    eased_end = [
        end[0] + (control[0] - end[0]) * 0.12,
        end[1] + (control[1] - end[1]) * 0.12,
    ]

    # Choose the quadratic control so the curve passes through `control` at t=0.5.
    ctrl = [
        2 * control[0] - 0.5 * eased_start[0] - 0.5 * eased_end[0],
        2 * control[1] - 0.5 * eased_start[1] - 0.5 * eased_end[1],
    ]
    points: list[list[float]] = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        points.append([
            mt * mt * eased_start[0] + 2 * mt * t * ctrl[0] + t * t * eased_end[0],
            mt * mt * eased_start[1] + 2 * mt * t * ctrl[1] + t * t * eased_end[1],
        ])
    return _dedupe_points(points)


def _build_basic_ferry_fallback(
    start: list[float],
    end: list[float],
) -> list[list[float]]:
    dlat = end[0] - start[0]
    dlon = end[1] - start[1]
    length = math.sqrt(dlat * dlat + dlon * dlon) or 1.0
    midpoint = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]
    perp = [-(dlon / length), dlat / length]
    offset = min(max(length * 0.02, 0.003), 0.015)
    control = [
        midpoint[0] + perp[0] * offset,
        midpoint[1] + perp[1] * offset,
    ]
    return _build_curve_through_control(start, end, control, n=36)


def _max_distance_from_chord(points: list[list[float]], start: list[float], end: list[float]) -> float:
    if len(points) < 3:
        return 0.0

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    denom = math.sqrt(dx * dx + dy * dy) or 1.0
    max_distance = 0.0

    for point in points[1:-1]:
        distance = abs(dy * point[0] - dx * point[1] + end[0] * start[1] - end[1] * start[0]) / denom
        max_distance = max(max_distance, distance)

    return max_distance


def _extract_route_segment(
    geometry: list[list[float]],
    start: list[float],
    end: list[float],
) -> tuple[float, list[list[float]]] | tuple[None, None]:
    if len(geometry) < 2:
        return None, None

    start_index = min(range(len(geometry)), key=lambda idx: _distance_sq(geometry[idx], start))
    end_index = min(range(len(geometry)), key=lambda idx: _distance_sq(geometry[idx], end))
    start_gap = _distance_sq(geometry[start_index], start)
    end_gap = _distance_sq(geometry[end_index], end)

    if start_gap > TERMINAL_MATCH_RADIUS_DEGREES ** 2 or end_gap > TERMINAL_MATCH_RADIUS_DEGREES ** 2:
        return None, None

    if start_index <= end_index:
        segment = geometry[start_index:end_index + 1]
    else:
        segment = list(reversed(geometry[end_index:start_index + 1]))

    if len(segment) < 2:
        return None, None

    direct_length = math.sqrt(_distance_sq(start, end))
    route_length = _polyline_length(segment)
    if direct_length > 0 and route_length > direct_length * MAX_ROUTE_LENGTH_RATIO:
        return None, None

    return start_gap + end_gap, _dedupe_points(segment)


async def _query_overpass_ferry_geometry(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Optional[list[list[float]]]:
    south = min(lat1, lat2) - SEARCH_PADDING_DEGREES
    north = max(lat1, lat2) + SEARCH_PADDING_DEGREES
    west = min(lon1, lon2) - SEARCH_PADDING_DEGREES
    east = max(lon1, lon2) + SEARCH_PADDING_DEGREES

    query = f"""
    [out:json][timeout:25];
    (
      way["route"="ferry"]({south},{west},{north},{east});
      relation["route"="ferry"]({south},{west},{north},{east});
    );
    out geom;
    """

    data = None
    last_exc: Optional[Exception] = None
    for endpoint in OVERPASS_FALLBACK_URLS:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    data={"data": query},
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "traveldiary/1.0",
                    },
                )
                response.raise_for_status()
                data = response.json()
                break
        except Exception as exc:
            last_exc = exc
            logger.warning("ferry_route: overpass query failed via %s: %s", endpoint, exc)
    if data is None:
        return None

    start = [lat1, lon1]
    end = [lat2, lon2]
    max_endpoint_gap_sq = TERMINAL_MATCH_RADIUS_DEGREES ** 2
    best_geometry = None
    best_score = None

    for element in data.get("elements") or []:
        if element.get("type") == "way":
            geometry = _geometry_from_way(element)
        elif element.get("type") == "relation":
            geometry = _geometry_from_relation(element)
        else:
            continue

        score, normalized_geometry = _extract_route_segment(geometry, start, end)
        if score is None or normalized_geometry is None:
            continue

        if best_score is None or score < best_score:
            best_score = score
            best_geometry = normalized_geometry

    return best_geometry


async def _query_overpass_water_control_point(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Optional[list[float]]:
    south = min(lat1, lat2) - SEARCH_PADDING_DEGREES
    north = max(lat1, lat2) + SEARCH_PADDING_DEGREES
    west = min(lon1, lon2) - SEARCH_PADDING_DEGREES
    east = max(lon1, lon2) + SEARCH_PADDING_DEGREES

    query = f"""
    [out:json][timeout:25];
    (
      way["natural"="water"]({south},{west},{north},{east});
      relation["natural"="water"]({south},{west},{north},{east});
      way["waterway"="riverbank"]({south},{west},{north},{east});
      relation["waterway"="riverbank"]({south},{west},{north},{east});
      way["landuse"="reservoir"]({south},{west},{north},{east});
      relation["landuse"="reservoir"]({south},{west},{north},{east});
    );
    out center tags;
    """

    data = None
    last_exc: Optional[Exception] = None
    for endpoint in OVERPASS_FALLBACK_URLS:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    data={"data": query},
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "traveldiary/1.0",
                    },
                )
                response.raise_for_status()
                data = response.json()
                break
        except Exception as exc:
            last_exc = exc
            logger.warning("ferry_route: water control query failed via %s: %s", endpoint, exc)
    if data is None:
        return None

    midpoint = [(lat1 + lat2) / 2, (lon1 + lon2) / 2]
    route_len = math.sqrt((lat2 - lat1) ** 2 + (lon2 - lon1) ** 2) or 1
    perp = [-(lon2 - lon1) / route_len, (lat2 - lat1) / route_len]
    parallel = [(lat2 - lat1) / route_len, (lon2 - lon1) / route_len]
    corridor_half_width = max(route_len * WATER_CORRIDOR_RATIO, 0.015)
    best_point = None
    best_score = None

    for element in data.get("elements") or []:
        center = element.get("center") or {}
        water_lat = center.get("lat")
        water_lon = center.get("lon")
        if water_lat is None or water_lon is None:
            continue

        candidate = [float(water_lat), float(water_lon)]
        side_projection = abs(
            (candidate[0] - midpoint[0]) * perp[0]
            + (candidate[1] - midpoint[1]) * perp[1]
        )
        along_projection = (
            (candidate[0] - midpoint[0]) * parallel[0]
            + (candidate[1] - midpoint[1]) * parallel[1]
        )

        # Ignore unrelated water bodies that are too far away from the direct
        # port-to-port corridor or too far beyond the endpoints.
        if side_projection > corridor_half_width:
            continue
        if abs(along_projection) > route_len * 0.7:
            continue

        midpoint_gap = _distance_sq(candidate, midpoint)
        # Prefer water centers close to the midpoint corridor, with a slight
        # preference for being somewhat off the straight chord so the route
        # visibly sits on water instead of scraping the shore.
        score = midpoint_gap - min(side_projection, corridor_half_width) * 0.08
        if best_score is None or score < best_score:
            best_score = score
            best_point = candidate

    if not best_point:
        return None

    # Blend toward the water center so the curve stays on water without overbending.
    return [
        midpoint[0] * 0.35 + best_point[0] * 0.65,
        midpoint[1] * 0.35 + best_point[1] * 0.65,
    ]


def get_ferry_route_state(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> tuple[Optional[list[list[float]]], str, Optional[str]]:
    cached = get_cached_geometry(db, make_cache_key(lat1, lon1, lat2, lon2))
    if cached is None:
        return None, "pending", None

    geometry = cached.get("geometry") or []
    if geometry:
        return geometry, "ready", cached.get("provider")
    return None, "unavailable", cached.get("provider")


def get_ferry_route_provider(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Optional[str]:
    cached = get_cached_geometry(db, make_cache_key(lat1, lon1, lat2, lon2))
    if cached is None:
        return None
    return cached.get("provider")


async def fetch_and_cache_ferry_route(
    db: Session,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Optional[list[list[float]]]:
    key = make_cache_key(lat1, lon1, lat2, lon2)
    cached = get_cached_geometry(db, key)
    if cached is not None:
        geometry = cached.get("geometry") or []
        return geometry or None

    start_terminal = await lookup_nearest_transport_place(lat1, lon1, "ferry")
    end_terminal = await lookup_nearest_transport_place(lat2, lon2, "ferry")

    lookup_start = start_terminal or {"latitude": lat1, "longitude": lon1}
    lookup_end = end_terminal or {"latitude": lat2, "longitude": lon2}
    start_point = [lookup_start["latitude"], lookup_start["longitude"]]
    end_point = [lookup_end["latitude"], lookup_end["longitude"]]

    terminal_key = make_cache_key(
        lookup_start["latitude"],
        lookup_start["longitude"],
        lookup_end["latitude"],
        lookup_end["longitude"],
    )
    terminal_cached = get_cached_geometry(db, terminal_key)
    if terminal_cached is not None:
        save_geometry(
            db,
            key,
            {
                "geometry": terminal_cached.get("geometry") or [],
                "provider": terminal_cached.get("provider"),
            },
        )
        geometry = terminal_cached.get("geometry") or []
        return geometry or None

    water_control = await _query_overpass_water_control_point(
        lookup_start["latitude"],
        lookup_start["longitude"],
        lookup_end["latitude"],
        lookup_end["longitude"],
    )

    geometry = await _query_overpass_ferry_geometry(
        lookup_start["latitude"],
        lookup_start["longitude"],
        lookup_end["latitude"],
        lookup_end["longitude"],
    )

    provider = None

    if geometry:
        provider = "osm_ferry"
    elif water_control:
        geometry = _build_curve_through_control(
            start_point,
            end_point,
            water_control,
        )
        provider = "ferry_water_curve"

    if not geometry:
        geometry = _build_basic_ferry_fallback(start_point, end_point)
        provider = "ferry_fallback"

    payload = {"geometry": geometry or [], "provider": provider}
    save_geometry(db, terminal_key, payload)
    if terminal_key != key:
        save_geometry(db, key, payload)

    return geometry or None
