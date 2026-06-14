from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models.user import User
from ..models.trip import Trip
from ..models.trip_journal import TripJournal
from ..models.trip_public_view import TripPublicView
from ..models.timeline_point import TimelinePoint
from ..models.travel_segment import TravelSegment
from ..schemas.trip import TripResponse
from ..schemas.timeline_point import TimelinePointResponse
from ..schemas.travel_segment import TravelSegmentResponse
from ..services.journal_service import sync_trip_journal_media
from ..services.train_route_service import get_train_route_provider, get_train_route_state
from ..services.trip_share_service import get_trip_public_stats, record_trip_public_view, build_public_share_url

router = APIRouter(tags=["public"])


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
    return payload


@router.get("/u/{username}")
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
        "trips": [
            {
                **TripResponse.model_validate(t).model_dump(),
                "share_url": build_public_share_url(t.share_slug),
                "public_stats": get_trip_public_stats(db, t.id),
                "journal_exists": db.query(TripJournal.id).filter(TripJournal.trip_id == t.id).first() is not None,
            }
            for t in trips
        ],
    }


@router.get("/u/{username}/trips/{trip_id}")
def public_trip(username: str, trip_id: int, request: Request, db: Session = Depends(get_db)):
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

    record_trip_public_view(db, trip, request)
    points = (
        db.query(TimelinePoint)
        .filter(TimelinePoint.trip_id == trip_id)
        .order_by(TimelinePoint.sequence_no)
        .all()
    )
    segments = db.query(TravelSegment).filter(TravelSegment.trip_id == trip_id).all()
    db.commit()
    db.refresh(trip)

    return {
        "owner": username,
        "trip": {
            **TripResponse.model_validate(trip).model_dump(),
            "share_url": build_public_share_url(trip.share_slug),
            "public_stats": get_trip_public_stats(db, trip.id),
            "journal_exists": db.query(TripJournal.id).filter(TripJournal.trip_id == trip.id).first() is not None,
        },
        "points": [TimelinePointResponse.model_validate(p).model_dump() for p in points],
        "segments": [_public_segment_response(db, s) for s in segments],
    }


@router.get("/shared-trips")
def shared_trips(
    db: Session = Depends(get_db),
    sort: str = Query(default="popular"),
    limit: int = Query(default=24, ge=1, le=60),
):
    normalized_sort = " ".join(str(sort or "popular").strip().lower().split())
    base_query = (
        db.query(Trip, User.username.label("owner_username"), func.count(TripPublicView.id).label("view_count"))
        .join(User, Trip.user_id == User.id)
        .outerjoin(TripPublicView, TripPublicView.trip_id == Trip.id)
        .filter(Trip.visibility == "public", Trip.share_slug.isnot(None))
        .group_by(Trip.id, User.username)
    )
    if normalized_sort == "recent":
        rows = base_query.order_by(func.coalesce(Trip.shared_at, Trip.created_at).desc(), Trip.created_at.desc()).limit(limit).all()
    else:
        rows = base_query.order_by(func.count(TripPublicView.id).desc(), func.coalesce(Trip.shared_at, Trip.created_at).desc(), Trip.created_at.desc()).limit(limit).all()

    items = []
    for trip, owner_username, view_count in rows:
        items.append({
            **TripResponse.model_validate(trip).model_dump(),
            "owner_username": owner_username,
            "share_url": build_public_share_url(trip.share_slug),
            "public_stats": {
                **get_trip_public_stats(db, trip.id),
                "unique_views_total": int(view_count or 0),
            },
        })
    return {"items": items, "sort": normalized_sort}


@router.get("/shared/{share_slug}")
def shared_trip(share_slug: str, request: Request, db: Session = Depends(get_db)):
    trip = (
        db.query(Trip)
        .join(User, Trip.user_id == User.id)
        .filter(
            Trip.share_slug == share_slug,
            Trip.visibility.in_(["unlisted", "public"]),
        )
        .first()
    )
    if not trip:
        raise HTTPException(404, "Shared trip not found")

    record_trip_public_view(db, trip, request)
    points = (
        db.query(TimelinePoint)
        .filter(TimelinePoint.trip_id == trip.id)
        .order_by(TimelinePoint.sequence_no)
        .all()
    )
    segments = db.query(TravelSegment).filter(TravelSegment.trip_id == trip.id).all()
    db.commit()
    db.refresh(trip)

    owner = db.query(User).filter(User.id == trip.user_id).first()
    return {
        "owner": owner.username if owner else "",
        "trip": {
            **TripResponse.model_validate(trip).model_dump(),
            "share_url": build_public_share_url(trip.share_slug),
            "public_stats": get_trip_public_stats(db, trip.id),
            "journal_exists": db.query(TripJournal.id).filter(TripJournal.trip_id == trip.id).first() is not None,
        },
        "points": [TimelinePointResponse.model_validate(p).model_dump() for p in points],
        "segments": [_public_segment_response(db, s) for s in segments],
    }


@router.get("/shared/{share_slug}/journal")
def shared_trip_journal(share_slug: str, db: Session = Depends(get_db)):
    trip = (
        db.query(Trip)
        .filter(
            Trip.share_slug == share_slug,
            Trip.visibility.in_(["unlisted", "public"]),
        )
        .first()
    )
    if not trip:
        raise HTTPException(status_code=404, detail="Shared trip not found")

    journal = db.query(TripJournal).filter(TripJournal.trip_id == trip.id).first()
    if not journal:
        raise HTTPException(status_code=404, detail="Travel journal not found")

    owner = db.query(User).filter(User.id == trip.user_id).first()
    return {
        "owner": owner.username if owner else "",
        "trip": {
            **TripResponse.model_validate(trip).model_dump(),
            "share_url": build_public_share_url(trip.share_slug),
            "public_stats": get_trip_public_stats(db, trip.id),
        },
        "journal": {
            "id": journal.id,
            "trip_id": journal.trip_id,
            "title": journal.title,
            "intro_text": journal.intro_text,
            "closing_text": journal.closing_text,
            "tone": journal.tone,
            "length_mode": journal.length_mode,
            "content_json": journal.content_json,
            "created_at": journal.created_at,
            "updated_at": journal.updated_at,
        },
    }
@router.get("/u/{username}/trips/{trip_id}/journal")
def public_trip_journal(username: str, trip_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.user_id == user.id,
        Trip.visibility == "public",
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found or not public")
    journal = db.query(TripJournal).filter(TripJournal.trip_id == trip.id).first()
    if not journal:
        raise HTTPException(status_code=404, detail="Travel journal not found")
    return {
        "owner": username,
        "trip": {
            **TripResponse.model_validate(trip).model_dump(),
            "share_url": build_public_share_url(trip.share_slug),
            "public_stats": get_trip_public_stats(db, trip.id),
        },
        "journal": {
            "id": journal.id,
            "trip_id": journal.trip_id,
            "title": journal.title,
            "intro_text": journal.intro_text,
            "closing_text": journal.closing_text,
            "tone": journal.tone,
            "length_mode": journal.length_mode,
            "content_json": journal.content_json,
            "created_at": journal.created_at,
            "updated_at": journal.updated_at,
        },
    }
