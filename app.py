from flask import Flask, request, render_template, jsonify
from datetime import datetime, timedelta
from geopy.distance import distance
from geopy.geocoders import Nominatim
import dotenv
import os
import pycountry
import requests
import pytz
import string
import sqlite3
import re
import math

dotenv.load_dotenv()

app = Flask(__name__)


API_KEY = os.getenv("api_key")

DB_PATH = "data/cities.sqlite3"


@app.template_filter("fmt_dt")
def fmt_dt(unix_ts, fmt="%Y-%m-%d %H:%M:%S", tz_name="UTC"):
    tz = pytz.timezone(tz_name)
    dt = datetime.fromtimestamp(int(unix_ts), tz)
    return dt.strftime(fmt)


@app.template_filter("to_bft")
def to_bft(speed_ms):
    if speed_ms < 0:
        return 0
    bft = int(math.floor((speed_ms / 0.836) ** (2 / 3)))
    return min(bft, 12)


BASE62 = string.digits + string.ascii_lowercase + string.ascii_uppercase


def to_base62(num):
    if num == 0:
        return "0"
    digits = []
    while num:
        num, rem = divmod(num, 62)
        digits.append(BASE62[rem])
    return "".join(reversed(digits))


def from_base62(s):
    num = 0
    for char in s:
        num = num * 62 + BASE62.index(char)
    return num


def encode_place_id(lat, lon, precision=5):
    lat_int = int((lat + 90) * 10**precision)
    lon_int = int((lon + 180) * 10**precision)
    combined = (lat_int << 26) + lon_int
    id_str = to_base62(combined)

    return id_str


def decode_place_id(encoded, precision=5):
    combined = from_base62(encoded)
    lon_mask = (1 << 26) - 1
    lon_int = combined & lon_mask
    lat_int = combined >> 26
    lat = lat_int / 10**precision - 90
    lon = lon_int / 10**precision - 180
    return lat, lon


def full_country(country_code):
    country = pycountry.countries.get(alpha_2=country_code.upper())
    return country.name if country else None


def country_for_coordinates(lat, lon):
    geolocator = Nominatim(user_agent="geoapi")
    try:
        lat = float(lat)
        lon = float(lon)
        location = geolocator.reverse((lat, lon), language="en")
        if location and "country_code" in location.raw["address"]:
            return location.raw["address"]["country_code"].upper()
    except (ValueError, TypeError):
        pass
    return None


def valid_coords(input_str):
    match = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", input_str)
    if not match:
        return False
    lat, lon = float(match.group(1)), float(match.group(2))
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return [lat, lon]
    return False


def user_search(term, limit=25):
    coords_test = valid_coords(term)
    if valid_coords(term):
        lat, lon = coords_test[0], coords_test[1]
        country = country_for_coordinates(lat, lon)

        if country:
            country_code = country
        else:
            country_code = "globe"
        return [
            {
                "name": f"{round(lat, 3)}, {round(lon, 3)}",
                "state": "Your coordinates",
                "country": country_code,
                "lat": lat,
                "lon": lon,
                "cool_id": encode_place_id(lat, lon),
            }
        ] + find_nearest_places(coords_test[0], coords_test[1])
    return search_city(term, limit)


def search_city(term, limit=25):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    query = """
        SELECT id, name, state_code, country_code, latitude, longitude
        FROM cities
        WHERE name LIKE ?
        ORDER BY 
          CASE 
            WHEN name = ? THEN 0
            WHEN name LIKE ? THEN 1
            ELSE 2
          END,
          name
        LIMIT ?
    """
    rows = cur.execute(query, (f"%{term}%", term, f"{term}%", limit)).fetchall()
    con.close()
    return [
        {
            "stupid_id": row[0],
            "name": row[1],
            "state": row[2],
            "country": row[3],
            "lat": float(row[4]),
            "lon": float(row[5]),
            "cool_id": encode_place_id(float(row[4]), float(row[5])),
        }
        for row in rows
    ]


def find_nearest_places(lat, lon):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    query = """
        SELECT id, name, state_code, country_code, latitude, longitude, 
        (6371 * acos(
            cos(radians(?)) * cos(radians(latitude)) * cos(radians(longitude) - radians(?)) +
            sin(radians(?)) * sin(radians(latitude))
        )) AS distance
        FROM cities
        ORDER BY distance
        LIMIT 10;
    """
    cur.execute(query, (lat, lon, lat))
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "stupid_id": row[0],
            "name": row[1],
            "state": row[2],
            "country": row[3],
            "lat": float(row[4]),
            "lon": float(row[5]),
            "cool_id": encode_place_id(float(row[4]), float(row[5])),
            "distance": row[6],
        }
        for row in rows
    ]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search")
def search():
    term = request.args.get("q")
    places = user_search(term)
    return render_template(
        "search.html",
        opt_list=places,
        term=term,
        full_country=full_country,
    )


@app.route("/search_list")
def search_list():
    term = request.args.get("q")
    places = user_search(term, limit=5)
    return render_template(
        "search_results.html",
        opt_list=places,
        term=term,
        full_country=full_country,
    )


@app.route("/weather/<string:place_id>")
def weather_place(place_id):
    lat, lon = decode_place_id(place_id)
    place_data = find_nearest_places(lat, lon)[0]

    if place_data["distance"] > 5:
        country = country_for_coordinates(lat, lon)

        if country:
            name = f"Somewhere in {full_country(country)}"
            country_code = country
        else:
            name = f"{round(lat, 3)}, {round(lon, 3)}"
            country_code = "globe"

        place_data = {
            "name": name,
            "state": "Unknown",
            "country": country_code,
            "lat": lat,
            "lon": lon,
            "cool_id": place_id,
            "distance": place_data["distance"],
        }

    country = full_country(place_data["country"])

    weather_data = requests.get(
        f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={API_KEY}&lang=en&units=metric"
    ).json()

    today = datetime.now(pytz.timezone(weather_data["timezone"]))
    today_fmt = today.strftime("%Y-%m-%d")
    tomorrow = today + timedelta(days=1)
    tomorrow_fmt = tomorrow.strftime("%Y-%m-%d")

    today_overview = requests.get(
        f"https://api.openweathermap.org/data/3.0/onecall/overview?lat={lat}&lon={lon}&appid={API_KEY}&date={today_fmt}&units=metric"
    ).json()

    tomorrow_overview = requests.get(
        f"https://api.openweathermap.org/data/3.0/onecall/overview?lat={lat}&lon={lon}&appid={API_KEY}&date={tomorrow_fmt}&units=metric"
    ).json()

    def get_icon(id):
        return f"https://openweathermap.org/img/wn/{id}@2x.png"

    return render_template(
        "weather.html",
        weather_data=weather_data,
        place_data=place_data,
        today_overview=today_overview,
        tomorrow_overview=tomorrow_overview,
        country=country,
        get_icon=get_icon,
    )


@app.route("/encode_place_id")
def encode_place_id_route():
    lat = float(request.args.get("lat"))
    lon = float(request.args.get("lon"))

    place_id = encode_place_id(lat, lon)

    return jsonify({"id": place_id})


if __name__ == "__main__":
    app.run(debug=True)
