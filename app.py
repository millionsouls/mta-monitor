from flask import Flask, jsonify, render_template, request
from nyct_refs import (fmt_time,NYCTFeed, NYCTStaticData)
from lirr_refs import (
    fmt_time as lirr_fmt_time, LIRRFeed, fetch_lirr_feed, LIRRStaticData
)

app = Flask(__name__)
LIRR_STATIC = LIRRStaticData()
NYCT_STATIC = NYCTStaticData()

@app.route("/")
def index():
    return render_template("index.html")

# --- NYCT (Subway) Endpoints ---
@app.route("/api/nyct/trains")
def api_nyct_trains():
    # Fetch the line from query parameters, default to "A"
    line = request.args.get("line", "A").upper()
    feed = NYCTFeed(line)
    if feed is None:
        return
    
    train_list = []
    for trip in feed.trips:
        # Only filter by line if not "ALL"
        if line != "ALL" and hasattr(trip.trip, "route_id") and trip.trip.route_id.upper() != line:
            continue

        if trip.stop_time_updates:
            stu = trip.stop_time_updates[0]
            color_info = NYCT_STATIC.get_colors(trip.trip.route_id)
            train_list.append({
                "route_id": trip.trip.route_id,
                "route_color": color_info["color"],
                "route_text_color": color_info["text_color"],
                "trip_name": NYCT_STATIC.get_headsign(trip.id),
                "trip_id": trip.id,
                "train_id": trip.nyct_trip.train_id,
                "direction": trip.direction,
                "next_stop": stu.stop_id,
                "next_stop_name": stu.stop_name,
                "departure": fmt_time(stu.departure),
                "arrival": fmt_time(stu.arrival),
                "actual_track": stu.actual_track,
                "is_assigned": trip.assigned,
            })
        else:
            train_list.append({
                "route_id": trip.trip.route_id,
                "route_color": color_info["color"],
                "route_text_color": color_info["text_color"],
                "route_long_name": "PH",
                "trip_id": trip.id,
                "direction": "PH",
                "next_stop": "000",
                "next_stop_name": "N/A",
                "departure": "",
                "arrival": "",
                "actual_track": "",
                "is_assigned": trip.assigned,
            })

    # Sort by route_id alphabetically
    train_list.sort(key=lambda x: x.get("route_id", ""))
    return jsonify(train_list)

# --- LIRR Endpoints ---

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
            "stop_name": LIRR_STATIC.get_station_name(vehicle.stop_id),
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
    stops = [{"stop_id": k, "stop_name": v} for k, v in LIRR_STATIC.stop_names.items()]
    return jsonify(stops)

if __name__ == "__main__":
    app.run(debug=True)