from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import httpx

from ..config import settings
from .geojson_transport_service import (
    DATASET_DIR,
    DATASET_ROOT_DIR,
    dataset_output_path,
    load_imported_dataset_metadata,
    remove_imported_dataset_metadata,
    reset_geojson_transport_datasets,
    save_imported_dataset_metadata,
)
from .country_route_policy_service import reset_country_route_policy_capabilities
from .place_lookup_service import reset_place_lookup_caches

logger = logging.getLogger(__name__)

TASKS_PATH = DATASET_ROOT_DIR / "geojson_import_tasks.json"
IMPORT_HISTORY_PATH = DATASET_ROOT_DIR / "geojson_import_history.json"
BACKUP_DIR = DATASET_ROOT_DIR / "backups"
LOG_DIR = DATASET_ROOT_DIR / "logs"
REPO_ROOT_DIR = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT_DIR / "backend"
OVERPASS_IMPORT_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
)
IMPORT_TYPES = {"rail", "airport"}
LARGE_RAIL_COUNTRY_KEYS = {
    "australia",
    "brazil",
    "canada",
    "china",
    "japan",
    "mexico",
    "united states",
    "united states of america",
    "usa",
    "us",
    "russia",
    "russian federation",
    "india",
}

AIRPORT_QUERY_VARIANTS = (
    (
        "ISO3166-1 + admin_level=2",
        """
[out:json][timeout:600];
area["ISO3166-1"="{iso}"]["admin_level"="2"]->.country;
(
  node["aeroway"~"^(aerodrome|terminal)$"](area.country);
  way["aeroway"~"^(aerodrome|terminal)$"](area.country);
  relation["aeroway"~"^(aerodrome|terminal)$"](area.country);
);
out center tags;
""",
    ),
    (
        "ISO3166-1:alpha2 + admin_level=2",
        """
[out:json][timeout:600];
area["ISO3166-1:alpha2"="{iso}"]["admin_level"="2"]->.country;
(
  node["aeroway"~"^(aerodrome|terminal)$"](area.country);
  way["aeroway"~"^(aerodrome|terminal)$"](area.country);
  relation["aeroway"~"^(aerodrome|terminal)$"](area.country);
);
out center tags;
""",
    ),
    (
        "ISO3166-1 without admin_level",
        """
[out:json][timeout:600];
area["ISO3166-1"="{iso}"]->.country;
(
  node["aeroway"~"^(aerodrome|terminal)$"](area.country);
  way["aeroway"~"^(aerodrome|terminal)$"](area.country);
  relation["aeroway"~"^(aerodrome|terminal)$"](area.country);
);
out center tags;
""",
    ),
    (
        "ISO3166-1:alpha2 without admin_level",
        """
[out:json][timeout:600];
area["ISO3166-1:alpha2"="{iso}"]->.country;
(
  node["aeroway"~"^(aerodrome|terminal)$"](area.country);
  way["aeroway"~"^(aerodrome|terminal)$"](area.country);
  relation["aeroway"~"^(aerodrome|terminal)$"](area.country);
);
out center tags;
""",
    ),
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _history_entries() -> list[dict]:
    if not IMPORT_HISTORY_PATH.exists():
        return []
    try:
        payload = json.loads(IMPORT_HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("geojson_import: failed to read import history at %s", IMPORT_HISTORY_PATH)
        return []
    if isinstance(payload, dict):
        payload = payload.get("items") or []
    return payload if isinstance(payload, list) else []


def _persist_history_entries(entries: list[dict]) -> None:
    IMPORT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = IMPORT_HISTORY_PATH.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps({"items": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(IMPORT_HISTORY_PATH)


def _append_import_history_entry(entry: dict) -> None:
    entries = _history_entries()
    entries.insert(0, entry)
    _persist_history_entries(entries)


def _backup_existing_file(target_path: Path, *, dataset_key: str, task_id: str) -> Optional[dict]:
    if not target_path.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_filename = f"{dataset_key}__{task_id}__{target_path.name}"
    backup_path = BACKUP_DIR / backup_filename
    shutil.copy2(target_path, backup_path)
    return {
        "target_path": str(target_path),
        "backup_path": str(backup_path),
        "filename": target_path.name,
    }


def _slugify_country_name(country_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (country_name or "").strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug


def _normalize_china_city_name(city_name: str) -> str:
    value = " ".join((city_name or "").strip().split())
    if not value:
        return value
    value = re.sub(r"\s*\((?:city|municipality)\)\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+(city|municipality)\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+shi\s*$", "", value, flags=re.IGNORECASE)
    return " ".join(value.strip().split())


def _normalize_import_names(country_name: str, city_name: Optional[str] = None) -> tuple[str, str]:
    normalized_country = " ".join((country_name or "").strip().split())
    normalized_city = " ".join((city_name or "").strip().split())
    if normalized_country.lower() == "china":
        normalized_city = _normalize_china_city_name(normalized_city)
    return normalized_country, normalized_city


def _country_key(country_name: str) -> str:
    return " ".join((country_name or "").strip().lower().split())


def _rail_import_needs_subdivision(country_name: str) -> bool:
    return _country_key(country_name) in LARGE_RAIL_COUNTRY_KEYS


def _normalize_import_type(import_type: str) -> str:
    normalized = (import_type or "rail").strip().lower()
    if normalized not in IMPORT_TYPES:
        raise ValueError("Import type must be rail or airport.")
    return normalized


def _normalize_iso_code(iso_code: Optional[str]) -> str:
    normalized = (iso_code or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", normalized):
        raise ValueError("Airport imports require a 2-letter ISO country code.")
    return normalized


def _task_summary(task: dict) -> dict:
    return {
        "id": task["id"],
        "country_name": task["country_name"],
        "city_name": task.get("city_name"),
        "import_type": task.get("import_type") or "rail",
        "iso_code": task.get("iso_code"),
        "overwrite": bool(task.get("overwrite")),
        "dataset_key": task["dataset_key"],
        "status": task["status"],
        "stage": task["stage"],
        "progress_percent": task["progress_percent"],
        "created_at": task["created_at"],
        "started_at": task.get("started_at"),
        "finished_at": task.get("finished_at"),
        "error": task.get("error"),
        "line_file": task.get("line_file"),
        "station_file": task.get("station_file"),
        "log_file": task.get("log_file"),
        "worker_pid": task.get("worker_pid"),
    }


def _task_log_path(task_id: str, dataset_key: str) -> Path:
    safe_key = _slugify_country_name(dataset_key) or "dataset"
    return LOG_DIR / f"{safe_key}__{task_id}.log"


def _is_process_running(pid: Optional[int]) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _tail_text(path: Path, max_bytes: int = 48_000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes), os.SEEK_SET)
        chunk = handle.read()
    return chunk.decode("utf-8", errors="replace")


def _title_from_slug(value: str) -> str:
    return " ".join(part.capitalize() for part in (value or "").split("_") if part)


def _build_dataset_metadata(country_name: str, dataset_key: str, city_name: Optional[str] = None) -> dict:
    normalized_country, normalized_city = _normalize_import_names(country_name, city_name)
    display_city = normalized_city or _title_from_slug(dataset_key)

    aliases = [dataset_key.replace("_", " ")]
    if normalized_country:
        aliases.append(normalized_country.lower())
    if normalized_city:
        aliases.append(normalized_city.lower())
        aliases.append(f"{normalized_city.lower()} {normalized_country.lower()}")

    deduped_aliases: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        normalized_alias = " ".join(alias.strip().lower().split())
        if not normalized_alias or normalized_alias in seen:
            continue
        seen.add(normalized_alias)
        deduped_aliases.append(normalized_alias)

    return {
        "country": (normalized_country or _title_from_slug(dataset_key)).title(),
        "city": display_city if normalized_city else "",
        "aliases": deduped_aliases,
    }


def _build_airport_dataset_metadata(country_name: str, dataset_key: str) -> dict:
    normalized_country = " ".join((country_name or "").strip().split())
    country_key = _slugify_country_name(normalized_country)
    aliases = [normalized_country.lower(), f"{normalized_country.lower()} airport", country_key]
    deduped_aliases: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        normalized_alias = " ".join(alias.strip().lower().split())
        if not normalized_alias or normalized_alias in seen:
            continue
        seen.add(normalized_alias)
        deduped_aliases.append(normalized_alias)

    return {
        "country": normalized_country,
        "city": "",
        "aliases": deduped_aliases,
        "methods": ["flight"],
    }


def _line_query(area_name: str) -> str:
    area_expr = _overpass_area_expression(area_name)
    return f"""[out:json][timeout:600];

{area_expr}

(
  way["railway"~"rail|subway|light_rail|monorail|narrow_gauge"](area.searchArea);
  relation["type"="route"]["route"~"train|railway|subway|light_rail|monorail"](area.searchArea);

  node["railway"~"station|halt|subway_entrance"](area.searchArea);
  way["railway"~"station|halt|platform"](area.searchArea);
  relation["railway"~"station|halt|platform"](area.searchArea);

  node["public_transport"~"station|platform|stop_position"]
      ["bus"!="yes"]
      ["ferry"!="yes"]
      ["aerialway"!="yes"]
      (area.searchArea);

  way["public_transport"~"station|platform"]
      ["bus"!="yes"]
      ["ferry"!="yes"]
      ["aerialway"!="yes"]
      (area.searchArea);
);

out body;
>;
out skel qt;
"""


def _station_query(area_name: str) -> str:
    area_expr = _overpass_area_expression(area_name)
    return f"""[out:json][timeout:600];

{area_expr}

(
  node["public_transport"~"station|platform|stop_position"](area.searchArea);
  way["public_transport"~"station|platform|stop_position"](area.searchArea);
  relation["public_transport"~"station|platform|stop_position"](area.searchArea);

  node["railway"~"station|halt|tram_stop|subway_entrance"](area.searchArea);
  way["railway"~"station|halt|platform|tram_stop"](area.searchArea);
  relation["railway"~"station|halt|platform"](area.searchArea);

  node["highway"="bus_stop"](area.searchArea);
  way["highway"="bus_stop"](area.searchArea);

  node["amenity"="bus_station"](area.searchArea);
  way["amenity"="bus_station"](area.searchArea);
  relation["amenity"="bus_station"](area.searchArea);

  node["amenity"="ferry_terminal"](area.searchArea);
  way["amenity"="ferry_terminal"](area.searchArea);
  relation["amenity"="ferry_terminal"](area.searchArea);

  node["aeroway"~"terminal|station"](area.searchArea);
  way["aeroway"~"terminal|station"](area.searchArea);
  relation["aeroway"~"terminal|station"](area.searchArea);

  node["amenity"="taxi"](area.searchArea);
  way["amenity"="taxi"](area.searchArea);
);

out center tags;
"""


def _escape_overpass_value(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def _overpass_area_expression(country_name: str) -> str:
    escaped = _escape_overpass_value(country_name.strip())
    return f"""(
  relation["name"="{escaped}"]["boundary"="administrative"]["admin_level"~"2|3|4|5|6"];
  relation["name:en"="{escaped}"]["boundary"="administrative"]["admin_level"~"2|3|4|5|6"];
  relation["official_name:en"="{escaped}"]["boundary"="administrative"]["admin_level"~"2|3|4|5|6"];
  relation["short_name:en"="{escaped}"]["boundary"="administrative"]["admin_level"~"2|3|4|5|6"];
  relation["int_name"="{escaped}"]["boundary"="administrative"]["admin_level"~"2|3|4|5|6"];
  way["name"="{escaped}"]["boundary"="administrative"]["admin_level"~"2|3|4|5|6"];
  way["name:en"="{escaped}"]["boundary"="administrative"]["admin_level"~"2|3|4|5|6"];
  way["official_name:en"="{escaped}"]["boundary"="administrative"]["admin_level"~"2|3|4|5|6"];
  way["short_name:en"="{escaped}"]["boundary"="administrative"]["admin_level"~"2|3|4|5|6"];
  way["int_name"="{escaped}"]["boundary"="administrative"]["admin_level"~"2|3|4|5|6"];
);
map_to_area -> .searchArea;"""


def _feature_properties(element: dict) -> dict:
    props = dict(element.get("tags") or {})
    props["@id"] = f"{element.get('type', 'element')}/{element.get('id', '')}"
    props["osm_type"] = element.get("type")
    props["osm_id"] = element.get("id")
    return props


def _coords_from_way(element: dict, node_lookup: dict[int, list[float]]) -> list[list[float]]:
    coords: list[list[float]] = []
    for node_id in element.get("nodes") or []:
        point = node_lookup.get(node_id)
        if point:
            coords.append(point)
    return coords


def _center_point(element: dict, node_lookup: dict[int, list[float]]) -> Optional[list[float]]:
    center = element.get("center")
    if isinstance(center, dict) and center.get("lat") is not None and center.get("lon") is not None:
        return [float(center["lon"]), float(center["lat"])]

    coords = _coords_from_way(element, node_lookup)
    if not coords:
        return None

    avg_lon = sum(point[0] for point in coords) / len(coords)
    avg_lat = sum(point[1] for point in coords) / len(coords)
    return [avg_lon, avg_lat]


def _overpass_lines_to_geojson(payload: dict) -> dict:
    elements = payload.get("elements") or []
    node_lookup = {
        int(element["id"]): [float(element["lon"]), float(element["lat"])]
        for element in elements
        if element.get("type") == "node" and element.get("lat") is not None and element.get("lon") is not None
    }
    way_lookup = {
        int(element["id"]): element
        for element in elements
        if element.get("type") == "way"
    }

    features: list[dict] = []

    for element in elements:
        element_type = element.get("type")
        props = _feature_properties(element)

        if element_type == "node":
            if element.get("lat") is None or element.get("lon") is None:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": props,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(element["lon"]), float(element["lat"])],
                    },
                }
            )
            continue

        if element_type == "way":
            coords = _coords_from_way(element, node_lookup)
            if len(coords) < 2:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": props,
                    "geometry": {"type": "LineString", "coordinates": coords},
                }
            )
            continue

        if element_type == "relation":
            line_parts: list[list[list[float]]] = []
            for member in element.get("members") or []:
                if member.get("type") != "way":
                    continue
                way = way_lookup.get(int(member.get("ref") or 0))
                if not way:
                    continue
                coords = _coords_from_way(way, node_lookup)
                if len(coords) >= 2:
                    line_parts.append(coords)
            if line_parts:
                geometry_type = "LineString" if len(line_parts) == 1 else "MultiLineString"
                coordinates = line_parts[0] if len(line_parts) == 1 else line_parts
                features.append(
                    {
                        "type": "Feature",
                        "properties": props,
                        "geometry": {"type": geometry_type, "coordinates": coordinates},
                    }
                )

    return {"type": "FeatureCollection", "features": features}


def _overpass_stations_to_geojson(payload: dict) -> dict:
    elements = payload.get("elements") or []
    node_lookup = {
        int(element["id"]): [float(element["lon"]), float(element["lat"])]
        for element in elements
        if element.get("type") == "node" and element.get("lat") is not None and element.get("lon") is not None
    }

    features: list[dict] = []
    for element in elements:
        props = _feature_properties(element)
        point = None

        if element.get("type") == "node":
            if element.get("lat") is not None and element.get("lon") is not None:
                point = [float(element["lon"]), float(element["lat"])]
        else:
            point = _center_point(element, node_lookup)

        if not point:
            continue

        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "Point", "coordinates": point},
            }
        )

    return {"type": "FeatureCollection", "features": features}


def _preferred_airport_name(tags: dict) -> str:
    for key in ("name:en", "int_name", "official_name:en", "name", "iata", "icao"):
        value = str(tags.get(key) or "").strip()
        if value:
            return value
    return ""


def _airport_country_tags_match(tags: dict, iso: str, country_name: str) -> bool:
    iso_upper = iso.upper()
    country_lower = country_name.lower()

    for tag_key in ("addr:country", "is_in:country_code", "country_code"):
        value = str(tags.get(tag_key) or "").strip().upper()
        if value and value != iso_upper:
            return False

    for tag_key in ("is_in:country", "addr:country_name"):
        value = str(tags.get(tag_key) or "").strip().lower()
        if value and value != country_lower:
            return False

    return True


def _overpass_airports_to_geojson(payload: dict, country_name: str, iso: str) -> dict:
    features: list[dict] = []
    for element in payload.get("elements") or []:
        center = element.get("center") or {}
        lat = element.get("lat") if element.get("lat") is not None else center.get("lat")
        lon = element.get("lon") if element.get("lon") is not None else center.get("lon")
        if lat is None or lon is None:
            continue

        tags = element.get("tags") or {}
        name = _preferred_airport_name(tags)
        if not name:
            continue
        if not _airport_country_tags_match(tags, iso, country_name):
            continue

        properties = _feature_properties(element)
        properties["country"] = country_name
        properties.setdefault("name", name)
        if not properties.get("aeroway"):
            properties["aeroway"] = "aerodrome"

        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(lon), float(lat)],
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


class _GeoJsonImportTaskManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: list[dict] = []
        self._active_task_id: Optional[str] = None
        self._current_output_country_name: Optional[str] = None
        self._load()

    def _load(self) -> None:
        active_worker_task_id = str(os.environ.get("GEOJSON_IMPORT_TASK_ID") or "").strip()
        if not TASKS_PATH.exists():
            self._tasks = []
            self._active_task_id = None
            return

        try:
            payload = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("geojson_import: failed to read task file at %s", TASKS_PATH)
            self._tasks = []
            self._active_task_id = None
            return

        tasks = payload.get("tasks") if isinstance(payload, dict) else []
        self._tasks = tasks if isinstance(tasks, list) else []
        self._active_task_id = None
        for task in self._tasks:
            if str(task.get("id") or "") == active_worker_task_id and task.get("status") in {"queued", "running"}:
                self._active_task_id = task.get("id")
                continue
            if task.get("status") == "queued":
                task["status"] = "failed"
                task["stage"] = "Interrupted by server restart"
                task["error"] = "Task did not finish before the server restarted."
                task["finished_at"] = _utc_now_iso()
                task["progress_percent"] = max(int(task.get("progress_percent") or 0), 1)
                continue
            if task.get("status") == "running":
                worker_pid = int(task.get("worker_pid") or 0)
                if _is_process_running(worker_pid):
                    self._active_task_id = task.get("id")
                    continue
                task["status"] = "failed"
                task["stage"] = "Worker stopped unexpectedly"
                task["error"] = task.get("error") or "The GeoJSON import worker stopped before completing."
                task["finished_at"] = task.get("finished_at") or _utc_now_iso()
                task["progress_percent"] = max(int(task.get("progress_percent") or 0), 1)
        self._persist()

    def _persist(self) -> None:
        TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
        TASKS_PATH.write_text(
            json.dumps({"tasks": self._tasks}, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def list_tasks(self) -> list[dict]:
        with self._lock:
            self._load()
            return [_task_summary(task) for task in self._tasks]

    def create_task(
        self,
        country_name: str,
        city_name: Optional[str] = None,
        import_type: str = "rail",
        iso_code: Optional[str] = None,
        overwrite: bool = False,
    ) -> dict:
        normalized_import_type = _normalize_import_type(import_type)
        normalized, normalized_city = _normalize_import_names(country_name, city_name)
        if len(normalized) < 2:
            raise ValueError("Country name is required.")

        needs_subdivision = normalized_import_type == "rail" and _rail_import_needs_subdivision(normalized)
        if needs_subdivision and len(normalized_city) < 2:
            raise ValueError("City or region name is required for this country.")

        normalized_iso = _normalize_iso_code(iso_code) if normalized_import_type == "airport" else None
        dataset_source_name = normalized_city if needs_subdivision else normalized
        dataset_key = _slugify_country_name(dataset_source_name)
        if normalized_import_type == "airport":
            dataset_key = f"{dataset_key}_airport"
        if not dataset_key:
            raise ValueError("Country or city name is not valid.")

        target_dir_country = normalized
        line_path = dataset_output_path(f"{dataset_key}.geojson", target_dir_country)
        station_path = dataset_output_path(f"{dataset_key}_station.geojson", target_dir_country)
        paths_to_check = (station_path,) if normalized_import_type == "airport" else (line_path, station_path)
        existing_files = [
            path.name
            for path in paths_to_check
            if path.exists()
        ]
        if existing_files and not overwrite:
            raise ValueError(
                f"GeoJSON file already exists for {dataset_source_name}: {', '.join(existing_files)}"
            )

        with self._lock:
            if self._active_task_id or any(task.get("status") in {"queued", "running"} for task in self._tasks):
                raise RuntimeError("Another GeoJSON import task is already running.")

            task = {
                "id": uuid.uuid4().hex,
                "country_name": normalized,
                "city_name": normalized_city if needs_subdivision and normalized_city else None,
                "import_type": normalized_import_type,
                "iso_code": normalized_iso,
                "overwrite": bool(overwrite),
                "dataset_key": dataset_key,
                "status": "queued",
                "stage": "Queued",
                "progress_percent": 0,
                "created_at": _utc_now_iso(),
                "started_at": None,
                "finished_at": None,
                "error": None,
                "line_file": f"{dataset_key}.geojson" if normalized_import_type == "rail" else None,
                "station_file": f"{dataset_key}_station.geojson",
            }
            self._tasks.insert(0, task)
            self._active_task_id = task["id"]
            self._persist()

        try:
            worker_pid, log_path = self._launch_worker_process(task)
            task.update({
                "status": "running",
                "stage": "Worker process started",
                "started_at": _utc_now_iso(),
                "progress_percent": 1,
                "worker_pid": worker_pid,
                "log_file": str(log_path),
            })
            self._update_task(
                task["id"],
                status=task["status"],
                stage=task["stage"],
                started_at=task["started_at"],
                progress_percent=task["progress_percent"],
                worker_pid=task["worker_pid"],
                log_file=task["log_file"],
            )
        except Exception as exc:
            logger.exception("geojson_import: failed to launch worker for %s", dataset_key)
            task.update({
                "status": "failed",
                "stage": "Failed to start worker",
                "error": str(exc),
                "finished_at": _utc_now_iso(),
            })
            self._finish_task(task["id"], status="failed", stage="Failed to start worker", error=str(exc))
        return _task_summary(task)

    def _launch_worker_process(self, task: dict) -> tuple[int, Path]:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = _task_log_path(task["id"], task["dataset_key"])
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{_utc_now_iso()}] Launching GeoJSON import worker for {task['dataset_key']}\n")

        command = [sys.executable, "-m", "app.geojson_import_worker", task["id"]]
        child_env = os.environ.copy()
        child_env["GEOJSON_IMPORT_TASK_ID"] = str(task["id"])
        log_handle = log_path.open("a", encoding="utf-8")
        try:
            process = subprocess.Popen(
                command,
                cwd=str(BACKEND_DIR),
                env=child_env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            log_handle.close()
        return int(process.pid), log_path

    def _update_task(self, task_id: str, **updates) -> None:
        with self._lock:
            task = next((row for row in self._tasks if row.get("id") == task_id), None)
            if not task:
                return
            task.update(updates)
            self._persist()

    def _finish_task(self, task_id: str, *, status: str, stage: str, error: Optional[str] = None) -> None:
        with self._lock:
            task = next((row for row in self._tasks if row.get("id") == task_id), None)
            if not task:
                self._active_task_id = None
                return
            task["status"] = status
            task["stage"] = stage
            task["error"] = error
            task["finished_at"] = _utc_now_iso()
            task["worker_pid"] = None
            if status == "completed":
                task["progress_percent"] = 100
            self._active_task_id = None
            self._persist()

    def _execute_overpass_query(
        self,
        query: str,
        *,
        context: str,
        on_retry_status: Optional[Callable[[str], None]] = None,
    ) -> dict:
        timeout = httpx.Timeout(settings.OVERPASS_GEOJSON_IMPORT_TIMEOUT_SECONDS)
        last_error: Optional[Exception] = None

        for index, url in enumerate(OVERPASS_IMPORT_URLS):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(
                        url,
                        data={"data": query},
                        headers={
                            "Accept": "application/json",
                            "User-Agent": "traveldiary/1.0",
                        },
                    )
                    response.raise_for_status()
                    logger.info("geojson_import: %s fetched via %s", context, url)
                    return response.json()
            except Exception as exc:
                last_error = exc
                logger.warning("geojson_import: %s failed via %s: %s", context, url, exc)
                if index < len(OVERPASS_IMPORT_URLS) - 1 and on_retry_status:
                    if isinstance(exc, httpx.HTTPStatusError):
                        status_code = exc.response.status_code
                        on_retry_status(
                            f"{context} hit Overpass status {status_code}. Retrying fallback endpoint..."
                        )
                    else:
                        on_retry_status(
                            f"{context} failed on one Overpass endpoint. Retrying fallback endpoint..."
                        )

        raise RuntimeError(f"{context} failed from all Overpass endpoints: {last_error}")

    def _write_geojson(self, filename: str, payload: dict, *, dataset_key: str, task_id: str) -> tuple[Path, Optional[dict]]:
        target_country = self._current_output_country_name or ""
        final_path = dataset_output_path(filename, target_country)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        backup_entry = _backup_existing_file(final_path, dataset_key=dataset_key, task_id=task_id)
        temp_path = final_path.with_suffix(final_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(final_path)
        return final_path, backup_entry

    def _ensure_non_empty_geojson(self, payload: dict, *, context: str) -> None:
        features = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(features, list) or not features:
            raise RuntimeError(f"{context} returned no features. Try a different boundary name or city search result.")

    def _run_task(self, task_id: str) -> None:
        with self._lock:
            self._load()
        task = next((row for row in self._tasks if row.get("id") == task_id), None)
        if not task:
            raise ValueError("GeoJSON import task not found.")
        if task.get("status") not in {"queued", "running"}:
            raise ValueError("GeoJSON import task is not runnable.")
        if (task.get("import_type") or "rail") == "airport":
            self._run_airport_task(task_id, task)
            return
        self._run_rail_task(task_id, task)

    def get_task_log(self, task_id: str, *, max_bytes: int = 48_000) -> dict:
        with self._lock:
            self._load()
            task = next((row for row in self._tasks if row.get("id") == task_id), None)
        if not task:
            raise ValueError("GeoJSON import task not found.")

        log_file = str(task.get("log_file") or "").strip()
        log_path = Path(log_file) if log_file else _task_log_path(task_id, str(task.get("dataset_key") or "dataset"))
        return {
            "task": _task_summary(task),
            "log_file": str(log_path),
            "content": _tail_text(log_path, max_bytes=max_bytes),
        }

    def run_task(self, task_id: str) -> None:
        self._run_task(task_id)

    def _run_rail_task(self, task_id: str, task: dict) -> None:
        country_name = task["country_name"]
        city_name = task.get("city_name")
        dataset_key = task["dataset_key"]
        area_name = city_name or country_name
        task_label = f"{country_name} / {city_name}" if city_name else country_name

        self._update_task(
            task_id,
            status="running",
            stage="Fetching rail network data",
            started_at=_utc_now_iso(),
            progress_percent=10,
        )

        try:
            self._current_output_country_name = country_name
            metadata_before = load_imported_dataset_metadata().get(dataset_key)
            line_payload = self._execute_overpass_query(
                _line_query(area_name),
                context=f"{task_label} rail query",
                on_retry_status=lambda stage: self._update_task(task_id, stage=stage, progress_percent=10),
            )
            self._update_task(task_id, stage="Converting rail network data", progress_percent=40)
            line_geojson = _overpass_lines_to_geojson(line_payload)
            self._ensure_non_empty_geojson(line_geojson, context=f"{task_label} rail export")

            self._update_task(task_id, stage="Fetching station and transport stop data", progress_percent=60)
            station_payload = self._execute_overpass_query(
                _station_query(area_name),
                context=f"{task_label} station query",
                on_retry_status=lambda stage: self._update_task(task_id, stage=stage, progress_percent=60),
            )
            self._update_task(task_id, stage="Converting station and transport stop data", progress_percent=85)
            station_geojson = _overpass_stations_to_geojson(station_payload)
            self._ensure_non_empty_geojson(station_geojson, context=f"{task_label} station export")

            self._update_task(task_id, stage="Saving GeoJSON files", progress_percent=92)
            line_path, line_backup = self._write_geojson(
                f"{dataset_key}.geojson",
                line_geojson,
                dataset_key=dataset_key,
                task_id=task_id,
            )
            station_path, station_backup = self._write_geojson(
                f"{dataset_key}_station.geojson",
                station_geojson,
                dataset_key=dataset_key,
                task_id=task_id,
            )
            metadata_after = _build_dataset_metadata(country_name, dataset_key, city_name)
            save_imported_dataset_metadata(
                dataset_key,
                metadata_after,
            )
            _append_import_history_entry({
                "id": uuid.uuid4().hex,
                "type": "import",
                "task_id": task_id,
                "dataset_key": dataset_key,
                "country_name": country_name,
                "city_name": city_name,
                "import_type": "rail",
                "created_at": _utc_now_iso(),
                "line_file": str(line_path),
                "station_file": str(station_path),
                "backup_files": [entry for entry in [line_backup, station_backup] if entry],
                "metadata_before": metadata_before,
                "metadata_after": metadata_after,
            })

            reset_geojson_transport_datasets()
            reset_country_route_policy_capabilities()
            reset_place_lookup_caches()
            self._finish_task(task_id, status="completed", stage="Completed")
            logger.info("geojson_import: completed dataset %s", dataset_key)
        except Exception as exc:
            logger.exception("geojson_import: task failed for %s", task_label)
            self._finish_task(task_id, status="failed", stage="Failed", error=str(exc))
        finally:
            self._current_output_country_name = None

    def _execute_airport_query(
        self,
        iso_code: str,
        *,
        task_label: str,
        on_retry_status: Optional[Callable[[str], None]] = None,
    ) -> dict:
        last_error: Optional[Exception] = None
        for variant_description, query_template in AIRPORT_QUERY_VARIANTS:
            query = query_template.format(iso=iso_code)
            context = f"{task_label} airport query ({variant_description})"
            try:
                payload = self._execute_overpass_query(
                    query,
                    context=context,
                    on_retry_status=on_retry_status,
                )
            except Exception as exc:
                last_error = exc
                if on_retry_status:
                    on_retry_status(f"{context} failed. Trying next airport query variant...")
                continue

            if payload.get("elements"):
                return payload

            if on_retry_status:
                on_retry_status(f"{context} returned no airport elements. Trying next query variant...")

        raise RuntimeError(f"{task_label} airport query returned no elements: {last_error}")

    def _run_airport_task(self, task_id: str, task: dict) -> None:
        country_name = task["country_name"]
        dataset_key = task["dataset_key"]
        iso_code = task.get("iso_code") or ""
        task_label = f"{country_name} airports"

        self._update_task(
            task_id,
            status="running",
            stage="Fetching airport data",
            started_at=_utc_now_iso(),
            progress_percent=15,
        )

        try:
            self._current_output_country_name = country_name
            metadata_before = load_imported_dataset_metadata().get(dataset_key)
            airport_payload = self._execute_airport_query(
                iso_code,
                task_label=task_label,
                on_retry_status=lambda stage: self._update_task(task_id, stage=stage, progress_percent=20),
            )
            self._update_task(task_id, stage="Converting airport data", progress_percent=75)
            airport_geojson = _overpass_airports_to_geojson(airport_payload, country_name, iso_code)
            self._ensure_non_empty_geojson(airport_geojson, context=f"{task_label} export")

            self._update_task(task_id, stage="Saving airport GeoJSON file", progress_percent=92)
            station_path, station_backup = self._write_geojson(
                f"{dataset_key}_station.geojson",
                airport_geojson,
                dataset_key=dataset_key,
                task_id=task_id,
            )
            metadata_after = _build_airport_dataset_metadata(country_name, dataset_key)
            save_imported_dataset_metadata(
                dataset_key,
                metadata_after,
            )
            _append_import_history_entry({
                "id": uuid.uuid4().hex,
                "type": "import",
                "task_id": task_id,
                "dataset_key": dataset_key,
                "country_name": country_name,
                "city_name": None,
                "import_type": "airport",
                "created_at": _utc_now_iso(),
                "line_file": None,
                "station_file": str(station_path),
                "backup_files": [entry for entry in [station_backup] if entry],
                "metadata_before": metadata_before,
                "metadata_after": metadata_after,
            })

            reset_geojson_transport_datasets()
            reset_country_route_policy_capabilities()
            reset_place_lookup_caches()
            self._finish_task(task_id, status="completed", stage="Completed")
            logger.info("geojson_import: completed airport dataset %s", dataset_key)
        except Exception as exc:
            logger.exception("geojson_import: airport task failed for %s", task_label)
            self._finish_task(task_id, status="failed", stage="Failed", error=str(exc))
        finally:
            self._current_output_country_name = None


_task_manager = _GeoJsonImportTaskManager()


def list_geojson_import_tasks() -> list[dict]:
    return _task_manager.list_tasks()


def get_geojson_import_task_log(task_id: str, *, max_bytes: int = 48_000) -> dict:
    return _task_manager.get_task_log(task_id, max_bytes=max_bytes)


def create_geojson_import_task(
    country_name: str,
    city_name: Optional[str] = None,
    import_type: str = "rail",
    iso_code: Optional[str] = None,
    overwrite: bool = False,
) -> dict:
    return _task_manager.create_task(country_name, city_name, import_type, iso_code, overwrite)


def run_geojson_import_task(task_id: str) -> None:
    _task_manager.run_task(task_id)


def list_geojson_import_history(limit: int = 200) -> list[dict]:
    return _history_entries()[:limit]


def rollback_geojson_import_history_entry(history_id: str) -> dict:
    entries = _history_entries()
    target_entry = next((entry for entry in entries if str(entry.get("id") or "") == str(history_id)), None)
    if not target_entry:
        raise ValueError("Import history entry not found.")

    backup_files = target_entry.get("backup_files") or []
    if not backup_files:
        raise ValueError("This import has no stored backup files to roll back to.")

    rollback_task_id = uuid.uuid4().hex
    rollback_backups: list[dict] = []
    for item in backup_files:
        target_path = Path(str(item.get("target_path") or ""))
        backup_path = Path(str(item.get("backup_path") or ""))
        if not backup_path.exists():
            raise ValueError(f"Backup file is missing for rollback: {backup_path}")
        current_backup = _backup_existing_file(
            target_path,
            dataset_key=str(target_entry.get("dataset_key") or "dataset"),
            task_id=f"rollback_{rollback_task_id}",
        )
        if current_backup:
            rollback_backups.append(current_backup)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, target_path)

    dataset_key = str(target_entry.get("dataset_key") or "").strip()
    metadata_before = load_imported_dataset_metadata().get(dataset_key)
    metadata_after = target_entry.get("metadata_before")
    if dataset_key:
        if isinstance(metadata_after, dict) and metadata_after:
            save_imported_dataset_metadata(dataset_key, metadata_after)
        else:
            remove_imported_dataset_metadata(dataset_key)

    reset_geojson_transport_datasets()
    reset_country_route_policy_capabilities()
    reset_place_lookup_caches()

    rollback_entry = {
        "id": uuid.uuid4().hex,
        "type": "rollback",
        "task_id": rollback_task_id,
        "dataset_key": dataset_key,
        "country_name": target_entry.get("country_name"),
        "city_name": target_entry.get("city_name"),
        "import_type": target_entry.get("import_type"),
        "created_at": _utc_now_iso(),
        "line_file": target_entry.get("line_file"),
        "station_file": target_entry.get("station_file"),
        "backup_files": rollback_backups,
        "metadata_before": metadata_before,
        "metadata_after": metadata_after,
        "restored_from_history_id": history_id,
    }
    _append_import_history_entry(rollback_entry)
    return rollback_entry
