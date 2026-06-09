from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..models.trip import Trip
from ..models.timeline_point import TimelinePoint
from ..models.travel_segment import TravelSegment
from ..schemas.timeline_point import (
    TimelinePointCreate,
    TimelinePointUpdate,
    TimelinePointResponse,
)
from ..utils.deps import get_current_user
from ..models.user import User
from ..services.weather_service import get_weather
from ..services.r2_service import delete_image

router = APIRouter(tags=["timeline"])


def _get_trip(trip_id: int, user_id: int, db: Session) -> Trip:
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user_id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")
    return trip


def _validate_visit_date_in_trip_range(trip: Trip, visit_date) -> None:
    if trip.start_date and visit_date < trip.start_date:
        raise HTTPException(400, "Visit date cannot be earlier than the trip start date")
    if trip.end_date and visit_date > trip.end_date:
        raise HTTPException(400, "Visit date cannot be later than the trip end date")


@router.post("/trips/{trip_id}/points", response_model=TimelinePointResponse, status_code=201)
async def add_point(
    trip_id: int,
    data: TimelinePointCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = _get_trip(trip_id, user.id, db)
    _validate_visit_date_in_trip_range(trip, data.visit_date)

    existing_count = (
        db.query(TimelinePoint).filter(TimelinePoint.trip_id == trip_id).count()
    )

    point_data = data.model_dump(exclude={"travel_method"})
    if point_data.get("sequence_no") is None:
        point_data["sequence_no"] = existing_count

    weather = None
    if point_data.get("latitude") and point_data.get("longitude"):
        weather = await get_weather(
            point_data["latitude"],
            point_data["longitude"],
            point_data.get("visit_date"),
        )

    point = TimelinePoint(**point_data, trip_id=trip_id, weather_data=weather)
    db.add(point)
    db.flush()

    # Auto-create segment from previous point
    if data.travel_method and existing_count > 0:
        prev = (
            db.query(TimelinePoint)
            .filter(
                TimelinePoint.trip_id == trip_id,
                TimelinePoint.sequence_no == existing_count - 1,
            )
            .first()
        )
        if prev:
            db.add(
                TravelSegment(
                    trip_id=trip_id,
                    from_point_id=prev.id,
                    to_point_id=point.id,
                    travel_method=data.travel_method,
                )
            )

    db.commit()
    db.refresh(point)
    return point


@router.get("/trips/{trip_id}/points", response_model=List[TimelinePointResponse])
async def list_points(
    trip_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from datetime import date, timedelta
    _get_trip(trip_id, user.id, db)
    points = (
        db.query(TimelinePoint)
        .filter(TimelinePoint.trip_id == trip_id)
        .order_by(TimelinePoint.sequence_no)
        .all()
    )
    # Auto-refresh weather for points whose stored data isn't from the historical archive
    today = date.today()
    for pt in points:
        if not pt.visit_date or not pt.latitude or not pt.longitude:
            continue
        w = pt.weather_data or {}
        is_historical_date = pt.visit_date < today - timedelta(days=7)
        already_historical = w.get("source") == "historical"
        if is_historical_date and not already_historical:
            fresh = await get_weather(pt.latitude, pt.longitude, pt.visit_date)
            if fresh:
                pt.weather_data = fresh
                db.add(pt)
    db.commit()
    return points


@router.put("/points/{point_id}", response_model=TimelinePointResponse)
async def update_point(
    point_id: int,
    data: TimelinePointUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    point = (
        db.query(TimelinePoint)
        .join(Trip)
        .filter(TimelinePoint.id == point_id, Trip.user_id == user.id)
        .first()
    )
    if not point:
        raise HTTPException(404, "Point not found")

    updates = data.model_dump(exclude_unset=True)
    trip = point.trip

    if "visit_date" in updates and updates["visit_date"] is not None:
        _validate_visit_date_in_trip_range(trip, updates["visit_date"])

    new_lat = updates.get("latitude", point.latitude)
    new_lon = updates.get("longitude", point.longitude)
    if new_lat and new_lon and (new_lat != point.latitude or new_lon != point.longitude):
        visit_date = updates.get("visit_date") or point.visit_date
        updates["weather_data"] = await get_weather(new_lat, new_lon, visit_date)

    for k, v in updates.items():
        setattr(point, k, v)

    db.commit()
    db.refresh(point)
    return point


@router.delete("/points/{point_id}", status_code=204)
async def delete_point(
    point_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    point = (
        db.query(TimelinePoint)
        .join(Trip)
        .filter(TimelinePoint.id == point_id, Trip.user_id == user.id)
        .first()
    )
    if not point:
        raise HTTPException(404, "Point not found")
    image_url = point.image_url
    # Delete all segments touching this point before deleting the point
    db.query(TravelSegment).filter(
        (TravelSegment.from_point_id == point_id) | (TravelSegment.to_point_id == point_id)
    ).delete(synchronize_session=False)
    db.delete(point)
    db.commit()
    if image_url:
        await delete_image(image_url)
