from __future__ import annotations

import logging
import math
from typing import Optional

import httpx

from .geojson_transport_service import (
    _country_bbox,
    _europe_country_bbox,
    country_has_airport_dataset,
    lookup_nearest_transport_place_from_geojson,
    search_transport_places_from_geojson,
)
from .airport_search_service import nearest_airport, search_airports

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_FALLBACK_URLS = [
    OVERPASS_URL,
    "https://overpass.private.coffee/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"

REVERSE_CACHE: dict[str, Optional[dict]] = {}
NEAREST_PLACE_CACHE: dict[str, Optional[dict]] = {}

SEARCH_CONFIG = {
    "train": {
        "label": "Train station",
        "radius_meters": 1500,
        "queries": [
            'node(around:{radius},{lat},{lon})["railway"~"station|halt|tram_stop"];',
            'node(around:{radius},{lat},{lon})["railway"="stop"];',
            'node(around:{radius},{lat},{lon})["public_transport"="station"];',
            'node(around:{radius},{lat},{lon})["public_transport"="platform"];',
            'node(around:{radius},{lat},{lon})["public_transport"="stop_position"];',
            'way(around:{radius},{lat},{lon})["railway"~"station|halt|tram_stop"];',
            'way(around:{radius},{lat},{lon})["railway"="stop"];',
            'way(around:{radius},{lat},{lon})["public_transport"="station"];',
            'way(around:{radius},{lat},{lon})["public_transport"="platform"];',
            'way(around:{radius},{lat},{lon})["public_transport"="stop_position"];',
            'relation(around:{radius},{lat},{lon})["railway"~"station|halt|tram_stop"];',
            'relation(around:{radius},{lat},{lon})["railway"="stop"];',
            'relation(around:{radius},{lat},{lon})["public_transport"="station"];',
            'relation(around:{radius},{lat},{lon})["public_transport"="platform"];',
            'relation(around:{radius},{lat},{lon})["public_transport"="stop_position"];',
        ],
    },
    "flight": {
        "label": "Airport",
        "radius_meters": 30000,
        "queries": [
            'node(around:{radius},{lat},{lon})["aeroway"~"aerodrome|terminal"];',
            'way(around:{radius},{lat},{lon})["aeroway"~"aerodrome|terminal"];',
            'relation(around:{radius},{lat},{lon})["aeroway"~"aerodrome|terminal"];',
        ],
    },
    "ferry": {
        "label": "Ferry terminal",
        "radius_meters": 15000,
        "queries": [
            'node(around:{radius},{lat},{lon})["amenity"="ferry_terminal"];',
            'node(around:{radius},{lat},{lon})["ferry"="yes"];',
            'node(around:{radius},{lat},{lon})["harbour"~"ferry|yes"];',
            'way(around:{radius},{lat},{lon})["amenity"="ferry_terminal"];',
            'way(around:{radius},{lat},{lon})["ferry"="yes"];',
            'way(around:{radius},{lat},{lon})["harbour"~"ferry|yes"];',
            'relation(around:{radius},{lat},{lon})["amenity"="ferry_terminal"];',
            'relation(around:{radius},{lat},{lon})["ferry"="yes"];',
            'relation(around:{radius},{lat},{lon})["harbour"~"ferry|yes"];',
        ],
    },
    "bus": {
        "label": "Bus stop",
        "radius_meters": 1000,
        "queries": [
            'node(around:{radius},{lat},{lon})["highway"="bus_stop"];',
            'node(around:{radius},{lat},{lon})["public_transport"~"platform|stop_position"];',
            'way(around:{radius},{lat},{lon})["highway"="bus_stop"];',
            'way(around:{radius},{lat},{lon})["public_transport"~"platform|stop_position"];',
        ],
    },
    "excursion": {
        "label": "Lift station",
        "radius_meters": 3000,
        "queries": [
            'node(around:{radius},{lat},{lon})["aerialway"~"station|cable_car|gondola|chair_lift|mixed_lift|drag_lift"];',
            'way(around:{radius},{lat},{lon})["aerialway"~"station|cable_car|gondola|chair_lift|mixed_lift|drag_lift"];',
            'relation(around:{radius},{lat},{lon})["aerialway"~"station|cable_car|gondola|chair_lift|mixed_lift|drag_lift"];',
        ],
    },
}


def _preferred_english_name(tags: dict, fallback: str) -> str:
    return (
        tags.get("name:en")
        or tags.get("official_name:en")
        or tags.get("alt_name:en")
        or tags.get("short_name:en")
        or tags.get("int_name")
        or tags.get("official_name")
        or tags.get("short_name")
        or tags.get("iata")
        or tags.get("icao")
        or tags.get("name")
        or fallback
    )


def _cache_key(prefix: str, lat: float, lon: float, method: Optional[str] = None, country_hint: Optional[str] = None) -> str:
    suffix = f"|{method}" if method else ""
    country_suffix = f"|{country_hint.lower().strip()}" if country_hint else ""
    return f"{prefix}|{lat:.4f},{lon:.4f}{suffix}{country_suffix}"


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


async def reverse_geocode_location(lat: float, lon: float) -> Optional[dict]:
    cache_key = _cache_key("reverse", lat, lon)
    if cache_key in REVERSE_CACHE:
        return REVERSE_CACHE[cache_key]

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
        logger.warning("place_lookup: reverse geocode failed: %s", exc)
        REVERSE_CACHE[cache_key] = None
        return None

    address = data.get("address") or {}
    result = {
        "place_name": data.get("name")
        or address.get("attraction")
        or address.get("tourism")
        or address.get("building")
        or address.get("amenity")
        or address.get("road")
        or data.get("display_name", "").split(",")[0].strip()
        or "Pinned location",
        "city": address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("suburb")
        or address.get("county")
        or "",
        "country": address.get("country") or "",
        "latitude": float(lat),
        "longitude": float(lon),
    }
    REVERSE_CACHE[cache_key] = result
    return result


async def lookup_nearest_transport_place(lat: float, lon: float, method: str, *, country_hint: Optional[str] = None) -> Optional[dict]:
    # Airports: try per-country GeoJSON datasets first (authoritative, no bbox overlap issue),
    # then fall back to the global airport.geojson with bbox + reverse-geocode verification.
    if method == "flight":
        cache_key = _cache_key("nearest", lat, lon, method, country_hint or "")
        if cache_key in NEAREST_PLACE_CACHE:
            return NEAREST_PLACE_CACHE[cache_key]

        # 1. Try per-country airport file (e.g. vietnam_airport_station.geojson)
        geojson_match = lookup_nearest_transport_place_from_geojson(
            lat, lon, method,
            country_hint=country_hint,
            max_distance_meters=80_000,  # 80 km snap radius for airports
        )
        if geojson_match:
            NEAREST_PLACE_CACHE[cache_key] = geojson_match
            return geojson_match

        # 2. Fall back to global airport.geojson ONLY if no per-country file exists.
        # If a per-country file exists and returned nothing, that means no airport is
        # nearby in that country — don't leak results from the global file.
        if country_hint and country_has_airport_dataset(country_hint):
            NEAREST_PLACE_CACHE[cache_key] = None
            return None
        bbox = _country_bbox(country_hint) if country_hint else None
        result = nearest_airport(lat, lon, country_bbox=bbox)
        if result and country_hint:
            rev = await reverse_geocode_location(result["latitude"], result["longitude"])
            rev_country = (rev or {}).get("country", "")
            if rev_country and rev_country.strip().lower() != country_hint.strip().lower():
                logger.info(
                    "airport_search: snap rejected %s (rev_country=%r, wanted=%r)",
                    result.get("place_name"), rev_country, country_hint,
                )
                result = None
            elif rev_country:
                result = {
                    **result,
                    "country": rev_country,
                }
        NEAREST_PLACE_CACHE[cache_key] = result
        return result

    config = SEARCH_CONFIG.get(method)
    if not config:
        return None

    cache_key = _cache_key("nearest", lat, lon, method, country_hint or "")
    if cache_key in NEAREST_PLACE_CACHE:
        return NEAREST_PLACE_CACHE[cache_key]

    geojson_match = lookup_nearest_transport_place_from_geojson(
        lat,
        lon,
        method,
        country_hint=country_hint,
        max_distance_meters=float(config["radius_meters"]),
    )
    if geojson_match:
        NEAREST_PLACE_CACHE[cache_key] = geojson_match
        return geojson_match

    # When a country filter is active, don't fall back to the unfiltered Overpass
    # API — it has no spatial filter and would return terminals from neighbouring countries.
    if country_hint:
        NEAREST_PLACE_CACHE[cache_key] = None
        return None

    query_parts = "\n".join(
        item.format(radius=config["radius_meters"], lat=lat, lon=lon)
        for item in config["queries"]
    )
    query = f"""
    [out:json][timeout:15];
    (
      {query_parts}
    );
    out center tags;
    """

    data = None
    last_exc: Optional[Exception] = None
    for endpoint in OVERPASS_FALLBACK_URLS:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    endpoint,
                    data={"data": query},
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "traveldiary/1.0",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                break
        except Exception as exc:
            last_exc = exc
            logger.warning("place_lookup: nearest %s lookup failed via %s: %s", method, endpoint, exc)
    if data is None:
        NEAREST_PLACE_CACHE[cache_key] = None
        return None

    best_place = None
    best_distance = None
    for element in data.get("elements") or []:
        place_lat = element.get("lat") or (element.get("center") or {}).get("lat")
        place_lon = element.get("lon") or (element.get("center") or {}).get("lon")
        if place_lat is None or place_lon is None:
            continue

        distance = _haversine_meters(lat, lon, float(place_lat), float(place_lon))
        if best_distance is not None and distance >= best_distance:
            continue

        tags = element.get("tags") or {}
        best_distance = distance
        best_place = {
            "place_name": _preferred_english_name(tags, config["label"]),
            "city": tags.get("addr:city") or tags.get("is_in:city") or "",
            "country": tags.get("addr:country") or tags.get("is_in:country") or "",
            "latitude": float(place_lat),
            "longitude": float(place_lon),
            "distance_meters": round(distance, 1),
            "transport_mode": method,
        }

    if best_place and (not best_place["city"] or not best_place["country"]):
        reverse = await reverse_geocode_location(best_place["latitude"], best_place["longitude"])
        if reverse:
            best_place["city"] = best_place["city"] or reverse.get("city", "")
            best_place["country"] = best_place["country"] or reverse.get("country", "")

    NEAREST_PLACE_CACHE[cache_key] = best_place
    return best_place


def search_transport_places(query: str, method: str, country: Optional[str] = None, limit: int = 10) -> list[dict]:
    if method == "flight":
        # 1. Try per-country airport GeoJSON datasets first (exact country boundary).
        geojson_results = search_transport_places_from_geojson(
            query, method, country_hint=country, limit=limit
        )
        if geojson_results:
            for r in geojson_results:
                r.setdefault("transport_mode", "flight")
            return geojson_results
        # 2. Fall back to global airport.geojson ONLY if no per-country file exists.
        if country and country_has_airport_dataset(country):
            return []  # per-country file is authoritative; no cross-border leakage
        bbox = _country_bbox(country) if country else None
        return search_airports(query, country_hint=country, country_bbox=bbox, limit=limit)
    results = search_transport_places_from_geojson(
        query,
        method,
        country_hint=country,
        limit=limit,
    )
    for result in results:
        result.setdefault("transport_mode", method)
    return results


def reset_place_lookup_caches() -> None:
    NEAREST_PLACE_CACHE.clear()
