from sqlalchemy import Column, Integer, String, DateTime, Date, Text, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base


class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    starting_place_name = Column(String(255), nullable=True)
    starting_city = Column(String(255), nullable=True)
    starting_country = Column(String(255), nullable=True)
    starting_latitude = Column(Float, nullable=True)
    starting_longitude = Column(Float, nullable=True)
    travel_companions = Column(String(255), nullable=True)
    planned_countries = Column(JSON, nullable=True)
    cover_image_url = Column(String(500), nullable=True)
    visibility = Column(String(12), default="private")
    share_slug = Column(String(64), unique=True, index=True, nullable=True)
    shared_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="trips")
    points = relationship(
        "TimelinePoint",
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TimelinePoint.sequence_no",
    )
    segments = relationship(
        "TravelSegment",
        back_populates="trip",
        cascade="all, delete-orphan",
    )
    public_views = relationship(
        "TripPublicView",
        back_populates="trip",
        cascade="all, delete-orphan",
    )
    journal = relationship(
        "TripJournal",
        back_populates="trip",
        cascade="all, delete-orphan",
        uselist=False,
    )
