from flask import Flask, request, render_template, jsonify, redirect, session
from datetime import datetime, timedelta
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
import logging
import traceback
from flask_babel import Babel, get_locale, gettext, format_datetime
from babel import Locale

dotenv.load_dotenv()

app = Flask(__name__)

logging.basicConfig(level=logging.WARNING)

API_KEY = os.getenv("api_key")

DB_PATH = "data/cities.sqlite3"

app.config["BABEL_DEFAULT_LOCALE"] = "en"
app.config["BABEL_SUPPORTED_LOCALES"] = ["en", "nl", "fr"]
app.config["BABEL_TRANSLATION_DIRECTORIES"] = "./translations"

app.secret_key = os.urandom(50)


def get_locale_thing():
    return (
        request.args.get("lang")
        or session.get("lang")
        or request.accept_languages.best_match(["en", "nl", "fr"])
    )


babel = Babel(app, locale_selector=get_locale_thing)


@app.route("/set_lang/<lang>")
def set_lang(lang):
    session["lang"] = lang
    return redirect("/")


# Babel format_datetimes uses ICU for the format, while I'm already using the normal python strftime and strptime behaviour, so here is a stupid converter

def strftime_to_icu(fmt):
    replacements = {
        '%Y': 'yyyy',
        '%y': 'yy',
        '%B': 'MMMM',
        '%b': 'MMM',
        '%m': 'MM',
        '%d': 'dd',
        '%A': 'EEEE',
        '%a': 'EEE',
        '%H': 'HH',
        '%I': 'hh',
        '%M': 'mm',
        '%S': 'ss',
        '%p': 'a',
        '%z': 'Z',
        '%Z': 'z',
    }

    for py_token, icu_token in replacements.items():
        fmt = fmt.replace(py_token, icu_token)
    return fmt


@app.template_filter("fmt_dt")
def fmt_dt(unix_ts, fmt="%Y-%m-%d %H:%M:%S", tz_name="UTC"):
    tz = pytz.timezone(tz_name)
    dt = datetime.fromtimestamp(int(unix_ts), tz)
    icu_fmt = strftime_to_icu(fmt)
    return format_datetime(dt, icu_fmt)


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
    country_code = country_code.upper()
    locale = str(get_locale())[:2]

    try:
        babel_locale = Locale.parse(locale)
        country_name = babel_locale.territories.get(country_code)
    except:
        country_name = None

    if not country_name:
        country = pycountry.countries.get(alpha_2=country_code)
        if not country:
            return gettext("Unknown")
        country_name = country.name

    return country_name


def country_for_coordinates(lat, lon):
    geolocator = Nominatim(user_agent="geoapi")
    try:
        lat = float(lat)
        lon = float(lon)
        location = geolocator.reverse((lat, lon), language=str(get_locale))
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
                "state": gettext("Your coordinates"),
                "country": country_code,
                "lat": lat,
                "lon": lon,
                "cool_id": encode_place_id(lat, lon),
            }
        ] + find_nearest_places(coords_test[0], coords_test[1])
    return search_city(term, limit)


def search_city(term, limit=25):
    try:
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


@app.route("/weather/<string:place_id>")
def weather_place(place_id):
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
            "state": gettext("Unknown"),
            "country": "globe",
            "lat": lat,
            "lon": lon,
            "cool_id": place_id,
            "distance": 0,
        }

    if place_data["distance"] > 5:
        country = country_for_coordinates(lat, lon)

        if country:
            name = gettext("Somewhere in %(place)s", place=full_country(country))
            country_code = country
        else:
            name = f"{round(lat, 3)}, {round(lon, 3)}"
            country_code = "globe"

        place_data = {
            "name": name,
            "state": gettext("Unknown"),
            "country": country_code,
            "lat": lat,
            "lon": lon,
            "cool_id": place_id,
            "distance": place_data.get("distance", 0),
        }

    lang = str(get_locale())

    try:
        weather_data = requests.get(
            f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={API_KEY}&lang={lang}&units=metric"
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
                f"https://api.openweathermap.org/data/3.0/onecall/overview?lat={lat}&lon={lon}&appid={API_KEY}&date={today_fmt}&units=metric&lang={lang}"
            ).json()

        if tomorrow_fmt:
            tomorrow_overview = requests.get(
                f"https://api.openweathermap.org/data/3.0/onecall/overview?lat={lat}&lon={lon}&appid={API_KEY}&date={tomorrow_fmt}&units=metric&lang={lang}"
            ).json()
    except Exception as e:
        logging.warning(f"Error fetching overview data: {e}")
        today_overview = {}
        tomorrow_overview = {}

    def get_icon(id):
        return f"https://openweathermap.org/img/wn/{id}@2x.png"

    return render_template(
        "weather.html",
        weather_data=weather_data,
        place_data=place_data,
        today_overview=today_overview,
        tomorrow_overview=tomorrow_overview,
        get_icon=get_icon,
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


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_server_error(e):
    logging.error("Internal Server Error: %s", traceback.format_exc())
    return render_template("500.html"), 500


if __name__ == "__main__":
    app.run(debug=True)
