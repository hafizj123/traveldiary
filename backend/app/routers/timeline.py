from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

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
from ..services.journal_service import sync_trip_journal_media
from ..services.train_route_service import fetch_and_cache, get_train_route_provider

import logging
from ..services.audit_service import log_audit_event

router = APIRouter(tags=["timeline"])
logger = logging.getLogger(__name__)


class TimelinePointReorderBody(BaseModel):
    point_ids: list[int]


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


def _validate_append_point_date(prev_point: Optional[TimelinePoint], visit_date) -> None:
    if not prev_point or not prev_point.visit_date:
        return
    if visit_date < prev_point.visit_date:
        raise HTTPException(
            400,
            f"New location cannot be earlier than the latest existing location date ({prev_point.visit_date})",
        )


def _ordered_trip_points(db: Session, trip_id: int) -> list[TimelinePoint]:
    return (
        db.query(TimelinePoint)
        .filter(TimelinePoint.trip_id == trip_id)
        .order_by(TimelinePoint.sequence_no, TimelinePoint.id)
        .all()
    )


def _normalize_trip_sequence_numbers(db: Session, trip_id: int) -> list[TimelinePoint]:
    points = _ordered_trip_points(db, trip_id)
    changed = False
    for index, point in enumerate(points):
        if point.sequence_no != index:
            point.sequence_no = index
            changed = True
    if changed:
        db.flush()
    return points


def _neighbor_points_for_point(
    db: Session,
    trip_id: int,
    point_id: int,
) -> tuple[Optional[TimelinePoint], Optional[TimelinePoint]]:
    ordered_points = _normalize_trip_sequence_numbers(db, trip_id)
    point_index = next((index for index, item in enumerate(ordered_points) if item.id == point_id), None)
    if point_index is None:
        return None, None
    prev_point = ordered_points[point_index - 1] if point_index > 0 else None
    next_point = ordered_points[point_index + 1] if point_index < len(ordered_points) - 1 else None
    return prev_point, next_point


def _validate_edit_point_date(
    prev_point: Optional[TimelinePoint],
    next_point: Optional[TimelinePoint],
    visit_date,
) -> None:
    if prev_point and prev_point.visit_date and visit_date < prev_point.visit_date:
        raise HTTPException(
            400,
            f"Visit date cannot be earlier than the previous location date ({prev_point.visit_date})",
        )
    if next_point and next_point.visit_date and visit_date > next_point.visit_date:
        raise HTTPException(
            400,
            f"Visit date cannot be later than the next location date ({next_point.visit_date})",
        )


def _validate_reordered_point_dates(ordered_points: list[TimelinePoint]) -> None:
    for index, point in enumerate(ordered_points):
        prev_point = ordered_points[index - 1] if index > 0 else None
        next_point = ordered_points[index + 1] if index < len(ordered_points) - 1 else None
        if point.visit_date is None:
            continue
        if prev_point and prev_point.visit_date and point.visit_date < prev_point.visit_date:
            raise HTTPException(
                400,
                detail=(
                    f"Cannot move {point.place_name} before {prev_point.place_name}. "
                    f"{point.place_name} is dated {point.visit_date} but the stop above is {prev_point.visit_date}. "
                    f"Edit one of the dates first, or move a different stop."
                ),
            )
        if next_point and next_point.visit_date and point.visit_date > next_point.visit_date:
            raise HTTPException(
                400,
                detail=(
                    f"Cannot move {point.place_name} after {next_point.place_name}. "
                    f"{point.place_name} is dated {point.visit_date} but the stop below is {next_point.visit_date}. "
                    f"Edit one of the dates first, or move a different stop."
                ),
            )


def _point_by_id(points: list[TimelinePoint], point_id: int) -> Optional[TimelinePoint]:
    return next((item for item in points if item.id == point_id), None)


@router.post("/trips/{trip_id}/points", response_model=TimelinePointResponse, status_code=201)
async def add_point(
    trip_id: int,
    data: TimelinePointCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = _get_trip(trip_id, user.id, db)
    _validate_visit_date_in_trip_range(trip, data.visit_date)

    ordered_points = _normalize_trip_sequence_numbers(db, trip_id)
    point_data = data.model_dump(exclude={"travel_method"})
    insert_after_point_id = point_data.pop("insert_after_point_id", None)
    prev = None
    next_point = None
    split_segment = None

    if insert_after_point_id is not None:
        prev = _point_by_id(ordered_points, insert_after_point_id)
        if not prev:
            raise HTTPException(404, "Insert position not found in this trip")
        insert_index = next((index for index, item in enumerate(ordered_points) if item.id == insert_after_point_id), None)
        next_point = ordered_points[insert_index + 1] if insert_index is not None and insert_index < len(ordered_points) - 1 else None
        if next_point:
            split_segment = (
                db.query(TravelSegment)
                .filter(
                    TravelSegment.trip_id == trip_id,
                    TravelSegment.from_point_id == prev.id,
                    TravelSegment.to_point_id == next_point.id,
                )
                .first()
            )
        _validate_edit_point_date(prev, next_point, data.visit_date)
        for point in ordered_points[(insert_index + 1 if insert_index is not None else len(ordered_points)):]:
            point.sequence_no += 1
        point_data["sequence_no"] = (prev.sequence_no or 0) + 1
        db.flush()
    else:
        prev = ordered_points[-1] if ordered_points else None
        _validate_append_point_date(prev, data.visit_date)
        if point_data.get("sequence_no") is None:
            point_data["sequence_no"] = len(ordered_points)

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
    # Auto-create segment from previous point, or inherit the split segment's method when inserting in between.
    incoming_method = data.travel_method or (split_segment.travel_method if split_segment else None)
    incoming_description = split_segment.description if split_segment else None
    if incoming_method and prev:
        db.add(
            TravelSegment(
                trip_id=trip_id,
                from_point_id=prev.id,
                to_point_id=point.id,
                travel_method=incoming_method,
                description=incoming_description,
            )
        )
        if (
            incoming_method == "train"
            and prev.latitude and prev.longitude
            and point.latitude and point.longitude
        ):
            created_train_pairs.append((prev, point))

    if split_segment and next_point:
        outgoing_method = split_segment.travel_method
        outgoing_description = split_segment.description
        db.delete(split_segment)
        db.add(
            TravelSegment(
                trip_id=trip_id,
                from_point_id=point.id,
                to_point_id=next_point.id,
                travel_method=outgoing_method,
                description=outgoing_description,
            )
        )
        if (
            outgoing_method == "train"
            and point.latitude and point.longitude
            and next_point.latitude and next_point.longitude
        ):
            created_train_pairs.append((point, next_point))

    log_audit_event(
        db,
        user=user,
        action="create_point",
        resource_type="timeline_point",
        resource_id=str(point.id),
        details={"trip_id": trip_id, "place_name": point.place_name, "visit_date": point.visit_date.isoformat() if point.visit_date else None},
    )
    db.commit()
    db.refresh(point)

    if trip.journal:
        journal_points = _ordered_trip_points(db, trip_id)
        if sync_trip_journal_media(trip.journal, trip, journal_points):
            db.commit()

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
        provider = get_train_route_provider(
            db,
            from_pt.latitude,
            from_pt.longitude,
            to_pt.latitude,
            to_pt.longitude,
        )
        logger.info(
            "timeline: train segment prefetched trip=%s from=%s to=%s provider=%s",
            trip_id,
            from_pt.place_name,
            to_pt.place_name,
            provider,
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
    points = _normalize_trip_sequence_numbers(db, trip_id)
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


@router.post("/trips/{trip_id}/points/reorder", response_model=List[TimelinePointResponse])
async def reorder_points(
    trip_id: int,
    payload: TimelinePointReorderBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_trip(trip_id, user.id, db)
    points = _normalize_trip_sequence_numbers(db, trip_id)
    if not points:
        raise HTTPException(404, "Trip points not found")

    existing_ids = [point.id for point in points]
    requested_ids = payload.point_ids
    if sorted(existing_ids) != sorted(requested_ids) or len(existing_ids) != len(requested_ids):
        raise HTTPException(400, "Reorder request must include every trip point exactly once")

    point_lookup = {point.id: point for point in points}
    proposed_points = [point_lookup[point_id] for point_id in requested_ids]
    _validate_reordered_point_dates(proposed_points)
    old_incoming_segments = {
        segment.to_point_id: segment
        for segment in db.query(TravelSegment).filter(TravelSegment.trip_id == trip_id).all()
    }
    changed = 0
    for index, point_id in enumerate(requested_ids):
        point = point_lookup[point_id]
        if point.sequence_no != index:
            point.sequence_no = index
            changed += 1

    db.flush()

    db.query(TravelSegment).filter(TravelSegment.trip_id == trip_id).delete(synchronize_session=False)
    created_train_pairs = []
    for index in range(1, len(requested_ids)):
        point_id = requested_ids[index]
        point = point_lookup[point_id]
        prev_point = point_lookup[requested_ids[index - 1]]
        template = old_incoming_segments.get(point_id)
        if not template:
            continue

        db.add(
            TravelSegment(
                trip_id=trip_id,
                from_point_id=prev_point.id,
                to_point_id=point.id,
                travel_method=template.travel_method,
                description=template.description,
            )
        )
        if (
            template.travel_method == "train"
            and prev_point.latitude and prev_point.longitude
            and point.latitude and point.longitude
        ):
            created_train_pairs.append((prev_point, point))

    log_audit_event(
        db,
        user=user,
        action="reorder_points",
        resource_type="trip",
        resource_id=str(trip_id),
        details={"changed_points": changed, "point_ids": requested_ids},
    )
    db.commit()
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
    return [
        point_lookup[point_id]
        for point_id in requested_ids
    ]


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

    original_image_url = point.image_url
    updates = data.model_dump(exclude_unset=True)
    trip = point.trip
    prev_point, next_point = _neighbor_points_for_point(db, point.trip_id, point.id)

    if "visit_date" in updates and updates["visit_date"] is not None:
        _validate_visit_date_in_trip_range(trip, updates["visit_date"])
        _validate_edit_point_date(prev_point, next_point, updates["visit_date"])

    new_lat = updates.get("latitude", point.latitude)
    new_lon = updates.get("longitude", point.longitude)
    if new_lat and new_lon and (new_lat != point.latitude or new_lon != point.longitude):
        visit_date = updates.get("visit_date") or point.visit_date
        updates["weather_data"] = await get_weather(new_lat, new_lon, visit_date)

    for k, v in updates.items():
        setattr(point, k, v)

    log_audit_event(
        db,
        user=user,
        action="update_point",
        resource_type="timeline_point",
        resource_id=str(point.id),
        details={"updated_fields": sorted(updates.keys()), "trip_id": point.trip_id},
    )
    db.commit()
    db.refresh(point)

    if trip.journal:
        journal_points = _ordered_trip_points(db, point.trip_id)
        if sync_trip_journal_media(trip.journal, trip, journal_points):
            db.commit()

    next_image_url = point.image_url
    if (
        original_image_url
        and original_image_url != next_image_url
    ):
        await delete_image(original_image_url)

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
        provider = get_train_route_provider(
            db,
            from_pt.latitude,
            from_pt.longitude,
            to_pt.latitude,
            to_pt.longitude,
        )
        logger.info(
            "timeline: train segment refreshed point=%s from=%s to=%s provider=%s",
            point.id,
            from_pt.place_name,
            to_pt.place_name,
            provider,
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

    trip = point.trip
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
    point_id_value = point.id
    trip_id_value = point.trip_id
    place_name = point.place_name
    visit_date = point.visit_date.isoformat() if point.visit_date else None
    # Delete all segments touching this point before deleting the point
    db.query(TravelSegment).filter(
        (TravelSegment.from_point_id == point_id) | (TravelSegment.to_point_id == point_id)
    ).delete(synchronize_session=False)
    db.delete(point)
    db.flush()
    _normalize_trip_sequence_numbers(db, trip_id_value)
    log_audit_event(
        db,
        user=user,
        action="delete_point",
        resource_type="timeline_point",
        resource_id=str(point_id_value),
        details={"trip_id": trip_id_value, "place_name": place_name, "visit_date": visit_date},
    )
    db.commit()

    if trip and trip.journal:
        remaining_points = _ordered_trip_points(db, trip_id_value)
        if sync_trip_journal_media(trip.journal, trip, remaining_points):
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
        provider = get_train_route_provider(
            db,
            from_pt.latitude,
            from_pt.longitude,
            to_pt.latitude,
            to_pt.longitude,
        )
        logger.info(
            "timeline: train segment bridged trip=%s from=%s to=%s provider=%s",
            trip_id_value,
            from_pt.place_name,
            to_pt.place_name,
            provider,
        )

    if image_url:
        await delete_image(image_url)
