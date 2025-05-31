# Outflow

Outflow is a small weather app prototype built with Flask.  
You can search for places and get weather info using the OpenWeatherMap API. Still a bit of a mess, still work in progress.

## Running the app

- Clone the repo
- Add a .env file with your OpenWeatherMap API key  
  `api_key={your_api_key}`
- Install dependencies: pip install -r requirements.txt
- Install the cities db from <https://github.com/dr5hn/countries-states-cities-database/blob/master/sqlite/cities.sqlite3> and put it in /data/cities.sqlite3
- (optinal but nice) install flags from <https://github.com/lipis/flag-icons/tree/main/flags/4x3> and put them in /static/flags
- Run it with `python app.py`
