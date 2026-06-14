from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from ..database import Base


class TripJournal(Base):
    __tablename__ = "trip_journals"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False)
    intro_text = Column(Text, nullable=True)
    closing_text = Column(Text, nullable=True)
    tone = Column(String(32), nullable=False, default="warm")
    length_mode = Column(String(32), nullable=False, default="standard")
    content_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    trip = relationship("Trip", back_populates="journal")
