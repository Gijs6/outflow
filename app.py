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


@app.route("/search/<string:term>")
def search(term):
    url = f"http://api.openweathermap.org/geo/1.0/direct?q={term}&limit=1000&appid={API_KEY}"

    response = requests.get(url)
    data = response.json()

    return jsonify(data)


@app.route("/weather/<string:place>")
def weather_place(place):
    # The URL of the places is the place name in the slug and a lat and lon in the query params
    # If there is no lat or lon in the query params, it will search for lat and lon based on the place name, and return the first result
    # To ensure that the correct lat and lon for a place name is being used (because there are many, many places with the same name), users use the search page

    lat = request.args.get("lat")
    lon = request.args.get("lon")

    if not lat or not lon:
        search_data = requests.get(
            f"http://api.openweathermap.org/geo/1.0/direct?q={place}&limit=1&appid={API_KEY}"
        ).json()
        lat = search_data[0]["lat"]
        lon = search_data[0]["lon"]

        return redirect(url_for("weather_place", place=place, lat=lat, lon=lon))

    weather_data = requests.get(
        f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={API_KEY}&lang=en&units=metric"
    ).json()

    return render_template("weather.html", weather_data=weather_data)


if __name__ == "__main__":
    app.run(debug=True)
