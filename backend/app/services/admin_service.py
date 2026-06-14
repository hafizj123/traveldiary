from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models.admin_audit_log import AdminAuditLog
from ..models.route_cache import RouteCache
from ..models.search_alias_override import SearchAliasOverride
from ..models.timeline_point import TimelinePoint
from ..models.travel_segment import TravelSegment
from ..models.trip import Trip
from ..models.user import User
from .country_route_policy_service import list_country_route_policies_with_capabilities
from .geojson_import_service import list_geojson_import_history, list_geojson_import_tasks
from .geojson_transport_service import (
    DATASET_DIR,
    DATASET_ROOT_DIR,
    get_dataset_file_index,
    get_dataset_metadata_map,
    load_imported_dataset_metadata,
)
from .route_cache_service import normalize_countries

BROKEN_ROUTE_PROVIDERS = {"fallback", "ferry_fallback", "excursion_straight"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_loads(value: str) -> Optional[Any]:
    try:
        return json.loads(value)
    except Exception:
        return None


def _path_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def _bytes_to_mb(value: int) -> float:
    return round(value / (1024 * 1024), 2)


def get_system_status(db: Session) -> dict:
    database_url = str(getattr(getattr(db, "bind", None), "url", "") or "")
    db_path = ""
    if database_url.startswith("sqlite:///"):
        db_path = database_url.replace("sqlite:///", "", 1)

    disk = shutil.disk_usage(DATASET_ROOT_DIR)
    dataset_size = _path_size_bytes(DATASET_DIR)
    backup_dir = DATASET_ROOT_DIR / "backups"
    backup_size = _path_size_bytes(backup_dir)
    route_cache_count = db.query(RouteCache).count()
    trip_count = db.query(Trip).count()
    point_count = db.query(TimelinePoint).count()
    segment_count = db.query(TravelSegment).count()
    user_count = db.query(User).count()

    return {
        "generated_at": _now_iso(),
        "database_path": db_path,
        "database_size_mb": _bytes_to_mb(_path_size_bytes(Path(db_path))) if db_path else 0.0,
        "dataset_root": str(DATASET_ROOT_DIR),
        "dataset_size_mb": _bytes_to_mb(dataset_size),
        "backup_size_mb": _bytes_to_mb(backup_size),
        "disk_total_mb": _bytes_to_mb(disk.total),
        "disk_used_mb": _bytes_to_mb(disk.used),
        "disk_free_mb": _bytes_to_mb(disk.free),
        "route_cache_count": route_cache_count,
        "trip_count": trip_count,
        "point_count": point_count,
        "segment_count": segment_count,
        "user_count": user_count,
        "active_import_tasks": len([
            task for task in list_geojson_import_tasks()
            if task.get("status") in {"queued", "running"}
        ]),
        "search_alias_count": db.query(SearchAliasOverride).filter(SearchAliasOverride.is_active.is_(True)).count(),
    }


def get_data_health_summary(db: Session) -> dict:
    policies = list_country_route_policies_with_capabilities(db)
    file_index = get_dataset_file_index()
    metadata_map = get_dataset_metadata_map()
    imported_metadata = load_imported_dataset_metadata()
    route_cache_rows = db.query(RouteCache.countries_json).all()

    route_cache_counts: dict[str, int] = {}
    for (countries_json,) in route_cache_rows:
        parsed_countries = _safe_json_loads(countries_json)
        countries = normalize_countries(parsed_countries if isinstance(parsed_countries, list) else [])
        for country in countries:
            route_cache_counts[country] = route_cache_counts.get(country, 0) + 1

    dataset_entries: list[dict] = []
    for dataset_key, paths in file_index.items():
        metadata = metadata_map.get(dataset_key) or {}
        country_name = str(metadata.get("country") or "").strip() or dataset_key.replace("_", " ").title()
        city_name = str(metadata.get("city") or "").strip()
        station_path = paths.get("station_path")
        rail_path = paths.get("rail_path")
        dataset_entries.append({
            "dataset_key": dataset_key,
            "country_name": country_name,
            "city_name": city_name,
            "station_file": str(station_path) if station_path else None,
            "rail_file": str(rail_path) if rail_path else None,
            "station_size_mb": _bytes_to_mb(station_path.stat().st_size) if station_path and station_path.exists() else 0.0,
            "rail_size_mb": _bytes_to_mb(rail_path.stat().st_size) if rail_path and rail_path.exists() else 0.0,
            "is_imported": dataset_key in imported_metadata,
        })

    last_import_by_country: dict[str, dict] = {}
    for item in list_geojson_import_history(limit=400):
        country_name = str(item.get("country_name") or "").strip()
        if not country_name or country_name in last_import_by_country:
            continue
        last_import_by_country[country_name] = item

    country_rows: list[dict] = []
    for item in policies:
        country_name = item.get("country_name") or item.get("country_key")
        matching_datasets = [
            dataset
            for dataset in dataset_entries
            if (dataset.get("country_name") or "").strip().lower() == str(country_name or "").strip().lower()
        ]
        country_rows.append({
            "country_key": item.get("country_key"),
            "country_name": country_name,
            "continent": item.get("continent"),
            "selected_mode": item.get("selected_mode"),
            "supports_google": bool(item.get("supports_google")),
            "supports_geojson": bool(item.get("supports_geojson")),
            "dataset_count": len(matching_datasets),
            "dataset_keys": [dataset["dataset_key"] for dataset in matching_datasets],
            "route_cache_count": route_cache_counts.get(country_name, 0),
            "last_import_at": (last_import_by_country.get(country_name) or {}).get("created_at"),
        })

    return {
        "generated_at": _now_iso(),
        "countries": country_rows,
        "datasets": dataset_entries,
        "summary": {
            "country_count": len(country_rows),
            "dataset_count": len(dataset_entries),
            "imported_dataset_count": len([entry for entry in dataset_entries if entry["is_imported"]]),
            "countries_with_local_data": len([row for row in country_rows if row["dataset_count"] > 0]),
        },
    }


def list_broken_route_cache_rows(db: Session, limit: int = 200) -> list[dict]:
    rows = (
        db.query(RouteCache)
        .order_by(RouteCache.id.desc())
        .limit(max(limit * 6, 600))
        .all()
    )
    results: list[dict] = []
    for row in rows:
        if (row.provider or "").strip().lower() not in BROKEN_ROUTE_PROVIDERS:
            continue
        countries = _safe_json_loads(row.countries_json or "[]")
        results.append({
            "id": row.id,
            "cache_key": row.cache_key,
            "provider": row.provider,
            "point_count": int(row.point_count or 0),
            "countries": normalize_countries(countries if isinstance(countries, list) else []),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
        if len(results) >= limit:
            break
    return results


def delete_route_cache_rows(
    db: Session,
    *,
    ids: Optional[list[int]] = None,
    country: Optional[str] = None,
    provider: Optional[str] = None,
) -> int:
    rows = db.query(RouteCache).all()
    target_country = " ".join(str(country or "").strip().split()).casefold()
    target_provider = " ".join(str(provider or "").strip().split()).casefold()

    deleted = 0
    for row in rows:
        if ids and row.id not in ids:
            continue
        if target_provider and str(row.provider or "").strip().casefold() != target_provider:
            continue
        if target_country:
            countries = _safe_json_loads(row.countries_json or "[]")
            normalized = {str(item).strip().casefold() for item in countries or [] if str(item).strip()}
            if target_country not in normalized:
                continue
        db.delete(row)
        deleted += 1

    if deleted:
        db.commit()
    return deleted


def list_admin_audit_rows(db: Session, limit: int = 200) -> list[dict]:
    rows = (
        db.query(AdminAuditLog)
        .order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "actor_email": row.actor_email,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "details": _safe_json_loads(row.details_json or "{}") or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def build_admin_export_snapshot(db: Session, *, include_route_cache: bool = False) -> dict:
    payload = {
        "generated_at": _now_iso(),
        "system_status": get_system_status(db),
        "data_health": get_data_health_summary(db),
        "route_policies": list_country_route_policies_with_capabilities(db),
        "geojson_import_tasks": list_geojson_import_tasks(),
        "geojson_import_history": list_geojson_import_history(limit=1000),
        "imported_dataset_metadata": load_imported_dataset_metadata(),
        "search_alias_overrides": [
            {
                "id": row.id,
                "alias": row.alias,
                "method": row.method,
                "place_name": row.place_name,
                "city": row.city,
                "country": row.country,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "notes": row.notes,
                "is_active": row.is_active,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in list(db.query(SearchAliasOverride).order_by(SearchAliasOverride.id.asc()).all())
        ],
        "users": list_admin_users(db, limit=1000),
        "audit_logs": list_admin_audit_rows(db, limit=1000),
        "broken_routes": list_broken_route_cache_rows(db, limit=500),
    }
    if include_route_cache:
        payload["route_cache"] = [
            {
                "id": row.id,
                "cache_key": row.cache_key,
                "provider": row.provider,
                "point_count": row.point_count,
                "countries_json": row.countries_json,
                "geometry_signature": row.geometry_signature,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in db.query(RouteCache).order_by(RouteCache.id.asc()).all()
        ]
    return payload


def list_admin_trip_summaries(db: Session, query: str = "", limit: int = 60) -> list[dict]:
    rows = (
        db.query(Trip, User)
        .join(User, Trip.user_id == User.id)
        .order_by(Trip.updated_at.desc(), Trip.created_at.desc())
        .limit(max(limit * 4, 200))
        .all()
    )
    normalized_query = " ".join((query or "").strip().lower().split())
    results: list[dict] = []
    for trip, user in rows:
        haystack = " ".join([
            str(trip.title or ""),
            str(user.email or ""),
            str(user.username or ""),
            str(trip.starting_country or ""),
        ]).lower()
        if normalized_query and normalized_query not in haystack:
            continue
        point_count = db.query(TimelinePoint).filter(TimelinePoint.trip_id == trip.id).count()
        results.append({
            "trip_id": trip.id,
            "title": trip.title,
            "owner_email": user.email,
            "owner_username": user.username,
            "start_date": trip.start_date.isoformat() if trip.start_date else None,
            "end_date": trip.end_date.isoformat() if trip.end_date else None,
            "starting_country": trip.starting_country,
            "point_count": point_count,
            "updated_at": trip.updated_at.isoformat() if trip.updated_at else None,
        })
        if len(results) >= limit:
            break
    return results


def list_admin_users(db: Session, query: str = "", limit: int = 200) -> list[dict]:
    rows = (
        db.query(User)
        .order_by(User.created_at.desc(), User.id.desc())
        .limit(max(limit * 4, 200))
        .all()
    )
    normalized_query = " ".join((query or "").strip().lower().split())
    results: list[dict] = []
    for user in rows:
        haystack = " ".join([
            str(user.email or ""),
            str(user.username or ""),
            str(user.auth_provider or ""),
        ]).lower()
        if normalized_query and normalized_query not in haystack:
            continue
        results.append({
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "auth_provider": user.auth_provider or "local",
            "is_verified": bool(user.is_verified),
            "is_active": bool(getattr(user, "is_active", True)),
            "is_admin": bool(getattr(user, "is_admin", False)),
            "avatar_url": getattr(user, "avatar_url", None),
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "last_login_at": user.last_login_at.isoformat() if getattr(user, "last_login_at", None) else None,
        })
        if len(results) >= limit:
            break
    return results
