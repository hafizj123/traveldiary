from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
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
from ..services.train_route_service import fetch_and_cache, get_train_route_state

router = APIRouter(tags=["segments"])


def _segment_response_with_route(
    db: Session,
    seg: TravelSegment,
    from_pt: Optional[TimelinePoint] = None,
    to_pt: Optional[TimelinePoint] = None,
):
    payload = TravelSegmentResponse.model_validate(seg).model_dump()
    payload["route_geometry"] = None
    payload["route_status"] = None

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

    geometry, status = get_train_route_state(
        db,
        from_pt.latitude,
        from_pt.longitude,
        to_pt.latitude,
        to_pt.longitude,
    )
    payload["route_geometry"] = geometry
    payload["route_status"] = status
    return payload


def _prefetch_if_train(method: str, from_pt: TimelinePoint, to_pt: TimelinePoint, db: Session):
    """Background task: pre-compute and cache the train route immediately."""
    if method != "train":
        return
    if not (from_pt.latitude and from_pt.longitude and to_pt.latitude and to_pt.longitude):
        return
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(
        fetch_and_cache(
            db,
            from_pt.latitude,
            from_pt.longitude,
            to_pt.latitude,
            to_pt.longitude,
        )
    )


@router.post("/trips/{trip_id}/segments", response_model=TravelSegmentResponse, status_code=201)
def create_segment(
    trip_id: int,
    data: TravelSegmentCreate,
    background_tasks: BackgroundTasks,
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
    db.commit()
    db.refresh(segment)

    background_tasks.add_task(_prefetch_if_train, data.travel_method, from_pt, to_pt, db)

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
def update_segment(
    segment_id: int,
    data: TravelSegmentUpdate,
    background_tasks: BackgroundTasks,
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
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(seg, k, v)
    db.commit()
    db.refresh(seg)

    from_pt = db.query(TimelinePoint).filter(TimelinePoint.id == seg.from_point_id).first()
    to_pt   = db.query(TimelinePoint).filter(TimelinePoint.id == seg.to_point_id).first()
    if from_pt and to_pt:
        background_tasks.add_task(_prefetch_if_train, seg.travel_method, from_pt, to_pt, db)

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
    db.delete(seg)
    db.commit()
