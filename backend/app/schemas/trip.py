from pydantic import BaseModel, computed_field
from typing import Optional
from datetime import date, datetime

_EUROPE_COUNTRIES: frozenset[str] = frozenset({
    "albania", "andorra", "austria", "belarus", "belgium", "bosnia and herzegovina",
    "bulgaria", "croatia", "czechia", "czech republic", "denmark", "estonia", "finland",
    "france", "germany", "greece", "hungary", "iceland", "ireland", "italy", "kosovo",
    "latvia", "liechtenstein", "lithuania", "luxembourg", "malta", "moldova", "monaco",
    "montenegro", "netherlands", "north macedonia", "norway", "poland", "portugal",
    "romania", "san marino", "serbia", "slovakia", "slovenia", "spain", "sweden",
    "switzerland", "uk", "united kingdom", "england", "scotland", "wales", "turkey",
    "ukraine", "vatican city",
})


def _is_europe_country(name: str) -> bool:
    return " ".join((name or "").strip().lower().split()) in _EUROPE_COUNTRIES


class TripCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    starting_place_name: str
    starting_city: Optional[str] = None
    starting_country: str
    starting_latitude: float
    starting_longitude: float
    planned_countries: list[str]
    cover_image_url: Optional[str] = None
    visibility: str = "private"


class TripUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    starting_place_name: Optional[str] = None
    starting_city: Optional[str] = None
    starting_country: Optional[str] = None
    starting_latitude: Optional[float] = None
    starting_longitude: Optional[float] = None
    planned_countries: Optional[list[str]] = None
    cover_image_url: Optional[str] = None
    visibility: Optional[str] = None


class TripResponse(BaseModel):
    id: int
    user_id: int
    title: str
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    starting_place_name: Optional[str] = None
    starting_city: Optional[str] = None
    starting_country: Optional[str] = None
    starting_latitude: Optional[float] = None
    starting_longitude: Optional[float] = None
    planned_countries: Optional[list[str]] = None
    cover_image_url: Optional[str] = None
    visibility: str
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def category(self) -> str:
        countries = self.planned_countries or []
        if not countries:
            return "Trip"
        if all(_is_europe_country(c) for c in countries):
            return "Europe Trip"
        if len(countries) == 1:
            return f"{countries[0]} Trip"
        return "\u2013".join(countries) + " Trip"

    model_config = {"from_attributes": True}
