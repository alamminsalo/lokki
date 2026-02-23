"""Weather data analysis example using DuckDB."""

import duckdb
import requests
from geopy.geocoders import Nominatim

from lokki import flow, step


@step
def geocode_location(location: str) -> tuple[float, float]:
    """Convert location name to coordinates using Nominatim."""
    geolocator = Nominatim(user_agent="lokki-weather-example")
    loc = geolocator.geocode(location)
    if loc is None:
        raise ValueError(f"Could not find location: {location}")
    return (loc.latitude, loc.longitude)


@step
def fetch_weather(
    coords: tuple[float, float], start_date: str, end_date: str
) -> list[dict]:
    """Fetch historical weather data from Open-Meteo API."""
    latitude, longitude = coords
    url = "https://archive-api.open-meteo.com/v1/archive"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "temperature_2m_mean",
            "relative_humidity_2m_mean",
            "precipitation_sum",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "weather_code",
        ],
        "timezone": "auto",
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()
    daily = data.get("daily", {})

    dates = daily.get("time", [])
    weather_data = []
    for i, date in enumerate(dates):
        weather_data.append(
            {
                "date": date,
                "temp_max": daily.get("temperature_2m_max", [None])[i],
                "temp_min": daily.get("temperature_2m_min", [None])[i],
                "temp_avg": daily.get("temperature_2m_mean", [None])[i],
                "humidity": daily.get("relative_humidity_2m_mean", [None])[i],
                "precipitation": daily.get("precipitation_sum", [None])[i],
                "wind_speed": daily.get("wind_speed_10m_max", [None])[i],
                "wind_gust": daily.get("wind_gusts_10m_max", [None])[i],
                "weather_code": daily.get("weather_code", [None])[i],
            }
        )

    return weather_data


@step(job_type="batch", vcpu=4, memory_mb=8192)
def run_duckdb_analysis(weather_data: list[dict]) -> dict:
    """Run all analyses in a single DuckDB connection."""
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE weather (
            date DATE,
            temp_max DOUBLE,
            temp_min DOUBLE,
            temp_avg DOUBLE,
            humidity DOUBLE,
            precipitation DOUBLE,
            wind_speed DOUBLE,
            wind_gust DOUBLE,
            weather_code INT
        )
    """)

    for row in weather_data:
        if row["date"]:
            con.execute(
                "INSERT INTO weather VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    row["date"],
                    row["temp_max"],
                    row["temp_min"],
                    row["temp_avg"],
                    row["humidity"],
                    row["precipitation"],
                    row["wind_speed"],
                    row["wind_gust"],
                    row["weather_code"],
                ],
            )

    temp = con.execute("""
        SELECT MIN(temp_min), MAX(temp_max), AVG(temp_avg), AVG(humidity) FROM weather
    """).fetchone()

    monthly = con.execute("""
        SELECT strftime(date, '%Y-%m'), MIN(temp_min), MAX(temp_max), AVG(temp_avg)
        FROM weather GROUP BY 1 ORDER BY 1
    """).fetchall()

    precip = con.execute("""
        SELECT SUM(precipitation), COUNT(*), MAX(precipitation) FROM weather WHERE precipitation > 0
    """).fetchone()

    rainy_days = con.execute("""
        SELECT date, precipitation, weather_code FROM weather WHERE precipitation > 0 ORDER BY precipitation DESC LIMIT 5
    """).fetchall()

    wind = con.execute("""
        SELECT AVG(wind_speed), MAX(wind_gust), COUNT(*) FROM weather WHERE wind_speed > 30
    """).fetchone()

    gusty = con.execute("""
        SELECT date, wind_speed, wind_gust FROM weather WHERE wind_gust IS NOT NULL ORDER BY wind_gust DESC LIMIT 5
    """).fetchall()

    con.close()

    WMO_CODES = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        80: "Slight showers",
        81: "Moderate showers",
        82: "Violent showers",
        95: "Thunderstorm",
    }

    return {
        "temperature": {
            "min_temp": temp[0],
            "max_temp": temp[1],
            "avg_temp": round(temp[2], 1) if temp[2] else 0,
            "avg_humidity": round(temp[3], 1) if temp[3] else 0,
            "monthly": [
                {"month": m[0], "min": m[1], "max": m[2], "avg": round(m[3], 1)}
                for m in monthly
            ],
        },
        "precipitation": {
            "total": precip[0] or 0,
            "rainy_days": precip[1] or 0,
            "max_daily": precip[2] or 0,
            "rainiest": [
                {
                    "date": r[0],
                    "precip": r[1],
                    "code": WMO_CODES.get(r[2], f"Code {r[2]}"),
                }
                for r in rainy_days
            ],
        },
        "wind": {
            "avg_speed": round(wind[0], 1) if wind[0] else 0,
            "max_gust": wind[1] or 0,
            "windy_days": wind[2] or 0,
            "gustiest": [{"date": g[0], "speed": g[1], "gust": g[2]} for g in gusty],
        },
    }


@step
def format_summary(data: dict) -> str:
    """Format results as readable summary."""
    t = data["temperature"]
    p = data["precipitation"]
    w = data["wind"]

    lines = [
        "=" * 50,
        "WEATHER ANALYSIS SUMMARY (Open-Meteo Data)",
        "=" * 50,
        "",
        "TEMPERATURE:",
        f"  Range: {t['min_temp']}°C to {t['max_temp']}°C",
        f"  Average: {t['avg_temp']}°C, Humidity: {t['avg_humidity']}%",
    ]

    if t.get("monthly"):
        lines.append("  Monthly:")
        for m in t["monthly"]:
            lines.append(
                f"    {m['month']}: {m['avg']}°C (min: {m['min']}°, max: {m['max']}°)"
            )

    lines.extend(
        [
            "",
            "PRECIPITATION:",
            f"  Total: {p['total']}mm, Rainy days: {p['rainy_days']}",
            f"  Max daily: {p['max_daily']}mm",
            "  Rainiest days:",
        ]
    )
    for r in p.get("rainiest", [])[:3]:
        lines.append(f"    {r['date']}: {r['precip']}mm ({r['code']})")

    lines.extend(
        [
            "",
            "WIND:",
            f"  Avg speed: {w['avg_speed']} km/h, Max gust: {w['max_gust']} km/h",
            f"  Windy days (>30 km/h): {w['windy_days']}",
            "=" * 50,
        ]
    )

    return "\n".join(lines)


@flow
def weather_flow(
    location: str = "New York",
    start_date: str = "2024-01-01",
    end_date: str = "2024-01-31",
):
    """Weather data analysis pipeline using DuckDB and Open-Meteo."""
    return (
        geocode_location(location)
        .next(fetch_weather, start_date=start_date, end_date=end_date)
        .next(run_duckdb_analysis)
        .next(format_summary)
    )


if __name__ == "__main__":
    from lokki import main

    main(weather_flow)
