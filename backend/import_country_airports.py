"""
Download airport nodes/ways/relations for a specific country from Overpass API
and save them as a per-country GeoJSON file that the travel-diary backend can
auto-discover.

Usage
-----
  python import_country_airports.py --country "Vietnam" --iso VN
  python import_country_airports.py --country "Malaysia" --iso MY
  python import_country_airports.py --country "Laos" --iso LA

The script writes:
  backend/gpkg/hotosm_chn_railways_osm_gpkg/{country_lower}_airport_station.geojson

And registers the dataset in:
  backend/gpkg/hotosm_chn_railways_osm_gpkg/imported_dataset_metadata.json

so that the backend auto-discovers it as a "flight" dataset for that country.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
GPKG_DIR = SCRIPT_DIR / "gpkg" / "hotosm_chn_railways_osm_gpkg"
METADATA_PATH = GPKG_DIR / "imported_dataset_metadata.json"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# ---------------------------------------------------------------------------
# Overpass queries — tried in order until one returns results
# ---------------------------------------------------------------------------
# Each entry is a (description, query_template) pair.
# {iso} is substituted with the uppercase ISO 3166-1 alpha-2 code.
QUERY_VARIANTS = [
    (
        'ISO3166-1 + admin_level=2 (standard)',
        """
[out:json][timeout:120];
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
        'ISO3166-1:alpha2 + admin_level=2 (SARs / territories)',
        """
[out:json][timeout:120];
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
        'ISO3166-1 (no admin_level restriction)',
        """
[out:json][timeout:120];
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
        'ISO3166-1:alpha2 (no admin_level restriction)',
        """
[out:json][timeout:120];
area["ISO3166-1:alpha2"="{iso}"]->.country;
(
  node["aeroway"~"^(aerodrome|terminal)$"](area.country);
  way["aeroway"~"^(aerodrome|terminal)$"](area.country);
  relation["aeroway"~"^(aerodrome|terminal)$"](area.country);
);
out center tags;
""",
    ),
]


def _post_overpass(endpoint: str, query: str) -> dict:
    with httpx.Client(timeout=150.0) as client:
        resp = client.post(
            endpoint,
            data={"data": query},
            headers={"Accept": "application/json", "User-Agent": "traveldiary-airport-importer/1.0"},
        )
        resp.raise_for_status()
        return resp.json()


def run_overpass_query(iso: str) -> dict:
    iso_upper = iso.upper()
    for variant_desc, query_template in QUERY_VARIANTS:
        query = query_template.format(iso=iso_upper)
        for endpoint in OVERPASS_ENDPOINTS:
            print(f"  Trying variant '{variant_desc}' via {endpoint} ...", flush=True)
            try:
                data = _post_overpass(endpoint, query)
                elements = data.get("elements") or []
                if elements:
                    print(f"  Got {len(elements)} elements with variant '{variant_desc}'")
                    return data
                # Empty result from this endpoint — try next variant, not next endpoint
                print(f"  0 elements returned, trying next variant...")
                break
            except Exception as exc:
                print(f"  Warning: {endpoint} failed: {exc}", file=sys.stderr)
                time.sleep(2)

    # All variants exhausted with 0 results — return empty
    return {"elements": []}


def _preferred_name(tags: dict) -> str:
    for key in ("name:en", "int_name", "official_name:en", "name", "iata"):
        val = tags.get(key, "").strip()
        if val:
            return val
    return ""


def _tag_country_matches(tags: dict, iso: str, country_name: str) -> bool:
    """Return False when OSM tags explicitly identify this feature as belonging to a
    different country (e.g. addr:country=SG when we're importing Malaysia)."""
    iso_upper = iso.upper()
    country_lower = country_name.lower()

    for tag_key in ("addr:country", "is_in:country_code", "country_code"):
        val = str(tags.get(tag_key) or "").strip().upper()
        if val and val != iso_upper:
            return False  # explicit ISO code for a different country

    for tag_key in ("is_in:country", "addr:country_name"):
        val = str(tags.get(tag_key) or "").strip().lower()
        if val and val != country_lower:
            return False  # explicit country name for a different country

    return True


def elements_to_geojson(elements: list[dict], country_name: str, iso: str) -> dict:
    features = []
    skipped = 0
    for el in elements:
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue

        tags = el.get("tags") or {}
        name = _preferred_name(tags)
        if not name:
            continue  # skip unnamed entries

        if not _tag_country_matches(tags, iso, country_name):
            skipped += 1
            continue  # OSM tags say this belongs to a different country

        properties = dict(tags)
        properties["country"] = country_name
        if not properties.get("aeroway"):
            properties["aeroway"] = "aerodrome"

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "properties": properties,
        })

    if skipped:
        print(f"  Skipped {skipped} features whose OSM tags indicate a different country")

    return {"type": "FeatureCollection", "features": features}


def load_metadata() -> dict:
    if not METADATA_PATH.exists():
        return {}
    try:
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_metadata(data: dict) -> None:
    GPKG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = METADATA_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(METADATA_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import airports for a country from Overpass")
    parser.add_argument("--country", required=True, help='Country name as used in the app, e.g. "Vietnam"')
    parser.add_argument("--iso", required=True, help="ISO 3166-1 alpha-2 code, e.g. VN")
    args = parser.parse_args()

    country_name: str = args.country.strip()
    iso: str = args.iso.strip().upper()
    country_key = country_name.lower().replace(" ", "_")
    dataset_key = f"{country_key}_airport"
    output_path = GPKG_DIR / f"{dataset_key}_station.geojson"

    print(f"Importing airports for {country_name!r} (ISO={iso}) → {output_path.name}")

    data = run_overpass_query(iso)
    elements = data.get("elements") or []
    print(f"  Received {len(elements)} elements from Overpass")

    geojson = elements_to_geojson(elements, country_name, iso)
    print(f"  Converted to {len(geojson['features'])} named airport features")

    if not geojson["features"]:
        print("  No named airports found — aborting.", file=sys.stderr)
        sys.exit(1)

    GPKG_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved → {output_path}")

    # Register in imported_dataset_metadata.json so get_dataset_metadata() picks it up correctly.
    metadata = load_metadata()
    metadata[dataset_key] = {
        "country": country_name,
        "city": "",
        "aliases": [country_name.lower(), f"{country_name.lower()} airport", country_key],
        "methods": ["flight"],
    }
    save_metadata(metadata)
    print(f"  Registered dataset key {dataset_key!r} in imported_dataset_metadata.json")
    print("Done.")


if __name__ == "__main__":
    main()
