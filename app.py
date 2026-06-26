from flask import (
    Flask,
    Response,
    abort,
    render_template,
    url_for,
    redirect,
    request,
    session,
    send_from_directory,
)

import os
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from dotenv import load_dotenv
import pycountry

from utils.filters import register_filters
import utils.owm as owm_module
from utils.owm import (
    get_weather,
    get_location,
    search_cities,
    get_air_pollution,
    get_hourly_forecast,
    get_16day_forecast,
    random_city,
    db_stats,
    session as owm_session,
    api_key as owm_api_key,
)
from utils.places import decode_place_id, encode_place_id, parse_as_location


load_dotenv(override=True)

app = Flask(__name__)


def get_secret_key():
    if key := os.getenv("SECRET_KEY"):
        return key
    key_path = os.path.join(os.path.dirname(__file__), "data", ".secret_key")
    if os.path.exists(key_path):
        with open(key_path) as f:
            return f.read().strip()
    key = os.urandom(50).hex()
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    with open(key_path, "w") as f:
        f.write(key)
    return key


app.secret_key = get_secret_key()
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=365)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

register_filters(app)
owm_module.DEBUG = app.debug


@app.before_request
def make_session_permanent():
    session.permanent = True


OWM_TILE_LAYERS = frozenset(
    {"precipitation_new", "temp_new", "clouds_new", "wind_new", "pressure_new"}
)

SUGGESTED_CITIES = [
    {
        "name": "Amsterdam",
        "country": "Netherlands",
        "place_id": encode_place_id(52.374, 4.890),
    },
    {
        "name": "London",
        "country": "United Kingdom",
        "place_id": encode_place_id(51.507, -0.128),
    },
    {
        "name": "New York",
        "country": "United States",
        "place_id": encode_place_id(40.713, -74.006),
    },
    {"name": "Tokyo", "country": "Japan", "place_id": encode_place_id(35.689, 139.692)},
    {
        "name": "Sydney",
        "country": "Australia",
        "place_id": encode_place_id(-33.868, 151.209),
    },
    {"name": "Paris", "country": "France", "place_id": encode_place_id(48.853, 2.350)},
]


@app.route("/tiles/<layer>/<int:z>/<int:x>/<int:y>.png")
def weather_tile(layer, z, x, y):
    if layer not in OWM_TILE_LAYERS:
        abort(404)
    try:
        resp = owm_session.get(
            f"https://tile.openweathermap.org/map/{layer}/{z}/{x}/{y}.png",
            params={"appid": owm_api_key()},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.HTTPError as e:
        abort(e.response.status_code if e.response is not None else 502)
    except requests.RequestException:
        abort(502)
    return Response(
        resp.content,
        content_type=resp.headers.get("content-type", "image/png"),
        headers={"Cache-Control": "public, max-age=600"},
    )


@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js", mimetype="application/javascript")


@app.route("/")
def index():
    recent = session.get("recent_places", [])
    favs = session.get("favourite_places", [])
    suggested = SUGGESTED_CITIES if not recent and not favs else []
    stats = db_stats()
    return render_template(
        "index.jinja",
        recent_places=recent,
        favourite_places=favs,
        suggested_cities=suggested,
        db_stats=stats,
    )


@app.route("/recents/clear", methods=["POST"])
def clear_recents():
    session["recent_places"] = []
    return ""


@app.route("/home/place/<place_id>/weather-mini")
def place_weather_mini(place_id):
    try:
        lat, lon = decode_place_id(place_id)
        data = get_weather(lat, lon)
        icon = data["current"]["weather"][0]["icon"]
        temp = round(data["current"]["temp"], 1)
    except Exception:
        return ""
    return render_template("home_place_weather.jinja", icon=icon, temp=temp)


@app.route("/lucky")
def lucky():
    row = random_city()
    if not row:
        return redirect(url_for("index"))
    return redirect(url_for("weather", place_id=encode_place_id(row[0], row[1])))


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    is_htmx = request.headers.get("HX-Request") == "true"

    if is_htmx and len(query) < 2:
        return ""

    places = []
    error = None

    location = parse_as_location(query)
    if location:
        lat, lon = location
        places.append(
            {
                "place_id": encode_place_id(lat, lon),
                "name": f"{lat}, {lon}",
                "state": None,
                "country": None,
                "is_direct": True,
            }
        )

    if len(query) >= 2:
        try:
            results = search_cities(query, limit=5 if is_htmx else None)
            for result in results:
                places.append(
                    {
                        "place_id": encode_place_id(result["lat"], result["lon"]),
                        "name": result["name"],
                        "state": result.get("state"),
                        "country": result.get("country"),
                    }
                )
        except Exception as e:
            error = str(e)

    if not error and len(places) == 1:
        target = url_for("weather", place_id=places[0]["place_id"])
        if is_htmx:
            return Response(status=204, headers={"HX-Redirect": target})
        return redirect(target)

    if is_htmx:
        return render_template(
            "search_results.jinja", places=places, query=query, error=error
        )

    return render_template("search.jinja", places=places, query=query, error=error)


@app.route("/goto/<coords>")
def weather_coords_redirect(coords):
    lat, lon = coords.split(",")
    return redirect(
        url_for("weather", place_id=encode_place_id(float(lat), float(lon))), 301
    )


@app.route("/weather/<place_id>")
def weather(place_id):
    island_url = url_for("weather_island", place_id=place_id)
    return render_template("weather.jinja", island_url=island_url)


@app.route("/weather/<place_id>/island")
def weather_island(place_id):
    lat, lon = decode_place_id(place_id)

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(get_weather, lat, lon): "weather",
            executor.submit(get_location, lat, lon): "location",
            executor.submit(get_air_pollution, lat, lon): "air_pollution",
            executor.submit(get_hourly_forecast, lat, lon): "hourly_forecast",
            executor.submit(get_16day_forecast, lat, lon): "daily_16",
        }
        results = {
            "weather": None,
            "location": {},
            "air_pollution": None,
            "hourly_forecast": None,
            "daily_16": None,
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception:
                results[key] = None if key != "location" else {}

    data = results["weather"]
    location = results["location"] or {}
    air_pollution = results["air_pollution"]
    hourly_forecast = results["hourly_forecast"]
    daily_16 = results["daily_16"]
    minutely = (data or {}).get("minutely")
    def alert_sort_key(a):
        ev = (a.get("event") or "").lower().strip()
        if ev[:7] == "extreme":
            level = 0
        elif ev[:8] == "moderate":
            level = 2
        else:
            level = 1
        return (level, a.get("start") or 0)

    alerts = sorted((data or {}).get("alerts") or [], key=alert_sort_key)

    country_code = location.get("country")
    country = pycountry.countries.get(alpha_2=country_code) if country_code else None

    name = location.get("name") or f"{lat}, {lon}"
    country_name = (
        (getattr(country, "common_name", None) or country.name) if country else ""
    )
    state = location.get("state") or ""
    entry = {
        "place_id": place_id,
        "name": name,
        "state": state,
        "country": country_name,
    }
    recent = session.get("recent_places", [])
    recent = [
        p
        for p in recent
        if p["place_id"] != place_id
        and not (
            p["name"] == name and p["state"] == state and p["country"] == country_name
        )
    ]
    recent.insert(0, entry)
    session["recent_places"] = recent[:5]

    favourites = session.get("favourite_places", [])
    is_favourite = any(p["place_id"] == place_id for p in favourites)

    return render_template(
        "weather/island.jinja",
        weather=data,
        air_pollution=air_pollution,
        hourly_forecast=hourly_forecast,
        daily_16=daily_16,
        minutely=minutely,
        alerts=alerts,
        location=location,
        country=country,
        lat=lat,
        lon=lon,
        place_id=place_id,
        name=name,
        state=state,
        country_name=country_name,
        is_favourite=is_favourite,
    )


@app.route("/weather/<place_id>/favourite", methods=["POST"])
def toggle_favourite(place_id):
    name = request.form.get("name", "")
    state = request.form.get("state", "")
    country = request.form.get("country", "")

    favourites = session.get("favourite_places", [])
    is_favourite = any(p["place_id"] == place_id for p in favourites)

    if is_favourite:
        favourites = [p for p in favourites if p["place_id"] != place_id]
    else:
        favourites.append(
            {"place_id": place_id, "name": name, "state": state, "country": country}
        )

    session["favourite_places"] = favourites

    return render_template(
        "weather/favourite_btn.jinja",
        place_id=place_id,
        is_favourite=not is_favourite,
        name=name,
        state=state,
        country_name=country,
    )


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.jinja"), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.jinja"), 500


if __name__ == "__main__":
    app.run(debug=True, port=8000, host="0.0.0.0")
