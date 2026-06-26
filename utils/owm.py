import math
import os
import sqlite3

import requests


OWM_BASE = "https://api.openweathermap.org"
OWM_PRO_BASE = "https://pro.openweathermap.org"


def debug_log(response, *args, **kwargs):
    print(f"[OWM] {response.request.method} {response.url}", flush=True)


session = requests.Session()
session.hooks["response"].append(debug_log)


def api_key():
    key = os.getenv("OWM_API_KEY")
    if not key:
        raise RuntimeError("OWM_API_KEY is not set")
    return key


def get_weather(lat, lon, units="metric"):
    r = session.get(
        f"{OWM_BASE}/data/3.0/onecall",
        params={"lat": lat, "lon": lon, "units": units, "appid": api_key()},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def get_hourly_forecast(lat, lon, units="metric"):
    try:
        r = session.get(
            f"{OWM_PRO_BASE}/data/2.5/forecast/hourly",
            params={
                "lat": lat,
                "lon": lon,
                "units": units,
                "cnt": 96,
                "appid": api_key(),
            },
            timeout=10,
        )
        r.raise_for_status()
        items = r.json().get("list", [])
        result = []
        for item in items:
            main = item.get("main", {})
            wind = item.get("wind", {})
            clouds = item.get("clouds", {})
            rain = item.get("rain", {})
            snow = item.get("snow", {})
            entry = {
                "dt": item["dt"],
                "temp": main.get("temp"),
                "feels_like": main.get("feels_like"),
                "pressure": main.get("pressure"),
                "humidity": main.get("humidity"),
                "dew_point": main.get("temp_kf"),
                "uvi": item.get("uvi", 0),
                "clouds": clouds.get("all", 0),
                "visibility": item.get("visibility"),
                "wind_speed": wind.get("speed"),
                "wind_gust": wind.get("gust"),
                "wind_deg": wind.get("deg"),
                "pop": item.get("pop", 0),
                "weather": item.get("weather", []),
            }
            if rain:
                entry["rain"] = rain
            if snow:
                entry["snow"] = snow
            result.append(entry)
        return result
    except Exception:
        return None


def get_16day_forecast(lat, lon, units="metric"):
    try:
        r = session.get(
            f"{OWM_BASE}/data/2.5/forecast/daily",
            params={
                "lat": lat,
                "lon": lon,
                "units": units,
                "cnt": 16,
                "appid": api_key(),
            },
            timeout=10,
        )
        r.raise_for_status()
        items = r.json().get("list", [])
        result = []
        for item in items:
            entry = {
                "dt": item["dt"],
                "sunrise": item.get("sunrise"),
                "sunset": item.get("sunset"),
                "temp": item.get("temp", {}),
                "feels_like": item.get("feels_like", {}),
                "pressure": item.get("pressure"),
                "humidity": item.get("humidity"),
                "dew_point": item.get("dew_point"),
                "wind_speed": item.get("speed"),
                "wind_deg": item.get("deg"),
                "wind_gust": item.get("gust"),
                "weather": item.get("weather", []),
                "clouds": item.get("clouds"),
                "pop": item.get("pop", 0),
                "uvi": item.get("uvi"),
                "rain": item.get("rain"),
                "snow": item.get("snow"),
            }
            result.append(entry)
        return result
    except Exception:
        return None


def get_location(lat, lon):
    r = session.get(
        f"{OWM_BASE}/geo/1.0/reverse",
        params={"lat": lat, "lon": lon, "limit": 1, "appid": api_key()},
        timeout=10,
    )
    r.raise_for_status()
    results = r.json()
    return results[0] if results else {}


def get_air_pollution(lat, lon):
    try:
        r = session.get(
            f"{OWM_BASE}/data/2.5/air_pollution",
            params={"lat": lat, "lon": lon, "appid": api_key()},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def random_city(min_population=500_000):
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "cities.sqlite3")
    db = sqlite3.connect(db_path)
    row = db.execute(
        "SELECT latitude, longitude FROM cities WHERE population > ? ORDER BY RANDOM() LIMIT 1",
        (min_population,),
    ).fetchone()
    db.close()
    return row


def db_stats():
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "cities.sqlite3")
    db = sqlite3.connect(db_path)
    city_count = db.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
    country_count = db.execute(
        "SELECT COUNT(DISTINCT country_code) FROM cities"
    ).fetchone()[0]
    db.close()
    return {"city_count": city_count, "country_count": country_count}


def search_cities(query, limit=5):
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "cities.sqlite3")
    safe_query = query.replace('"', '""')
    fts_query = f'"{safe_query}"*'
    db = sqlite3.connect(db_path)
    rows = db.execute(
        """
        SELECT c.name, c.ascii_name, c.latitude, c.longitude, c.country_code, c.state, c.population
        FROM cities_fts f
        JOIN cities c ON c.id = f.rowid
        WHERE cities_fts MATCH ?
        LIMIT 500
        """,
        (fts_query,),
    ).fetchall()
    db.close()

    query_len = len(query)

    def score(row):
        ascii_name = row[1] or row[0]
        ratio = query_len / len(ascii_name) if ascii_name else 0
        return ratio * math.log10(max(row[6], 1))

    rows.sort(key=score, reverse=True)
    if limit is not None:
        rows = rows[:limit]

    return [
        {"name": r[0], "lat": r[2], "lon": r[3], "country": r[4], "state": r[5]}
        for r in rows
    ]
