from __future__ import annotations

import argparse
import json
import sys
import time

import httpx
from sqlalchemy.exc import IntegrityError

from app.database import Base, SessionLocal, engine
from app.models import TrainStation

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]


def preferred_english_name(tags: dict, fallback: str) -> str:
    return (
        tags.get("name:en")
        or tags.get("official_name:en")
        or tags.get("alt_name:en")
        or tags.get("short_name:en")
        or tags.get("int_name")
        or tags.get("official_name")
        or tags.get("uic_name")
        or tags.get("short_name")
        or tags.get("name")
        or fallback
    )


def build_country_query(country: str, admin_level: int) -> str:
    safe_country = country.replace('"', '\\"')
    return f"""
[out:json][timeout:180];
area["name"="{safe_country}"]["boundary"="administrative"]["admin_level"="{admin_level}"]->.searchArea;
(
  node(area.searchArea)["railway"~"station|halt|tram_stop|subway_entrance"];
  node(area.searchArea)["railway"="stop"];
  node(area.searchArea)["station"];
  node(area.searchArea)["public_transport"="station"];
  node(area.searchArea)["public_transport"="platform"];
  node(area.searchArea)["public_transport"="stop_position"];
  node(area.searchArea)["subway"="yes"];
  node(area.searchArea)["monorail"="yes"];
  way(area.searchArea)["railway"~"station|halt|tram_stop|subway_entrance"];
  way(area.searchArea)["railway"="stop"];
  way(area.searchArea)["station"];
  way(area.searchArea)["public_transport"="station"];
  way(area.searchArea)["public_transport"="platform"];
  way(area.searchArea)["public_transport"="stop_position"];
  way(area.searchArea)["subway"="yes"];
  way(area.searchArea)["monorail"="yes"];
  relation(area.searchArea)["railway"~"station|halt|tram_stop|subway_entrance"];
  relation(area.searchArea)["railway"="stop"];
  relation(area.searchArea)["station"];
  relation(area.searchArea)["public_transport"="station"];
  relation(area.searchArea)["public_transport"="platform"];
  relation(area.searchArea)["public_transport"="stop_position"];
  relation(area.searchArea)["subway"="yes"];
  relation(area.searchArea)["monorail"="yes"];
);
out center tags;
"""


def build_bbox_query(south: float, west: float, north: float, east: float) -> str:
    return f"""
[out:json][timeout:180];
(
  node({south},{west},{north},{east})["railway"~"station|halt|tram_stop|subway_entrance"];
  node({south},{west},{north},{east})["railway"="stop"];
  node({south},{west},{north},{east})["station"];
  node({south},{west},{north},{east})["public_transport"="station"];
  node({south},{west},{north},{east})["public_transport"="platform"];
  node({south},{west},{north},{east})["public_transport"="stop_position"];
  node({south},{west},{north},{east})["subway"="yes"];
  node({south},{west},{north},{east})["monorail"="yes"];
  way({south},{west},{north},{east})["railway"~"station|halt|tram_stop|subway_entrance"];
  way({south},{west},{north},{east})["railway"="stop"];
  way({south},{west},{north},{east})["station"];
  way({south},{west},{north},{east})["public_transport"="station"];
  way({south},{west},{north},{east})["public_transport"="platform"];
  way({south},{west},{north},{east})["public_transport"="stop_position"];
  way({south},{west},{north},{east})["subway"="yes"];
  way({south},{west},{north},{east})["monorail"="yes"];
  relation({south},{west},{north},{east})["railway"~"station|halt|tram_stop|subway_entrance"];
  relation({south},{west},{north},{east})["railway"="stop"];
  relation({south},{west},{north},{east})["station"];
  relation({south},{west},{north},{east})["public_transport"="station"];
  relation({south},{west},{north},{east})["public_transport"="platform"];
  relation({south},{west},{north},{east})["public_transport"="stop_position"];
  relation({south},{west},{north},{east})["subway"="yes"];
  relation({south},{west},{north},{east})["monorail"="yes"];
);
out center tags;
"""


def fetch_overpass(query: str) -> dict:
    last_error: Exception | None = None

    for endpoint in OVERPASS_ENDPOINTS:
        try:
            with httpx.Client(timeout=180.0) as client:
                response = client.post(
                    endpoint,
                    data={"data": query},
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "traveldiary-importer/1.0",
                    },
                )
                response.raise_for_status()
                print(f"Fetched data from {endpoint}")
                return response.json()
        except Exception as exc:
            last_error = exc
            print(f"Overpass failed via {endpoint}: {exc}")
            time.sleep(1.5)

    raise RuntimeError(f"Overpass import failed on all endpoints: {last_error}")


def station_coords(element: dict) -> tuple[float | None, float | None]:
    lat = element.get("lat")
    lon = element.get("lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)

    center = element.get("center") or {}
    lat = center.get("lat")
    lon = center.get("lon")
    if lat is None or lon is None:
        return None, None
    return float(lat), float(lon)


def save_station(session, element: dict, default_country: str) -> bool:
    lat, lon = station_coords(element)
    if lat is None or lon is None:
        return False

    tags = element.get("tags") or {}
    osm_type = element.get("type") or "unknown"
    osm_id = str(element.get("id") or "")
    if not osm_id:
        return False

    osm_key = f"osm_{osm_type}_{osm_id}"
    row = session.query(TrainStation).filter(TrainStation.osm_key == osm_key).first()
    if not row:
        row = TrainStation(osm_key=osm_key)
        session.add(row)

    row.osm_type = osm_type
    row.osm_id = osm_id
    row.name = preferred_english_name(tags, "Train station")
    row.latitude = lat
    row.longitude = lon
    row.city = tags.get("addr:city") or tags.get("is_in:city") or tags.get("addr:suburb") or ""
    row.country = tags.get("addr:country") or tags.get("is_in:country") or default_country or ""
    row.railway_type = tags.get("railway") or tags.get("station") or tags.get("public_transport") or ""
    row.source = "osm_overpass_import"
    row.tags_json = json.dumps(tags, ensure_ascii=True)
    return True


def run_import(country: str | None, bbox: str | None, admin_level: int) -> None:
    if not country and not bbox:
        raise ValueError("Provide either --country or --bbox")

    if country and bbox:
        raise ValueError("Use only one of --country or --bbox")

    if country:
        query = build_country_query(country, admin_level)
        default_country = country
    else:
        parts = [part.strip() for part in (bbox or "").split(",")]
        if len(parts) != 4:
            raise ValueError("--bbox must be south,west,north,east")
        south, west, north, east = [float(part) for part in parts]
        query = build_bbox_query(south, west, north, east)
        default_country = ""

    Base.metadata.create_all(bind=engine)

    data = fetch_overpass(query)
    elements = data.get("elements") or []
    print(f"Received {len(elements)} raw station elements")

    session = SessionLocal()
    saved = 0
    try:
        for element in elements:
            if save_station(session, element, default_country):
                saved += 1

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            print("Commit hit a duplicate key; retrying row-by-row for safe upsert...")
            for element in elements:
                try:
                    save_station(session, element, default_country)
                    session.commit()
                except Exception:
                    session.rollback()
    finally:
        session.close()

    print(f"Imported/updated {saved} train station rows")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import train stations from Overpass into train_stations")
    parser.add_argument("--country", help="Country name, for example Morocco or China")
    parser.add_argument("--bbox", help="Bounding box as south,west,north,east")
    parser.add_argument("--admin-level", type=int, default=2, help="Administrative level for country area lookup")
    args = parser.parse_args()

    try:
        run_import(args.country, args.bbox, args.admin_level)
    except Exception as exc:
        print(f"Import failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
