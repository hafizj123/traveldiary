from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TravelSegmentCreate(BaseModel):
    from_point_id: int
    to_point_id: int
    travel_method: str
    description: Optional[str] = None


class TravelSegmentUpdate(BaseModel):
    travel_method: Optional[str] = None
    description: Optional[str] = None


class TravelSegmentResponse(BaseModel):
    id: int
    trip_id: int
    from_point_id: int
    to_point_id: int
    travel_method: str
    description: Optional[str] = None
    route_geometry: Optional[list[list[float]]] = None
    route_status: Optional[str] = None
    route_provider: Optional[str] = None
    route_anchor_start: Optional[list[float]] = None
    route_anchor_end: Optional[list[float]] = None
    created_at: datetime

    model_config = {"from_attributes": True}
