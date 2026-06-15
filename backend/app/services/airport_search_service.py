from __future__ import annotations

import json
import logging
import math
import threading
import unicodedata
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

AIRPORT_GEOJSON_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend/gpkg/hotosm_chn_railways_osm_gpkg/geojson_file/global/airport.geojson"
)

_lock = threading.Lock()
_airports_cache: Optional[list[dict]] = None

COUNTRY_EQUIVALENTS = {
    "united kingdom": {
        "united kingdom",
        "uk",
        "great britain",
        "england",
        "scotland",
        "wales",
        "northern ireland",
    },
    "uk": {
        "united kingdom",
        "uk",
        "great britain",
        "england",
        "scotland",
        "wales",
        "northern ireland",
    },
    "great britain": {
        "united kingdom",
        "uk",
        "great britain",
        "england",
        "scotland",
        "wales",
        "northern ireland",
    },
}


def _normalize(value: str) -> str:
    text = " ".join((value or "").strip().lower().split())
    text = (
        text.replace("ø", "o")
        .replace("œ", "oe")
        .replace("æ", "ae")
        .replace("å", "a")
        .replace("ö", "o")
        .replace("ü", "u")
        .replace("ä", "a")
        .replace("ß", "ss")
    )
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("ascii")


def _preferred_name(properties: dict) -> str:
    for key in (
        "name:en",
        "official_name:en",
        "alt_name:en",
        "short_name:en",
        "int_name",
        "iata",
        "icao",
        "name",
    ):
        value = str(properties.get(key) or "").strip()
        if value:
            return value
    return ""


def _extract_city(properties: dict) -> str:
    for key in ("addr:city", "is_in:city", "closest_town", "city_served", "city", "town"):
        value = str(properties.get(key) or "").strip()
        if value:
            return value

    is_in = str(properties.get("is_in") or "").strip()
    if is_in:
        return is_in.split(",")[0].strip()

    return ""


def _extract_aliases(properties: dict) -> list[str]:
    seen: set[str] = set()
    aliases: list[str] = []
    for key in (
        "name:en",
        "official_name:en",
        "alt_name:en",
        "short_name:en",
        "int_name",
        "iata",
        "icao",
        "official_name",
        "short_name",
        "name",
        "alt_name",
    ):
        value = str(properties.get(key) or "").strip()
        normalized = _normalize(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            aliases.append(value)
    city = _extract_city(properties)
    for value in (city, f"{city} airport" if city else ""):
        normalized = _normalize(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            aliases.append(value)
    return aliases


def _country_matches_hint(airport_country: str, country_hint: str) -> bool:
    normalized_country = _normalize(airport_country)
    normalized_hint = _normalize(country_hint)
    if not normalized_hint:
        return True
    if not normalized_country:
        return True
    if normalized_country == normalized_hint:
        return True

    equivalents = COUNTRY_EQUIVALENTS.get(normalized_hint)
    if equivalents and normalized_country in equivalents:
        return True

    reverse_equivalents = COUNTRY_EQUIVALENTS.get(normalized_country)
    if reverse_equivalents and normalized_hint in reverse_equivalents:
        return True

    return (
        normalized_hint in normalized_country
        or normalized_country in normalized_hint
    )


def _display_country(airport_country: str, country_hint: Optional[str]) -> str:
    if country_hint and _country_matches_hint(airport_country, country_hint):
        normalized_hint = _normalize(country_hint)
        if normalized_hint in COUNTRY_EQUIVALENTS:
            return country_hint
    return airport_country


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def _infer_country_from_bbox(lat: float, lon: float) -> str:
    """Return the most specific (smallest-area) country whose bounding box
    contains this coordinate.  Returns an empty string when no bbox matches.

    Importing inside the function avoids circular imports at module load time.
    """
    from .geojson_transport_service import EUROPE_COUNTRY_BOUNDS, WORLD_COUNTRY_BOUNDS  # noqa: PLC0415

    best_country = ""
    best_area = float("inf")
    for country_name, bb in {**EUROPE_COUNTRY_BOUNDS, **WORLD_COUNTRY_BOUNDS}.items():
        if bb["south"] <= lat <= bb["north"] and bb["west"] <= lon <= bb["east"]:
            area = (bb["north"] - bb["south"]) * (bb["east"] - bb["west"])
            if area < best_area:
                best_area = area
                best_country = country_name
    # Title-case so display names like "Switzerland" are returned, not "switzerland".
    return best_country.title() if best_country else ""


def _load_airports() -> list[dict]:
    global _airports_cache
    if _airports_cache is not None:
        return _airports_cache

    with _lock:
        if _airports_cache is not None:
            return _airports_cache

        if not AIRPORT_GEOJSON_PATH.exists():
            logger.warning("airport_search: airport.geojson not found at %s", AIRPORT_GEOJSON_PATH)
            _airports_cache = []
            return _airports_cache

        with AIRPORT_GEOJSON_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

        airports: list[dict] = []
        for feature in data.get("features") or []:
            geometry = feature.get("geometry") or {}
            if geometry.get("type") != "Point":
                continue
            coords = geometry.get("coordinates") or []
            if len(coords) < 2:
                continue

            lon, lat = float(coords[0]), float(coords[1])
            props = feature.get("properties") or {}

            # Only keep actual airports / aerodromes (skip heliports, airstrips etc.)
            aeroway = str(props.get("aeroway") or "").strip().lower()
            if aeroway not in {"aerodrome", "terminal"}:
                continue

            name = _preferred_name(props)
            if not name:
                continue

            aliases = _extract_aliases(props)
            city = _extract_city(props)
            country = str(
                props.get("addr:country") or
                props.get("is_in:country") or
                props.get("addr:country_code") or
                ""
            ).strip()
            iata = str(props.get("iata") or "").strip()

            # If the GeoJSON feature has no usable country tag, infer the country
            # from whichever known bounding box most tightly contains this point.
            # This correctly attributes Changi Airport to Singapore rather than
            # to Malaysia (whose bbox encloses Singapore's entire bbox).
            if not country:
                country = _infer_country_from_bbox(lat, lon)

            airports.append(
                {
                    "id": str(feature.get("id") or props.get("@id") or f"{lat:.6f},{lon:.6f}"),
                    "name": name,
                    "aliases": aliases,
                    "iata": iata,
                    "city": city,
                    "country": country,
                    "latitude": lat,
                    "longitude": lon,
                }
            )

        _airports_cache = airports
        logger.info("airport_search: loaded %d airports from GeoJSON", len(airports))
        return _airports_cache


def search_airports(
    query: str,
    *,
    country_hint: Optional[str] = None,
    country_bbox: Optional[dict] = None,
    limit: int = 10,
) -> list[dict]:
    normalized_query = _normalize(query)
    if not normalized_query:
        return []

    airports = _load_airports()
    ranked: list[tuple[int, dict]] = []

    normalized_country = _normalize(country_hint or "")

    for airport in airports:
        # Hard bbox filter: when a bounding box is provided only airports within it are returned.
        if country_bbox is not None:
            if not (
                country_bbox["south"] <= airport["latitude"] <= country_bbox["north"]
                and country_bbox["west"] <= airport["longitude"] <= country_bbox["east"]
            ):
                continue
            # Within the bbox, apply a second hard filter using the airport's
            # inferred country so neighbours that happen to be inside the bbox
            # (e.g. Singapore inside Malaysia's bbox) are excluded.
            if normalized_country and airport["country"]:
                if not _country_matches_hint(airport["country"], country_hint or ""):
                    continue
            country_match = True
        else:
            # No bbox: soft country name filter (boost only)
            country_match = (
                not normalized_country
                or _country_matches_hint(airport["country"], country_hint or "")
            )

        best_score: Optional[int] = None
        for alias in airport["aliases"]:
            norm = _normalize(alias)
            if not norm:
                continue
            if norm == normalized_query:
                score = 500
            elif norm.startswith(normalized_query):
                score = 400
            elif normalized_query in norm:
                score = 300
            else:
                # Also match IATA code exactly
                if airport["iata"] and _normalize(airport["iata"]) == normalized_query:
                    score = 450
                else:
                    continue
            if best_score is None or score > best_score:
                best_score = score

        if best_score is None:
            continue

        # Boost results from the hinted country
        if country_match and normalized_country:
            best_score += 50

        ranked.append((best_score, airport))

    ranked.sort(key=lambda x: (-x[0], x[1]["name"]))

    results: list[dict] = []
    seen: set[str] = set()
    for _, airport in ranked:
        display_country = _display_country(airport["country"], country_hint)
        key = f"{_normalize(airport['name'])}|{_normalize(display_country)}"
        if key in seen:
            continue
        seen.add(key)
        subtitle_parts = [p for p in [airport["iata"], airport["city"], display_country] if p]
        results.append(
            {
                "id": airport["id"],
                "place_name": airport["name"],
                "city": airport["city"],
                "country": display_country,
                "latitude": airport["latitude"],
                "longitude": airport["longitude"],
                "subtitle": ", ".join(subtitle_parts),
                "transport_mode": "airport",
                "source": "airport_geojson",
            }
        )
        if len(results) >= limit:
            break

    return results


def nearest_airport(
    lat: float,
    lon: float,
    *,
    max_distance_meters: float = 50_000,
    country_bbox: Optional[dict] = None,
) -> Optional[dict]:
    airports = _load_airports()
    best: Optional[tuple[float, dict]] = None
    for airport in airports:
        # Hard country bbox filter — skip airports outside the selected country.
        if country_bbox is not None:
            if not (
                country_bbox["south"] <= airport["latitude"] <= country_bbox["north"]
                and country_bbox["west"] <= airport["longitude"] <= country_bbox["east"]
            ):
                continue
        distance = _haversine_meters(lat, lon, airport["latitude"], airport["longitude"])
        if distance > max_distance_meters:
            continue
        if best is None or distance < best[0]:
            best = (distance, airport)

    if best is None:
        return None

    distance, airport = best
    subtitle_parts = [p for p in [airport["iata"], airport["city"], airport["country"]] if p]
    return {
        "place_name": airport["name"],
        "city": airport["city"],
        "country": airport["country"],
        "latitude": airport["latitude"],
        "longitude": airport["longitude"],
        "distance_meters": round(distance, 1),
        "source": "airport_geojson",
        "subtitle": ", ".join(subtitle_parts),
    }
