from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.search_alias_override import SearchAliasOverride
from ..models.timeline_point import TimelinePoint
from ..models.travel_segment import TravelSegment
from ..models.trip import Trip
from ..models.user import User
from ..services.admin_service import (
    build_admin_export_snapshot,
    delete_route_cache_rows,
    get_data_health_summary,
    list_admin_users,
    get_system_status,
    list_admin_audit_rows,
    list_admin_trip_summaries,
    list_broken_route_cache_rows,
)
from ..services.audit_service import is_admin_user, log_audit_event
from ..services.country_route_policy_service import (
    country_display_name,
    country_key_from_name,
    list_country_route_policies_with_capabilities,
    upsert_country_route_policy,
)
from ..services.geojson_import_service import (
    list_geojson_import_history,
    rollback_geojson_import_history_entry,
)
from ..services.search_alias_service import list_search_alias_overrides
from ..utils.deps import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


class RouteCacheDeleteBody(BaseModel):
    ids: list[int] = Field(default_factory=list)
    country: Optional[str] = None
    provider: Optional[str] = None


class CountryRoutePolicyBulkUpdateBody(BaseModel):
    country_keys: list[str]
    train_mode: str


class SearchAliasCreateBody(BaseModel):
    alias: str
    method: Optional[str] = None
    place_name: str
    city: Optional[str] = None
    country: str
    latitude: float
    longitude: float
    notes: Optional[str] = None
    is_active: bool = True


class AdminUserUpdateBody(BaseModel):
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


def _require_admin_user(user: User) -> None:
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/system-status")
def get_admin_system_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    return get_system_status(db)


@router.get("/data-health")
def get_admin_data_health(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    return get_data_health_summary(db)


@router.get("/import-history")
def get_admin_import_history(
    limit: int = Query(200, ge=1, le=1000),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    return {"items": list_geojson_import_history(limit=limit)}


@router.post("/import-history/{history_id}/rollback")
def post_admin_import_history_rollback(
    history_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    try:
        entry = rollback_geojson_import_history_entry(history_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_audit_event(
        db,
        user=user,
        action="rollback_import",
        resource_type="geojson_import_history",
        resource_id=history_id,
        details={"dataset_key": entry.get("dataset_key"), "rollback_entry_id": entry.get("id")},
    )
    db.commit()
    return {"item": entry}


@router.get("/broken-routes")
def get_admin_broken_routes(
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    return {"items": list_broken_route_cache_rows(db, limit=limit)}


@router.post("/route-cache/delete")
def post_admin_route_cache_delete(
    payload: RouteCacheDeleteBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    if not payload.ids and not (payload.country or "").strip() and not (payload.provider or "").strip():
        raise HTTPException(status_code=400, detail="Provide ids, country, or provider before deleting route cache.")
    deleted = delete_route_cache_rows(
        db,
        ids=payload.ids or None,
        country=payload.country,
        provider=payload.provider,
    )
    log_audit_event(
        db,
        user=user,
        action="delete_route_cache",
        resource_type="route_cache",
        details={"ids": payload.ids, "country": payload.country, "provider": payload.provider, "deleted": deleted},
    )
    db.commit()
    return {"deleted": deleted}


@router.put("/country-route-policies/bulk")
def put_admin_country_route_policy_bulk(
    payload: CountryRoutePolicyBulkUpdateBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    normalized_keys = [" ".join((key or "").strip().lower().split()) for key in payload.country_keys if str(key or "").strip()]
    if not normalized_keys:
        raise HTTPException(status_code=400, detail="At least one country key is required.")

    updated = []
    failed = []
    for country_key in normalized_keys:
        try:
            row = upsert_country_route_policy(db, country_key, payload.train_mode)
            updated.append({
                "country_key": row.country_key,
                "country_name": row.country_name,
                "train_mode": row.train_mode,
            })
        except ValueError as exc:
            normalized_failed_key = country_key_from_name(country_key)
            failed.append({
                "country_key": normalized_failed_key or country_key,
                "country_name": country_display_name(normalized_failed_key) if normalized_failed_key else country_key,
                "error": str(exc),
            })
    log_audit_event(
        db,
        user=user,
        action="bulk_update_country_route_policy",
        resource_type="country_route_policy",
        details={
            "country_keys": normalized_keys,
            "train_mode": payload.train_mode,
            "updated_count": len(updated),
            "failed_count": len(failed),
            "failed": failed,
        },
    )
    db.commit()
    return {
        "items": updated,
        "failed": failed,
        "capabilities": list_country_route_policies_with_capabilities(db),
    }


@router.get("/search-aliases")
def get_admin_search_aliases(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    rows = list_search_alias_overrides(db)
    return {
        "items": [
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
            for row in rows
        ]
    }


@router.post("/search-aliases")
def post_admin_search_alias(
    payload: SearchAliasCreateBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    row = SearchAliasOverride(
        alias=payload.alias.strip(),
        method=(payload.method or "").strip().lower() or None,
        place_name=payload.place_name.strip(),
        city=" ".join((payload.city or "").strip().split()) or None,
        country=payload.country.strip(),
        latitude=payload.latitude,
        longitude=payload.longitude,
        notes=(payload.notes or "").strip() or None,
        is_active=payload.is_active,
    )
    db.add(row)
    log_audit_event(
        db,
        user=user,
        action="create_search_alias",
        resource_type="search_alias_override",
        details={
            "alias": row.alias,
            "method": row.method,
            "place_name": row.place_name,
            "country": row.country,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "item": {
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
    }


@router.delete("/search-aliases/{alias_id}")
def delete_admin_search_alias(
    alias_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    row = db.query(SearchAliasOverride).filter(SearchAliasOverride.id == alias_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Search alias not found.")
    details = {"alias": row.alias, "place_name": row.place_name, "country": row.country, "method": row.method}
    db.delete(row)
    log_audit_event(
        db,
        user=user,
        action="delete_search_alias",
        resource_type="search_alias_override",
        resource_id=str(alias_id),
        details=details,
    )
    db.commit()
    return {"deleted": True}


@router.get("/audit-logs")
def get_admin_audit_logs(
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    return {"items": list_admin_audit_rows(db, limit=limit)}


@router.get("/export")
def get_admin_export(
    include_route_cache: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    return build_admin_export_snapshot(db, include_route_cache=include_route_cache)


@router.get("/trips")
def get_admin_trips(
    q: str = Query("", alias="query"),
    limit: int = Query(60, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    return {"items": list_admin_trip_summaries(db, query=q, limit=limit)}


@router.get("/users")
def get_admin_users(
    q: str = Query("", alias="query"),
    limit: int = Query(120, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    return {"items": list_admin_users(db, query=q, limit=limit)}


@router.patch("/users/{user_id}")
def patch_admin_user(
    user_id: int,
    payload: AdminUserUpdateBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.id == target.id and (payload.is_admin is not None or payload.is_active is not None):
        raise HTTPException(status_code=400, detail="You cannot change your own admin or active status from this screen.")

    changed_fields: list[str] = []
    if payload.is_admin is not None and bool(getattr(target, "is_admin", False)) != payload.is_admin:
        target.is_admin = payload.is_admin
        changed_fields.append("is_admin")
    if payload.is_active is not None and bool(getattr(target, "is_active", True)) != payload.is_active:
        target.is_active = payload.is_active
        changed_fields.append("is_active")

    if not changed_fields:
        return {
            "item": {
                "id": target.id,
                "email": target.email,
                "username": target.username,
                "auth_provider": target.auth_provider or "local",
                "is_verified": bool(target.is_verified),
                "is_active": bool(getattr(target, "is_active", True)),
                "is_admin": bool(getattr(target, "is_admin", False)),
                "avatar_url": getattr(target, "avatar_url", None),
                "created_at": target.created_at.isoformat() if target.created_at else None,
                "updated_at": target.updated_at.isoformat() if target.updated_at else None,
                "last_login_at": target.last_login_at.isoformat() if getattr(target, "last_login_at", None) else None,
            }
        }

    log_audit_event(
        db,
        user=user,
        action="update_user_access",
        resource_type="user",
        resource_id=str(target.id),
        details={
            "updated_fields": changed_fields,
            "target_email": target.email,
            "is_admin": bool(getattr(target, "is_admin", False)),
            "is_active": bool(getattr(target, "is_active", True)),
        },
    )
    db.commit()
    db.refresh(target)
    return {
        "item": {
            "id": target.id,
            "email": target.email,
            "username": target.username,
            "auth_provider": target.auth_provider or "local",
            "is_verified": bool(target.is_verified),
            "is_active": bool(getattr(target, "is_active", True)),
            "is_admin": bool(getattr(target, "is_admin", False)),
            "avatar_url": getattr(target, "avatar_url", None),
            "created_at": target.created_at.isoformat() if target.created_at else None,
            "updated_at": target.updated_at.isoformat() if target.updated_at else None,
            "last_login_at": target.last_login_at.isoformat() if getattr(target, "last_login_at", None) else None,
        }
    }


@router.get("/trips/{trip_id}")
def get_admin_trip_detail(
    trip_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    trip = (
        db.query(Trip, User)
        .join(User, Trip.user_id == User.id)
        .filter(Trip.id == trip_id)
        .first()
    )
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")

    trip_row, owner = trip
    points = (
        db.query(TimelinePoint)
        .filter(TimelinePoint.trip_id == trip_id)
        .order_by(TimelinePoint.sequence_no, TimelinePoint.id)
        .all()
    )
    segments = (
        db.query(TravelSegment)
        .filter(TravelSegment.trip_id == trip_id)
        .order_by(TravelSegment.id.asc())
        .all()
    )
    return {
        "trip": {
            "id": trip_row.id,
            "title": trip_row.title,
            "owner_email": owner.email,
            "owner_username": owner.username,
            "start_date": trip_row.start_date.isoformat() if trip_row.start_date else None,
            "end_date": trip_row.end_date.isoformat() if trip_row.end_date else None,
            "starting_country": trip_row.starting_country,
            "updated_at": trip_row.updated_at.isoformat() if trip_row.updated_at else None,
        },
        "points": [
            {
                "id": point.id,
                "sequence_no": point.sequence_no,
                "visit_date": point.visit_date.isoformat() if point.visit_date else None,
                "place_name": point.place_name,
                "city": point.city,
                "country": point.country,
                "latitude": point.latitude,
                "longitude": point.longitude,
            }
            for point in points
        ],
        "segments": [
            {
                "id": segment.id,
                "from_point_id": segment.from_point_id,
                "to_point_id": segment.to_point_id,
                "travel_method": segment.travel_method,
            }
            for segment in segments
        ],
    }


@router.post("/trips/{trip_id}/normalize-sequence")
def post_admin_trip_normalize_sequence(
    trip_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin_user(user)
    points = (
        db.query(TimelinePoint)
        .filter(TimelinePoint.trip_id == trip_id)
        .order_by(TimelinePoint.sequence_no, TimelinePoint.id)
        .all()
    )
    if not points:
        raise HTTPException(status_code=404, detail="Trip points not found.")

    changed = 0
    for index, point in enumerate(points):
        if point.sequence_no != index:
            point.sequence_no = index
            changed += 1

    log_audit_event(
        db,
        user=user,
        action="normalize_trip_sequence",
        resource_type="trip",
        resource_id=str(trip_id),
        details={"changed_points": changed},
    )
    db.commit()
    return {"normalized": True, "changed_points": changed}
