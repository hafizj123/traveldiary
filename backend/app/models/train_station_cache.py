from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String

from ..database import Base


class TrainStationCache(Base):
    __tablename__ = "train_station_cache"

    id = Column(Integer, primary_key=True)
    lookup_key = Column(String(64), unique=True, index=True, nullable=False)
    query_latitude = Column(Float, index=True, nullable=False)
    query_longitude = Column(Float, index=True, nullable=False)
    station_name = Column(String(255), nullable=False)
    station_latitude = Column(Float, nullable=False)
    station_longitude = Column(Float, nullable=False)
    distance_meters = Column(Float, nullable=False, default=0)
    city = Column(String(255), nullable=False, default="")
    country = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
