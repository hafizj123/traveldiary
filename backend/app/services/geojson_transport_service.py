from __future__ import annotations

import heapq
import json
import logging
import math
import re
import threading
import unicodedata
from pathlib import Path
from typing import Optional

from ..database import SessionLocal
from .search_alias_service import list_special_excursion_stations

logger = logging.getLogger(__name__)

DATASET_ROOT_DIR = Path(__file__).resolve().parents[3] / "backend/gpkg/hotosm_chn_railways_osm_gpkg"
DATASET_DIR = DATASET_ROOT_DIR / "geojson_file"
LEGACY_DATASET_DIR = DATASET_ROOT_DIR
IMPORTED_DATASET_METADATA_PATH = DATASET_ROOT_DIR / "imported_dataset_metadata.json"
IMPORT_TASKS_PATH = DATASET_ROOT_DIR / "geojson_import_tasks.json"
GRAPH_NODE_SNAP_RADIUS_DEGREES = 0.05
GRAPH_NODE_CANDIDATE_LIMIT = 12
MAX_ROUTE_LENGTH_RATIO = 4.5
BOUND_PADDING_DEGREES = 0.1

EUROPE_INTERNATIONAL_RAIL_KEY = "europe_international_rail"
SPECIAL_EXCURSION_STATION_MATCH_RADIUS_METERS = 450

SPECIAL_EXCURSION_STATIONS = (
    {
        "id": "special-excursion-lauterbrunnen",
        "place_name": "Lauterbrunnen",
        "aliases": [
            "Lauterbrunnen",
            "Lauterbrunnen Station",
            "Lauterbrunnen Lift",
        ],
        "city": "Lauterbrunnen",
        "country": "Switzerland",
        "latitude": 46.5983618,
        "longitude": 7.9080357,
        "source": "special_excursion_station",
    },
    {
        "id": "special-excursion-grutschalp",
        "place_name": "Grütschalp",
        "aliases": [
            "Grütschalp",
            "Grutschalp",
            "Gruetschalp",
            "Grütschalp Lift",
        ],
        "city": "Lauterbrunnen",
        "country": "Switzerland",
        "latitude": 46.5965617,
        "longitude": 7.890707,
        "source": "special_excursion_station",
    },
)

STATIC_DATASET_METADATA = {
    "beijing": {"country": "China", "city": "Beijing", "aliases": ["beijing", "beijing china"], "bounds": {"south": 39.4, "north": 41.1, "west": 115.7, "east": 117.4}},
    "costa_rica": {"country": "Costa Rica", "city": "", "aliases": ["costa rica"], "bounds": {"south": 8.0, "north": 11.5, "west": -86.2, "east": -82.4}},
    "ecuador": {"country": "Ecuador", "city": "", "aliases": ["ecuador"], "bounds": {"south": -5.2, "north": 1.7, "west": -92.2, "east": -75.0}},
    "egypt": {"country": "Egypt", "city": "", "aliases": ["egypt"], "bounds": {"south": 21.5, "north": 31.9, "west": 24.5, "east": 36.2}},
    EUROPE_INTERNATIONAL_RAIL_KEY: {"country": "Europe", "city": "", "aliases": ["europe international rail", "europe"], "bounds": {"south": 35.0, "north": 72.0, "west": -12.0, "east": 45.0}},
    "europe_ferry": {"country": "Europe", "city": "", "aliases": ["europe", "ferry", "europe ferry"], "bounds": {"south": 35.0, "north": 72.0, "west": -12.0, "east": 45.0}},
    "europe_lift": {"country": "Europe", "city": "", "aliases": ["europe", "alps"], "bounds": {"south": 35.0, "north": 72.0, "west": -12.0, "east": 40.0}},
    "europe_tram": {"country": "Europe", "city": "", "aliases": ["europe", "tram", "europe tram"], "bounds": {"south": 35.0, "north": 72.0, "west": -12.0, "east": 45.0}},
    "europe_urban_rail": {"country": "Europe", "city": "", "aliases": ["europe", "urban rail", "europe urban rail"], "bounds": {"south": 35.0, "north": 72.0, "west": -12.0, "east": 45.0}},
    "harbin": {"country": "China", "city": "Harbin", "aliases": ["harbin", "harbin china"], "bounds": {"south": 44.9, "north": 46.1, "west": 125.0, "east": 127.0}},
    "hong_kong": {"country": "Hong Kong", "city": "Hong Kong", "aliases": ["hong kong", "hongkong"], "bounds": {"south": 22.1, "north": 22.6, "west": 113.8, "east": 114.5}},
    "italy": {"country": "Italy", "city": "", "aliases": ["italy"], "bounds": {"south": 36.0, "north": 47.8, "west": 6.0, "east": 18.8}},
    "macau": {"country": "Macau", "city": "Macau", "aliases": ["macau", "macao"], "bounds": {"south": 22.05, "north": 22.25, "west": 113.45, "east": 113.65}},
    "morocco": {"country": "Morocco", "city": "", "aliases": ["morocco"], "bounds": {"south": 27.0, "north": 36.2, "west": -13.5, "east": -0.5}},
    "panama": {"country": "Panama", "city": "", "aliases": ["panama"], "bounds": {"south": 7.0, "north": 9.8, "west": -83.1, "east": -77.0}},
    "peru": {"country": "Peru", "city": "", "aliases": ["peru"], "bounds": {"south": -18.6, "north": 0.2, "west": -81.5, "east": -68.4}},
    "philippines": {"country": "Philippines", "city": "", "aliases": ["philippines", "the philippines"], "bounds": {"south": 4.0, "north": 21.5, "west": 116.0, "east": 127.5}},
    "shanghai": {"country": "China", "city": "Shanghai", "aliases": ["shanghai", "shanghai china"], "bounds": {"south": 30.6, "north": 31.95, "west": 120.8, "east": 122.1}},
    "south_africa": {"country": "South Africa", "city": "", "aliases": ["south africa"], "bounds": {"south": -35.2, "north": -22.0, "west": 16.3, "east": 33.3}},
    "south_korea": {"country": "South Korea", "city": "", "aliases": ["south korea", "korea", "republic of korea"], "bounds": {"south": 33.0, "north": 39.5, "west": 124.5, "east": 131.0}},
    "united_arab_emirates": {"country": "United Arab Emirates", "city": "", "aliases": ["united arab emirates", "uae"], "bounds": {"south": 22.5, "north": 26.5, "west": 51.4, "east": 56.6}},
    "uruguay": {"country": "Uruguay", "city": "", "aliases": ["uruguay"], "bounds": {"south": -35.1, "north": -30.0, "west": -58.5, "east": -53.0}},
    "vietnam": {"country": "Vietnam", "city": "", "aliases": ["vietnam", "viet nam"], "bounds": {"south": 8.0, "north": 23.6, "west": 102.0, "east": 110.8}},
}

DATASET_METADATA = STATIC_DATASET_METADATA

_dataset_lock = threading.Lock()
_datasets_cache: Optional[list["_GeoJsonTransportDataset"]] = None
_dataset_file_index_lock = threading.Lock()
_dataset_file_index_cache: Optional[dict[str, dict[str, Optional[Path]]]] = None
_dataset_metadata_map_cache: Optional[dict[str, dict]] = None

# Bounding box used for coordinate-based Europe detection.
# Slightly wider than the dataset bounds to account for coastal/border areas.
EUROPE_BOUNDS = {"south": 34.0, "north": 72.0, "west": -25.0, "east": 45.0}

# Dataset keys that are exclusively European and should only be searched
# when the current location coordinate is within European bounds.
EUROPE_TRANSPORT_DATASETS = {
    EUROPE_INTERNATIONAL_RAIL_KEY,
    "europe_tram",
    "europe_urban_rail",
    "europe_ferry",
    "europe_lift",
}

EUROPE_COUNTRY_HINTS = {
    "albania", "andorra", "austria", "belarus", "belgium", "bosnia and herzegovina",
    "bulgaria", "croatia", "czechia", "czech republic", "denmark", "estonia", "finland",
    "france", "germany", "greece", "hungary", "iceland", "ireland", "italy", "kosovo",
    "latvia", "liechtenstein", "lithuania", "luxembourg", "malta", "moldova", "monaco",
    "montenegro", "netherlands", "north macedonia", "norway", "poland", "portugal",
    "romania", "san marino", "serbia", "slovakia", "slovenia", "spain", "sweden",
    "switzerland", "uk", "united kingdom", "england", "scotland", "wales", "turkey",
    "ukraine", "vatican city", "europe",
}

# Bounding boxes for individual European countries, used to spatially filter
# results returned from Europe-wide datasets (which have no per-feature country tag).
EUROPE_COUNTRY_BOUNDS: dict[str, dict[str, float]] = {
    "albania":                  {"south": 39.6,  "north": 42.7,  "west": 19.2,  "east": 21.1},
    "andorra":                  {"south": 42.4,  "north": 42.7,  "west":  1.4,  "east":  1.8},
    "austria":                  {"south": 46.3,  "north": 49.0,  "west":  9.5,  "east": 17.2},
    "belarus":                  {"south": 51.2,  "north": 56.2,  "west": 23.2,  "east": 32.8},
    "belgium":                  {"south": 49.5,  "north": 51.5,  "west":  2.5,  "east":  6.4},
    "bosnia and herzegovina":   {"south": 42.6,  "north": 45.3,  "west": 15.7,  "east": 19.6},
    "bulgaria":                 {"south": 41.2,  "north": 44.2,  "west": 22.4,  "east": 28.6},
    "croatia":                  {"south": 42.4,  "north": 46.6,  "west": 13.5,  "east": 19.5},
    "czechia":                  {"south": 48.5,  "north": 51.1,  "west": 12.1,  "east": 18.9},
    "czech republic":           {"south": 48.5,  "north": 51.1,  "west": 12.1,  "east": 18.9},
    "denmark":                  {"south": 54.6,  "north": 57.8,  "west":  8.1,  "east": 15.2},
    "england":                  {"south": 49.9,  "north": 55.8,  "west": -6.4,  "east":  2.0},
    "estonia":                  {"south": 57.5,  "north": 59.7,  "west": 21.8,  "east": 28.2},
    "finland":                  {"south": 59.8,  "north": 70.1,  "west": 19.5,  "east": 31.6},
    "france":                   {"south": 41.3,  "north": 51.1,  "west": -5.2,  "east":  9.6},
    "germany":                  {"south": 47.3,  "north": 55.1,  "west":  6.0,  "east": 15.0},
    "greece":                   {"south": 34.8,  "north": 42.0,  "west": 19.4,  "east": 28.3},
    "hungary":                  {"south": 45.7,  "north": 48.6,  "west": 16.1,  "east": 22.9},
    "iceland":                  {"south": 63.3,  "north": 66.6,  "west":-24.5,  "east": -13.5},
    "ireland":                  {"south": 51.4,  "north": 55.4,  "west": -10.5, "east": -6.0},
    "italy":                    {"south": 36.6,  "north": 47.1,  "west":  6.6,  "east": 18.5},
    "kosovo":                   {"south": 41.8,  "north": 43.3,  "west": 20.0,  "east": 21.8},
    "latvia":                   {"south": 55.7,  "north": 58.1,  "west": 21.0,  "east": 28.2},
    "liechtenstein":            {"south": 47.0,  "north": 47.3,  "west":  9.5,  "east":  9.6},
    "lithuania":                {"south": 53.9,  "north": 56.5,  "west": 21.0,  "east": 26.8},
    "luxembourg":               {"south": 49.4,  "north": 50.2,  "west":  5.7,  "east":  6.5},
    "malta":                    {"south": 35.8,  "north": 36.1,  "west": 14.3,  "east": 14.6},
    "moldova":                  {"south": 45.5,  "north": 48.5,  "west": 26.6,  "east": 30.2},
    "monaco":                   {"south": 43.7,  "north": 43.8,  "west":  7.4,  "east":  7.5},
    "montenegro":               {"south": 41.8,  "north": 43.6,  "west": 18.4,  "east": 20.4},
    "netherlands":              {"south": 50.8,  "north": 53.6,  "west":  3.3,  "east":  7.2},
    "north macedonia":          {"south": 40.9,  "north": 42.4,  "west": 20.5,  "east": 23.0},
    "norway":                   {"south": 57.9,  "north": 71.2,  "west":  4.5,  "east": 31.2},
    "poland":                   {"south": 49.0,  "north": 54.9,  "west": 14.1,  "east": 24.2},
    "portugal":                 {"south": 36.8,  "north": 42.2,  "west": -9.5,  "east": -6.2},
    "romania":                  {"south": 43.6,  "north": 48.3,  "west": 20.3,  "east": 29.7},
    "san marino":               {"south": 43.9,  "north": 44.0,  "west": 12.4,  "east": 12.5},
    "scotland":                 {"south": 54.6,  "north": 60.9,  "west": -7.6,  "east": -0.7},
    "serbia":                   {"south": 42.2,  "north": 46.2,  "west": 18.8,  "east": 23.0},
    "slovakia":                 {"south": 47.7,  "north": 49.6,  "west": 16.8,  "east": 22.6},
    "slovenia":                 {"south": 45.4,  "north": 46.9,  "west": 13.4,  "east": 16.6},
    "spain":                    {"south": 35.9,  "north": 43.8,  "west": -9.3,  "east":  4.3},
    "sweden":                   {"south": 55.3,  "north": 69.1,  "west": 10.9,  "east": 24.2},
    "switzerland":              {"south": 45.8,  "north": 47.8,  "west":  5.9,  "east": 10.5},
    "turkey":                   {"south": 35.8,  "north": 42.1,  "west": 25.7,  "east": 44.8},
    "uk":                       {"south": 49.9,  "north": 60.9,  "west": -8.2,  "east":  2.0},
    "united kingdom":           {"south": 49.9,  "north": 60.9,  "west": -8.2,  "east":  2.0},
    "ukraine":                  {"south": 44.4,  "north": 52.4,  "west": 22.2,  "east": 40.2},
    "vatican city":             {"south": 41.9,  "north": 41.91, "west": 12.44, "east": 12.46},
    "wales":                    {"south": 51.3,  "north": 53.5,  "west": -5.3,  "east": -2.6},
}

# Bounding boxes for non-European countries used for hard spatial filtering of
# the global airport dataset (and any other worldwide dataset).
WORLD_COUNTRY_BOUNDS: dict[str, dict[str, float]] = {
    # --- Americas ---
    "antigua and barbuda":  {"south":  16.9, "north":  17.7, "west": -62.0, "east": -61.6},
    "argentina":            {"south": -55.1, "north": -21.8, "west": -73.6, "east": -53.6},
    "bahamas":              {"south":  20.9, "north":  27.3, "west": -80.0, "east": -72.7},
    "barbados":             {"south":  13.0, "north":  13.3, "west": -59.7, "east": -59.4},
    "belize":               {"south":  15.9, "north":  18.5, "west": -89.2, "east": -87.8},
    "bolivia":              {"south": -23.0, "north":  -9.7, "west": -69.7, "east": -57.5},
    "brazil":               {"south": -33.8, "north":   5.3, "west": -73.9, "east": -34.8},
    "canada":               {"south":  41.7, "north":  83.1, "west":-141.0, "east": -52.6},
    "chile":                {"south": -55.9, "north": -17.5, "west": -75.7, "east": -66.4},
    "colombia":             {"south":  -4.2, "north":  13.4, "west": -79.0, "east": -66.9},
    "costa rica":           {"south":   8.0, "north":  11.2, "west": -85.9, "east": -82.6},
    "cuba":                 {"south":  19.8, "north":  23.3, "west": -85.0, "east": -74.1},
    "dominican republic":   {"south":  17.5, "north":  20.0, "west": -72.0, "east": -68.3},
    "ecuador":              {"south":  -5.0, "north":   1.5, "west": -81.0, "east": -75.2},
    "el salvador":          {"south":  13.1, "north":  14.5, "west": -90.1, "east": -87.7},
    "guatemala":            {"south":  13.7, "north":  17.8, "west": -92.2, "east": -88.2},
    "haiti":                {"south":  18.0, "north":  20.1, "west": -74.5, "east": -71.6},
    "honduras":             {"south":  13.0, "north":  16.5, "west": -89.4, "east": -83.1},
    "jamaica":              {"south":  17.7, "north":  18.6, "west": -78.4, "east": -76.2},
    "mexico":               {"south":  14.5, "north":  32.7, "west":-118.5, "east": -86.7},
    "nicaragua":            {"south":  10.7, "north":  15.0, "west": -87.7, "east": -83.1},
    "panama":               {"south":   7.2, "north":   9.7, "west": -83.1, "east": -77.2},
    "paraguay":             {"south": -27.6, "north": -19.3, "west": -62.6, "east": -54.3},
    "peru":                 {"south": -18.4, "north":  -0.0, "west": -81.3, "east": -68.7},
    "trinidad and tobago":  {"south":  10.0, "north":  11.4, "west": -61.9, "east": -60.5},
    "united states":        {"south":  18.9, "north":  71.4, "west":-179.2, "east": -66.9},
    "usa":                  {"south":  18.9, "north":  71.4, "west":-179.2, "east": -66.9},
    "uruguay":              {"south": -34.9, "north": -30.1, "west": -58.4, "east": -53.1},
    "venezuela":            {"south":   0.7, "north":  12.2, "west": -73.4, "east": -59.8},
    # --- East & Southeast Asia ---
    "brunei":               {"south":   4.0, "north":   5.1, "west": 114.1, "east": 115.4},
    "cambodia":             {"south":  10.4, "north":  14.7, "west": 102.3, "east": 107.6},
    "china":                {"south":  18.2, "north":  53.6, "west":  73.5, "east": 134.8},
    "hong kong":            {"south":  22.1, "north":  22.6, "west": 113.8, "east": 114.5},
    "indonesia":            {"south":  -8.5, "north":   5.9, "west":  95.0, "east": 141.0},
    "japan":                {"south":  24.0, "north":  45.6, "west": 122.9, "east": 145.8},
    "laos":                 {"south":  13.9, "north":  22.5, "west": 100.1, "east": 107.7},
    "macau":                {"south":  22.1, "north":  22.2, "west": 113.5, "east": 113.6},
    "malaysia":             {"south":   0.9, "north":   7.4, "west": 99.6,  "east": 119.3},
    "mongolia":             {"south":  41.6, "north":  52.1, "west":  87.8, "east": 119.9},
    "myanmar":              {"south":   9.8, "north":  28.5, "west":  92.2, "east": 101.2},
    "north korea":          {"south":  37.7, "north":  43.0, "west": 124.2, "east": 130.7},
    "philippines":          {"south":   4.6, "north":  21.1, "west": 116.9, "east": 126.6},
    "singapore":            {"south":   1.2, "north":   1.5, "west": 103.6, "east": 104.0},
    "south korea":          {"south":  33.1, "north":  38.6, "west": 124.6, "east": 129.6},
    "korea":                {"south":  33.1, "north":  38.6, "west": 124.6, "east": 129.6},
    "taiwan":               {"south":  21.9, "north":  25.3, "west": 120.0, "east": 122.0},
    "thailand":             {"south":   5.6, "north":  20.5, "west":  97.3, "east": 105.7},
    "timor-leste":          {"south":  -9.5, "north":  -8.1, "west": 124.0, "east": 127.4},
    "vietnam":              {"south":   8.6, "north":  23.4, "west": 102.1, "east": 109.5},
    # --- South Asia ---
    "bangladesh":           {"south":  20.7, "north":  26.6, "west":  88.0, "east":  92.7},
    "bhutan":               {"south":  26.7, "north":  28.3, "west":  88.7, "east":  92.1},
    "india":                {"south":   8.0, "north":  35.5, "west":  68.1, "east":  97.4},
    "maldives":             {"south":  -0.7, "north":   7.1, "west":  72.7, "east":  73.8},
    "nepal":                {"south":  26.4, "north":  30.4, "west":  80.1, "east":  88.2},
    "pakistan":             {"south":  23.6, "north":  36.9, "west":  60.9, "east":  77.8},
    "sri lanka":            {"south":   5.9, "north":   9.8, "west":  79.7, "east":  81.9},
    # --- Central Asia ---
    "afghanistan":          {"south":  29.4, "north":  38.5, "west":  60.5, "east":  74.9},
    "kazakhstan":           {"south":  40.6, "north":  55.4, "west":  50.3, "east":  87.3},
    "kyrgyzstan":           {"south":  39.2, "north":  43.2, "west":  69.3, "east":  80.3},
    "tajikistan":           {"south":  36.7, "north":  41.0, "west":  67.3, "east":  75.2},
    "turkmenistan":         {"south":  35.1, "north":  42.8, "west":  52.4, "east":  66.7},
    "uzbekistan":           {"south":  37.2, "north":  45.6, "west":  56.0, "east":  73.1},
    # --- Middle East ---
    "bahrain":              {"south":  25.8, "north":  26.3, "west":  50.4, "east":  50.8},
    "cyprus":               {"south":  34.6, "north":  35.7, "west":  32.3, "east":  34.6},
    "iran":                 {"south":  25.1, "north":  39.8, "west":  44.0, "east":  63.3},
    "iraq":                 {"south":  29.1, "north":  37.4, "west":  38.8, "east":  48.6},
    "israel":               {"south":  29.5, "north":  33.3, "west":  34.3, "east":  35.9},
    "jordan":               {"south":  29.2, "north":  33.4, "west":  35.0, "east":  39.3},
    "kuwait":               {"south":  28.5, "north":  30.1, "west":  46.6, "east":  48.4},
    "lebanon":              {"south":  33.1, "north":  34.7, "west":  35.1, "east":  36.6},
    "oman":                 {"south":  16.7, "north":  26.4, "west":  51.9, "east":  59.8},
    "palestine":            {"south":  31.2, "north":  32.5, "west":  34.2, "east":  35.6},
    "qatar":                {"south":  24.5, "north":  26.2, "west":  50.7, "east":  51.7},
    "saudi arabia":         {"south":  16.3, "north":  32.2, "west":  34.6, "east":  55.7},
    "syria":                {"south":  32.3, "north":  37.3, "west":  35.7, "east":  42.4},
    "uae":                  {"south":  22.6, "north":  26.1, "west":  51.6, "east":  56.4},
    "united arab emirates": {"south":  22.6, "north":  26.1, "west":  51.6, "east":  56.4},
    "yemen":                {"south":  12.1, "north":  19.0, "west":  42.5, "east":  54.0},
    # --- Africa ---
    "algeria":              {"south":  18.9, "north":  37.1, "west":  -8.7, "east":   9.0},
    "angola":               {"south": -18.1, "north":  -4.4, "west":  11.7, "east":  24.1},
    "cameroon":             {"south":   1.7, "north":  13.1, "west":   8.5, "east":  16.2},
    "democratic republic of the congo": {"south": -13.5, "north": 5.4, "west": 12.2, "east": 31.3},
    "drc":                  {"south": -13.5, "north":   5.4, "west":  12.2, "east":  31.3},
    "egypt":                {"south":  22.0, "north":  31.7, "west":  24.7, "east":  37.1},
    "ethiopia":             {"south":   3.4, "north":  14.9, "west":  33.0, "east":  48.0},
    "ghana":                {"south":   4.7, "north":  11.2, "west":  -3.3, "east":   1.2},
    "ivory coast":          {"south":   4.3, "north":  10.7, "west":  -8.6, "east":  -2.5},
    "cote d'ivoire":        {"south":   4.3, "north":  10.7, "west":  -8.6, "east":  -2.5},
    "kenya":                {"south":  -4.7, "north":   4.6, "west":  34.0, "east":  42.0},
    "libya":                {"south":  19.5, "north":  33.2, "west":   9.3, "east":  25.2},
    "madagascar":           {"south": -25.6, "north": -11.9, "west":  43.2, "east":  50.5},
    "mali":                 {"south":  10.1, "north":  25.0, "west": -12.2, "east":   4.2},
    "mauritius":            {"south": -20.5, "north": -19.9, "west":  57.3, "east":  57.8},
    "morocco":              {"south":  27.7, "north":  35.9, "west": -13.2, "east":  -1.0},
    "mozambique":           {"south": -26.9, "north": -10.5, "west":  30.2, "east":  40.9},
    "namibia":              {"south": -29.0, "north": -16.9, "west":  11.7, "east":  25.3},
    "nigeria":              {"south":   4.3, "north":  13.9, "west":   2.7, "east":  14.7},
    "rwanda":               {"south":  -2.8, "north":  -1.1, "west":  28.9, "east":  30.9},
    "senegal":              {"south":  12.3, "north":  16.7, "west": -17.5, "east":  -11.3},
    "somalia":              {"south":  -1.7, "north":  12.0, "west":  41.0, "east":  51.4},
    "south africa":         {"south": -34.8, "north": -22.1, "west":  16.5, "east":  32.9},
    "south sudan":          {"south":   3.5, "north":  12.2, "west":  23.4, "east":  36.9},
    "sudan":                {"south":   8.7, "north":  22.2, "west":  21.8, "east":  38.6},
    "tanzania":             {"south": -11.7, "north":  -0.9, "west":  29.3, "east":  40.4},
    "tunisia":              {"south":  30.2, "north":  37.5, "west":   7.5, "east":  11.6},
    "uganda":               {"south":  -1.5, "north":   4.2, "west":  29.6, "east":  35.0},
    "zambia":               {"south": -18.1, "north":  -8.2, "west":  22.0, "east":  33.7},
    "zimbabwe":             {"south": -22.4, "north": -15.6, "west":  25.2, "east":  33.1},
    # --- Oceania ---
    "australia":            {"south": -43.7, "north": -10.7, "west": 113.3, "east": 153.6},
    "fiji":                 {"south": -19.2, "north": -15.7, "west": 177.1, "east": 180.0},
    "new zealand":          {"south": -47.3, "north": -34.4, "west": 166.4, "east": 178.6},
    "papua new guinea":     {"south":  -11.7, "north":  -0.9, "west": 141.0, "east": 155.7},
    "solomon islands":      {"south": -11.9, "north":  -5.5, "west": 155.5, "east": 162.8},
    "vanuatu":              {"south": -20.2, "north": -13.1, "west": 166.5, "east": 170.2},
    # --- Russia & Caucasus ---
    "armenia":              {"south":  38.8, "north":  41.3, "west":  43.4, "east":  46.6},
    "azerbaijan":           {"south":  38.4, "north":  41.9, "west":  44.8, "east":  50.4},
    "georgia":              {"south":  41.1, "north":  43.6, "west":  40.0, "east":  46.7},
    "russia":               {"south":  41.2, "north":  81.9, "west":  19.6, "east": 180.0},
}


def _is_europe_coordinate(lat: float, lon: float) -> bool:
    """Return True when the coordinate falls within the European bounding box."""
    return (
        EUROPE_BOUNDS["south"] <= lat <= EUROPE_BOUNDS["north"]
        and EUROPE_BOUNDS["west"] <= lon <= EUROPE_BOUNDS["east"]
    )


def _country_bbox(country_hint: Optional[str]) -> Optional[dict[str, float]]:
    """Return the bounding box for any country (Europe or worldwide) by name, or None if unknown."""
    if not country_hint:
        return None
    key = _normalize_text(country_hint)
    return EUROPE_COUNTRY_BOUNDS.get(key) or WORLD_COUNTRY_BOUNDS.get(key)


def _europe_country_bbox(country_hint: Optional[str]) -> Optional[dict[str, float]]:
    """Return the bounding box for a European country by name, or None if unknown.
    Kept for backward-compatibility; now delegates to _country_bbox."""
    return _country_bbox(country_hint)


def _default_dataset_metadata(key: str) -> dict:
    return {
        "country": key.replace("_", " ").title(),
        "city": "",
        "aliases": [key.replace("_", " ")],
    }


def _slugify_path_part(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower())
    return re.sub(r"_+", "_", slug).strip("_")


def dataset_country_directory_name(country_name: Optional[str]) -> str:
    return _slugify_path_part(country_name or "") or "misc"


def dataset_country_directory(country_name: Optional[str]) -> Path:
    return DATASET_DIR / dataset_country_directory_name(country_name)


def dataset_output_path(filename: str, country_name: Optional[str]) -> Path:
    return dataset_country_directory(country_name) / filename


def _dataset_search_roots() -> list[Path]:
    roots: list[Path] = []
    if DATASET_DIR.exists():
        roots.append(DATASET_DIR)
    if LEGACY_DATASET_DIR.exists():
        roots.append(LEGACY_DATASET_DIR)
    return roots


def _build_dataset_file_index() -> dict[str, dict[str, Optional[Path]]]:
    line_paths_by_name: dict[str, Path] = {}
    station_paths_by_key: dict[str, Path] = {}

    for root in _dataset_search_roots():
        geojson_iter = root.rglob("*.geojson") if root == DATASET_DIR else root.glob("*.geojson")
        for path in sorted(geojson_iter):
            stem = path.stem
            if stem.endswith("_station"):
                key = stem.removesuffix("_station")
                station_paths_by_key.setdefault(key, path)
                continue
            line_paths_by_name.setdefault(path.name.lower(), path)

    index: dict[str, dict[str, Optional[Path]]] = {}
    for key, station_path in station_paths_by_key.items():
        expected_rail_path = station_path.with_name(f"{key}.geojson")
        rail_path = expected_rail_path if expected_rail_path.exists() else line_paths_by_name.get(f"{key}.geojson")
        index[key] = {
            "key": key,
            "station_path": station_path,
            "rail_path": rail_path,
        }
    return index


def get_dataset_file_index() -> dict[str, dict[str, Optional[Path]]]:
    global _dataset_file_index_cache
    if _dataset_file_index_cache is not None:
        return _dataset_file_index_cache

    with _dataset_file_index_lock:
        if _dataset_file_index_cache is None:
            _dataset_file_index_cache = _build_dataset_file_index()
        return _dataset_file_index_cache


def get_dataset_file_paths(dataset_key: str) -> dict[str, Optional[Path]]:
    return get_dataset_file_index().get(
        dataset_key,
        {
            "key": dataset_key,
            "station_path": None,
            "rail_path": None,
        },
    )


def load_imported_dataset_metadata() -> dict[str, dict]:
    if not IMPORTED_DATASET_METADATA_PATH.exists():
        return {}
    try:
        with IMPORTED_DATASET_METADATA_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        logger.warning("geojson_transport: failed to read imported dataset metadata: %s", exc)
        return {}

    if not isinstance(payload, dict):
        logger.warning("geojson_transport: imported dataset metadata is not a JSON object")
        return {}

    metadata: dict[str, dict] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        metadata[key] = value
    return metadata


def load_import_task_dataset_metadata() -> dict[str, dict]:
    if not IMPORT_TASKS_PATH.exists():
        return {}
    try:
        with IMPORT_TASKS_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        logger.warning("geojson_transport: failed to read import task history: %s", exc)
        return {}

    if not isinstance(payload, list):
        return {}

    metadata: dict[str, dict] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "completed":
            continue
        dataset_key = str(item.get("dataset_key") or "").strip()
        country_name = str(item.get("country_name") or "").strip()
        city_name = str(item.get("city_name") or "").strip()
        if not dataset_key or not country_name:
            continue

        aliases = [dataset_key.replace("_", " "), country_name.lower()]
        if city_name:
            aliases.extend([city_name.lower(), f"{city_name.lower()} {country_name.lower()}"])

        deduped_aliases: list[str] = []
        seen: set[str] = set()
        for alias in aliases:
            normalized_alias = _normalize_text(alias)
            if not normalized_alias or normalized_alias in seen:
                continue
            seen.add(normalized_alias)
            deduped_aliases.append(normalized_alias)

        metadata[dataset_key] = {
            "country": country_name,
            "city": city_name,
            "aliases": deduped_aliases,
        }
    return metadata


def get_dataset_metadata_map() -> dict[str, dict]:
    global _dataset_metadata_map_cache
    if _dataset_metadata_map_cache is not None:
        return _dataset_metadata_map_cache

    metadata = dict(STATIC_DATASET_METADATA)
    metadata.update(load_import_task_dataset_metadata())
    metadata.update(load_imported_dataset_metadata())
    _dataset_metadata_map_cache = metadata
    return _dataset_metadata_map_cache


def get_dataset_metadata(key: str) -> dict:
    return get_dataset_metadata_map().get(key, _default_dataset_metadata(key))


def save_imported_dataset_metadata(dataset_key: str, metadata: dict) -> None:
    DATASET_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    current = load_imported_dataset_metadata()
    current[dataset_key] = metadata
    _write_imported_dataset_metadata(current)
    global _dataset_metadata_map_cache
    _dataset_metadata_map_cache = None


def remove_imported_dataset_metadata(dataset_key: str) -> None:
    current = load_imported_dataset_metadata()
    if dataset_key in current:
        del current[dataset_key]
    _write_imported_dataset_metadata(current)
    global _dataset_metadata_map_cache
    _dataset_metadata_map_cache = None


def _write_imported_dataset_metadata(current: dict[str, dict]) -> None:
    temp_path = IMPORTED_DATASET_METADATA_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(IMPORTED_DATASET_METADATA_PATH)


def _normalize_text(value: str) -> str:
    text = " ".join((value or "").strip().lower().split())
    text = (
        text.replace("ø", "o")
        .replace("œ", "oe")
        .replace("æ", "ae")
        .replace("å", "a")
        .replace("ö", "o")
        .replace("ü", "u")
        .replace("ä", "a")
        .replace("ß", "ss")
    )
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("ascii")


def _matches_special_excursion_country(country_hint: Optional[str]) -> bool:
    if not country_hint:
        return True
    return _normalize_text(country_hint) in {"switzerland", "swiss"}


def _load_special_excursion_stations() -> list[dict]:
    db = SessionLocal()
    try:
        return list_special_excursion_stations(db)
    except Exception:
        logger.exception("geojson_transport: failed to load special excursion stations from alias overrides")
        return []
    finally:
        db.close()


def _search_special_excursion_stations(
    query: str,
    *,
    country_hint: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    if not _matches_special_excursion_country(country_hint):
        return []

    normalized_query = _normalize_text(query)
    if not normalized_query:
        return []

    ranked: list[tuple[int, dict]] = []
    for station in _load_special_excursion_stations():
        place_norm = _normalize_text(station["place_name"])
        city_norm = _normalize_text(station.get("city") or "")
        if place_norm == normalized_query:
            best_score = 600
        elif place_norm.startswith(normalized_query):
            best_score = 500
        elif normalized_query in place_norm or (city_norm and normalized_query in city_norm):
            best_score = 400
        else:
            continue
        ranked.append((
            best_score,
            {
                "id": station["id"],
                "place_name": station["place_name"],
                "city": station["city"],
                "country": station["country"],
                "latitude": station["latitude"],
                "longitude": station["longitude"],
                "subtitle": ", ".join(part for part in [station["city"], station["country"]] if part),
                "source": station["source"],
            },
        ))

    ranked.sort(key=lambda item: (-item[0], item[1]["place_name"]))
    return [result for _, result in ranked[:limit]]


def _nearest_special_excursion_station(
    lat: float,
    lon: float,
    *,
    country_hint: Optional[str] = None,
    max_distance_meters: Optional[float] = None,
) -> Optional[dict]:
    if not _matches_special_excursion_country(country_hint):
        return None

    best_station = None
    best_distance = None
    for station in _load_special_excursion_stations():
        distance = _haversine_meters(lat, lon, station["latitude"], station["longitude"])
        distance_limit = max_distance_meters or SPECIAL_EXCURSION_STATION_MATCH_RADIUS_METERS
        if distance > distance_limit:
            continue
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_station = {
                "name": station["place_name"],
                "place_name": station["place_name"],
                "latitude": station["latitude"],
                "longitude": station["longitude"],
                "distance_meters": round(distance, 1),
                "city": station["city"],
                "country": station["country"],
                "railway_type": "aerialway_station",
                "transport_mode": "excursion",
                "source": station["source"],
                "tags": {"special_case": "lauterbrunnen_grutschalp_excursion", "managed_by": "admin_alias_override"},
                "osm_id": station["id"],
                "dataset_key": "special_excursion",
            }
    return best_station


def _is_special_excursion_pair(lat1: float, lon1: float, lat2: float, lon2: float) -> bool:
    station_a = _nearest_special_excursion_station(
        lat1,
        lon1,
        country_hint="Switzerland",
        max_distance_meters=SPECIAL_EXCURSION_STATION_MATCH_RADIUS_METERS,
    )
    station_b = _nearest_special_excursion_station(
        lat2,
        lon2,
        country_hint="Switzerland",
        max_distance_meters=SPECIAL_EXCURSION_STATION_MATCH_RADIUS_METERS,
    )
    if not station_a or not station_b:
        return False
    return station_a["place_name"] != station_b["place_name"]


def _distance_sq(a: list[float], b: list[float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _polyline_length(points: list[list[float]]) -> float:
    total = 0.0
    for index in range(len(points) - 1):
        total += math.sqrt(_distance_sq(points[index], points[index + 1]))
    return total


def _dedupe_points(points: list[list[float]]) -> list[list[float]]:
    deduped: list[list[float]] = []
    for lat, lon in points:
        if not deduped or deduped[-1][0] != lat or deduped[-1][1] != lon:
            deduped.append([lat, lon])
    return deduped


def _graph_node_key(point: list[float]) -> str:
    return f"{point[0]:.6f},{point[1]:.6f}"


def _nearest_graph_candidates(
    graph_nodes: dict[str, list[float]],
    target: list[float],
    limit: int = GRAPH_NODE_CANDIDATE_LIMIT,
) -> list[tuple[str, list[float], float]]:
    candidates: list[tuple[str, list[float], float]] = []
    for key, point in graph_nodes.items():
        candidates.append((key, point, _distance_sq(point, target)))
    candidates.sort(key=lambda item: item[2])
    return candidates[:limit]


def _shortest_graph_path(
    adjacency: dict[str, list[tuple[str, float]]],
    graph_nodes: dict[str, list[float]],
    start_key: str,
    end_key: str,
) -> Optional[list[list[float]]]:
    queue: list[tuple[float, str]] = [(0.0, start_key)]
    distances = {start_key: 0.0}
    previous: dict[str, Optional[str]] = {start_key: None}

    while queue:
        current_distance, current_key = heapq.heappop(queue)
        if current_key == end_key:
            break
        if current_distance > distances.get(current_key, float("inf")):
            continue
        for next_key, edge_weight in adjacency.get(current_key, []):
            next_distance = current_distance + edge_weight
            if next_distance >= distances.get(next_key, float("inf")):
                continue
            distances[next_key] = next_distance
            previous[next_key] = current_key
            heapq.heappush(queue, (next_distance, next_key))

    if end_key not in previous:
        return None

    keys: list[str] = []
    current_key: Optional[str] = end_key
    while current_key is not None:
        keys.append(current_key)
        current_key = previous.get(current_key)
    keys.reverse()
    return [graph_nodes[key] for key in keys if key in graph_nodes]


_ISO_CODE_RE = re.compile(r'^[A-Z]{2,3}$')


def _resolve_station_country(properties: dict, dataset_country: str) -> str:
    """Return a usable country name from OSM properties, falling back to the dataset's country.

    OSM tags often use ISO 2/3-letter codes like ``addr:country=CN``. These are
    not meaningful to the UI, so treat them the same as missing and fall back to
    the dataset-level country name (e.g. "China").
    """
    raw = str(properties.get("addr:country") or "").strip() or str(properties.get("is_in:country") or "").strip()
    if raw and not _ISO_CODE_RE.match(raw):
        return raw
    return dataset_country


def _extract_aliases(properties: dict) -> list[str]:
    aliases = []
    for key in (
        "name:en",
        "official_name:en",
        "alt_name:en",
        "short_name:en",
        "int_name",
        "official_name",
        "uic_name",
        "short_name",
        "name",
        "name:zh",
        "name:zh-Hans",
        "name:zh-Hant",
        "name:ar",
        "name:ko",
        "name:vi",
        "alt_name",
        "alt_name:zh",
    ):
        value = str(properties.get(key) or "").strip()
        if value:
            aliases.append(value)

    deduped: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        normalized = _normalize_text(alias)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(alias)
    return deduped


def _preferred_name(properties: dict, fallback: str) -> str:
    aliases = _extract_aliases(properties)
    return aliases[0] if aliases else fallback


def _train_rank(properties: dict) -> int:
    railway = str(properties.get("railway") or "").strip().lower()
    station = str(properties.get("station") or "").strip().lower()
    public_transport = str(properties.get("public_transport") or "").strip().lower()
    building = str(properties.get("building") or "").strip().lower()
    train = str(properties.get("train") or "").strip().lower()
    subway = str(properties.get("subway") or "").strip().lower()
    light_rail = str(properties.get("light_rail") or "").strip().lower()
    operator = str(properties.get("operator") or "").strip().lower()
    network = str(properties.get("network") or "").strip().lower()
    name = str(properties.get("name") or "").strip().lower()

    score = 0
    if railway == "station":
        score += 6
    elif railway in {"halt", "stop"}:
        score += 4
    elif railway in {"tram_stop", "subway_entrance"}:
        score += 2

    if station == "train":
        score += 4
    elif station in {"subway", "light_rail", "monorail"}:
        score -= 4
    if public_transport == "station":
        score += 3
    elif public_transport in {"platform", "stop_position"}:
        score += 1
    if building == "train_station":
        score += 3
    if train == "yes":
        score += 2
    if subway == "yes":
        score -= 6
    if light_rail == "yes":
        score -= 5
    if "s-bahn" in operator or "s bahn" in operator or "s-bahn" in network or "s bahn" in network:
        score -= 4
    if "metro" in operator or "metro" in network:
        score -= 4
    if "tram" in name or "tram" in operator or "tram" in network:
        score -= 3
    return score


def _matches_train(properties: dict) -> bool:
    railway = str(properties.get("railway") or "").strip().lower()
    station = str(properties.get("station") or "").strip().lower()
    public_transport = str(properties.get("public_transport") or "").strip().lower()
    construction_railway = str(properties.get("construction:railway") or "").strip().lower()
    train = str(properties.get("train") or "").strip().lower()
    subway = str(properties.get("subway") or "").strip().lower()
    monorail = str(properties.get("monorail") or "").strip().lower()

    if railway in {"station", "halt", "stop", "tram_stop", "subway_entrance"}:
        return True
    if station in {"train", "subway", "light_rail", "monorail"}:
        return True
    if construction_railway == "station":
        return True
    if subway == "yes" or monorail == "yes" or train == "yes":
        return True
    if public_transport in {"station", "platform", "stop_position"} and (
        railway or station or train == "yes" or subway == "yes" or monorail == "yes"
    ):
        return True
    return False


def _matches_bus(properties: dict) -> bool:
    amenity = str(properties.get("amenity") or "").strip().lower()
    highway = str(properties.get("highway") or "").strip().lower()
    public_transport = str(properties.get("public_transport") or "").strip().lower()
    bus = str(properties.get("bus") or "").strip().lower()
    coach = str(properties.get("coach") or "").strip().lower()
    if amenity == "bus_station" or highway == "bus_stop":
        return True
    if bus == "yes" or coach == "yes":
        return True
    if public_transport in {"station", "platform", "stop_position"} and (bus == "yes" or coach == "yes"):
        return True
    return False


def _matches_ferry(properties: dict) -> bool:
    amenity = str(properties.get("amenity") or "").strip().lower()
    ferry = str(properties.get("ferry") or "").strip().lower()
    harbour = str(properties.get("harbour") or "").strip().lower()
    route = str(properties.get("route") or "").strip().lower()
    if amenity == "ferry_terminal":
        return True
    if ferry in {"yes", "terminal"}:
        return True
    if "ferry" in harbour or route == "ferry":
        return True
    return False


def _matches_flight(properties: dict) -> bool:
    """Return True for airport / aerodrome features (imported via per-country airport files)."""
    aeroway = str(properties.get("aeroway") or "").strip().lower()
    return aeroway in {"aerodrome", "terminal"}


def _matches_excursion(properties: dict) -> bool:
    aerialway = str(properties.get("aerialway") or "").strip().lower()
    tourism = str(properties.get("tourism") or "").strip().lower()
    public_transport = str(properties.get("public_transport") or "").strip().lower()
    station = str(properties.get("station") or "").strip().lower()
    if aerialway in {
        "cable_car",
        "gondola",
        "chair_lift",
        "mixed_lift",
        "drag_lift",
        "t-bar",
        "j-bar",
        "platter",
        "rope_tow",
        "magic_carpet",
        "zip_line",
        "station",
    }:
        return True
    if tourism in {"theme_park", "attraction"} and station in {"gondola", "cable_car", "chair_lift"}:
        return True
    if public_transport in {"station", "platform"} and aerialway:
        return True
    return False


def _is_rail_line_feature(properties: dict) -> bool:
    railway = str(properties.get("railway") or "").strip().lower()
    route = str(properties.get("route") or "").strip().lower()
    construction_railway = str(properties.get("construction:railway") or "").strip().lower()
    return (
        railway in {"rail", "light_rail", "subway", "tram", "monorail", "narrow_gauge"}
        or route in {"train", "subway", "light_rail", "tram", "monorail"}
        or construction_railway in {"rail", "light_rail", "subway", "tram", "monorail"}
    )


def _is_excursion_line_feature(properties: dict) -> bool:
    aerialway = str(properties.get("aerialway") or "").strip().lower()
    route = str(properties.get("route") or "").strip().lower()
    return aerialway in {
        "cable_car",
        "gondola",
        "chair_lift",
        "mixed_lift",
        "drag_lift",
        "t-bar",
        "j-bar",
        "platter",
        "rope_tow",
        "magic_carpet",
        "zip_line",
    } or route in {"aerialway", "ski", "piste"}


def _bbox_from_points(points: list[list[float]]) -> Optional[tuple[float, float, float, float]]:
    if not points:
        return None
    lats = [point[0] for point in points]
    lons = [point[1] for point in points]
    return min(lats), max(lats), min(lons), max(lons)


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


class _GeoJsonTransportDataset:
    def __init__(self, key: str, station_path: Path, rail_path: Optional[Path], metadata: dict):
        self.key = key
        self.station_path = station_path
        self.rail_path = rail_path
        self.country = (metadata.get("country") or key.replace("_", " ")).title()
        self.city = metadata.get("city") or ""
        self.aliases = [_normalize_text(alias) for alias in metadata.get("aliases") or []]
        self.bounds = metadata.get("bounds") or _country_bbox(self.country)
        self._station_lock = threading.Lock()
        self._station_items: Optional[list[dict]] = None
        self._bbox: Optional[tuple[float, float, float, float]] = None
        self._graph_nodes_by_kind: dict[str, dict[str, list[float]]] = {}
        self._adjacency_by_kind: dict[str, dict[str, list[tuple[str, float]]]] = {}

    def matches_country_hint(self, country_hint: Optional[str]) -> bool:
        if not country_hint:
            return True
        normalized = _normalize_text(country_hint)
        if not normalized:
            return True
        return normalized in self.aliases or normalized == _normalize_text(self.country) or normalized == _normalize_text(self.city)

    def contains_coordinate(self, lat: float, lon: float) -> bool:
        if self.bounds:
            south = float(self.bounds["south"])
            north = float(self.bounds["north"])
            west = float(self.bounds["west"])
            east = float(self.bounds["east"])
        else:
            self._ensure_station_items()
            if self._bbox is None:
                return False
            south, north, west, east = self._bbox
        return (
            south - BOUND_PADDING_DEGREES <= lat <= north + BOUND_PADDING_DEGREES
            and west - BOUND_PADDING_DEGREES <= lon <= east + BOUND_PADDING_DEGREES
        )

    def _ensure_station_items(self) -> list[dict]:
        if self._station_items is not None:
            return self._station_items

        with self._station_lock:
            if self._station_items is not None:
                return self._station_items

            with self.station_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)

            items: list[dict] = []
            bbox_points: list[list[float]] = []
            for feature in data.get("features") or []:
                geometry = feature.get("geometry") or {}
                if geometry.get("type") != "Point":
                    continue
                coordinates = geometry.get("coordinates") or []
                if len(coordinates) < 2:
                    continue

                lon = float(coordinates[0])
                lat = float(coordinates[1])
                properties = feature.get("properties") or {}
                methods: set[str] = set()
                if _matches_train(properties):
                    methods.add("train")
                if _matches_bus(properties):
                    methods.add("bus")
                if _matches_ferry(properties):
                    methods.add("ferry")
                if _matches_excursion(properties):
                    methods.add("excursion")
                if _matches_flight(properties):
                    methods.add("flight")
                if not methods:
                    continue

                aliases = _extract_aliases(properties)
                items.append(
                    {
                        "dataset_key": self.key,
                        "name": aliases[0] if aliases else f"{self.country} transport stop",
                        "aliases": aliases,
                        "has_name": bool(aliases),
                        "train_rank": _train_rank(properties),
                        "latitude": lat,
                        "longitude": lon,
                        "city": str(properties.get("addr:city") or "").strip() or str(properties.get("is_in:city") or "").strip() or self.city,
                        "country": _resolve_station_country(properties, self.country),
                        "railway_type": str(properties.get("station") or "").strip() or str(properties.get("railway") or "").strip() or str(properties.get("public_transport") or "").strip() or next(iter(methods)),
                        "methods": methods,
                        "tags": properties,
                        "osm_id": str(properties.get("@id") or ""),
                        "source": f"{self.key}_station_geojson",
                    }
                )
                bbox_points.append([lat, lon])

            self._station_items = items
            self._bbox = _bbox_from_points(bbox_points)
            logger.info("%s: loaded %s transport points", self.key, len(items))
            return items

    def _load_graph(self, kind: str) -> tuple[dict[str, list[float]], dict[str, list[tuple[str, float]]]]:
        if kind in self._graph_nodes_by_kind and kind in self._adjacency_by_kind:
            return self._graph_nodes_by_kind[kind], self._adjacency_by_kind[kind]

        graph_nodes: dict[str, list[float]] = {}
        adjacency: dict[str, list[tuple[str, float]]] = {}
        bbox_points: list[list[float]] = []

        if not self.rail_path or not self.rail_path.exists():
            self._graph_nodes_by_kind[kind] = graph_nodes
            self._adjacency_by_kind[kind] = adjacency
            return graph_nodes, adjacency

        with self.rail_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        for feature in data.get("features") or []:
            properties = feature.get("properties") or {}
            feature_matches = _is_rail_line_feature(properties) if kind == "train" else _is_excursion_line_feature(properties)
            if not feature_matches:
                continue

            geometry = feature.get("geometry") or {}
            geometry_type = geometry.get("type")
            coordinates = geometry.get("coordinates") or []
            line_sets = [coordinates] if geometry_type == "LineString" else coordinates if geometry_type == "MultiLineString" else []
            for line in line_sets:
                points = _dedupe_points([[float(pair[1]), float(pair[0])] for pair in line if len(pair) >= 2])
                if len(points) < 2:
                    continue
                bbox_points.extend(points)
                for index in range(len(points) - 1):
                    point_a = points[index]
                    point_b = points[index + 1]
                    key_a = _graph_node_key(point_a)
                    key_b = _graph_node_key(point_b)
                    graph_nodes[key_a] = point_a
                    graph_nodes[key_b] = point_b
                    weight = math.sqrt(_distance_sq(point_a, point_b))
                    adjacency.setdefault(key_a, []).append((key_b, weight))
                    adjacency.setdefault(key_b, []).append((key_a, weight))

        self._graph_nodes_by_kind[kind] = graph_nodes
        self._adjacency_by_kind[kind] = adjacency
        bbox = _bbox_from_points(bbox_points)
        if bbox is not None:
            if self._bbox is None:
                self._bbox = bbox
            else:
                south, north, west, east = self._bbox
                rail_south, rail_north, rail_west, rail_east = bbox
                self._bbox = (
                    min(south, rail_south),
                    max(north, rail_north),
                    min(west, rail_west),
                    max(east, rail_east),
                )
        return graph_nodes, adjacency

    def supports_method(self, method: str) -> bool:
        return any(method in item["methods"] for item in self._ensure_station_items())

    def search(self, query: str, method: str, limit: int = 10, country_bbox: Optional[dict] = None) -> list[dict]:
        normalized_query = _normalize_text(query)
        if not normalized_query:
            return []

        ranked: list[tuple[int, dict]] = []
        for item in self._ensure_station_items():
            if method not in item["methods"]:
                continue

            # When a country bounding box is provided (e.g. Italy inside the Europe dataset)
            # only include stations whose coordinates fall within that box.
            if country_bbox is not None:
                if not (
                    country_bbox["south"] <= item["latitude"] <= country_bbox["north"]
                    and country_bbox["west"] <= item["longitude"] <= country_bbox["east"]
                ):
                    continue

            best_score = None
            for alias in item.get("aliases") or [item["name"]]:
                normalized_alias = _normalize_text(alias)
                if not normalized_alias:
                    continue
                if normalized_alias == normalized_query:
                    score = 500
                elif normalized_alias.startswith(normalized_query):
                    score = 400
                elif normalized_query in normalized_alias:
                    score = 300
                else:
                    continue
                if best_score is None or score > best_score:
                    best_score = score

            if best_score is None:
                continue

            ranked.append(
                (
                    best_score,
                    {
                        "id": item["osm_id"] or f"{self.key}-{method}-{item['latitude']:.6f}-{item['longitude']:.6f}",
                        "place_name": item["name"],
                        "city": item["city"],
                        "country": item["country"],
                        "latitude": item["latitude"],
                        "longitude": item["longitude"],
                        "subtitle": ", ".join(part for part in [item["city"], item["country"]] if part),
                        "source": item["source"],
                        "train_rank": item["train_rank"],
                    },
                )
            )

        ranked.sort(key=lambda entry: (-entry[0], -int(entry[1].get("train_rank") or 0), entry[1]["place_name"]))
        results: list[dict] = []
        seen: set[str] = set()
        for _, result in ranked:
            dedupe_key = f"{_normalize_text(result['place_name'])}|{_normalize_text(result['country'])}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            results.append(result)
            if len(results) >= limit:
                break
        return results

    def nearest(self, lat: float, lon: float, method: str, max_distance_meters: Optional[float] = None, country_bbox: Optional[dict] = None) -> Optional[dict]:
        candidates: list[tuple[float, dict]] = []
        for item in self._ensure_station_items():
            if method not in item["methods"]:
                continue
            # Filter to country bounding box when provided (for Europe-wide datasets).
            if country_bbox is not None:
                if not (
                    country_bbox["south"] <= item["latitude"] <= country_bbox["north"]
                    and country_bbox["west"] <= item["longitude"] <= country_bbox["east"]
                ):
                    continue
            distance = _haversine_meters(lat, lon, item["latitude"], item["longitude"])
            if max_distance_meters is not None and distance > max_distance_meters:
                continue
            candidates.append((distance, item))

        if not candidates:
            return None

        if method == "train":
            named_candidates = [(distance, item) for distance, item in candidates if item.get("has_name")]
            strong_named_candidates = [
                (distance, item)
                for distance, item in named_candidates
                if int(item.get("train_rank") or 0) >= 4
            ]
            if strong_named_candidates:
                candidates = strong_named_candidates
            elif named_candidates:
                candidates = named_candidates

            best_distance = min(distance for distance, _ in candidates)
            close_candidates = [
                (distance, item)
                for distance, item in candidates
                if distance <= best_distance + 250.0
            ]
            if close_candidates:
                candidates = close_candidates

        candidates.sort(key=lambda entry: (entry[0], -int(entry[1].get("train_rank") or 0)))
        if method == "train":
            candidates.sort(key=lambda entry: (-int(entry[1].get("train_rank") or 0), entry[0]))
        best_distance, best_item = candidates[0]

        return {
            "name": best_item["name"],
            "place_name": best_item["name"],
            "latitude": best_item["latitude"],
            "longitude": best_item["longitude"],
            "distance_meters": round(best_distance, 1),
            "city": best_item["city"],
            "country": best_item["country"],
            "railway_type": best_item["railway_type"],
            "transport_mode": method,
            "source": best_item["source"],
            "tags": best_item["tags"],
            "osm_id": best_item["osm_id"],
            "dataset_key": self.key,
        }

    def build_route(self, lat1: float, lon1: float, lat2: float, lon2: float, kind: str) -> Optional[dict]:
        if not (self.contains_coordinate(lat1, lon1) and self.contains_coordinate(lat2, lon2)):
            return None

        graph_nodes, adjacency = self._load_graph(kind)
        if not graph_nodes:
            return None

        start = [lat1, lon1]
        end = [lat2, lon2]
        max_snap_dist = GRAPH_NODE_SNAP_RADIUS_DEGREES ** 2
        start_candidates = [candidate for candidate in _nearest_graph_candidates(graph_nodes, start) if candidate[2] <= max_snap_dist]
        end_candidates = [candidate for candidate in _nearest_graph_candidates(graph_nodes, end) if candidate[2] <= max_snap_dist]
        if not start_candidates or not end_candidates:
            logger.info(
                "%s_geojson: route failed no_snap_candidates for %.5f,%.5f -> %.5f,%.5f start_candidates=%s end_candidates=%s",
                self.key,
                lat1,
                lon1,
                lat2,
                lon2,
                len(start_candidates),
                len(end_candidates),
            )
            return None

        best_geometry = None
        best_start_point = None
        best_end_point = None
        best_score = None
        for start_key, start_point, start_dist in start_candidates:
            for end_key, end_point, end_dist in end_candidates:
                geometry = _shortest_graph_path(adjacency, graph_nodes, start_key, end_key)
                if not geometry or len(geometry) < 2:
                    continue
                route_length = _polyline_length(geometry)
                score = route_length + start_dist + end_dist
                if best_score is None or score < best_score:
                    best_geometry = geometry
                    best_start_point = start_point
                    best_end_point = end_point
                    best_score = score

        if not best_geometry or best_start_point is None or best_end_point is None:
            logger.info("%s_geojson: route failed no_connected_path for %.5f,%.5f -> %.5f,%.5f", self.key, lat1, lon1, lat2, lon2)
            return None

        direct_length = math.sqrt(_distance_sq(start, end))
        route_length = _polyline_length(best_geometry)
        if direct_length > 0 and route_length > direct_length * MAX_ROUTE_LENGTH_RATIO:
            logger.info(
                "%s_geojson: route failed length_ratio for %.5f,%.5f -> %.5f,%.5f route=%.6f direct=%.6f",
                self.key,
                lat1,
                lon1,
                lat2,
                lon2,
                route_length,
                direct_length,
            )
            return None

        return {
            "geometry": best_geometry,
            "anchor_start": best_start_point,
            "anchor_end": best_end_point,
            "provider": f"{self.key}_geojson",
        }


def _load_datasets() -> list[_GeoJsonTransportDataset]:
    global _datasets_cache
    if _datasets_cache is not None:
        return _datasets_cache

    with _dataset_lock:
        if _datasets_cache is not None:
            return _datasets_cache

        datasets: list[_GeoJsonTransportDataset] = []
        file_index = get_dataset_file_index()
        if not file_index:
            logger.warning("geojson_transport: no dataset files found under %s", DATASET_DIR)
            _datasets_cache = datasets
            return _datasets_cache

        for key in sorted(file_index):
            paths = file_index[key]
            station_path = paths.get("station_path")
            if station_path is None:
                continue
            metadata = get_dataset_metadata(key)
            datasets.append(
                _GeoJsonTransportDataset(
                    key=key,
                    station_path=station_path,
                    rail_path=paths.get("rail_path"),
                    metadata=metadata,
                )
            )

        _datasets_cache = datasets
        logger.info("geojson_transport: registered %s datasets", len(datasets))
        return _datasets_cache


def reset_geojson_transport_datasets() -> None:
    global _dataset_file_index_cache, _dataset_metadata_map_cache, _datasets_cache
    with _dataset_lock:
        _datasets_cache = None
    with _dataset_file_index_lock:
        _dataset_file_index_cache = None
    _dataset_metadata_map_cache = None


def country_has_airport_dataset(country_hint: Optional[str]) -> bool:
    """Return True if a per-country airport GeoJSON file has been imported for this country."""
    if not country_hint:
        return False
    for dataset in _load_datasets():
        if not dataset.key.endswith("_airport"):
            continue
        if dataset.matches_country_hint(country_hint):
            return True
    return False


def _is_europe_country_hint(country_hint: Optional[str]) -> bool:
    return _normalize_text(country_hint or "") in EUROPE_COUNTRY_HINTS


def _dataset_matches_method(
    dataset: _GeoJsonTransportDataset,
    method: str,
    country_hint: Optional[str],
    include_eu_international: bool = False,
    coord_is_europe: Optional[bool] = None,
) -> bool:
    # Resolve European context: coordinate-based when available, else country hint.
    if coord_is_europe is not None:
        context_is_europe: Optional[bool] = coord_is_europe
    elif country_hint:
        context_is_europe = True if _is_europe_country_hint(country_hint) else False
    else:
        context_is_europe = None  # unknown — permissive

    # --- excursion (cable car / lift) — Europe-only ---
    if method == "excursion":
        if dataset.key != "europe_lift":
            return False
        if context_is_europe is False:
            return False
        return True

    # --- Europe international rail — requires explicit opt-in (multi-country trip) ---
    if dataset.key == EUROPE_INTERNATIONAL_RAIL_KEY:
        if method != "train" or not include_eu_international:
            return False
        if context_is_europe is False:
            return False
        return True

    # --- Europe tram and urban rail — available for any European context ---
    if dataset.key in {"europe_tram", "europe_urban_rail"}:
        if method != "train":
            return False
        if context_is_europe is False:
            return False
        return True

    # --- Europe ferry — available for any European context ---
    if dataset.key == "europe_ferry":
        if method != "ferry":
            return False
        if context_is_europe is False:
            return False
        return True

    # --- Country-specific airport datasets (named *_airport) ---
    # These files are downloaded per-country from Overpass and are authoritative
    # for the flight method.  No bbox or Europe check needed — the file itself
    # is already country-scoped.
    if method == "flight":
        return dataset.key.endswith("_airport") and (
            not country_hint or dataset.matches_country_hint(country_hint)
        )

    # --- Country-specific datasets ---
    return not country_hint or dataset.matches_country_hint(country_hint)


def country_has_local_train_data(country: str) -> bool:
    """Return True if at least one loaded GeoJSON dataset covers train stations for the given country."""
    if not country:
        return False
    # The Europe international rail dataset covers all European countries.
    if _is_europe_country_hint(country):
        for dataset in _load_datasets():
            if dataset.key == EUROPE_INTERNATIONAL_RAIL_KEY and dataset.supports_method("train"):
                return True
    for dataset in _load_datasets():
        if dataset.key in {"europe_lift", EUROPE_INTERNATIONAL_RAIL_KEY}:
            continue
        if not dataset.matches_country_hint(country):
            continue
        if dataset.supports_method("train"):
            return True
    return False


def search_transport_places_from_geojson(
    query: str,
    method: str,
    *,
    country_hint: Optional[str] = None,
    limit: int = 10,
    include_eu_international: bool = False,
    # When provided, use the current coordinate to determine whether Europe
    # datasets should be searched rather than relying only on the country hint.
    current_lat: Optional[float] = None,
    current_lon: Optional[float] = None,
) -> list[dict]:
    if method == "excursion":
        special_results = _search_special_excursion_stations(
            query,
            country_hint=country_hint,
            limit=limit,
        )
    else:
        special_results = []

    if current_lat is not None and current_lon is not None:
        coord_is_europe: Optional[bool] = _is_europe_coordinate(current_lat, current_lon)
    else:
        coord_is_europe = None  # fall back to country-hint-based gating
    ranked: list[tuple[int, dict]] = []
    for result in special_results:
        ranked.append((1000, result))
    for dataset in _load_datasets():
        if not _dataset_matches_method(dataset, method, country_hint, include_eu_international, coord_is_europe):
            continue
        if not dataset.supports_method(method):
            continue
        base_score = 100 if (country_hint and dataset.matches_country_hint(country_hint)) or method == "excursion" else 0
        # For Europe-wide datasets, narrow results to the specific country's bounding box
        # so a search for Italian stations doesn't return German ones.
        bbox = _europe_country_bbox(country_hint) if dataset.key in EUROPE_TRANSPORT_DATASETS else None
        for result in dataset.search(query, method, limit=max(limit, 10), country_bbox=bbox):
            ranked.append((base_score, result))

    ranked.sort(key=lambda item: (-item[0], item[1]["place_name"]))
    results: list[dict] = []
    seen: set[str] = set()
    for _, result in ranked:
        dedupe_key = f"{_normalize_text(result['place_name'])}|{_normalize_text(result['country'])}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        results.append(result)
        if len(results) >= limit:
            break
    return results


def lookup_nearest_transport_place_from_geojson(
    lat: float,
    lon: float,
    method: str,
    *,
    country_hint: Optional[str] = None,
    max_distance_meters: Optional[float] = None,
    include_eu_international: bool = False,
) -> Optional[dict]:
    if method == "excursion":
        special_candidate = _nearest_special_excursion_station(
            lat,
            lon,
            country_hint=country_hint,
            max_distance_meters=max_distance_meters,
        )
        if special_candidate:
            return special_candidate

    # Use the actual coordinate to decide whether Europe-specific datasets apply.
    coord_is_europe = _is_europe_coordinate(lat, lon)
    best_result = None
    best_distance = None
    for dataset in _load_datasets():
        if not _dataset_matches_method(dataset, method, country_hint, include_eu_international, coord_is_europe):
            continue
        if not dataset.contains_coordinate(lat, lon):
            continue
        # For Europe-wide datasets, apply the country bounding box filter so snapping
        # does not return stations from a different European country.
        bbox = _europe_country_bbox(country_hint) if dataset.key in EUROPE_TRANSPORT_DATASETS else None
        candidate = dataset.nearest(lat, lon, method, max_distance_meters=max_distance_meters, country_bbox=bbox)
        if not candidate:
            continue
        distance = float(candidate.get("distance_meters") or 0.0)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_result = candidate
    return best_result


def build_train_route_from_geojson(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    *,
    country_hint: Optional[str] = None,
) -> Optional[dict]:
    for dataset in _load_datasets():
        if not _dataset_matches_method(dataset, "train", country_hint):
            continue
        if not dataset.contains_coordinate(lat1, lon1) or not dataset.contains_coordinate(lat2, lon2):
            continue
        route = dataset.build_route(lat1, lon1, lat2, lon2, "train")
        if route:
            return route
    return None


def build_excursion_route_from_geojson(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    *,
    country_hint: Optional[str] = None,
) -> Optional[dict]:
    if _is_special_excursion_pair(lat1, lon1, lat2, lon2):
        return {
            "geometry": [
                [float(lat1), float(lon1)],
                [float(lat2), float(lon2)],
            ],
            "anchor_start": [float(lat1), float(lon1)],
            "anchor_end": [float(lat2), float(lon2)],
            "provider": "special_excursion_straight",
        }

    for dataset in _load_datasets():
        if not _dataset_matches_method(dataset, "excursion", country_hint):
            continue
        if not dataset.contains_coordinate(lat1, lon1) or not dataset.contains_coordinate(lat2, lon2):
            continue
        route = dataset.build_route(lat1, lon1, lat2, lon2, "excursion")
        if route:
            return route
    return None


def match_geojson_dataset_for_route(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    *,
    country_hint: Optional[str] = None,
) -> Optional[dict]:
    for dataset in _load_datasets():
        if country_hint and not dataset.matches_country_hint(country_hint):
            continue
        if not dataset.contains_coordinate(lat1, lon1) or not dataset.contains_coordinate(lat2, lon2):
            continue
        return {
            "key": dataset.key,
            "country": dataset.country,
            "city": dataset.city,
        }
    return None
