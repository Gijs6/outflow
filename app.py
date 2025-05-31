from flask import Flask, request, render_template
from datetime import datetime, timedelta
from geopy.distance import distance
import dotenv
import os
import pycountry
import requests
import pytz
import string
import sqlite3
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


def encode_place_id(lat, lon, data, precision=5):
    lat_int = int((lat + 90) * 10**precision)
    lon_int = int((lon + 180) * 10**precision)
    combined = (lat_int << 26) + lon_int
    id_str = to_base62(combined)

    set_place_data(id_str, data)

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


# Temp fix, probs use a db
place_data = {}


def get_place_data(id, lat, lon):
    if place_data.get(id):
        return place_data.get(id)
    else:
        geo_data = requests.get(
            f"http://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={lon}&limit=1&appid={API_KEY}"
        ).json()[0]
        set_place_data(id, geo_data)
        return geo_data


def set_place_data(id, data):
    place_data[id] = data


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
        }
        for row in rows
    ]


def fetch_places(term, limit=25, min_km=3):
    if term:
        data = search_city(term, limit)

        used_coords, filtered = [], []
        for opt in data:
            if all(
                distance((opt["lat"], opt["lon"]), (lat, lon)).km >= min_km
                for lat, lon in used_coords
            ):
                used_coords.append((opt["lat"], opt["lon"]))
                filtered.append(opt)
        return filtered
    return []


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search")
def search():
    term = request.args.get("q")
    places = fetch_places(term)
    return render_template(
        "search.html",
        opt_list=places,
        term=term,
        encode_place_id=encode_place_id,
        full_country=full_country,
    )


@app.route("/search_list")
def search_list():
    term = request.args.get("q")
    places = fetch_places(term, limit=5)
    return render_template(
        "search_results.html",
        opt_list=places,
        term=term,
        encode_place_id=encode_place_id,
        full_country=full_country,
    )


@app.route("/weather/<string:place_id>")
def weather_place(place_id):
    lat, lon = decode_place_id(place_id)
    place_data = get_place_data(place_id, lat, lon)
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


if __name__ == "__main__":
    app.run(debug=True)
