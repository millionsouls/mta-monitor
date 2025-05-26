from flask import Flask, jsonify, render_template, request
import requests
from nyct_refs import (
    fmt_time, load_stop_names, get_station_name, get_direction_name,
    NYCTFeed
)

app = Flask(__name__)

STOP_NAMES = load_stop_names()
ROUTE_FEED_MAP = [
    (["1", "2", "3", "4", "5", "6", "7", "S"], "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"),
    (["A", "C", "E", "SR"], "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace"),
    (["B", "D", "F", "M", "SF"], "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm"),
    (["G"], "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g"),
    (["J", "Z"], "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz"),
    (["L"], "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l"),
    (["N", "Q", "R", "W"], "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw"),
    (["SIR"], "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-sir"),
]

def get_feed_url_for_route(route):
    route = route.upper()
    for routes, url in ROUTE_FEED_MAP:
        if route in routes:
            return url
    raise ValueError(f"No feed URL for route {route}")

def fetch_feed(line):
    url = get_feed_url_for_route(line)
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.content

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/trains")
def api_trains():
    line = request.args.get("line", "A").upper()
    feed_bytes = fetch_feed(line)
    feed = NYCTFeed(feed_bytes)
    train_list = []
    for trip in feed.trips:
        # Filter by route_id (the train line)
        if hasattr(trip.trip, "route_id") and trip.trip.route_id.upper() != line:
            continue
        trip_id = trip.id
        direction = get_direction_name(trip.direction_id, trip_id, trip.stop_time_updates[0].stop_id if trip.stop_time_updates else "")
        if trip.stop_time_updates:
            next_stop = trip.stop_time_updates[0]
            train_list.append({
                "trip_id": trip_id,
                "direction": direction,
                "next_stop": next_stop.stop_id,
                "next_stop_name": get_station_name(next_stop.stop_id, STOP_NAMES),
                "departure": fmt_time(next_stop.departure_time),
                "arrival": fmt_time(next_stop.arrival_time),
                "actual_track": next_stop.actual_track,
                "is_assigned": next_stop.is_assigned,
            })
        else:
            train_list.append({
                "trip_id": trip_id,
                "direction": direction,
                "start_time": fmt_time(trip.start_time),
                "next_stop": "000",
                "next_stop_name": "N/A",
                "departure": "",
                "arrival": "",
                "actual_track": "",
                "is_assigned": "",
            })
    return jsonify(train_list)

@app.route("/api/vehicles")
def api_vehicles():
    line = request.args.get("line", "A").upper()
    feed_bytes = fetch_feed(line)
    feed = NYCTFeed(feed_bytes)
    vehicles = []
    for vehicle in feed.vehicles:
        # Filter by route_id (the train line)
        if hasattr(vehicle.vehicle.trip, "route_id") and vehicle.vehicle.trip.route_id.upper() != line:
            continue
        vehicles.append({
            "trip_id": vehicle.trip_id,
            "current_status": vehicle.current_status,
            "stop_id": vehicle.stop_id,
            "stop_name": get_station_name(vehicle.stop_id, STOP_NAMES),
            "timestamp": fmt_time(vehicle.timestamp),
        })
    return jsonify(vehicles)

@app.route("/api/alerts")
def api_alerts():
    line = request.args.get("line", "A")
    feed_bytes = fetch_feed(line)
    feed = NYCTFeed(feed_bytes)
    alerts = []
    for alert in feed.alerts:
        alerts.append({
            "header_text": alert.header_text,
            "description_text": alert.description_text,
            "effect": alert.effect,
        })
    return jsonify(alerts)

@app.route("/api/stops")
def api_stops():
    stops = [{"stop_id": k, "stop_name": v} for k, v in STOP_NAMES.items()]
    return jsonify(stops)

if __name__ == "__main__":
    STOP_NAMES = load_stop_names()
    app.run(debug=True)