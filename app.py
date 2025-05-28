from flask import Flask, jsonify, request, redirect, url_for, render_template
import dotenv
import os
import requests


dotenv.load_dotenv()

app = Flask(__name__)


API_KEY = os.getenv("api_key")


@app.route("/")
def index():
    return "Between subtle shading and the absence of light lies the nuance of iqlusion"


def encode_place_id(lat, lon):
    lat_shortened = float(f"{lat:.6f}")
    lon_shortened = float(f"{lon:.6f}")

    lat_non_neg = lat_shortened + 180
    lon_non_neg = lon_shortened + 180

    lat_format = ("0" * (3 - len(str(lat_non_neg).split(".")[0])) + str(lat_non_neg)).replace(".", "")
    lon_format = ("0" * (3 - len(str(lon_non_neg).split(".")[0])) + str(lon_non_neg)).replace(".", "")

    encoded = f"{lat_format}_{lon_format}"
    return encoded


def decode_place_id(encoded):
    lat, lon = encoded.split("_")
    lat_decoded = float(lat[:3] + "." + lat[3:]) - 180
    lon_decoded = float(lon[:3] + "." + lon[3:]) - 180
    return lat_decoded, lon_decoded


@app.route("/search")
def search():
    term = request.args.get("q")
    url = f"http://api.openweathermap.org/geo/1.0/direct?q={term}&limit=1000&appid={API_KEY}"

    response = requests.get(url)
    data = response.json()

    return render_template("search.html", result_list=data, encode_place_id=encode_place_id)


@app.route("/weather/<string:place_id>")
def weather_place(place_id):
    lat, lon = decode_place_id(place_id)

    geo_data = requests.get(f"http://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={lon}&limit=1&appid={API_KEY}").json()
    place_info = geo_data[0]

    weather_data = requests.get(
        f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={API_KEY}&lang=en&units=metric"
    ).json()

    return render_template("weather.html", weather_data=weather_data, place_info=place_info)


if __name__ == "__main__":
    app.run(debug=True)
