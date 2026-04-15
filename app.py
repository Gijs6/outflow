from flask import Flask, render_template, url_for

import os

from dotenv import load_dotenv
import pycountry

from utils.filters import register_filters
from utils.owm import get_weather, get_location


load_dotenv(override=True)

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", os.urandom(100).hex())

register_filters(app)


@app.route("/")
def index():
    return render_template("index.jinja")


@app.route("/weather/<coords>")
def weather(coords):
    island_url = url_for("weather_island", coords=coords)
    return render_template("weather.jinja", island_url=island_url)


@app.route("/weather/<coords>/island")
def weather_island(coords):
    lat, lon = coords.split(",")

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
