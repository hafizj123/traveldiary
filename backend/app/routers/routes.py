from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.ferry_route_service import fetch_and_cache_ferry_route, get_ferry_route_state
from ..services.place_lookup_service import lookup_nearest_transport_place, reverse_geocode_location
from ..services.train_route_service import get_train_route_state, lookup_nearest_train_station

router = APIRouter(tags=["routes"])


# ─── Endpoint ─────────────────────────────────────────────────────────────────
@router.get("/routes/train")
async def get_train_route(
    lat1: float = Query(...),
    lon1: float = Query(...),
    lat2: float = Query(...),
    lon2: float = Query(...),
    db: Session = Depends(get_db),
):
    geometry, status, anchor_start, anchor_end = get_train_route_state(db, lat1, lon1, lat2, lon2)
    return {
        "geometry": geometry,
        "status": status,
        "anchor_start": anchor_start,
        "anchor_end": anchor_end,
    }


@router.get("/routes/ferry")
async def get_ferry_route(
    lat1: float = Query(...),
    lon1: float = Query(...),
    lat2: float = Query(...),
    lon2: float = Query(...),
    db: Session = Depends(get_db),
):
    geometry, status = get_ferry_route_state(db, lat1, lon1, lat2, lon2)
    if status == "pending":
        geometry = await fetch_and_cache_ferry_route(db, lat1, lon1, lat2, lon2)
        status = "ready" if geometry else "unavailable"
    return {
        "geometry": geometry,
        "status": status,
    }


@router.get("/stations/nearest-train")
async def get_nearest_train_station(
    lat: float = Query(...),
    lon: float = Query(...),
):
    station = await lookup_nearest_train_station(lat, lon)
    return {"station": station}


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
):
    place = await lookup_nearest_transport_place(lat, lon, method)
    return {"place": place}
