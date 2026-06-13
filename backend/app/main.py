import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from .config import get_cors_origins
from .database import Base, SessionLocal, engine
from .models import User, EmailOTP, Trip, TimelinePoint, TravelSegment, RouteCache, CountryRoutePolicy, TrainStationCache, TrainStation, AdminAuditLog, SearchAliasOverride  # register models
from .routers import auth, trips, timeline, segments, upload, public, routes, admin
from .services.search_alias_service import ensure_default_search_alias_overrides


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
        "planned_countries": "ALTER TABLE trips ADD COLUMN planned_countries JSON",
    }

    with engine.begin() as conn:
        for column_name, ddl in missing_columns.items():
            if column_name in columns:
                continue
            conn.execute(text(ddl))


_ensure_trip_columns()


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


@app.get("/", tags=["root"])
def root():
    return {"message": "Travel Diary API", "version": "1.0.0", "docs": "/docs"}


@app.get("/health", tags=["root"])
def health():
    return {"status": "healthy"}
