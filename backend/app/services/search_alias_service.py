from __future__ import annotations

import unicodedata
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models.search_alias_override import SearchAliasOverride

SPECIAL_EXCURSION_ALIAS_NOTES = "system:special_excursion_station:lauterbrunnen_grutschalp"

DEFAULT_SEARCH_ALIAS_OVERRIDES = (
    {
        "alias": "Lauterbrunnen",
        "method": "excursion",
        "place_name": "Lauterbrunnen",
        "city": "Lauterbrunnen",
        "country": "Switzerland",
        "latitude": 46.5983618,
        "longitude": 7.9080357,
        "notes": SPECIAL_EXCURSION_ALIAS_NOTES,
    },
    {
        "alias": "Lauterbrunnen Station",
        "method": "excursion",
        "place_name": "Lauterbrunnen",
        "city": "Lauterbrunnen",
        "country": "Switzerland",
        "latitude": 46.5983618,
        "longitude": 7.9080357,
        "notes": SPECIAL_EXCURSION_ALIAS_NOTES,
    },
    {
        "alias": "Lauterbrunnen Lift",
        "method": "excursion",
        "place_name": "Lauterbrunnen",
        "city": "Lauterbrunnen",
        "country": "Switzerland",
        "latitude": 46.5983618,
        "longitude": 7.9080357,
        "notes": SPECIAL_EXCURSION_ALIAS_NOTES,
    },
    {
        "alias": "Gr\u00fctschalp",
        "method": "excursion",
        "place_name": "Gr\u00fctschalp",
        "city": "Lauterbrunnen",
        "country": "Switzerland",
        "latitude": 46.5965617,
        "longitude": 7.890707,
        "notes": SPECIAL_EXCURSION_ALIAS_NOTES,
    },
    {
        "alias": "Grutschalp",
        "method": "excursion",
        "place_name": "Gr\u00fctschalp",
        "city": "Lauterbrunnen",
        "country": "Switzerland",
        "latitude": 46.5965617,
        "longitude": 7.890707,
        "notes": SPECIAL_EXCURSION_ALIAS_NOTES,
    },
    {
        "alias": "Gruetschalp",
        "method": "excursion",
        "place_name": "Gr\u00fctschalp",
        "city": "Lauterbrunnen",
        "country": "Switzerland",
        "latitude": 46.5965617,
        "longitude": 7.890707,
        "notes": SPECIAL_EXCURSION_ALIAS_NOTES,
    },
    {
        "alias": "Gr\u00fctschalp Lift",
        "method": "excursion",
        "place_name": "Gr\u00fctschalp",
        "city": "Lauterbrunnen",
        "country": "Switzerland",
        "latitude": 46.5965617,
        "longitude": 7.890707,
        "notes": SPECIAL_EXCURSION_ALIAS_NOTES,
    },
)


def _normalize_text(value: str) -> str:
    text = " ".join((value or "").strip().lower().split())
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("ascii")


def _repair_special_excursion_alias_rows(db: Session) -> None:
    alias_fixes = {
        "GrÃ¼tschalp": "Gr\u00fctschalp",
        "GrÃ¼tschalp Lift": "Gr\u00fctschalp Lift",
    }
    place_fixes = {
        "GrÃ¼tschalp": "Gr\u00fctschalp",
    }
    seen: dict[str, SearchAliasOverride] = {}
    duplicates: list[SearchAliasOverride] = []

    rows = (
        db.query(SearchAliasOverride)
        .filter(SearchAliasOverride.method == "excursion")
        .filter(SearchAliasOverride.notes == SPECIAL_EXCURSION_ALIAS_NOTES)
        .order_by(SearchAliasOverride.id.asc())
        .all()
    )

    for row in rows:
        if row.alias in alias_fixes:
            row.alias = alias_fixes[row.alias]
        if row.place_name in place_fixes:
            row.place_name = place_fixes[row.place_name]

        dedupe_key = "|".join([
            row.alias or "",
            row.method or "",
            row.place_name or "",
            row.country or "",
            f"{float(row.latitude):.7f}",
            f"{float(row.longitude):.7f}",
        ])
        if dedupe_key in seen:
            duplicates.append(row)
            continue
        seen[dedupe_key] = row

    for row in duplicates:
        db.delete(row)


def ensure_default_search_alias_overrides(db: Session) -> int:
    _repair_special_excursion_alias_rows(db)
    created = 0
    for item in DEFAULT_SEARCH_ALIAS_OVERRIDES:
        existing = (
            db.query(SearchAliasOverride)
            .filter(SearchAliasOverride.alias == item["alias"])
            .filter(SearchAliasOverride.method == item["method"])
            .filter(SearchAliasOverride.place_name == item["place_name"])
            .filter(SearchAliasOverride.country == item["country"])
            .filter(SearchAliasOverride.latitude == item["latitude"])
            .filter(SearchAliasOverride.longitude == item["longitude"])
            .first()
        )
        if existing:
            if existing.notes != item["notes"] or not existing.is_active:
                existing.notes = item["notes"]
                existing.is_active = True
            continue
        db.add(SearchAliasOverride(**item, is_active=True))
        created += 1

    if created:
        db.commit()
    else:
        db.flush()
    return created


def list_special_excursion_stations(db: Session) -> list[dict]:
    ensure_default_search_alias_overrides(db)
    rows = (
        db.query(SearchAliasOverride)
        .filter(SearchAliasOverride.is_active.is_(True))
        .filter(SearchAliasOverride.method == "excursion")
        .filter(SearchAliasOverride.notes == SPECIAL_EXCURSION_ALIAS_NOTES)
        .order_by(SearchAliasOverride.place_name.asc(), SearchAliasOverride.alias.asc())
        .all()
    )
    stations: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        key = "|".join([
            _normalize_text(row.place_name or ""),
            _normalize_text(row.country or ""),
            f"{float(row.latitude):.7f}",
            f"{float(row.longitude):.7f}",
        ])
        if key in seen:
            continue
        seen.add(key)
        stations.append({
            "id": f"special-excursion-{_normalize_text(row.place_name or '').replace(' ', '-')}",
            "place_name": row.place_name,
            "city": row.city or "",
            "country": row.country or "",
            "latitude": float(row.latitude),
            "longitude": float(row.longitude),
            "source": "admin_alias_override",
            "notes": row.notes or "",
        })
    return stations


def list_search_alias_overrides(db: Session) -> list[SearchAliasOverride]:
    ensure_default_search_alias_overrides(db)
    return (
        db.query(SearchAliasOverride)
        .order_by(SearchAliasOverride.alias.asc(), SearchAliasOverride.id.desc())
        .all()
    )


def search_alias_matches(
    db: Session,
    query: str,
    *,
    method: Optional[str] = None,
    country_hint: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    ensure_default_search_alias_overrides(db)
    normalized_query = _normalize_text(query)
    if len(normalized_query) < 2:
        return []

    rows = (
        db.query(SearchAliasOverride)
        .filter(SearchAliasOverride.is_active.is_(True))
        .filter(
            or_(
                SearchAliasOverride.alias.ilike(f"%{query.strip()}%"),
                SearchAliasOverride.place_name.ilike(f"%{query.strip()}%"),
            )
        )
        .order_by(SearchAliasOverride.alias.asc(), SearchAliasOverride.id.desc())
        .limit(max(limit * 6, 40))
        .all()
    )

    results: list[tuple[int, dict]] = []
    seen: set[str] = set()
    normalized_country_hint = _normalize_text(country_hint or "")
    normalized_method = (method or "").strip().lower()

    for row in rows:
        alias_norm = _normalize_text(row.alias or "")
        place_norm = _normalize_text(row.place_name or "")
        country_norm = _normalize_text(row.country or "")

        if normalized_method and row.method and row.method.strip().lower() != normalized_method:
            continue
        if normalized_country_hint and country_norm and country_norm != normalized_country_hint:
            continue

        if alias_norm == normalized_query:
            score = 700
        elif alias_norm.startswith(normalized_query):
            score = 600
        elif normalized_query in alias_norm:
            score = 500
        elif place_norm == normalized_query:
            score = 450
        elif normalized_query in place_norm:
            score = 350
        else:
            continue

        dedupe_key = f"{place_norm}|{country_norm}|{normalized_method or row.method or ''}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        results.append((
            score,
            {
                "id": f"alias-{row.id}",
                "place_name": row.place_name,
                "city": row.city or "",
                "country": row.country or "",
                "latitude": float(row.latitude),
                "longitude": float(row.longitude),
                "subtitle": ", ".join(part for part in [row.city or "", row.country or ""] if part),
                "source": "admin_alias_override",
                "transport_mode": row.method or method or "",
                "alias_label": row.alias,
                "notes": row.notes or "",
            },
        ))

    results.sort(key=lambda item: (-item[0], item[1]["place_name"]))
    return [result for _, result in results[:limit]]
