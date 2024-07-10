from flask import Flask, render_template, jsonify
import redis
import pandas as pd
import json
import requests_cache
import openmeteo_requests
from retry_requests import retry
import logging

logging.basicConfig(level=logging.DEBUG)
app = Flask(__name__, template_folder='templates')
r = redis.Redis(host='127.0.0.1', port=6379, db=0, socket_timeout=10, socket_connect_timeout=5)

def fetch_and_store_temperature_data():
    try:
        df = pd.read_csv("temperature_humidity_data1.csv")
        temperature_data = df.to_dict(orient="records")
        for i, record in enumerate(temperature_data):
            r.set(f"temperature_data_{i}", json.dumps(record))  # Store in Redis
        print("Temperature and humidity data stored in Redis successfully")
        return temperature_data
    except Exception as e:
        print(f"Error fetching and storing temperature data: {e}")
        return []

def fetch_weather_data():
    cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": 39.9334,
        "longitude": 32.8597,
        "hourly": ["temperature_2m", "relative_humidity_2m", "rain", "temperature_80m", "temperature_120m"],
        "timezone": "Europe/Istanbul",
        "past_days": 1,
        "forecast_days": 3
    }
    responses = openmeteo.weather_api(url, params=params)
    response = responses[0]

    hourly = response.Hourly()
    hourly_data = {
        "date": pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left"
        ).tolist(),
        "temperature_2m": hourly.Variables(0).ValuesAsNumpy().tolist(),
        "relative_humidity_2m": hourly.Variables(1).ValuesAsNumpy().tolist(),
        "rain": hourly.Variables(2).ValuesAsNumpy().tolist(),
        "temperature_80m": hourly.Variables(3).ValuesAsNumpy().tolist(),
        "temperature_120m": hourly.Variables(4).ValuesAsNumpy().tolist()
    }
    return hourly_data

def fetch_air_quality_data():
    cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": 39.9334,
        "longitude": 32.8597,
        "current": ["european_aqi", "us_aqi", "aerosol_optical_depth", "dust", "alder_pollen", "birch_pollen"],
        "hourly": ["pm10", "pm2_5", "carbon_monoxide", "ozone", "dust", "uv_index", "uv_index_clear_sky", "alder_pollen", "birch_pollen", "grass_pollen", "european_aqi"]
    }
    responses = openmeteo.weather_api(url, params=params)
    response = responses[0]
    
    current = response.Current()
    current_data = {
        "european_aqi": current.Variables(0).Value(),
        "us_aqi": current.Variables(1).Value(),
        "aerosol_optical_depth": current.Variables(2).Value(),
        "dust": current.Variables(3).Value(),
        "alder_pollen": current.Variables(4).Value(),
        "birch_pollen": current.Variables(5).Value()
    }

    return current_data

@app.route("/api/weather")
def get_weather():
    weather_data = fetch_weather_data()
    return jsonify(weather_data)

@app.route("/api/temperature")
def get_temperature():
    temperature_data = []
    i = 0
    while True:
        record = r.get(f"temperature_data_{i}")
        if record is None:
            break
        temperature_data.append(json.loads(record))
        i += 1
    if not temperature_data:
        temperature_data = fetch_and_store_temperature_data()
    return jsonify(temperature_data)

@app.route("/api/air_quality")
def get_air_quality():
    air_quality_data = fetch_air_quality_data()
    mask_needed = air_quality_data['european_aqi'] > 100
    air_quality_data['mask_needed'] = mask_needed
    return jsonify(air_quality_data)

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    fetch_and_store_temperature_data()
    app.run(debug=True)
