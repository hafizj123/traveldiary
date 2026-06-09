from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import date, datetime


class TimelinePointCreate(BaseModel):
    country: str
    city: Optional[str] = None
    place_name: str
    description: Optional[str] = None
    visit_date: date
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    image_url: Optional[str] = None
    sequence_no: Optional[int] = None
    travel_method: Optional[str] = None  # auto-creates segment from previous point


class TimelinePointUpdate(BaseModel):
    country: Optional[str] = None
    city: Optional[str] = None
    place_name: Optional[str] = None
    description: Optional[str] = None
    visit_date: Optional[date] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    image_url: Optional[str] = None
    sequence_no: Optional[int] = None


class TimelinePointResponse(BaseModel):
    id: int
    trip_id: int
    country: str
    city: Optional[str] = None
    place_name: str
    description: Optional[str] = None
    visit_date: date
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    image_url: Optional[str] = None
    sequence_no: int
    weather_data: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
