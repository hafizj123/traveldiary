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

router = APIRouter(prefix="/u", tags=["public"])


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
        "segments": [TravelSegmentResponse.model_validate(s).model_dump() for s in segments],
    }
