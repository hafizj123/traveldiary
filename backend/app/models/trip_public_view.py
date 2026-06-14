from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime, date

from ..database import Base


class TripPublicView(Base):
    __tablename__ = "trip_public_views"
    __table_args__ = (
        UniqueConstraint("trip_id", "viewer_hash", "view_date", name="uq_trip_public_views_daily"),
        Index("ix_trip_public_views_trip_id", "trip_id"),
        Index("ix_trip_public_views_view_date", "view_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    viewer_hash = Column(String(64), nullable=False)
    view_date = Column(Date, nullable=False, default=date.today)
    viewed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    user_agent = Column(String(255), nullable=True)

    trip = relationship("Trip", back_populates="public_views")
