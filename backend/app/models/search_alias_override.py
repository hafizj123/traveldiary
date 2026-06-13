from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from ..database import Base


class SearchAliasOverride(Base):
    __tablename__ = "search_alias_overrides"

    id = Column(Integer, primary_key=True, index=True)
    alias = Column(String(255), nullable=False, index=True)
    method = Column(String(32), nullable=True, index=True)
    place_name = Column(String(255), nullable=False)
    city = Column(String(255), nullable=True)
    country = Column(String(255), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
