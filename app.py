from flask import Flask, jsonify, render_template, request
from nyct_gtfs import NYCTFeed
from datetime import datetime

app = Flask(__name__)

def get_train_data(line="A"):
    feed = NYCTFeed(line)
    trains = feed.filter_trips(line_id=[line], underway=True)
    train_list = []
    
    for train in trains:
        if train.stop_time_updates:
            next_stop = train.stop_time_updates[0]
            stop_name = getattr(next_stop, "stop_name", next_stop.stop_id)
            arrival_time = getattr(next_stop, "arrival", None)
            departure_time = getattr(next_stop, "departure", None)

            # Use the time string as-is, or return empty string if None
            def fmt_time(ts):
                return ts if ts else ""

            train_list.append({
                "trip_id": train.trip_id,
                "direction": train.direction,
                "next_stop": stop_name,
                "departure": fmt_time(departure_time),
                "arrival": fmt_time(arrival_time),
                "actual_track": getattr(train, "actual_track", ""),
                "is_assigned": getattr(train, "is_assigned", False)
            })
        else:
            train_list.append({
                "trip_id": train.trip_id,
                "direction": train.direction,
                "start_time": fmt_time(getattr(train, "start_time", "")),
                "next_stop": "No upcoming stops listed.",
                "departure": "",
                "arrival": "",
                "actual_track": getattr(train, "actual_track", ""),
                "is_assigned": getattr(train, "is_assigned", False)
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