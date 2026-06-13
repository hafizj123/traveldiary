from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path

ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str = "mysql+pymysql://root:@localhost/travel_diary"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174,http://localhost:3000"

    SECRET_KEY: str = "traveldiary-super-secret-key-change-in-production-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@traveldiary.local"

    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""
    R2_PUBLIC_URL: str = ""

    OWM_API_KEY: str = ""
    GOOGLE_MAPS_API_KEY: str = ""
    GEOAPIFY_API_KEY: str = ""
    CHINA_RAIL_GPKG_PATH: str = ""
    CHINA_RAIL_GPKG_TIMEOUT_SECONDS: float = 5.0
    GEOJSON_ROUTE_TIMEOUT_SECONDS: float = 40.0
    OVERPASS_GEOJSON_IMPORT_TIMEOUT_SECONDS: float = 1800.0
    SHANGHAI_RAIL_GEOJSON_PATH: str = "backend/gpkg/hotosm_chn_railways_osm_gpkg/geojson_file/china/shanghai.geojson"
    SHANGHAI_STATION_GEOJSON_PATH: str = "backend/gpkg/hotosm_chn_railways_osm_gpkg/geojson_file/china/shanghai_station.geojson"
    EGYPT_RAIL_GEOJSON_PATH: str = "backend/gpkg/hotosm_chn_railways_osm_gpkg/geojson_file/egypt/egypt.geojson"
    EGYPT_STATION_GEOJSON_PATH: str = "backend/gpkg/hotosm_chn_railways_osm_gpkg/geojson_file/egypt/egypt_station.geojson"

    DEBUG: bool = True

    class Config:
        env_file = str(ENV_FILE)


settings = Settings()


def get_cors_origins() -> list[str]:
    return [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
