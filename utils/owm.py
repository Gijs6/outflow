import os
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
