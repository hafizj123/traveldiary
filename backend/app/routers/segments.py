import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..models.trip import Trip
from ..models.timeline_point import TimelinePoint
from ..models.travel_segment import TravelSegment
from ..schemas.travel_segment import (
    TravelSegmentCreate,
    TravelSegmentUpdate,
    TravelSegmentResponse,
)
from ..utils.deps import get_current_user
from ..models.user import User
from ..services.audit_service import log_audit_event
from ..services.train_route_service import fetch_and_cache, get_train_route_provider, get_train_route_state

router = APIRouter(tags=["segments"])
logger = logging.getLogger(__name__)


def _prune_stale_segments_for_trip(db: Session, trip_id: int) -> None:
    ordered_points = (
        db.query(TimelinePoint)
        .filter(TimelinePoint.trip_id == trip_id)
        .order_by(TimelinePoint.sequence_no, TimelinePoint.id)
        .all()
    )
    valid_pairs = {
        (ordered_points[index].id, ordered_points[index + 1].id)
        for index in range(len(ordered_points) - 1)
    }
    if not valid_pairs:
        return

    segments = db.query(TravelSegment).filter(TravelSegment.trip_id == trip_id).all()
    stale_segments = [seg for seg in segments if (seg.from_point_id, seg.to_point_id) not in valid_pairs]
    if not stale_segments:
        return

    for seg in stale_segments:
        logger.info(
            "segments: pruning stale segment id=%s trip=%s from=%s to=%s method=%s",
            seg.id,
            trip_id,
            seg.from_point_id,
            seg.to_point_id,
            seg.travel_method,
        )
        db.delete(seg)
    db.commit()


def _segment_response_with_route(
    db: Session,
    seg: TravelSegment,
    from_pt: Optional[TimelinePoint] = None,
    to_pt: Optional[TimelinePoint] = None,
):
    payload = TravelSegmentResponse.model_validate(seg).model_dump()
    payload["route_geometry"] = None
    payload["route_status"] = None
    payload["route_provider"] = None
    payload["route_anchor_start"] = None
    payload["route_anchor_end"] = None

    if seg.travel_method != "train":
        return payload

    if not from_pt:
        from_pt = db.query(TimelinePoint).filter(TimelinePoint.id == seg.from_point_id).first()
    if not to_pt:
        to_pt = db.query(TimelinePoint).filter(TimelinePoint.id == seg.to_point_id).first()
    if not from_pt or not to_pt:
        payload["route_status"] = "pending"
        return payload
    if not (from_pt.latitude and from_pt.longitude and to_pt.latitude and to_pt.longitude):
        payload["route_status"] = "pending"
        return payload

    geometry, status, anchor_start, anchor_end = get_train_route_state(
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
        from_pt.country,
        to_pt.country,
    )
    payload["route_geometry"] = geometry
    payload["route_status"] = status
    payload["route_provider"] = provider
    payload["route_anchor_start"] = anchor_start
    payload["route_anchor_end"] = anchor_end
    logger.info(
        "segments: %s response seg=%s trip=%s from=(%s,%s) to=(%s,%s) status=%s provider=%s geometry_points=%s",
        "train",
        seg.id,
        seg.trip_id,
        from_pt.latitude,
        from_pt.longitude,
        to_pt.latitude,
        to_pt.longitude,
        status,
        payload["route_provider"],
        len(geometry or []),
    )
    return payload


async def _prefetch_route_if_needed(method: str, from_pt: TimelinePoint, to_pt: TimelinePoint, db: Session):
    """Pre-compute and cache routed transport geometry before responding."""
    if method != "train":
        return
    if not (from_pt.latitude and from_pt.longitude and to_pt.latitude and to_pt.longitude):
        return
    await fetch_and_cache(
        db,
        from_pt.latitude,
        from_pt.longitude,
        to_pt.latitude,
        to_pt.longitude,
        from_pt.country,
        to_pt.country,
    )


@router.post("/trips/{trip_id}/segments", response_model=TravelSegmentResponse, status_code=201)
async def create_segment(
    trip_id: int,
    data: TravelSegmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")

    from_pt = db.query(TimelinePoint).filter(
        TimelinePoint.id == data.from_point_id, TimelinePoint.trip_id == trip_id
    ).first()
    to_pt = db.query(TimelinePoint).filter(
        TimelinePoint.id == data.to_point_id, TimelinePoint.trip_id == trip_id
    ).first()
    if not from_pt or not to_pt:
        raise HTTPException(404, "One or both timeline points not found in this trip")

    segment = TravelSegment(**data.model_dump(), trip_id=trip_id)
    db.add(segment)
    db.flush()
    log_audit_event(
        db,
        user=user,
        action="create_segment",
        resource_type="travel_segment",
        resource_id=str(segment.id),
        details={
            "trip_id": trip_id,
            "from_point_id": segment.from_point_id,
            "to_point_id": segment.to_point_id,
            "travel_method": segment.travel_method,
        },
    )
    db.commit()
    db.refresh(segment)

    await _prefetch_route_if_needed(data.travel_method, from_pt, to_pt, db)

    return _segment_response_with_route(db, segment, from_pt, to_pt)


@router.get("/trips/{trip_id}/segments", response_model=List[TravelSegmentResponse])
def list_segments(
    trip_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")
    _prune_stale_segments_for_trip(db, trip_id)
    points = {
        p.id: p
        for p in db.query(TimelinePoint).filter(TimelinePoint.trip_id == trip_id).all()
    }
    segments = db.query(TravelSegment).filter(TravelSegment.trip_id == trip_id).all()
    return [
        _segment_response_with_route(db, seg, points.get(seg.from_point_id), points.get(seg.to_point_id))
        for seg in segments
    ]


@router.put("/segments/{segment_id}", response_model=TravelSegmentResponse)
async def update_segment(
    segment_id: int,
    data: TravelSegmentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    seg = (
        db.query(TravelSegment)
        .join(Trip)
        .filter(TravelSegment.id == segment_id, Trip.user_id == user.id)
        .first()
    )
    if not seg:
        raise HTTPException(404, "Segment not found")
    updates = data.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(seg, k, v)
    log_audit_event(
        db,
        user=user,
        action="update_segment",
        resource_type="travel_segment",
        resource_id=str(seg.id),
        details={"updated_fields": sorted(updates.keys()), "trip_id": seg.trip_id},
    )
    db.commit()
    db.refresh(seg)

    from_pt = db.query(TimelinePoint).filter(TimelinePoint.id == seg.from_point_id).first()
    to_pt   = db.query(TimelinePoint).filter(TimelinePoint.id == seg.to_point_id).first()
    if from_pt and to_pt:
        await _prefetch_route_if_needed(seg.travel_method, from_pt, to_pt, db)

    return _segment_response_with_route(db, seg, from_pt, to_pt)


@router.delete("/segments/{segment_id}", status_code=204)
def delete_segment(
    segment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    seg = (
        db.query(TravelSegment)
        .join(Trip)
        .filter(TravelSegment.id == segment_id, Trip.user_id == user.id)
        .first()
    )
    if not seg:
        raise HTTPException(404, "Segment not found")
    segment_id_value = seg.id
    trip_id_value = seg.trip_id
    method_value = seg.travel_method
    from_point_id = seg.from_point_id
    to_point_id = seg.to_point_id
    db.delete(seg)
    log_audit_event(
        db,
        user=user,
        action="delete_segment",
        resource_type="travel_segment",
        resource_id=str(segment_id_value),
        details={
            "trip_id": trip_id_value,
            "travel_method": method_value,
            "from_point_id": from_point_id,
            "to_point_id": to_point_id,
        },
    )
    db.commit()
