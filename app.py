from flask import Flask, jsonify, render_template, request
from nyct_refs import (
    fmt_time, load_stop_names, get_station_name, get_direction_name,
    NYCTFeed, fetch_feed, NYCTStaticData
)
from lirr_refs import (
    fmt_time as lirr_fmt_time, LIRRFeed, fetch_lirr_feed, LIRRStaticData
)

app = Flask(__name__)

STOP_NAMES = load_stop_names()
LIRR_STATIC = LIRRStaticData()
NYCT_STATIC = NYCTStaticData()

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
        if hasattr(trip.trip, "route_id") and trip.trip.route_id.upper() != line:
            continue
        trip_id = trip.id
        direction = get_direction_name(trip.direction_id, trip_id, trip.stop_time_updates[0].stop_id if trip.stop_time_updates else "")
        route_long_name = NYCT_STATIC.get_route_long_name_by_trip(trip_id)
        if trip.stop_time_updates:
            next_stop = trip.stop_time_updates[0]
            train_list.append({
                "route_long_name": route_long_name,
                "trip_id": trip_id,
                "direction": direction,
                "next_stop": next_stop.stop_id,
                "next_stop_name": get_station_name(next_stop.stop_id, STOP_NAMES),
                "departure": fmt_time(next_stop.departure),
                "arrival": fmt_time(next_stop.arrival),
                "actual_track": next_stop.track,
                "is_assigned": next_stop.is_assigned,
            })
        else:
            train_list.append({
                "route_long_name": route_long_name,
                "trip_id": trip_id,
                "direction": direction,
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

@app.route("/api/lirr/trains")
def api_lirr_trains():
    feed_bytes = fetch_lirr_feed()
    feed = LIRRFeed(feed_bytes)
    train_list = []
    for trip in feed.trips:
        trip_id = trip.id
        route_info = LIRR_STATIC.get_route_info_by_trip(trip_id)
        if trip.stop_time_updates:
            next_stop = trip.stop_time_updates[0]
            train_list.append({
                "route_name": route_info["name"],
                "route_color": route_info["color"],
                "route_text_color": route_info["text_color"],
                "trip_id": trip_id,
                "next_stop": next_stop.stop_id,
                "next_stop_name": LIRR_STATIC.get_station_name(next_stop.stop_id),
                "departure": next_stop.departure,
                "arrival": next_stop.arrival,
                "track": next_stop.track,
                "status": next_stop.train_status,
            })
        else:
            train_list.append({
                "route_name": route_info["name"],
                "route_color": route_info["color"],
                "route_text_color": route_info["text_color"],
                "trip_id": trip_id,
                "next_stop": "000",
                "next_stop_name": "N/A",
                "departure": "",
                "arrival": "",
                "track": "",
                "status": "",
            })
    return jsonify(train_list)

@app.route("/api/lirr/vehicles")
def api_lirr_vehicles():
    feed_bytes = fetch_lirr_feed()
    feed = LIRRFeed(feed_bytes)
    vehicles = []
    for vehicle in feed.vehicles:
        vehicles.append({
            "trip_id": vehicle.trip_id,
            "current_status": vehicle.current_status,
            "stop_id": vehicle.stop_id,
            "stop_name": lirr_get_station_name(vehicle.stop_id, LIRR_STOP_NAMES),
            "timestamp": lirr_fmt_time(vehicle.timestamp),
        })
    return jsonify(vehicles)

@app.route("/api/lirr/alerts")
def api_lirr_alerts():
    feed_bytes = fetch_lirr_feed()
    feed = LIRRFeed(feed_bytes)
    alerts = []
    for alert in feed.alerts:
        alerts.append({
            "header_text": alert.header_text,
            "description_text": alert.description_text,
            "effect": alert.effect,
        })
    return jsonify(alerts)

@app.route("/api/lirr/stops")
def api_lirr_stops():
    stops = [{"stop_id": k, "stop_name": v} for k, v in LIRR_STOP_NAMES.items()]
    return jsonify(stops)

if __name__ == "__main__":
    STOP_NAMES = load_stop_names()
    app.run(debug=True)