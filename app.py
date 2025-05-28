from flask import Flask, request, render_template
import dotenv
import os
import pycountry
import requests
import string


dotenv.load_dotenv()

app = Flask(__name__)


API_KEY = os.getenv("api_key")


@app.route("/")
def index():
    return render_template("index.html")


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


def encode_place_id(lat, lon, name, country, precision=5):
    lat_int = int((lat + 90) * 10**precision)
    lon_int = int((lon + 180) * 10**precision)
    combined = (lat_int << 26) + lon_int
    id_str = to_base62(combined)
    meta = f"{name.replace(' ', '_')}:{country}"
    return f"{id_str}:{meta}"


def decode_place_id(encoded, precision=5):
    id_str, meta = encoded.split(":", 1)
    combined = from_base62(id_str)
    lon_mask = (1 << 26) - 1
    lon_int = combined & lon_mask
    lat_int = combined >> 26
    lat = lat_int / 10**precision - 90
    lon = lon_int / 10**precision - 180
    name, country = meta.split(":", 1)
    name = name.replace("_", " ")
    return lat, lon, name, country


def full_country(country_code):
    country = pycountry.countries.get(alpha_2=country_code.upper())
    return country.name if country else None


@app.route("/search")
def search():
    term = request.args.get("q")
    url = f"http://api.openweathermap.org/geo/1.0/direct?q={term}&limit=1000&appid={API_KEY}"

    response = requests.get(url)
    data = response.json()

    return render_template(
        "search.html",
        opt_list=data,
        encode_place_id=encode_place_id,
        full_country=full_country,
        term=term,
    )


@app.route("/weather/<string:place_id>")
def weather_place(place_id):
    lat, lon, name, country_code = decode_place_id(place_id)
    country = full_country(country_code)

    weather_data = requests.get(
        f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={API_KEY}&lang=en&units=metric"
    ).json()

    def get_icon(id):
        return f"https://openweathermap.org/img/wn/{id}@2x.png"

    return render_template(
        "weather.html",
        weather_data=weather_data,
        place_info={"name": name, "country": country, "country_code": country_code},
        get_icon=get_icon,
    )


if __name__ == "__main__":
    app.run(debug=True)
