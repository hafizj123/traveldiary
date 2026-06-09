from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_cors_origins
from .database import Base, engine
from .models import User, EmailOTP, Trip, TimelinePoint, TravelSegment  # register models
from .routers import auth, trips, timeline, segments, upload, public

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Travel Diary API",
    version="1.0.0",
    description="Personal travel timeline and world map diary",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(trips.router)
app.include_router(timeline.router)
app.include_router(segments.router)
app.include_router(upload.router)
app.include_router(public.router)


@app.get("/", tags=["root"])
def root():
    return {"message": "Travel Diary API", "version": "1.0.0", "docs": "/docs"}


@app.get("/health", tags=["root"])
def health():
    return {"status": "healthy"}
