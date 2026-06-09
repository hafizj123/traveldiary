from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from ..database import Base


class RouteCache(Base):
    __tablename__ = "route_cache"

    id         = Column(Integer, primary_key=True)
    cache_key  = Column(String(255), unique=True, index=True, nullable=False)
    geometry_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
