import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from .config import get_cors_origins, settings
from .database import Base, SessionLocal, engine
from .models import User, EmailOTP, Trip, TimelinePoint, TravelSegment, RouteCache, CountryRoutePolicy, TrainStationCache, TrainStation, AdminAuditLog, SearchAliasOverride, TripPublicView, TripJournal  # register models
from .routers import auth, trips, timeline, segments, upload, public, routes, admin, journals
from .services.search_alias_service import ensure_default_search_alias_overrides
from .services.trip_share_service import create_share_slug


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logging.getLogger("app").setLevel(logging.INFO)

Base.metadata.create_all(bind=engine)


def _ensure_trip_columns() -> None:
    inspector = inspect(engine)
    try:
        columns = {column["name"] for column in inspector.get_columns("trips")}
    except Exception:
        return

    missing_columns = {
        "starting_place_name": "ALTER TABLE trips ADD COLUMN starting_place_name VARCHAR(255)",
        "starting_city": "ALTER TABLE trips ADD COLUMN starting_city VARCHAR(255)",
        "starting_country": "ALTER TABLE trips ADD COLUMN starting_country VARCHAR(255)",
        "starting_latitude": "ALTER TABLE trips ADD COLUMN starting_latitude FLOAT",
        "starting_longitude": "ALTER TABLE trips ADD COLUMN starting_longitude FLOAT",
        "travel_companions": "ALTER TABLE trips ADD COLUMN travel_companions VARCHAR(255)",
        "planned_countries": "ALTER TABLE trips ADD COLUMN planned_countries JSON",
        "share_slug": "ALTER TABLE trips ADD COLUMN share_slug VARCHAR(64) NULL",
        "shared_at": "ALTER TABLE trips ADD COLUMN shared_at DATETIME NULL",
    }

    with engine.begin() as conn:
        for column_name, ddl in missing_columns.items():
            if column_name in columns:
                continue
            conn.execute(text(ddl))
        conn.execute(
            text("UPDATE trips SET visibility = 'private' WHERE visibility IS NULL OR TRIM(visibility) = ''")
        )
        conn.execute(
            text("UPDATE trips SET visibility = 'public' WHERE LOWER(TRIM(visibility)) = 'public'")
        )
        conn.execute(
            text("UPDATE trips SET visibility = 'private' WHERE LOWER(TRIM(visibility)) NOT IN ('private', 'public', 'unlisted')")
        )

    try:
        indexes = {index["name"] for index in inspector.get_indexes("trips")}
    except Exception:
        return

    with engine.begin() as conn:
        if "ix_trips_share_slug" not in indexes:
            conn.execute(text("CREATE UNIQUE INDEX ix_trips_share_slug ON trips (share_slug)"))


_ensure_trip_columns()


def _ensure_trip_public_views_table() -> None:
    inspector = inspect(engine)
    try:
        tables = set(inspector.get_table_names())
    except Exception:
        return
    if "trip_public_views" in tables:
        return

    TripPublicView.__table__.create(bind=engine, checkfirst=True)


_ensure_trip_public_views_table()


def _ensure_trip_journals_table() -> None:
    TripJournal.__table__.create(bind=engine, checkfirst=True)


_ensure_trip_journals_table()


def _ensure_trip_share_data() -> None:
    db = SessionLocal()
    try:
        trips_to_update = (
            db.query(Trip)
            .filter(Trip.visibility.in_(["public", "unlisted"]))
            .all()
        )
        seen_slugs: set[str] = {
            slug for (slug,) in db.query(Trip.share_slug).filter(Trip.share_slug.isnot(None)).all() if slug
        }
        changed = False
        for trip in trips_to_update:
            if not trip.share_slug:
                slug = create_share_slug()
                while slug in seen_slugs:
                    slug = create_share_slug()
                trip.share_slug = slug
                seen_slugs.add(slug)
                changed = True
            if not trip.shared_at:
                trip.shared_at = trip.updated_at or trip.created_at
                changed = True
        if changed:
            db.commit()
    except Exception:
        logging.exception("Failed to ensure trip share data")
        db.rollback()
    finally:
        db.close()


_ensure_trip_share_data()


def _ensure_route_cache_columns() -> None:
    inspector = inspect(engine)
    try:
        columns = {column["name"] for column in inspector.get_columns("route_cache")}
    except Exception:
        return

    missing_columns = {
        "provider": "ALTER TABLE route_cache ADD COLUMN provider VARCHAR(64) NULL",
        "point_count": "ALTER TABLE route_cache ADD COLUMN point_count INTEGER NOT NULL DEFAULT 0",
        "countries_json": "ALTER TABLE route_cache ADD COLUMN countries_json LONGTEXT NOT NULL DEFAULT '[]'",
        "geometry_signature": "ALTER TABLE route_cache ADD COLUMN geometry_signature VARCHAR(40) NULL",
    }

    with engine.begin() as conn:
        for column_name, ddl in missing_columns.items():
            if column_name in columns:
                continue
            conn.execute(text(ddl))

    try:
        indexes = {index["name"] for index in inspector.get_indexes("route_cache")}
    except Exception:
        return

    with engine.begin() as conn:
        if "ix_route_cache_geometry_signature" not in indexes:
            conn.execute(text("CREATE INDEX ix_route_cache_geometry_signature ON route_cache (geometry_signature)"))


_ensure_route_cache_columns()


def _ensure_user_columns() -> None:
    inspector = inspect(engine)
    try:
        columns = {column["name"] for column in inspector.get_columns("users")}
    except Exception:
        return

    missing_columns = {
        "auth_provider": "ALTER TABLE users ADD COLUMN auth_provider VARCHAR(32) NOT NULL DEFAULT 'local'",
        "google_sub": "ALTER TABLE users ADD COLUMN google_sub VARCHAR(255) NULL",
        "avatar_url": "ALTER TABLE users ADD COLUMN avatar_url VARCHAR(500) NULL",
        "is_admin": "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0",
        "is_active": "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1",
        "last_login_at": "ALTER TABLE users ADD COLUMN last_login_at DATETIME NULL",
    }

    with engine.begin() as conn:
        for column_name, ddl in missing_columns.items():
            if column_name in columns:
                continue
            conn.execute(text(ddl))
        conn.execute(
            text("UPDATE users SET auth_provider = 'local' WHERE auth_provider IS NULL OR TRIM(auth_provider) = ''")
        )
        conn.execute(
            text("UPDATE users SET is_active = 1 WHERE is_active IS NULL")
        )
        conn.execute(
            text("UPDATE users SET is_admin = 1 WHERE LOWER(TRIM(email)) = :admin_email"),
            {"admin_email": " ".join(str(settings.ADMIN_EMAIL).strip().lower().split())},
        )

    try:
        indexes = {index["name"] for index in inspector.get_indexes("users")}
    except Exception:
        return

    with engine.begin() as conn:
        if "ix_users_google_sub" not in indexes:
            conn.execute(text("CREATE UNIQUE INDEX ix_users_google_sub ON users (google_sub)"))


_ensure_user_columns()


def _ensure_default_search_aliases() -> None:
    db = SessionLocal()
    try:
        ensure_default_search_alias_overrides(db)
    except Exception:
        logging.exception("Failed to ensure default search alias overrides")
        db.rollback()
    finally:
        db.close()


_ensure_default_search_aliases()

app = FastAPI(
    title="Travel Diary API",
    version="1.0.0",
    description="Personal travel timeline and world map diary",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(trips.router)
app.include_router(timeline.router)
app.include_router(segments.router)
app.include_router(routes.router)
app.include_router(admin.router)
app.include_router(upload.router)
app.include_router(public.router)
app.include_router(journals.router)


@app.get("/", tags=["root"])
def root():
    return {"message": "Travel Diary API", "version": "1.0.0", "docs": "/docs"}


@app.get("/health", tags=["root"])
def health():
    return {"status": "healthy"}
