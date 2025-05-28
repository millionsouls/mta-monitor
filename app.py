from flask import Flask, jsonify, render_template, request
from nyct_refs import (NYCTFeed, NYCTStaticData)
from lirr_refs import ( LIRRFeed, LIRRStaticData)
from datetime import datetime

app = Flask(__name__)
LIRR_STATIC = LIRRStaticData()
NYCT_STATIC = NYCTStaticData()

def fmt_time(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    except Exception:
        return str(ts)
    
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
        
        color_info = NYCT_STATIC.get_colors(trip.trip.route_id)
        if trip.stop_time_updates:
            stu = trip.stop_time_updates[0]
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
    line = request.args.get("line", "ALL").upper()
    feed = LIRRFeed(line)
    if feed is None:
        return 

    train_list = []
    for trip in feed.trips:
        if line != "ALL" and hasattr(trip.trip, "route_id") and trip.trip.route_id.upper() != line:
            continue
        
        color_info = LIRR_STATIC.get_colors(trip.trip.route_id)
        if trip.stop_time_updates:
            stu = [s.to_dict(trip) for s in trip.stop_time_updates]
            train_list.append({
                "route_name": LIRR_STATIC.get_headsign(trip.trip.route_id),
                "route_color": color_info["color"],
                "route_text_color": color_info["text_color"],
                "trip_id": trip.id,
                "stu": stu,
            })
        else:
            train_list.append({
                "route_name":trip.trip.route_id,
                "route_color": color_info["color"],
                "route_text_color": color_info["text_color"],
                "trip_id": trip.id,
            })
    return jsonify(train_list)

if __name__ == "__main__":
    app.run(debug=True)