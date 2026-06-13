from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base

TRAVEL_METHODS = ["flight", "train", "car", "bus", "walk", "ferry", "excursion", "other"]


class TravelSegment(Base):
    __tablename__ = "travel_segments"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    from_point_id = Column(Integer, ForeignKey("timeline_points.id"), nullable=False)
    to_point_id = Column(Integer, ForeignKey("timeline_points.id"), nullable=False)
    travel_method = Column(String(20), nullable=False, default="other")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    trip = relationship("Trip", back_populates="segments")
    from_point = relationship(
        "TimelinePoint",
        foreign_keys=[from_point_id],
        back_populates="from_segments",
    )
    to_point = relationship(
        "TimelinePoint",
        foreign_keys=[to_point_id],
        back_populates="to_segments",
    )
