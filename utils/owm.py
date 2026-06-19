import math
import os
import sqlite3

import requests


OWM_BASE = "https://api.openweathermap.org"


def api_key():
    key = os.getenv("OWM_API_KEY")
    if not key:
        raise RuntimeError("OWM_API_KEY is not set")
    return key


def get_weather(lat, lon, units="metric"):
    url = f"{OWM_BASE}/data/3.0/onecall"
    params = {
        "lat": lat,
        "lon": lon,
        "units": units,
        "appid": api_key(),
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def get_location(lat, lon):
    url = f"{OWM_BASE}/geo/1.0/reverse"
    params = {
        "lat": lat,
        "lon": lon,
        "limit": 1,
        "appid": api_key(),
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    results = response.json()
    return results[0] if results else {}


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
