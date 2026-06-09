from typing import Optional, Dict, Any
import httpx
from datetime import date, timedelta

# WMO weather code → human description
_WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "icy fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "light freezing drizzle", 57: "freezing drizzle",
    61: "slight rain", 63: "rain", 65: "heavy rain",
    66: "light freezing rain", 67: "heavy freezing rain",
    71: "slight snow", 73: "snowfall", 75: "heavy snowfall", 77: "snow grains",
    80: "slight showers", 81: "rain showers", 82: "violent showers",
    85: "slight snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "heavy thunderstorm",
}

def _wmo_icon(code: int) -> str:
    if code == 0: return "01d"
    if code in (1, 2): return "02d"
    if code == 3: return "04d"
    if code in (45, 48): return "50d"
    if 51 <= code <= 82: return "10d"
    if code in (71, 73, 75, 77, 85, 86): return "13d"
    if code >= 95: return "11d"
    return "02d"


async def get_weather(
    lat: float, lon: float, visit_date: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    """Fetch historical (or short-range forecast) weather via Open-Meteo — no API key required."""
    if not visit_date:
        return None

    today = date.today()

    # Open-Meteo archive has ~5-day lag; use forecast API for recent/upcoming dates
    if visit_date < today - timedelta(days=7):
        base_url = "https://archive-api.open-meteo.com/v1/archive"
    elif visit_date <= today + timedelta(days=15):
        base_url = "https://api.open-meteo.com/v1/forecast"
    else:
        return None  # too far in the future

    date_str = visit_date.isoformat()

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                base_url,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": date_str,
                    "end_date": date_str,
                    "daily": (
                        "temperature_2m_max,temperature_2m_min,"
                        "weathercode,precipitation_sum,windspeed_10m_max"
                    ),
                    "timezone": "auto",
                },
            )
            if r.status_code != 200:
                return None

            d = r.json()
            daily = d.get("daily", {})
            if not daily.get("temperature_2m_max") or daily["temperature_2m_max"][0] is None:
                return None

            # Archive API uses "weather_code"; forecast API uses "weathercode" — accept both
            raw_code = daily.get("weather_code") or daily.get("weathercode") or [0]
            code = int(raw_code[0] or 0)
            tmax = daily["temperature_2m_max"][0]
            tmin = daily["temperature_2m_min"][0]

            return {
                "temp":        round((tmax + tmin) / 2, 1),
                "temp_max":    tmax,
                "temp_min":    tmin,
                "description": _WMO.get(code, "unknown"),
                "icon":        _wmo_icon(code),
                "wind_speed":  daily.get("windspeed_10m_max", [None])[0],
                "precipitation": daily.get("precipitation_sum", [None])[0],
                "date":        date_str,
                "source":      "historical" if visit_date < today - timedelta(days=7) else "forecast",
            }
    except Exception as exc:
        print(f"[weather] fetch failed for {lat},{lon} on {date_str}: {exc}")
    return None
