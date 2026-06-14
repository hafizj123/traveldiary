from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.timeline_point import TimelinePoint
from ..models.travel_segment import TravelSegment
from ..models.trip import Trip
from ..models.trip_journal import TripJournal
from ..models.user import User
from ..schemas.journal import TripJournalGenerateRequest, TripJournalResponse, TripJournalUpdateRequest
from ..services.audit_service import log_audit_event
from ..services.journal_service import sync_trip_journal_media, upsert_trip_journal
from ..utils.deps import get_current_user

router = APIRouter(prefix="/trips", tags=["journals"])


def _get_trip_for_user(db: Session, trip_id: int, user_id: int) -> Trip:
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


def _get_trip_journal(db: Session, trip_id: int) -> TripJournal:
    journal = db.query(TripJournal).filter(TripJournal.trip_id == trip_id).first()
    if not journal:
        raise HTTPException(status_code=404, detail="Travel journal not found")
    return journal


def _trip_points(db: Session, trip_id: int):
    return (
        db.query(TimelinePoint)
        .filter(TimelinePoint.trip_id == trip_id)
        .order_by(TimelinePoint.visit_date, TimelinePoint.sequence_no, TimelinePoint.id)
        .all()
    )


def _trip_segments(db: Session, trip_id: int):
    return db.query(TravelSegment).filter(TravelSegment.trip_id == trip_id).all()


@router.get("/{trip_id}/journal", response_model=TripJournalResponse)
def get_trip_journal(
    trip_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = _get_trip_for_user(db, trip_id, user.id)
    journal = _get_trip_journal(db, trip_id)
    if sync_trip_journal_media(journal, trip, _trip_points(db, trip_id)):
        db.commit()
        db.refresh(journal)
    return journal


@router.post("/{trip_id}/journal/generate", response_model=TripJournalResponse)
async def generate_trip_journal(
    trip_id: int,
    data: TripJournalGenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = _get_trip_for_user(db, trip_id, user.id)
    points = _trip_points(db, trip_id)
    if not points:
        raise HTTPException(status_code=400, detail="Add at least one trip location before generating a journal")
    journal = await upsert_trip_journal(
        db,
        trip,
        points,
        _trip_segments(db, trip_id),
        data.tone,
        data.length_mode,
        use_ai=data.use_ai,
        template_key=data.template_key,
    )
    log_audit_event(
        db,
        user=user,
        action="generate_trip_journal",
        resource_type="trip",
        resource_id=str(trip.id),
        details={"tone": data.tone, "length_mode": data.length_mode, "use_ai": data.use_ai, "template_key": data.template_key},
    )
    db.commit()
    db.refresh(journal)
    return journal


@router.put("/{trip_id}/journal", response_model=TripJournalResponse)
def update_trip_journal(
    trip_id: int,
    data: TripJournalUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    trip = _get_trip_for_user(db, trip_id, user.id)
    journal = _get_trip_journal(db, trip_id)
    journal.title = data.title
    journal.intro_text = data.intro_text
    journal.closing_text = data.closing_text
    journal.tone = data.tone
    journal.length_mode = data.length_mode
    journal.content_json = data.content_json
    log_audit_event(
        db,
        user=user,
        action="update_trip_journal",
        resource_type="trip",
        resource_id=str(trip.id),
        details={"chapter_count": len((data.content_json or {}).get("chapters", []))},
    )
    db.commit()
    db.refresh(journal)
    return journal
