from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from ..database import Base


class CountryRoutePolicy(Base):
    __tablename__ = "country_route_policies"

    id = Column(Integer, primary_key=True, index=True)
    country_key = Column(String(100), unique=True, index=True, nullable=False)
    country_name = Column(String(255), nullable=False)
    train_mode = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
