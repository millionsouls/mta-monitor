from flask import Flask, jsonify, render_template, request
from datetime import datetime
import requests
import proto.gtfs_realtime_pb2 as gtfs_realtime_pb2

app = Flask(__name__)

# ([list of routes], feed URL)
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

def fmt_time(ts):
    if not ts:
        return ""
    # epoch seconds to HH:MM:SS
    try:
        return datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    except Exception:
        return str(ts)

def get_train_data(line="A"):
    feed_bytes = fetch_feed(line)
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(feed_bytes)
    train_list = []

    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        trip_update = entity.trip_update
        trip_id = trip_update.trip.trip_id
        direction = getattr(trip_update.trip, "direction_id", "")
        stop_time_updates = trip_update.stop_time_update

        if stop_time_updates:
            next_stop = stop_time_updates[0]
            stop_id = next_stop.stop_id
            arrival_time = next_stop.arrival.time if next_stop.HasField("arrival") else None
            departure_time = next_stop.departure.time if next_stop.HasField("departure") else None

            train_list.append({
                "trip_id": trip_id,
                "direction": direction,
                "next_stop": stop_id,
                "departure": fmt_time(departure_time),
                "arrival": fmt_time(arrival_time),
                "actual_track": "",  # NYCT extension: fill if needed
                "is_assigned": "",   # NYCT extension: fill if needed
            })
        else:
            train_list.append({
                "trip_id": trip_id,
                "direction": direction,
                "start_time": fmt_time(getattr(trip_update.trip, "start_time", "")),
                "next_stop": "No upcoming stops listed.",
                "departure": "",
                "arrival": "",
                "actual_track": "",
                "is_assigned": "",
            })
    return train_list

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/trains")
def api_trains():
    line = request.args.get("line", "A")
    return jsonify(get_train_data(line))

if __name__ == "__main__":
    app.run(debug=True)