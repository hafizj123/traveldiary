import asyncio
import json
import math
import re
from hashlib import sha1

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..models.route_cache import RouteCache
from ..models.timeline_point import TimelinePoint
from ..models.train_station import TrainStation
from ..models.train_station_cache import TrainStationCache
from ..models.user import User
from ..services.country_route_policy_service import (
    list_country_route_policies_with_capabilities,
    upsert_country_route_policy,
)
from ..services.geojson_transport_service import build_excursion_route_from_geojson, country_has_local_train_data
from ..services.excursion_route_service import fetch_and_cache_excursion_route, get_excursion_route_provider, get_excursion_route_state
from ..services.ferry_route_service import fetch_and_cache_ferry_route, get_ferry_route_provider, get_ferry_route_state
from ..services.geojson_import_service import create_geojson_import_task, list_geojson_import_tasks
from ..services.geojson_import_service import get_geojson_import_task_log
from ..services.place_lookup_service import lookup_nearest_transport_place, reverse_geocode_location, search_transport_places
from ..services.route_cache_service import build_route_cache_metadata, extract_geometry, normalize_countries
from ..services.search_alias_service import search_alias_matches
from ..services.audit_service import is_admin_user
from ..services.train_route_service import (
    fetch_and_cache,
    get_train_route_provider,
    get_train_route_state,
    lookup_nearest_train_station,
    search_train_stations,
)
from ..utils.deps import get_current_user

router = APIRouter(tags=["routes"])

# Detect ISO 2-/3-letter country codes (e.g. "CN", "DE", "GBR") that need
# to be resolved to full country names via reverse geocoding.
_ISO_CODE_RE = re.compile(r'^[A-Z]{2,3}$')


def _country_needs_geocode(country: str) -> bool:
    """Return True when `country` is absent, a generic label, or a raw ISO code."""
    if not country:
        return True
    if country.lower() == "europe":
        return True
    # 2- or 3-letter ISO codes like "CN", "DE", "GBR" are not usable as dropdown values.
    if _ISO_CODE_RE.match(country):
        return True
    return False

# Maximum straight-line distances for road/walk methods (meters).
# Beyond these thresholds users are warned before the segment is saved.
MAX_DISTANCE_CAR_BUS_OTHER_METERS = 2_000_000   # 2 000 km
MAX_DISTANCE_WALK_METERS          =   100_000   # 100 km


class GeoJsonImportCreateBody(BaseModel):
    country_name: str
    city_name: Optional[str] = None
    import_type: str = "rail"
    iso_code: Optional[str] = None
    overwrite: bool = False


class CountryRoutePolicyUpdateBody(BaseModel):
    train_mode: str


class RouteCheckBody(BaseModel):
    method: str
    lat1: float
    lon1: float
    lat2: float
    lon2: float
    country1: Optional[str] = None
    country2: Optional[str] = None


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


def _nearest_country_hint(db: Session, point: Optional[list], radius_meters: int = 25000) -> Optional[str]:
    if not point or len(point) < 2:
        return None

    lat = float(point[0])
    lon = float(point[1])
    max_delta = radius_meters / 111320

    def pick_country(rows, lat_attr: str, lon_attr: str, country_attr: str) -> Optional[str]:
        best_country = None
        best_distance = None
        for row in rows:
            row_lat = getattr(row, lat_attr, None)
            row_lon = getattr(row, lon_attr, None)
            country = getattr(row, country_attr, None)
            if row_lat is None or row_lon is None or not country:
                continue
            distance = _haversine_meters(lat, lon, float(row_lat), float(row_lon))
            if distance > radius_meters:
                continue
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_country = country
        return best_country

    station_rows = (
        db.query(TrainStation)
        .filter(TrainStation.latitude.between(lat - max_delta, lat + max_delta))
        .filter(TrainStation.longitude.between(lon - max_delta, lon + max_delta))
        .all()
    )
    country = pick_country(station_rows, "latitude", "longitude", "country")
    if country:
        return country

    cache_rows = (
        db.query(TrainStationCache)
        .filter(TrainStationCache.station_latitude.between(lat - max_delta, lat + max_delta))
        .filter(TrainStationCache.station_longitude.between(lon - max_delta, lon + max_delta))
        .all()
    )
    country = pick_country(cache_rows, "station_latitude", "station_longitude", "country")
    if country:
        return country

    point_rows = (
        db.query(TimelinePoint)
        .filter(TimelinePoint.latitude.between(lat - max_delta, lat + max_delta))
        .filter(TimelinePoint.longitude.between(lon - max_delta, lon + max_delta))
        .all()
    )
    return pick_country(point_rows, "latitude", "longitude", "country")


def _require_admin_route_user(user: User) -> None:
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Admin access required")


def _parse_countries_json(value: str) -> list[str]:
    try:
        payload = json.loads(value or "[]")
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return normalize_countries([str(item) for item in payload if item])


def _build_route_cache_row_item(
    db: Session,
    row: RouteCache,
    *,
    include_geometry: bool,
) -> Optional[dict]:
    try:
        payload = json.loads(row.geometry_json)
    except Exception:
        return None

    geometry = extract_geometry(payload)
    if len(geometry) < 2:
        return None

    metadata_missing = (
        row.point_count in {None, 0}
        or not row.geometry_signature
        or row.countries_json in {None, ""}
        or not row.provider
    )

    countries = _parse_countries_json(row.countries_json or "[]")
    if metadata_missing or not countries:
        anchor_start = payload.get("anchor_start") if isinstance(payload, dict) else None
        anchor_end = payload.get("anchor_end") if isinstance(payload, dict) else None
        inferred_countries = normalize_countries([
            country
            for country in (
                _nearest_country_hint(db, anchor_start),
                _nearest_country_hint(db, anchor_end),
            )
            if country
        ])
        metadata = build_route_cache_metadata(payload, countries=inferred_countries or countries)
        row.provider = metadata["provider"]
        row.point_count = metadata["point_count"]
        row.countries_json = json.dumps(metadata["countries"])
        row.geometry_signature = metadata["geometry_signature"]
        countries = metadata["countries"]

    item = {
        "id": row.id,
        "cache_key": row.cache_key,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "provider": row.provider,
        "countries": countries,
        "point_count": int(row.point_count or len(geometry)),
        "geometry_signature": row.geometry_signature or sha1(row.cache_key.encode("utf-8")).hexdigest(),
    }
    if include_geometry:
        item["geometry"] = geometry
        item["anchor_start"] = payload.get("anchor_start") if isinstance(payload, dict) else None
        item["anchor_end"] = payload.get("anchor_end") if isinstance(payload, dict) else None
    return item


# ─── Endpoint ─────────────────────────────────────────────────────────────────
@router.get("/routes/train")
async def get_train_route(
    lat1: float = Query(...),
    lon1: float = Query(...),
    lat2: float = Query(...),
    lon2: float = Query(...),
    country1: Optional[str] = Query(None),
    country2: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    geometry, status, anchor_start, anchor_end = get_train_route_state(
        db,
        lat1,
        lon1,
        lat2,
        lon2,
        country1,
        country2,
    )
    if status == "pending":
        geometry = await fetch_and_cache(db, lat1, lon1, lat2, lon2, country1, country2)
        geometry, status, anchor_start, anchor_end = get_train_route_state(
            db,
            lat1,
            lon1,
            lat2,
            lon2,
            country1,
            country2,
        )
    return {
        "geometry": geometry,
        "status": status,
        "anchor_start": anchor_start,
        "anchor_end": anchor_end,
        "provider": get_train_route_provider(db, lat1, lon1, lat2, lon2, country1, country2),
    }


@router.get("/routes/ferry")
async def get_ferry_route(
    lat1: float = Query(...),
    lon1: float = Query(...),
    lat2: float = Query(...),
    lon2: float = Query(...),
    db: Session = Depends(get_db),
):
    geometry, status, provider = get_ferry_route_state(db, lat1, lon1, lat2, lon2)
    if status == "pending":
        geometry = await fetch_and_cache_ferry_route(db, lat1, lon1, lat2, lon2)
        geometry, status, provider = get_ferry_route_state(db, lat1, lon1, lat2, lon2)
    return {
        "geometry": geometry,
        "status": status,
        "provider": provider,
    }


@router.get("/routes/excursion")
async def get_excursion_route(
    lat1: float = Query(...),
    lon1: float = Query(...),
    lat2: float = Query(...),
    lon2: float = Query(...),
    country: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    geometry, status, anchor_start, anchor_end = get_excursion_route_state(db, lat1, lon1, lat2, lon2)
    if status == "pending":
        geometry = await fetch_and_cache_excursion_route(db, lat1, lon1, lat2, lon2, country)
        geometry, status, anchor_start, anchor_end = get_excursion_route_state(db, lat1, lon1, lat2, lon2)
    return {
        "geometry": geometry,
        "status": status,
        "anchor_start": anchor_start,
        "anchor_end": anchor_end,
        "provider": get_excursion_route_provider(db, lat1, lon1, lat2, lon2),
    }


@router.post("/routes/check")
async def check_route_before_save(
    payload: RouteCheckBody,
    db: Session = Depends(get_db),
):
    method = (payload.method or "").strip().lower()
    if not method:
        return {"exists": True, "behavior": "allow", "message": ""}

    if method == "flight":
        return {"exists": True, "behavior": "allow", "message": ""}

    if method == "excursion":
        route = build_excursion_route_from_geojson(
            payload.lat1,
            payload.lon1,
            payload.lat2,
            payload.lon2,
            country_hint=payload.country1 or payload.country2,
        )
        if route:
            return {
                "exists": True,
                "behavior": "allow",
                "message": "",
                "provider": route.get("provider"),
            }
        return {
            "exists": False,
            "behavior": "block",
            "message": "These two lift stations cannot be connected.",
            "provider": None,
        }

    if method == "train":
        await fetch_and_cache(
            db,
            payload.lat1,
            payload.lon1,
            payload.lat2,
            payload.lon2,
            payload.country1,
            payload.country2,
        )
        provider = get_train_route_provider(
            db,
            payload.lat1,
            payload.lon1,
            payload.lat2,
            payload.lon2,
            payload.country1,
            payload.country2,
        )
        exists = provider not in {None, "fallback"}
        return {
            "exists": exists,
            "behavior": "allow" if exists else "confirm",
            "message": "" if exists else "No train route was found between these two locations. If you continue, we will draw a fallback line.",
            "provider": provider,
        }

    if method == "ferry":
        await fetch_and_cache_ferry_route(db, payload.lat1, payload.lon1, payload.lat2, payload.lon2)
        provider = get_ferry_route_provider(db, payload.lat1, payload.lon1, payload.lat2, payload.lon2)
        exists = provider not in {None, "ferry_fallback"}  # ferry_water_curve is considered valid
        return {
            "exists": exists,
            "behavior": "allow" if exists else "confirm",
            "message": "" if exists else "No ferry route was found between these two locations. If you continue, we will draw a fallback line.",
            "provider": provider,
        }

    if method in {"car", "bus", "walk", "other"}:
        max_m = MAX_DISTANCE_WALK_METERS if method == "walk" else MAX_DISTANCE_CAR_BUS_OTHER_METERS
        dist_m = _haversine_meters(payload.lat1, payload.lon1, payload.lat2, payload.lon2)
        if dist_m > max_m:
            dist_km = round(dist_m / 1000)
            return {
                "exists": False,
                "behavior": "block",
                "message": (
                    f"This location is approximately {dist_km:,} km from your previous stop. "
                    f"That is too far for {method.capitalize()}. "
                    "Please choose a closer destination or switch to a different transport method such as Flight."
                ),
            }

    return {"exists": True, "behavior": "allow", "message": ""}


@router.get("/stations/nearest-train")
async def get_nearest_train_station(
    lat: float = Query(...),
    lon: float = Query(...),
    country: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    station = await lookup_nearest_train_station(db, lat, lon, country_hint=country)
    if station:
        current_country = (station.get("country") or "").strip()
        needs_country = _country_needs_geocode(current_country)
        needs_city = not (station.get("city") or "").strip()
        if needs_country or needs_city:
            rev = await reverse_geocode_location(station["latitude"], station["longitude"])
            if rev:
                if needs_city:
                    station = {**station, "city": rev.get("city", "")}
                if needs_country:
                    station = {**station, "country": rev.get("country", current_country)}
    return {"station": station}


@router.get("/stations/search-train")
async def get_search_train_stations(
    q: str = Query(..., min_length=2),
    country: Optional[str] = Query(None),
    limit: int = Query(8, ge=1, le=20),
    include_eu_international: bool = Query(False),
    db: Session = Depends(get_db),
):
    results = search_train_stations(db, q, limit, country, include_eu_international=include_eu_international)
    alias_results = search_alias_matches(db, q, method="train", country_hint=country, limit=limit)
    if alias_results:
        seen_keys = {
            f"{(item.get('place_name') or '').strip().lower()}|{(item.get('country') or '').strip().lower()}"
            for item in results
        }
        for item in alias_results:
            key = f"{(item.get('place_name') or '').strip().lower()}|{(item.get('country') or '').strip().lower()}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            results.insert(0, item)
        results = results[:limit]
    if results:
        async def _enrich_station(r: dict) -> dict:
            current_country = (r.get("country") or "").strip()
            needs_country = _country_needs_geocode(current_country)
            needs_city = not (r.get("city") or "").strip()
            if not needs_country and not needs_city:
                return r
            rev = await reverse_geocode_location(r["latitude"], r["longitude"])
            if rev:
                city = rev.get("city", "") if needs_city else (r.get("city") or "")
                country_name = rev.get("country", current_country) if needs_country else current_country
                if needs_city:
                    r = {**r, "city": city}
                if needs_country:
                    r = {**r, "country": country_name}
                r = {**r, "subtitle": ", ".join(part for part in [city, country_name] if part)}
            return r
        results = list(await asyncio.gather(*[_enrich_station(r) for r in results]))
    has_local = country_has_local_train_data(country) if country else False
    return {"results": results, "has_local_data": has_local}


@router.get("/locations/search-transport")
async def get_search_transport_places(
    q: str = Query(..., min_length=2),
    method: str = Query(...),
    country: Optional[str] = Query(None),
    limit: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
):
    results = search_transport_places(q, method, country, limit)
    alias_results = search_alias_matches(db, q, method=method, country_hint=country, limit=limit)
    if alias_results:
        seen_keys = {
            f"{(item.get('place_name') or '').strip().lower()}|{(item.get('country') or '').strip().lower()}"
            for item in results
        }
        for item in alias_results:
            key = f"{(item.get('place_name') or '').strip().lower()}|{(item.get('country') or '').strip().lower()}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            results.insert(0, item)
        results = results[:limit]

    if results:
        # Local OSM/GeoJSON transport stops often lack city/country tags.
        # Europe lift data also uses region-level fallback labels like "Europe",
        # so we enrich those from reverse geocoding before sending to the UI.
        async def enrich(r: dict) -> dict:
            current_country = (r.get("country") or "").strip()
            needs_country = _country_needs_geocode(current_country)
            needs_city = not (r.get("city") or "").strip()
            if not needs_country and not needs_city:
                return r
            rev = await reverse_geocode_location(r["latitude"], r["longitude"])
            if rev:
                city = rev.get("city", "") if needs_city else (r.get("city") or "")
                country_name = rev.get("country", current_country) if needs_country else current_country
                if needs_city:
                    r = {**r, "city": city}
                if needs_country:
                    r = {**r, "country": country_name}
                r = {
                    **r,
                    "subtitle": ", ".join(part for part in [city, country_name] if part),
                }
            return r

        results = list(await asyncio.gather(*[enrich(r) for r in results]))

    return {"results": results}


@router.get("/locations/reverse")
async def get_reverse_geocoded_location(
    lat: float = Query(...),
    lon: float = Query(...),
):
    location = await reverse_geocode_location(lat, lon)
    return {"location": location}


@router.get("/locations/nearest-transport")
async def get_nearest_transport_place(
    lat: float = Query(...),
    lon: float = Query(...),
    method: str = Query(...),
    country: Optional[str] = Query(None),
):
    place = await lookup_nearest_transport_place(lat, lon, method, country_hint=country)
    if place:
        current_country = (place.get("country") or "").strip()
        needs_country = _country_needs_geocode(current_country)
        needs_city = not (place.get("city") or "").strip()
        if needs_country or needs_city:
            rev = await reverse_geocode_location(place["latitude"], place["longitude"])
            if rev:
                if needs_city:
                    place = {**place, "city": rev.get("city", "")}
                if needs_country:
                    place = {**place, "country": rev.get("country", current_country)}
    return {"place": place}


@router.get("/admin/route-cache")
def get_saved_route_cache(
    limit: int = Query(300, ge=1, le=2000),
    country: Optional[str] = Query(None),
    include_geometry: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not is_admin_user(user):
        return {"items": []}

    query_limit = limit if not country else max(limit * 8, 400)
    rows = (
        db.query(RouteCache)
        .order_by(RouteCache.id.desc())
        .limit(query_limit)
        .all()
    )

    items = []
    for row in rows:
        item = _build_route_cache_row_item(db, row, include_geometry=include_geometry)
        if not item:
            continue
        if country and country not in (item.get("countries") or []):
            continue
        items.append(item)
        if len(items) >= limit:
            break

    if db.dirty:
        db.commit()

    return {"items": items}


@router.get("/admin/geojson-import/tasks")
def get_geojson_import_tasks(user: User = Depends(get_current_user)):
    _require_admin_route_user(user)
    return {"items": list_geojson_import_tasks()}


@router.get("/admin/geojson-import/tasks/{task_id}/log")
def get_geojson_import_task_log_route(
    task_id: str,
    max_bytes: int = Query(48000, ge=1024, le=200000),
    user: User = Depends(get_current_user),
):
    _require_admin_route_user(user)
    try:
        return get_geojson_import_task_log(task_id, max_bytes=max_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/admin/geojson-import/tasks")
def post_geojson_import_task(
    payload: GeoJsonImportCreateBody,
    user: User = Depends(get_current_user),
):
    _require_admin_route_user(user)
    try:
        task = create_geojson_import_task(
            payload.country_name,
            payload.city_name,
            payload.import_type,
            payload.iso_code,
            payload.overwrite,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"task": task}


@router.get("/admin/country-route-policies")
def get_country_route_policies(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_route_user(user)
    return {"items": list_country_route_policies_with_capabilities(db)}


@router.put("/admin/country-route-policies/{country_key}")
def put_country_route_policy(
    country_key: str,
    payload: CountryRoutePolicyUpdateBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_route_user(user)
    try:
        row = upsert_country_route_policy(db, country_key, payload.train_mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "item": {
            "country_key": row.country_key,
            "country_name": row.country_name,
            "train_mode": row.train_mode,
        }
    }
