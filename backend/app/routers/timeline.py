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
from ..services.train_route_service import fetch_and_cache

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

    created_train_pairs = []
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
            if (
                data.travel_method == "train"
                and prev.latitude and prev.longitude
                and point.latitude and point.longitude
            ):
                created_train_pairs.append((prev, point))

    db.commit()
    db.refresh(point)
    for from_pt, to_pt in created_train_pairs:
        await fetch_and_cache(
            db,
            from_pt.latitude,
            from_pt.longitude,
            to_pt.latitude,
            to_pt.longitude,
            from_pt.country,
            to_pt.country,
        )
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

    connected_train_segments = db.query(TravelSegment).filter(
        ((TravelSegment.from_point_id == point.id) | (TravelSegment.to_point_id == point.id))
        & (TravelSegment.travel_method == "train")
    ).all()
    for seg in connected_train_segments:
        from_pt = seg.from_point
        to_pt = seg.to_point
        if not from_pt or not to_pt:
            continue
        if not (from_pt.latitude and from_pt.longitude and to_pt.latitude and to_pt.longitude):
            continue
        await fetch_and_cache(
            db,
            from_pt.latitude,
            from_pt.longitude,
            to_pt.latitude,
            to_pt.longitude,
            from_pt.country,
            to_pt.country,
        )
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

    ordered_points = (
        db.query(TimelinePoint)
        .filter(TimelinePoint.trip_id == point.trip_id)
        .order_by(TimelinePoint.sequence_no, TimelinePoint.id)
        .all()
    )
    point_index = next((idx for idx, item in enumerate(ordered_points) if item.id == point.id), None)
    prev_point = ordered_points[point_index - 1] if point_index is not None and point_index > 0 else None
    next_point = (
        ordered_points[point_index + 1]
        if point_index is not None and point_index < len(ordered_points) - 1
        else None
    )

    touching_segments = db.query(TravelSegment).filter(
        (TravelSegment.from_point_id == point_id) | (TravelSegment.to_point_id == point_id)
    ).all()
    incoming_segment = next((seg for seg in touching_segments if prev_point and seg.from_point_id == prev_point.id), None)
    outgoing_segment = next((seg for seg in touching_segments if next_point and seg.to_point_id == next_point.id), None)

    bridged_train_pair = None
    bridge_source_segment = outgoing_segment or incoming_segment
    should_bridge = (
        prev_point is not None
        and next_point is not None
        and incoming_segment is not None
        and outgoing_segment is not None
        and bridge_source_segment is not None
    )

    if should_bridge:
        existing_bridge = db.query(TravelSegment).filter(
            TravelSegment.trip_id == point.trip_id,
            TravelSegment.from_point_id == prev_point.id,
            TravelSegment.to_point_id == next_point.id,
        ).first()
        if not existing_bridge:
            bridged_segment = TravelSegment(
                trip_id=point.trip_id,
                from_point_id=prev_point.id,
                to_point_id=next_point.id,
                travel_method=bridge_source_segment.travel_method,
                description=bridge_source_segment.description,
            )
            db.add(bridged_segment)
            if (
                bridged_segment.travel_method == "train"
                and prev_point.latitude and prev_point.longitude
                and next_point.latitude and next_point.longitude
            ):
                bridged_train_pair = (prev_point, next_point)

    image_url = point.image_url
    # Delete all segments touching this point before deleting the point
    db.query(TravelSegment).filter(
        (TravelSegment.from_point_id == point_id) | (TravelSegment.to_point_id == point_id)
    ).delete(synchronize_session=False)
    db.delete(point)
    db.commit()

    if bridged_train_pair:
        from_pt, to_pt = bridged_train_pair
        await fetch_and_cache(
            db,
            from_pt.latitude,
            from_pt.longitude,
            to_pt.latitude,
            to_pt.longitude,
            from_pt.country,
            to_pt.country,
        )

    if image_url:
        await delete_image(image_url)
