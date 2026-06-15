from __future__ import annotations

from typing import Optional
import threading

from sqlalchemy.orm import Session

from ..models.country_route_policy import CountryRoutePolicy
from .geojson_transport_service import (
    EUROPE_COUNTRY_BOUNDS,
    WORLD_COUNTRY_BOUNDS,
    get_dataset_file_paths,
    get_dataset_file_index,
    get_dataset_metadata,
)

TRAIN_MODE_GOOGLE_OSM = "google_osm"
TRAIN_MODE_GEOJSON_OSM = "geojson_osm"
TRAIN_MODE_OSM_ONLY = "osm_only"
TRAIN_MODE_VALUES = {
    TRAIN_MODE_GOOGLE_OSM,
    TRAIN_MODE_GEOJSON_OSM,
    TRAIN_MODE_OSM_ONLY,
}

GOOGLE_TRAIN_COUNTRIES = {
    "australia",
    "austria",
    "belgium",
    "brazil",
    "canada",
    "chile",
    "colombia",
    "czechia",
    "czech republic",
    "denmark",
    "finland",
    "france",
    "germany",
    "greece",
    "hungary",
    "india",
    "indonesia",
    "ireland",
    "israel",
    "italy",
    "luxembourg",
    "malaysia",
    "mexico",
    "netherlands",
    "new zealand",
    "norway",
    "poland",
    "portugal",
    "puerto rico",
    "qatar",
    "romania",
    "singapore",
    "slovakia",
    "spain",
    "sweden",
    "switzerland",
    "taiwan",
    "thailand",
    "turkey",
    "united kingdom",
    "uk",
    "united states",
    "usa",
}

COUNTRY_KEY_ALIASES = {
    "czech_republic": "czechia",
    "hongkong": "hong_kong",
    "macao": "macau",
    "republic_of_korea": "south_korea",
    "the_philippines": "philippines",
    "uae": "united_arab_emirates",
    "uk": "united_kingdom",
    "usa": "united_states",
    "viet_nam": "vietnam",
}

DISPLAY_NAME_OVERRIDES = {
    "costa_rica": "Costa Rica",
    "czechia": "Czechia",
    "hong_kong": "Hong Kong",
    "japan": "Japan",
    "new_zealand": "New Zealand",
    "puerto_rico": "Puerto Rico",
    "south_africa": "South Africa",
    "south_korea": "South Korea",
    "united_arab_emirates": "United Arab Emirates",
    "united_kingdom": "United Kingdom",
    "united_states": "United States",
}

OSM_ONLY_VISIBLE_COUNTRIES = {
    "japan": "Japan",
}

GROUPED_CITY_POLICY_COUNTRY_KEYS = {
    "australia",
    "brazil",
    "canada",
    "china",
    "india",
    "japan",
    "mexico",
    "russia",
    "united_states",
}

EXCLUDED_POLICY_COUNTRY_KEYS = {
    "europe",
    "england",
    "scotland",
    "wales",
}

WORLD_COUNTRY_NAMES = [
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua and Barbuda",
    "Argentina", "Armenia", "Australia", "Austria", "Azerbaijan", "Bahamas",
    "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize",
    "Benin", "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil",
    "Brunei", "Bulgaria", "Burkina Faso", "Burundi", "Cambodia", "Cameroon",
    "Canada", "Cape Verde", "Central African Republic", "Chad", "Chile", "China",
    "Colombia", "Comoros", "Costa Rica", "Croatia", "Cuba", "Cyprus",
    "Czechia", "Democratic Republic of the Congo", "Denmark", "Djibouti", "Dominica",
    "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "Equatorial Guinea",
    "Eritrea", "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland",
    "France", "Gabon", "Gambia", "Georgia", "Germany", "Ghana",
    "Greece", "Grenada", "Guatemala", "Guinea", "Guinea-Bissau", "Guyana",
    "Haiti", "Honduras", "Hungary", "Iceland", "India", "Indonesia",
    "Iran", "Iraq", "Ireland", "Israel", "Italy", "Ivory Coast",
    "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kiribati",
    "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho",
    "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Madagascar",
    "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Marshall Islands",
    "Mauritania", "Mauritius", "Mexico", "Micronesia", "Moldova", "Monaco",
    "Mongolia", "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia",
    "Nauru", "Nepal", "Netherlands", "New Zealand", "Nicaragua", "Niger",
    "Nigeria", "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan",
    "Palau", "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru",
    "Philippines", "Poland", "Portugal", "Qatar", "Republic of the Congo", "Romania",
    "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia",
    "Saint Vincent and the Grenadines", "Samoa", "San Marino", "Sao Tome and Principe",
    "Saudi Arabia", "Senegal", "Serbia", "Seychelles", "Sierra Leone", "Singapore",
    "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa",
    "South Korea", "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname",
    "Sweden", "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania",
    "Thailand", "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago",
    "Tunisia", "Turkey", "Turkmenistan", "Tuvalu", "Uganda", "Ukraine",
    "United Arab Emirates", "United Kingdom", "United States", "Uruguay",
    "Uzbekistan", "Vanuatu", "Vatican City", "Venezuela", "Vietnam",
    "Yemen", "Zambia", "Zimbabwe",
]

CONTINENT_COUNTRIES = {
    "Africa": {
        "algeria", "angola", "benin", "botswana", "burkina_faso", "burundi", "cameroon",
        "cape_verde", "central_african_republic", "chad", "comoros", "democratic_republic_of_the_congo",
        "republic_of_the_congo", "djibouti", "egypt", "equatorial_guinea", "eritrea", "eswatini",
        "ethiopia", "gabon", "gambia", "ghana", "guinea", "guinea_bissau", "ivory_coast", "kenya",
        "lesotho", "liberia", "libya", "madagascar", "malawi", "mali", "mauritania", "mauritius",
        "morocco", "mozambique", "namibia", "niger", "nigeria", "rwanda", "sao_tome_and_principe",
        "senegal", "seychelles", "sierra_leone", "somalia", "south_africa", "south_sudan", "sudan",
        "tanzania", "togo", "tunisia", "uganda", "zambia", "zimbabwe", "ethiopia",
    },
    "Asia": {
        "afghanistan", "armenia", "azerbaijan", "bahrain", "bangladesh", "bhutan", "brunei",
        "cambodia", "china", "cyprus", "georgia", "hong_kong", "india", "indonesia", "iran", "iraq",
        "israel", "japan", "jordan", "kazakhstan", "kuwait", "kyrgyzstan", "laos", "lebanon",
        "macau", "malaysia", "maldives", "mongolia", "myanmar", "nepal", "north_korea", "oman",
        "pakistan", "palestine", "philippines", "qatar", "saudi_arabia", "singapore", "south_korea",
        "sri_lanka", "syria", "taiwan", "tajikistan", "thailand", "timor_leste", "turkey",
        "turkmenistan", "united_arab_emirates", "uzbekistan", "vietnam", "yemen",
    },
    "Europe": {
        "albania", "andorra", "austria", "belarus", "belgium", "bosnia_and_herzegovina", "bulgaria",
        "croatia", "czechia", "denmark", "estonia", "finland", "france", "germany", "greece",
        "hungary", "iceland", "ireland", "italy", "latvia", "liechtenstein", "lithuania",
        "luxembourg", "malta", "moldova", "monaco", "montenegro", "netherlands", "north_macedonia",
        "norway", "poland", "portugal", "romania", "san_marino", "serbia", "slovakia", "slovenia",
        "spain", "sweden", "switzerland", "ukraine", "united_kingdom", "vatican_city",
    },
    "North America": {
        "antigua_and_barbuda", "bahamas", "barbados", "belize", "canada", "costa_rica", "cuba",
        "dominica", "dominican_republic", "el_salvador", "grenada", "guatemala", "haiti",
        "honduras", "jamaica", "mexico", "nicaragua", "panama", "saint_kitts_and_nevis",
        "saint_lucia", "saint_vincent_and_the_grenadines", "trinidad_and_tobago", "united_states",
    },
    "South America": {
        "argentina", "bolivia", "brazil", "chile", "colombia", "ecuador", "guyana", "paraguay",
        "peru", "suriname", "uruguay", "venezuela",
    },
    "Oceania": {
        "australia", "fiji", "kiribati", "marshall_islands", "micronesia", "nauru", "new_zealand",
        "palau", "papua_new_guinea", "samoa", "solomon_islands", "tonga", "tuvalu", "vanuatu",
    },
}

_google_country_registry_cache: Optional[dict[str, dict]] = None
_local_geojson_capabilities_cache: Optional[dict[str, dict]] = None
_world_country_registry_cache: Optional[dict[str, dict]] = None
_capability_cache_lock = threading.Lock()


def _normalize_country_name(value: Optional[str]) -> str:
    return " ".join((value or "").strip().lower().split())


def country_key_from_name(value: Optional[str]) -> str:
    normalized = _normalize_country_name(value)
    if not normalized:
        return ""
    slug = normalized.replace("-", " ").replace("'", "").replace(".", "")
    slug = "_".join(part for part in slug.split() if part)
    return COUNTRY_KEY_ALIASES.get(slug, slug)


def country_display_name(country_key: str) -> str:
    if country_key in DISPLAY_NAME_OVERRIDES:
        return DISPLAY_NAME_OVERRIDES[country_key]
    return country_key.replace("_", " ").title()


def continent_for_country_key(country_key: str) -> str:
    normalized = country_key_from_name(country_key)
    for continent, keys in CONTINENT_COUNTRIES.items():
        if normalized in keys:
            return continent
    return "Other"


def _country_alias_keys(country_name: str, aliases: Optional[list[str]] = None) -> set[str]:
    keys = {country_key_from_name(country_name)}
    for alias in aliases or []:
        alias_key = country_key_from_name(alias)
        if alias_key:
            keys.add(alias_key)
    return {key for key in keys if key}


def _has_local_geojson_train_data(dataset_key: str) -> bool:
    paths = get_dataset_file_paths(dataset_key)
    return paths.get("rail_path") is not None and paths.get("station_path") is not None


def local_geojson_country_capabilities() -> dict[str, dict]:
    global _local_geojson_capabilities_cache
    if _local_geojson_capabilities_cache is not None:
        return _local_geojson_capabilities_cache

    with _capability_cache_lock:
        if _local_geojson_capabilities_cache is not None:
            return _local_geojson_capabilities_cache

    capabilities: dict[str, dict] = {}
    dataset_keys = sorted(get_dataset_file_index())

    for dataset_key in dataset_keys:
        metadata = get_dataset_metadata(dataset_key)
        country_name = str(metadata.get("country") or "").strip()
        if not country_name:
            continue
        if not _has_local_geojson_train_data(dataset_key):
            continue

        normalized_country_name = _normalize_country_name(country_name)
        if normalized_country_name == "europe":
            continue

        normalized_country_key = country_key_from_name(country_name)
        is_grouped_country = normalized_country_key in GROUPED_CITY_POLICY_COUNTRY_KEYS
        city_name = str(metadata.get("city") or "").strip()
        canonical_key = normalized_country_key if is_grouped_country else country_key_from_name(country_name)
        display_name = country_display_name(canonical_key) if is_grouped_country else country_name
        entry = capabilities.setdefault(
            canonical_key,
            {
                "country_key": canonical_key,
                "country_name": display_name,
                "aliases": set(),
                "dataset_keys": set(),
                "city_names": set(),
                "supports_geojson": False,
            },
        )
        entry["dataset_keys"].add(dataset_key)
        entry["supports_geojson"] = True
        if is_grouped_country:
            entry["aliases"].update({canonical_key, dataset_key})
            if city_name:
                entry["aliases"].add(country_key_from_name(city_name))
                entry["city_names"].add(city_name)
        else:
            entry["aliases"].update(_country_alias_keys(country_name, list(metadata.get("aliases") or [])))

    _local_geojson_capabilities_cache = capabilities
    return _local_geojson_capabilities_cache


def supports_google_train_country(country_name: Optional[str]) -> bool:
    return country_key_from_name(country_name) in google_country_registry()


def supports_local_geojson_train_country(country_name: Optional[str]) -> bool:
    return country_key_from_name(country_name) in local_geojson_country_capabilities()


def default_train_mode_for_country(country_name: Optional[str]) -> str:
    if supports_local_geojson_train_country(country_name):
        return TRAIN_MODE_GEOJSON_OSM
    if supports_google_train_country(country_name):
        return TRAIN_MODE_GOOGLE_OSM
    return TRAIN_MODE_OSM_ONLY


def google_country_registry() -> dict[str, dict]:
    global _google_country_registry_cache
    if _google_country_registry_cache is not None:
        return _google_country_registry_cache

    registry: dict[str, dict] = {}
    for raw_name in GOOGLE_TRAIN_COUNTRIES:
        key = country_key_from_name(raw_name)
        entry = registry.setdefault(
            key,
            {
                "country_key": key,
                "country_name": country_display_name(key),
                "aliases": set(),
                "supports_google": True,
            },
        )
        entry["aliases"].add(key)
        entry["aliases"].add(country_key_from_name(raw_name))
    _google_country_registry_cache = registry
    return _google_country_registry_cache


def world_country_registry() -> dict[str, dict]:
    global _world_country_registry_cache
    if _world_country_registry_cache is not None:
        return _world_country_registry_cache

    registry: dict[str, dict] = {}
    all_country_names = set(WORLD_COUNTRY_NAMES)
    all_country_names.update(country for country in EUROPE_COUNTRY_BOUNDS if country != "europe")
    all_country_names.update(country for country in WORLD_COUNTRY_BOUNDS if country != "europe")
    all_country_names.update(GOOGLE_TRAIN_COUNTRIES)

    for raw_name in sorted(all_country_names):
        key = country_key_from_name(raw_name)
        if not key or key in EXCLUDED_POLICY_COUNTRY_KEYS:
            continue
        registry.setdefault(
            key,
            {
                "country_key": key,
                "country_name": country_display_name(key),
            },
        )

    _world_country_registry_cache = registry
    return _world_country_registry_cache


def reset_country_route_policy_capabilities() -> None:
    global _local_geojson_capabilities_cache, _world_country_registry_cache
    with _capability_cache_lock:
        _local_geojson_capabilities_cache = None
        _world_country_registry_cache = None


def list_country_route_policy_rows(db: Session) -> list[CountryRoutePolicy]:
    return db.query(CountryRoutePolicy).order_by(CountryRoutePolicy.country_name.asc()).all()


def get_country_route_policy(db: Session, country_name: Optional[str]) -> Optional[CountryRoutePolicy]:
    country_key = country_key_from_name(country_name)
    if not country_key:
        return None
    return db.query(CountryRoutePolicy).filter(CountryRoutePolicy.country_key == country_key).first()


def get_effective_train_mode_for_country(db: Session, country_name: Optional[str]) -> str:
    lookup_name = country_name
    capabilities = local_geojson_country_capabilities()
    normalized_key = country_key_from_name(country_name)
    if normalized_key not in capabilities:
        metadata = get_dataset_metadata(normalized_key) if normalized_key else {}
        metadata_country_key = country_key_from_name(metadata.get("country"))
        if metadata_country_key in GROUPED_CITY_POLICY_COUNTRY_KEYS:
            lookup_name = country_display_name(metadata_country_key)

    row = get_country_route_policy(db, lookup_name)
    if row and row.train_mode in TRAIN_MODE_VALUES:
        return row.train_mode
    return default_train_mode_for_country(lookup_name)


def _is_hidden_grouped_city_policy_key(country_key: str) -> bool:
    if country_key in GROUPED_CITY_POLICY_COUNTRY_KEYS:
        return False
    metadata = get_dataset_metadata(country_key)
    metadata_country_key = country_key_from_name(metadata.get("country"))
    return metadata_country_key in GROUPED_CITY_POLICY_COUNTRY_KEYS


def available_train_modes_for_country(country_key: str) -> list[str]:
    modes = [TRAIN_MODE_OSM_ONLY]
    if country_key in local_geojson_country_capabilities():
        modes.insert(0, TRAIN_MODE_GEOJSON_OSM)
    if country_key in google_country_registry():
        modes.insert(0, TRAIN_MODE_GOOGLE_OSM)
    seen: set[str] = set()
    return [mode for mode in modes if not (mode in seen or seen.add(mode))]


def list_country_route_policies_with_capabilities(db: Session) -> list[dict]:
    policy_rows = {row.country_key: row for row in list_country_route_policy_rows(db)}
    countries: dict[str, dict] = {}

    for country_key, entry in world_country_registry().items():
        countries[country_key] = {
            "country_key": country_key,
            "country_name": entry["country_name"],
            "supports_google": False,
            "supports_geojson": False,
        }

    for country_key, entry in google_country_registry().items():
        country = countries.setdefault(
            country_key,
            {
                "country_key": country_key,
                "country_name": entry["country_name"],
                "supports_google": False,
                "supports_geojson": False,
            },
        )
        country["country_name"] = entry["country_name"] or country["country_name"]
        country["supports_google"] = True

    for country_key, entry in local_geojson_country_capabilities().items():
        country = countries.setdefault(
            country_key,
            {
                "country_key": country_key,
                "country_name": entry["country_name"],
                "supports_google": False,
                "supports_geojson": False,
            },
        )
        country["country_name"] = entry["country_name"] or country["country_name"]
        country["supports_geojson"] = True

    for country_key, row in policy_rows.items():
        if _is_hidden_grouped_city_policy_key(country_key):
            continue
        country = countries.setdefault(
            country_key,
            {
                "country_key": country_key,
                "country_name": row.country_name or country_display_name(country_key),
                "supports_google": False,
                "supports_geojson": False,
            },
        )
        country["country_name"] = row.country_name or country["country_name"]

    for country_key, country_name in OSM_ONLY_VISIBLE_COUNTRIES.items():
        countries.setdefault(
            country_key,
            {
                "country_key": country_key,
                "country_name": country_name,
                "supports_google": False,
                "supports_geojson": False,
            },
        )

    items = []
    for country_key, country in countries.items():
        if country_key in EXCLUDED_POLICY_COUNTRY_KEYS:
            continue
        if _is_hidden_grouped_city_policy_key(country_key):
            continue
        available_modes = available_train_modes_for_country(country_key)
        selected_mode = (
            policy_rows[country_key].train_mode
            if country_key in policy_rows and policy_rows[country_key].train_mode in available_modes
            else default_train_mode_for_country(country["country_name"])
        )
        items.append(
            {
                "country_key": country_key,
                "country_name": country["country_name"],
                "continent": continent_for_country_key(country_key),
                "supports_google": country["supports_google"],
                "supports_geojson": country["supports_geojson"],
                "available_modes": available_modes,
                "selected_mode": selected_mode,
                "available_city_datasets": sorted(local_geojson_country_capabilities().get(country_key, {}).get("city_names", [])),
            }
        )

    items.sort(key=lambda item: item["country_name"].lower())
    return items


def upsert_country_route_policy(db: Session, country_key: str, train_mode: str) -> CountryRoutePolicy:
    if train_mode not in TRAIN_MODE_VALUES:
        raise ValueError("Invalid train mode.")

    normalized_key = country_key_from_name(country_key)
    if not normalized_key:
        raise ValueError("Country key is required.")

    allowed_modes = available_train_modes_for_country(normalized_key)
    if train_mode not in allowed_modes:
        raise ValueError("Selected train mode is not available for this country.")

    row = db.query(CountryRoutePolicy).filter(CountryRoutePolicy.country_key == normalized_key).first()
    local_capabilities = local_geojson_country_capabilities()
    google_registry = google_country_registry()
    display_name = (
        local_capabilities.get(normalized_key, {}).get("country_name")
        or google_registry.get(normalized_key, {}).get("country_name")
        or country_display_name(normalized_key)
    )
    if row:
        row.country_name = display_name
        row.train_mode = train_mode
    else:
        row = CountryRoutePolicy(
            country_key=normalized_key,
            country_name=display_name,
            train_mode=train_mode,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row
