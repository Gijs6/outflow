from flask import Flask, request, render_template
import dotenv
import os
import requests
import string


dotenv.load_dotenv()

app = Flask(__name__)


API_KEY = os.getenv("api_key")


@app.route("/")
def index():
    return "Between subtle shading and the absence of light lies the nuance of iqlusion"


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


def encode_place_id(lat, lon, precision=4):
    lat_int = int((lat + 90) * 10**precision)
    lon_int = int((lon + 180) * 10**precision)

    combined = (lat_int << 24) + lon_int

    return to_base62(combined)


def decode_place_id(encoded, precision=4):
    combined = from_base62(encoded)

    lon_mask = (1 << 24) - 1
    lon_int = combined & lon_mask
    lat_int = combined >> 24

    lat = lat_int / 10**precision - 90
    lon = lon_int / 10**precision - 180

    return lat, lon


@app.route("/search")
def search():
    term = request.args.get("q")
    url = f"http://api.openweathermap.org/geo/1.0/direct?q={term}&limit=1000&appid={API_KEY}"

    response = requests.get(url)
    data = response.json()

    return render_template(
        "search.html", result_list=data, encode_place_id=encode_place_id
    )


@app.route("/weather/<string:place_id>")
def weather_place(place_id):
    lat, lon = decode_place_id(place_id)

    geo_data = requests.get(
        f"http://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={lon}&limit=1&appid={API_KEY}"
    ).json()
    place_info = geo_data[0]

    weather_data = requests.get(
        f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={API_KEY}&lang=en&units=metric"
    ).json()

    return render_template(
        "weather.html", weather_data=weather_data, place_info=place_info
    )


if __name__ == "__main__":
    app.run(debug=True)
