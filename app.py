from flask import Flask, render_template, url_for, redirect, request, session

import os

from dotenv import load_dotenv
import pycountry

from utils.filters import register_filters
from utils.owm import get_weather, get_location, search_cities
from utils.places import decode_place_id, encode_place_id, parse_as_location


load_dotenv(override=True)

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", os.urandom(100).hex())

register_filters(app)


@app.route("/")
def index():
    return render_template(
        "index.jinja", recent_places=session.get("recent_places", [])
    )


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    is_htmx = request.headers.get("HX-Request") == "true"

    if is_htmx and len(query) < 2:
        return ""

    places = []

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
        results = search_cities(query)
        for result in results:
            places.append(
                {
                    "place_id": encode_place_id(result["lat"], result["lon"]),
                    "name": result["name"],
                    "state": result.get("state"),
                    "country": result.get("country"),
                }
            )

    if is_htmx:
        return render_template("search_results.jinja", places=places, query=query)

    return render_template("search.jinja", places=places, query=query)


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

    data = get_weather(lat, lon)
    location = get_location(lat, lon)

    country_code = location.get("country")
    country = pycountry.countries.get(alpha_2=country_code) if country_code else None

    name = location.get("name") or f"{lat}, {lon}"
    country_name = country.name if country else ""
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

    return render_template(
        "weather/island.jinja",
        weather=data,
        location=location,
        country=country,
        lat=lat,
        lon=lon,
    )


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.jinja"), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.jinja"), 500


if __name__ == "__main__":
    app.run(debug=True, port=8000, host="0.0.0.0")
