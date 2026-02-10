from flask import Flask, jsonify, render_template, request
from nyct_refs import (NYCTFeed, NYCTStaticData)
from lirr_refs import ( LIRRFeed, LIRRStaticData)
from datetime import datetime
from cache_manager import start as start_cache, ensure_static_present, get_state as cache_get_state, wait_for_version as cache_wait_for_version
from flask import Response, stream_with_context
import gzip
from io import BytesIO
import json
import logging

app = Flask(__name__)

# Ensure GTFS static files exist (runs updater once if missing)
ensure_static_present()
# Start background tasks: realtime cache (1 min) and static updater (24h)
start_cache(realtime_interval=60, static_interval_hours=24)


# Simple SSE endpoint that notifies clients when cache version updates
@app.route('/events')
def sse_events():
    def gen():
        last_version = -1
        # send initial ping
        initial = cache_get_state().get('version')
        print(f"[app] SSE client connected, initial version={initial}")
        yield f"data: {json.dumps({'version': initial})}\n\n"
        last_version = initial
        while True:
            new_version = cache_wait_for_version(last_version, timeout=30)
            if new_version > last_version:
                # include timestamp so clients can show relative "updated X ago"
                payload = {'version': new_version, 'timestamp': time.time()}
                print(f"[app] SSE sending update version={new_version} ts={payload['timestamp']}")
                yield f"data: {json.dumps(payload)}\n\n"
                last_version = new_version
            else:
                # keep connection alive
                yield ': heartbeat\n\n'
    # Use stream_with_context so the generator has request context
    rv = Response(stream_with_context(gen()), mimetype='text/event-stream')
    # Recommended headers for SSE and to disable buffering in proxies (nginx, etc.)
    rv.headers['Cache-Control'] = 'no-cache'
    rv.headers['X-Accel-Buffering'] = 'no'
    rv.headers['Connection'] = 'keep-alive'
    rv.headers['Content-Type'] = 'text/event-stream; charset=utf-8'
    return rv


@app.route('/debug/cache')
def debug_cache():
    # return cache state for visualizer
    state = cache_get_state()
    return jsonify(state)


@app.route('/debug')
def debug_page():
    return render_template('debug.html')


@app.after_request
def compress_response(response):
    accept = request.headers.get('Accept-Encoding', '')
    if 'gzip' not in accept.lower():
        return response
    # don't compress SSE or already encoded
    if response.direct_passthrough:
        return response
    # explicitly skip SSE content type
    if response.mimetype == 'text/event-stream':
        return response
    if response.headers.get('Content-Encoding'):
        return response
    content_type = response.mimetype or ''
    if content_type.startswith('application/json') or content_type.startswith('text/'):
        try:
            data = response.get_data()
            gz = gzip.compress(data)
            response.set_data(gz)
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Content-Length'] = len(gz)
        except Exception:
            pass
    return response

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
    logging.info("Serving index page")
    return render_template("index.html")

# --- NYCT (Subway) Endpoints ---
@app.route("/api/nyct/trains")
def api_nyct_trains():
    # Fetch the line from query parameters, default to "A"
    line = request.args.get("line", "A").upper()
    logging.info(f"API: /api/nyct/trains line={line}")
    feed = NYCTFeed(line)
    if feed is None:
        logging.warning("NYCT feed was None")
        return jsonify([])
    
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
    logging.info(f"API: returning {len(train_list)} NYCT trains")
    return jsonify(train_list)

# --- LIRR Endpoints ---
@app.route("/api/lirr/trains")
def api_lirr_trains():
    line = request.args.get("line", "ALL").upper()
    logging.info(f"API: /api/lirr/trains line={line}")
    feed = LIRRFeed(line)
    if feed is None:
        logging.warning("LIRR feed was None")
        return jsonify([])

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
    logging.info(f"API: returning {len(train_list)} LIRR trains")
    return jsonify(train_list)

if __name__ == "__main__":
    app.run(debug=False)