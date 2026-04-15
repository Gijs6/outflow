from flask import Flask, render_template, url_for, redirect

import os

from dotenv import load_dotenv
import pycountry

from utils.filters import register_filters
from utils.owm import get_weather, get_location
from utils.places import decode_place_id, encode_place_id


load_dotenv(override=True)

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", os.urandom(100).hex())

register_filters(app)


@app.route("/")
def index():
    return render_template("index.jinja")


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

    country = pycountry.countries.get(alpha_2=location["country"])

    return render_template(
        "weather/island.jinja", weather=data, location=location, country=country
    )


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.jinja"), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.jinja"), 500


if __name__ == "__main__":
    app.run(debug=True, port=8000)
