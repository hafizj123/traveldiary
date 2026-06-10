from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from ..models.trip import Trip
from ..models.timeline_point import TimelinePoint
from ..models.travel_segment import TravelSegment
from ..schemas.trip import TripResponse
from ..schemas.timeline_point import TimelinePointResponse
from ..schemas.travel_segment import TravelSegmentResponse
from ..services.train_route_service import get_train_route_provider, get_train_route_state

router = APIRouter(prefix="/u", tags=["public"])


def _public_segment_response(db: Session, seg: TravelSegment):
    payload = TravelSegmentResponse.model_validate(seg).model_dump()
    payload["route_geometry"] = None
    payload["route_status"] = None
    payload["route_provider"] = None
    payload["route_anchor_start"] = None
    payload["route_anchor_end"] = None

    if seg.travel_method != "train":
        return payload
    from_pt = seg.from_point
    to_pt = seg.to_point
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
    )
    payload["route_geometry"] = geometry
    payload["route_status"] = status
    payload["route_provider"] = get_train_route_provider(
        db,
        from_pt.latitude,
        from_pt.longitude,
        to_pt.latitude,
        to_pt.longitude,
    )
    payload["route_anchor_start"] = anchor_start
    payload["route_anchor_end"] = anchor_end
    return payload


@router.get("/{username}")
def public_profile(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(404, "User not found")

    trips = (
        db.query(Trip)
        .filter(Trip.user_id == user.id, Trip.visibility == "public")
        .order_by(Trip.created_at.desc())
        .all()
    )

    return {
        "username": user.username,
        "trips": [TripResponse.model_validate(t).model_dump() for t in trips],
    }


@router.get("/{username}/trips/{trip_id}")
def public_trip(username: str, trip_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(404, "User not found")

    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.user_id == user.id,
        Trip.visibility == "public",
    ).first()
    if not trip:
        raise HTTPException(404, "Trip not found or not public")

    points = (
        db.query(TimelinePoint)
        .filter(TimelinePoint.trip_id == trip_id)
        .order_by(TimelinePoint.sequence_no)
        .all()
    )
    segments = db.query(TravelSegment).filter(TravelSegment.trip_id == trip_id).all()

    return {
        "owner": username,
        "trip": TripResponse.model_validate(trip).model_dump(),
        "points": [TimelinePointResponse.model_validate(p).model_dump() for p in points],
        "segments": [_public_segment_response(db, s) for s in segments],
    }
