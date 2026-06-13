from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.mysql import LONGTEXT
from datetime import datetime
from ..database import Base


class RouteCache(Base):
    __tablename__ = "route_cache"

    id         = Column(Integer, primary_key=True)
    cache_key  = Column(String(255), unique=True, index=True, nullable=False)
    geometry_json = Column(LONGTEXT, nullable=False)
    provider = Column(String(64), nullable=True)
    point_count = Column(Integer, nullable=False, default=0)
    countries_json = Column(LONGTEXT, nullable=False, default="[]")
    geometry_signature = Column(String(40), index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
