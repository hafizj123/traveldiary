from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base


class TimelinePoint(Base):
    __tablename__ = "timeline_points"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    country = Column(String(100), nullable=False)
    city = Column(String(100), nullable=True)
    place_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    visit_date = Column(Date, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    image_url = Column(String(500), nullable=True)
    sequence_no = Column(Integer, default=0)
    weather_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    trip = relationship("Trip", back_populates="points")
    from_segments = relationship(
        "TravelSegment",
        foreign_keys="[TravelSegment.from_point_id]",
        back_populates="from_point",
        cascade="all, delete-orphan",
    )
    to_segments = relationship(
        "TravelSegment",
        foreign_keys="[TravelSegment.to_point_id]",
        back_populates="to_point",
        cascade="all, delete-orphan",
    )
