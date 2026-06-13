from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.dialects.mysql import LONGTEXT

from ..database import Base


class TrainStation(Base):
    __tablename__ = "train_stations"

    id = Column(Integer, primary_key=True)
    osm_key = Column(String(64), unique=True, index=True, nullable=False)
    osm_type = Column(String(16), nullable=False)
    osm_id = Column(String(32), nullable=False)
    name = Column(String(255), nullable=False)
    latitude = Column(Float, index=True, nullable=False)
    longitude = Column(Float, index=True, nullable=False)
    city = Column(String(255), nullable=False, default="")
    country = Column(String(255), nullable=False, default="")
    railway_type = Column(String(64), nullable=False, default="")
    source = Column(String(64), nullable=False, default="osm")
    tags_json = Column(LONGTEXT, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
