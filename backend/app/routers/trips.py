from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..models.trip import Trip
from ..models.timeline_point import TimelinePoint
from ..schemas.trip import TripCreate, TripUpdate, TripResponse
from ..utils.deps import get_current_user
from ..models.user import User
from ..services.r2_service import delete_image

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post("", response_model=TripResponse, status_code=201)
def create_trip(
    data: TripCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = Trip(**data.model_dump(), user_id=user.id)
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


@router.get("", response_model=List[TripResponse])
def list_trips(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (
        db.query(Trip)
        .filter(Trip.user_id == user.id)
        .order_by(Trip.created_at.desc())
        .all()
    )


@router.get("/{trip_id}")
def get_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")

    points = db.query(TimelinePoint).filter(TimelinePoint.trip_id == trip_id).all()
    countries = list({p.country for p in points})

    return {
        **TripResponse.model_validate(trip).model_dump(),
        "stats": {
            "total_points": len(points),
            "total_countries": len(countries),
            "total_photos": sum(1 for p in points if p.image_url),
            "countries": countries,
        },
    }


@router.put("/{trip_id}", response_model=TripResponse)
def update_trip(
    trip_id: int,
    data: TripUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(trip, k, v)
    db.commit()
    db.refresh(trip)
    return trip


@router.delete("/{trip_id}", status_code=204)
async def delete_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")

    # Collect all R2 URLs before deleting DB rows
    urls_to_delete = []
    if trip.cover_image_url:
        urls_to_delete.append(trip.cover_image_url)
    points = db.query(TimelinePoint).filter(TimelinePoint.trip_id == trip_id).all()
    for pt in points:
        if pt.image_url:
            urls_to_delete.append(pt.image_url)

    db.delete(trip)
    db.commit()

    # Delete from R2 after DB commit (best-effort)
    for url in urls_to_delete:
        await delete_image(url)
