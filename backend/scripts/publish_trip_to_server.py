import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, selectinload, sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import dotenv_values

from app.database import SessionLocal
from app.models.route_cache import RouteCache
from app.models.timeline_point import TimelinePoint
from app.models.travel_segment import TravelSegment
from app.models.trip import Trip
from app.models.trip_journal import TripJournal
from app.models.user import User
from app.services.train_route_service import make_cache_key


SCRIPT_DIR = Path(__file__).resolve().parent
SYNC_MAP_PATH = SCRIPT_DIR.parent / ".trip_sync_map.json"
PUBLISH_ENV_PATH = SCRIPT_DIR.parent / ".publish.env"


def _load_sync_map() -> dict[str, Any]:
    if not SYNC_MAP_PATH.exists():
        return {}
    try:
        payload = json.loads(SYNC_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_sync_map(payload: dict[str, Any]) -> None:
    SYNC_MAP_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_publish_defaults() -> dict[str, str]:
    if not PUBLISH_ENV_PATH.exists():
        return {}
    return {
        str(key): str(value)
        for key, value in dotenv_values(PUBLISH_ENV_PATH).items()
        if key and value is not None
    }


def _copy_model_columns(source: Any, target: Any, *, exclude: set[str]) -> None:
    for column in source.__table__.columns:
        if column.name in exclude:
            continue
        setattr(target, column.name, getattr(source, column.name))


def _target_session_factory(target_url: str):
    engine = create_engine(
        target_url,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _load_source_trip(db: Session, trip_id: int) -> Optional[Trip]:
    return (
        db.query(Trip)
        .options(
            selectinload(Trip.points),
            selectinload(Trip.segments),
            selectinload(Trip.journal),
            selectinload(Trip.user),
        )
        .filter(Trip.id == trip_id)
        .first()
    )


def _find_target_trip(
    db: Session,
    *,
    target_user_id: int,
    target_name: str,
    local_trip_id: int,
    share_slug: Optional[str],
) -> Optional[Trip]:
    sync_map = _load_sync_map()
    mapped_trip_id = (
        (((sync_map.get("targets") or {}).get(target_name) or {}).get("trip_ids") or {}).get(str(local_trip_id))
    )
    if mapped_trip_id:
        trip = db.query(Trip).filter(Trip.id == int(mapped_trip_id), Trip.user_id == target_user_id).first()
        if trip:
            return trip

    if share_slug:
        trip = db.query(Trip).filter(Trip.share_slug == share_slug, Trip.user_id == target_user_id).first()
        if trip:
            return trip

    return db.query(Trip).filter(Trip.id == local_trip_id, Trip.user_id == target_user_id).first()


def _remember_trip_mapping(target_name: str, local_trip_id: int, server_trip_id: int) -> None:
    sync_map = _load_sync_map()
    targets = sync_map.setdefault("targets", {})
    target_entry = targets.setdefault(target_name, {})
    trip_ids = target_entry.setdefault("trip_ids", {})
    trip_ids[str(local_trip_id)] = int(server_trip_id)
    _save_sync_map(sync_map)


def _collect_route_cache_keys(source_trip: Trip, db: Session) -> set[str]:
    keys: set[str] = set()
    point_by_id = {point.id: point for point in source_trip.points}

    for segment in source_trip.segments:
        if (segment.travel_method or "").strip().lower() != "train":
            continue
        from_point = point_by_id.get(segment.from_point_id)
        to_point = point_by_id.get(segment.to_point_id)
        if not from_point or not to_point:
            continue
        if None in (from_point.latitude, from_point.longitude, to_point.latitude, to_point.longitude):
            continue
        exact_key = make_cache_key(
            float(from_point.latitude),
            float(from_point.longitude),
            float(to_point.latitude),
            float(to_point.longitude),
        )
        keys.add(exact_key)

    if not keys:
        return keys

    source_rows = db.query(RouteCache).filter(RouteCache.cache_key.in_(sorted(keys))).all()
    for row in source_rows:
        try:
            payload = json.loads(row.geometry_json or "{}")
        except Exception:
            continue
        anchor_start = payload.get("anchor_start") if isinstance(payload, dict) else None
        anchor_end = payload.get("anchor_end") if isinstance(payload, dict) else None
        if (
            isinstance(anchor_start, list)
            and len(anchor_start) >= 2
            and isinstance(anchor_end, list)
            and len(anchor_end) >= 2
        ):
            station_key = make_cache_key(
                float(anchor_start[0]),
                float(anchor_start[1]),
                float(anchor_end[0]),
                float(anchor_end[1]),
            )
            keys.add(station_key)

    return keys


def _upsert_route_cache_rows(source_db: Session, target_db: Session, cache_keys: set[str]) -> int:
    if not cache_keys:
        return 0
    copied = 0
    source_rows = source_db.query(RouteCache).filter(RouteCache.cache_key.in_(sorted(cache_keys))).all()
    for source_row in source_rows:
        target_row = target_db.query(RouteCache).filter(RouteCache.cache_key == source_row.cache_key).first()
        if target_row is None:
            target_row = RouteCache(cache_key=source_row.cache_key)
            target_db.add(target_row)
        _copy_model_columns(source_row, target_row, exclude={"id", "cache_key"})
        copied += 1
    return copied


def publish_trip(
    *,
    trip_id: int,
    target_url: str,
    target_name: str,
    target_user_email: Optional[str],
    dry_run: bool,
) -> dict[str, Any]:
    source_db = SessionLocal()
    TargetSession = _target_session_factory(target_url)
    target_db = TargetSession()
    try:
        source_trip = _load_source_trip(source_db, trip_id)
        if source_trip is None:
            raise ValueError(f"Trip {trip_id} was not found in the local database.")
        if source_trip.user is None:
            raise ValueError(f"Trip {trip_id} has no owning user.")

        source_user_email = (source_trip.user.email or "").strip().lower()
        destination_email = (target_user_email or source_user_email).strip().lower()
        if not destination_email:
            raise ValueError("Target user email could not be determined.")

        target_user = target_db.query(User).filter(User.email == destination_email).first()
        if target_user is None:
            raise ValueError(
                f"Target user '{destination_email}' was not found on the server database."
            )

        target_trip = _find_target_trip(
            target_db,
            target_user_id=target_user.id,
            target_name=target_name,
            local_trip_id=source_trip.id,
            share_slug=source_trip.share_slug,
        )
        created = target_trip is None
        if created:
            target_trip = Trip(user_id=target_user.id)
            target_db.add(target_trip)

        assert target_trip is not None
        _copy_model_columns(source_trip, target_trip, exclude={"id", "user_id"})
        target_trip.user_id = target_user.id
        target_db.flush()

        target_db.execute(delete(TravelSegment).where(TravelSegment.trip_id == target_trip.id))
        target_db.execute(delete(TripJournal).where(TripJournal.trip_id == target_trip.id))
        target_db.execute(delete(TimelinePoint).where(TimelinePoint.trip_id == target_trip.id))
        target_db.flush()

        point_id_map: dict[int, int] = {}
        copied_points = 0
        for source_point in sorted(source_trip.points, key=lambda row: (row.sequence_no, row.id)):
            target_point = TimelinePoint(trip_id=target_trip.id)
            _copy_model_columns(source_point, target_point, exclude={"id", "trip_id"})
            target_db.add(target_point)
            target_db.flush()
            point_id_map[source_point.id] = target_point.id
            copied_points += 1

        copied_segments = 0
        for source_segment in source_trip.segments:
            mapped_from_id = point_id_map.get(source_segment.from_point_id)
            mapped_to_id = point_id_map.get(source_segment.to_point_id)
            if not mapped_from_id or not mapped_to_id:
                continue
            target_segment = TravelSegment(
                trip_id=target_trip.id,
                from_point_id=mapped_from_id,
                to_point_id=mapped_to_id,
            )
            _copy_model_columns(
                source_segment,
                target_segment,
                exclude={"id", "trip_id", "from_point_id", "to_point_id"},
            )
            target_db.add(target_segment)
            copied_segments += 1

        copied_journal = 0
        if source_trip.journal is not None:
            target_journal = TripJournal(trip_id=target_trip.id)
            _copy_model_columns(source_trip.journal, target_journal, exclude={"id", "trip_id"})
            target_db.add(target_journal)
            copied_journal = 1

        route_cache_keys = _collect_route_cache_keys(source_trip, source_db)
        copied_route_cache = _upsert_route_cache_rows(source_db, target_db, route_cache_keys)

        if dry_run:
            target_db.rollback()
        else:
            target_db.commit()
            _remember_trip_mapping(target_name, source_trip.id, target_trip.id)

        return {
            "trip_id": source_trip.id,
            "server_trip_id": target_trip.id,
            "target_name": target_name,
            "target_user_email": destination_email,
            "created_server_trip": created,
            "copied_points": copied_points,
            "copied_segments": copied_segments,
            "copied_journal": copied_journal,
            "copied_route_cache_rows": copied_route_cache,
            "dry_run": dry_run,
        }
    finally:
        source_db.close()
        target_db.close()


def main() -> None:
    defaults = _load_publish_defaults()
    parser = argparse.ArgumentParser(
        description="Publish one locally prepared trip and its train route cache into a server database.",
    )
    parser.add_argument("--trip-id", type=int, required=True, help="Local trip ID to publish.")
    parser.add_argument(
        "--target-url",
        default=defaults.get("PUBLISH_TARGET_URL", ""),
        help="SQLAlchemy database URL for the server database. Use an SSH tunnel if the DB only listens on localhost.",
    )
    parser.add_argument(
        "--target-name",
        default=defaults.get("PUBLISH_TARGET_NAME", "server"),
        help="Friendly label used to remember which server trip matches this local trip.",
    )
    parser.add_argument(
        "--target-user-email",
        default=defaults.get("PUBLISH_TARGET_USER_EMAIL", ""),
        help="Server user email to own the published trip. Defaults to the local trip owner's email.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would sync without committing anything.")
    args = parser.parse_args()

    if not args.target_url:
        raise SystemExit(
            "Missing target DB URL. Set PUBLISH_TARGET_URL in backend/.publish.env or pass --target-url."
        )

    result = publish_trip(
        trip_id=args.trip_id,
        target_url=args.target_url,
        target_name=args.target_name,
        target_user_email=args.target_user_email or None,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
