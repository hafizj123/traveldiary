from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..models.trip import Trip
from ..models.trip_journal import TripJournal
from ..models.timeline_point import TimelinePoint
from ..models.travel_segment import TravelSegment
from ..schemas.trip import TripCreate, TripUpdate, TripResponse, ALLOWED_TRIP_VISIBILITY
from ..utils.deps import get_current_user
from ..models.user import User
from ..services.r2_service import delete_image
from ..services.audit_service import log_audit_event
from ..services.trip_share_service import ensure_trip_share_state, get_trip_public_stats, normalize_trip_visibility, regenerate_trip_share_slug, build_public_share_url
from ..services.train_route_service import fetch_and_cache, get_train_route_provider

router = APIRouter(prefix="/trips", tags=["trips"])


def _validate_trip_dates(start_date, end_date) -> None:
    if not start_date:
        raise HTTPException(400, "Start date is required")
    if not end_date:
        raise HTTPException(400, "End date is required")
    if end_date < start_date:
        raise HTTPException(400, "End date must be on or after start date")


def _validate_trip_starting_place(place_name, country, latitude, longitude) -> None:
    if not str(place_name or "").strip():
        raise HTTPException(400, "Starting place is required")
    if not str(country or "").strip():
        raise HTTPException(400, "Starting country is required")
    if latitude is None or longitude is None:
        raise HTTPException(400, "Starting location coordinates are required")


def _normalize_planned_countries(planned_countries, starting_country: Optional[str]) -> list[str]:
    values = list(planned_countries or [])
    if starting_country:
        values.append(starting_country)

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value or "").strip().split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def _validate_trip_visibility(value: Optional[str]) -> str:
    raw = " ".join(str(value or "private").strip().lower().split())
    if raw not in ALLOWED_TRIP_VISIBILITY:
        raise HTTPException(400, "Invalid trip visibility")
    return normalize_trip_visibility(raw)


def _trip_share_payload(db: Session, trip: Trip) -> dict:
    public_stats = get_trip_public_stats(db=db, trip_id=trip.id)
    journal = db.query(TripJournal).filter(TripJournal.trip_id == trip.id).first()
    return {
        "share_slug": trip.share_slug,
        "share_url": build_public_share_url(trip.share_slug),
        "public_stats": public_stats,
        "journal_exists": bool(journal),
        "journal_updated_at": journal.updated_at if journal else None,
    }


def _first_trip_point(db: Session, trip_id: int) -> Optional[TimelinePoint]:
    return (
        db.query(TimelinePoint)
        .filter(TimelinePoint.trip_id == trip_id)
        .order_by(TimelinePoint.sequence_no, TimelinePoint.id)
        .first()
    )


@router.post("", response_model=TripResponse, status_code=201)
def create_trip(
    data: TripCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate_trip_dates(data.start_date, data.end_date)
    _validate_trip_starting_place(
        data.starting_place_name,
        data.starting_country,
        data.starting_latitude,
        data.starting_longitude,
    )
    planned_countries = _normalize_planned_countries(data.planned_countries, data.starting_country)
    if not planned_countries:
        raise HTTPException(400, "At least one planned country is required")

    trip_payload = data.model_dump()
    trip_payload["planned_countries"] = planned_countries
    trip_payload["visibility"] = _validate_trip_visibility(data.visibility)
    trip = Trip(**trip_payload, user_id=user.id)
    ensure_trip_share_state(trip)
    db.add(trip)
    db.flush()

    db.add(
        TimelinePoint(
            trip_id=trip.id,
            country=data.starting_country.strip(),
            city=(data.starting_city or "").strip() or None,
            place_name=data.starting_place_name.strip(),
            description=None,
            visit_date=data.start_date,
            latitude=data.starting_latitude,
            longitude=data.starting_longitude,
            image_url=None,
            sequence_no=0,
            weather_data=None,
        )
    )
    log_audit_event(
        db,
        user=user,
        action="create_trip",
        resource_type="trip",
        resource_id=str(trip.id),
        details={"title": trip.title, "starting_country": trip.starting_country},
    )
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
        **_trip_share_payload(db, trip),
        "owner_username": user.username,
        "stats": {
            "total_points": len(points),
            "total_countries": len(countries),
            "total_photos": sum(1 for p in points if p.image_url),
            "countries": countries,
        },
    }


@router.put("/{trip_id}", response_model=TripResponse)
async def update_trip(
    trip_id: int,
    data: TripUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")
    updates = data.model_dump(exclude_unset=True)
    next_start_date = updates.get("start_date", trip.start_date)
    next_end_date = updates.get("end_date", trip.end_date)
    _validate_trip_dates(next_start_date, next_end_date)
    next_place_name = updates.get("starting_place_name", trip.starting_place_name)
    next_country = updates.get("starting_country", trip.starting_country)
    next_latitude = updates.get("starting_latitude", trip.starting_latitude)
    next_longitude = updates.get("starting_longitude", trip.starting_longitude)
    _validate_trip_starting_place(next_place_name, next_country, next_latitude, next_longitude)
    if "planned_countries" in updates:
        updates["planned_countries"] = _normalize_planned_countries(updates.get("planned_countries"), next_country)
        if not updates["planned_countries"]:
            raise HTTPException(400, "At least one planned country is required")
    if "visibility" in updates:
        updates["visibility"] = _validate_trip_visibility(updates["visibility"])

    first_point = _first_trip_point(db, trip.id)
    should_refresh_first_train_segment = False
    if first_point:
        old_train_anchor = (
            first_point.latitude,
            first_point.longitude,
            (first_point.country or "").strip(),
        )

    for k, v in updates.items():
        setattr(trip, k, v)
    ensure_trip_share_state(trip)

    if first_point:
        first_point.place_name = str(next_place_name).strip()
        first_point.country = str(next_country).strip()
        first_point.city = " ".join(str(updates.get("starting_city", trip.starting_city) or "").strip().split()) or None
        first_point.latitude = next_latitude
        first_point.longitude = next_longitude
        first_point.visit_date = next_start_date
        new_train_anchor = (
            first_point.latitude,
            first_point.longitude,
            (first_point.country or "").strip(),
        )
        should_refresh_first_train_segment = old_train_anchor != new_train_anchor

    log_audit_event(
        db,
        user=user,
        action="update_trip",
        resource_type="trip",
        resource_id=str(trip.id),
        details={"updated_fields": sorted(updates.keys())},
    )
    db.commit()
    db.refresh(trip)

    if should_refresh_first_train_segment and first_point:
        outgoing_train_segment = (
            db.query(TravelSegment)
            .filter(
                TravelSegment.trip_id == trip.id,
                TravelSegment.from_point_id == first_point.id,
                TravelSegment.travel_method == "train",
            )
            .first()
        )
        if outgoing_train_segment:
            to_point = outgoing_train_segment.to_point
            if (
                to_point
                and first_point.latitude and first_point.longitude
                and to_point.latitude and to_point.longitude
            ):
                await fetch_and_cache(
                    db,
                    first_point.latitude,
                    first_point.longitude,
                    to_point.latitude,
                    to_point.longitude,
                    first_point.country,
                    to_point.country,
                )
                get_train_route_provider(
                    db,
                    first_point.latitude,
                    first_point.longitude,
                    to_point.latitude,
                    to_point.longitude,
                    first_point.country,
                    to_point.country,
                )
    return trip


@router.post("/{trip_id}/share/regenerate")
def regenerate_trip_share(
    trip_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")
    if normalize_trip_visibility(trip.visibility) == "private":
        raise HTTPException(400, "Set trip visibility to Unlisted or Public before generating a share link")

    regenerate_trip_share_slug(db, trip)
    log_audit_event(
        db,
        user=user,
        action="regenerate_trip_share_link",
        resource_type="trip",
        resource_id=str(trip.id),
        details={"visibility": trip.visibility},
    )
    db.commit()
    db.refresh(trip)
    return {
        **TripResponse.model_validate(trip).model_dump(),
        **_trip_share_payload(db, trip),
    }


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

    log_audit_event(
        db,
        user=user,
        action="delete_trip",
        resource_type="trip",
        resource_id=str(trip.id),
        details={"title": trip.title},
    )
    db.delete(trip)
    db.commit()

    # Delete from R2 after DB commit (best-effort)
    for url in urls_to_delete:
        await delete_image(url)
