from flask import Flask, request, render_template, jsonify, redirect
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
import unicodedata
import dotenv
import os
import pycountry
import requests
import pytz
import string
import sqlite3
import re
import math
import logging
import traceback


dotenv.load_dotenv()

app = Flask(__name__)

logging.basicConfig(level=logging.WARNING)

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
    return round(lat, precision), round(lon, precision)  # Weird float behaviour


def full_country(country_code):
    country = pycountry.countries.get(alpha_2=country_code.upper())

    countries_that_need_an_article = [
        "BS",  # Bahamas
        "GM",  # Gambia
        "NL",  # Netherlands
        "PH",  # Philippines
        "AE",  # United Arab Emirates
        "GB",  # United Kingdom
        "US",  # United States
        "CZ",  # Czech Republic
        "DO",  # Dominican Republic
        "CF",  # Central African Republic
        "CG",  # Congo
        "CD",  # Democratic Republic of the Congo
        "MH",  # Marshall Islands
        "SB",  # Solomon Islands
        "MV",  # Maldives
        "KM",  # Comoros
        "FM",  # Federated States of Micronesia
        "VI",  # United States Virgin Islands
        "VG",  # British Virgin Islands
    ]

    if not country:
        return "Unknown"
    elif country_code.upper() in countries_that_need_an_article:
        return f"the {country.name}"
    else:
        return country.name


def country_for_coordinates(lat, lon):
    geolocator = Nominatim(user_agent="geoapi")
    try:
        lat = float(lat)
        lon = float(lon)
        location = geolocator.reverse((lat, lon), language="en")
        if location and "country_code" in location.raw["address"]:
            return location.raw["address"]["country_code"].upper()
    except Exception as e:
        logging.warning(f"Error in country_for_coordinates: {e}")
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


def strip_diacritics(s):
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).lower()


def make_col(con, column_name):
    cur = con.cursor()
    cur.execute("PRAGMA table_info(cities)")
    columns = [row[1] for row in cur.fetchall()]
    if column_name not in columns:
        cur.execute(f"ALTER TABLE cities ADD COLUMN {column_name} TEXT")
        return True
    return False


def normalize_city_names(con):
    if make_col(con, "search_name"):
        cur = con.cursor()
        cur.execute("SELECT id, name FROM cities")
        rows = cur.fetchall()

        for city_id, name in rows:
            normalized = strip_diacritics(name)
            cur.execute(
                "UPDATE cities SET search_name = ? WHERE id = ?", (normalized, city_id)
            )

        con.commit()


def search_city(term, limit=25):
    try:
        con = sqlite3.connect(DB_PATH)

        normalize_city_names(con)

        cur = con.cursor()
        query = """
            SELECT id, name, state_code, country_code, latitude, longitude
            FROM cities
            WHERE search_name LIKE ?
            LIMIT ?
        """
        norm_term = strip_diacritics(term)
        rows = cur.execute(query, (f"%{norm_term}%", limit)).fetchall()
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
    except Exception as e:
        logging.warning(f"Error in search_city: {e}")
        return []


def find_nearest_places(lat, lon):
    try:
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
    except Exception as e:
        logging.warning(f"Error in find_nearest_places: {e}")
        return []


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search")
def search():
    term = request.args.get("q")
    try:
        places = user_search(term)
    except Exception as e:
        logging.warning(f"Error in user_search: {e}")
        places = []

    if len(places) == 1:  # If there is only 1 search result, skip the search page
        return redirect(f"/weather/{places[0]['cool_id']}")

    return render_template(
        "search.html",
        opt_list=places,
        term=term,
        full_country=full_country,
    )


@app.route("/search_list")
def search_list():
    term = request.args.get("q")
    try:
        places = user_search(term, limit=5)
    except Exception as e:
        logging.warning(f"Error in user_search (search_list): {e}")
        places = []

    return render_template(
        "search_results.html",
        opt_list=places,
        term=term,
        full_country=full_country,
    )


def get_icon_url(id):
    return f"https://openweathermap.org/img/wn/{id}@2x.png"


@app.route("/weather/<string:place_id>")
def weather_page(place_id):
    try:
        lat, lon = decode_place_id(place_id)
    except Exception as e:
        logging.warning(f"Error decoding place_id {place_id}: {e}")
        return "Invalid place ID", 400

    try:
        place_data_list = find_nearest_places(lat, lon)
        if not place_data_list:
            raise ValueError("No nearby places found")
        place_data = place_data_list[0]
    except Exception as e:
        logging.warning(f"Error finding nearest places: {e}")
        place_data = {
            "name": f"{round(lat, 3)}, {round(lon, 3)}",
            "state": "Unknown",
            "country": "globe",
            "lat": lat,
            "lon": lon,
            "cool_id": place_id,
            "distance": 0,
        }

    try:
        place_data_list = find_nearest_places(lat, lon)
        if not place_data_list:
            raise ValueError("No nearby places found")
        place_data = place_data_list[0]
    except Exception as e:
        logging.warning(f"Error finding nearest places: {e}")
        place_data = {
            "name": f"{round(lat, 3)}, {round(lon, 3)}",
            "state": "Unknown",
            "country": "globe",
            "lat": lat,
            "lon": lon,
            "cool_id": place_id,
            "distance": 0,
        }

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
            "distance": place_data.get("distance", 0),
        }

    informative_data = {"lat": lat, "lon": lon, "place_data": place_data}

    return render_template(
        "weather.html",
        place_id=place_id,
        lat=lat,
        lon=lon,
        place_data=place_data,
        informative_data=informative_data,
    )


@app.route("/tables/<string:place_id>")
def weather_tables(place_id):
    lat, lon = decode_place_id(place_id)

    weather_data = requests.get(
        f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={API_KEY}&lang=en&units=metric"
    ).json()

    try:
        place_data_list = find_nearest_places(lat, lon)
        if not place_data_list:
            raise ValueError("No nearby places found")
        place_data = place_data_list[0]
    except Exception as e:
        logging.warning(f"Error finding nearest places: {e}")
        place_data = {
            "name": f"{round(lat, 3)}, {round(lon, 3)}",
            "state": "Unknown",
            "country": "globe",
            "lat": lat,
            "lon": lon,
            "cool_id": place_id,
            "distance": 0,
        }

    try:
        place_data_list = find_nearest_places(lat, lon)
        if not place_data_list:
            raise ValueError("No nearby places found")
        place_data = place_data_list[0]
    except Exception as e:
        logging.warning(f"Error finding nearest places: {e}")
        place_data = {
            "name": f"{round(lat, 3)}, {round(lon, 3)}",
            "state": "Unknown",
            "country": "globe",
            "lat": lat,
            "lon": lon,
            "cool_id": place_id,
            "distance": 0,
        }

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
            "distance": place_data.get("distance", 0),
        }

    for section_value in weather_data.values():
        if isinstance(section_value, list):
            all_keys = set()
            for item in section_value:
                if isinstance(item, dict):
                    all_keys.update(item.keys())

            for item in section_value:
                if isinstance(item, dict):
                    for key in all_keys:
                        if key not in item:
                            item[key] = ""

    def value_output(value):
        if isinstance(value, int):
            tz_name = weather_data["timezone"]
            tz = pytz.timezone(tz_name)
            dt = datetime.fromtimestamp(int(value), tz)

            now = datetime.now(tz)
            lower_bound = now - timedelta(days=365)
            upper_bound = now + timedelta(days=365)

            if lower_bound <= dt <= upper_bound:
                return dt.strftime("%Y-%m-%d %H:%M:%S")

        return value

    return render_template(
        "tables.html",
        table_data=weather_data,
        place_data=place_data,
        value_output=value_output,
    )


@app.route("/weather_content", methods=["POST"])
def weather_content():
    data = request.json

    lat = data["lat"]
    lon = data["lon"]
    place_data = data["place_data"]

    try:
        weather_data = requests.get(
            f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={API_KEY}&lang=en&units=metric"
        ).json()
    except Exception as e:
        logging.warning(f"Error fetching weather data: {e}")
        weather_data = {}

    try:
        today = datetime.now(pytz.timezone(weather_data.get("timezone", "UTC")))
        today_fmt = today.strftime("%Y-%m-%d")
        tomorrow = today + timedelta(days=1)
        tomorrow_fmt = tomorrow.strftime("%Y-%m-%d")
    except Exception as e:
        logging.warning(f"Error processing dates: {e}")
        today_fmt = tomorrow_fmt = None

    try:
        today_overview = {}
        tomorrow_overview = {}

        if today_fmt:
            today_overview = requests.get(
                f"https://api.openweathermap.org/data/3.0/onecall/overview?lat={lat}&lon={lon}&appid={API_KEY}&date={today_fmt}&units=metric"
            ).json()

        if tomorrow_fmt:
            tomorrow_overview = requests.get(
                f"https://api.openweathermap.org/data/3.0/onecall/overview?lat={lat}&lon={lon}&appid={API_KEY}&date={tomorrow_fmt}&units=metric"
            ).json()
    except Exception as e:
        logging.warning(f"Error fetching overview data: {e}")
        today_overview = {}
        tomorrow_overview = {}

    # map_coords = [
    #     {"lat": lat, "lon": lon},
    #     {"lat": lat - 10, "lon": lon},
    #     {"lat": lat + 10, "lon": lon},
    #     {"lat": lat, "lon": lon - 10},
    #     {"lat": lat, "lon": lon + 10},
    # ]

    return render_template(
        "weather_content.html",
        lat=lat,
        lon=lon,
        weather_data=weather_data,
        place_data=place_data,
        today_overview=today_overview,
        tomorrow_overview=tomorrow_overview,
        get_icon_url=get_icon_url,
        # map_coords=map_coords
    )


@app.route("/encode_place_id")
def encode_place_id_route():
    try:
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("lon"))
        place_id = encode_place_id(lat, lon)
    except Exception as e:
        logging.warning(f"Error in encode_place_id_route: {e}")
        return jsonify({"error": "Invalid parameters"}), 400

    return jsonify({"id": place_id})


@app.route("/decode_place_id")
def decode_place_id_route():
    try:
        id = request.args.get("id")
        lat, lon = decode_place_id(id)
    except Exception as e:
        logging.warning(f"Error in decode_place_id_route: {e}")
        return jsonify({"error": "Invalid place ID"}), 400

    return jsonify({"lat": lat, "lon": lon})


@app.route("/map_api/<layer>/<z>/<x>/<y>.png")
def mapapi(layer, z, x, y):
    response = requests.get(
        f"https://tile.openweathermap.org/map/{layer}/{z}/{x}/{y}.png?appid={API_KEY}"
    )
    return response.content


# @app.route("/icon_api/<id>")
# def iconapi(id):
#     response = requests.get(get_icon_url(id))
#     return response.content


# @app.route("/weather_api/current")
# def currentapi():
#     lat = request.args.get("lat")
#     lon = request.args.get("lon")

#     data = requests.get(
#         f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}"
#     ).json()

#     return data


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_server_error(e):
    logging.error("Internal Server Error: %s", traceback.format_exc())
    return render_template("500.html"), 500


if __name__ == "__main__":
    app.run(debug=True, port=8000)
