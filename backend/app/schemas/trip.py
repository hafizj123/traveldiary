from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class TripCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    cover_image_url: Optional[str] = None
    visibility: str = "private"


class TripUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    cover_image_url: Optional[str] = None
    visibility: Optional[str] = None


class TripResponse(BaseModel):
    id: int
    user_id: int
    title: str
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    cover_image_url: Optional[str] = None
    visibility: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
