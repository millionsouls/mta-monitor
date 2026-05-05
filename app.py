from flask import Flask, jsonify, render_template, request
from nyct_refs import (NYCTFeed, NYCTStaticData)
from lirr_refs import ( LIRRFeed, LIRRStaticData)
from datetime import datetime
from cache_manager import start as start_cache, ensure_static_present, get_state as cache_get_state, wait_for_version as cache_wait_for_version, client_connected, client_disconnected
import time
from flask import Response, stream_with_context
import gzip
from io import BytesIO
import json
import logging
import threading

app = Flask(__name__)

_LAST_BUILT_VERSION = None
_LAST_BUILT_TRAINS = None
_BUILD_LOCK = threading.Lock()


# Ensure GTFS static files exist (runs updater once if missing)
ensure_static_present()
# Start background tasks: realtime cache (1 min) and static updater (24h)
start_cache(realtime_interval=60, static_interval_hours=24)

# SSE endpoint that pushes complete train data when updates arrive
# This is the ONLY data channel — all train data flows through here
@app.route('/events')
def sse_events():
    def gen():
        last_version = -1
        client_addr = request.remote_addr
        # register client so background fetcher can be enabled
        client_connected()
        try:
            # send initial data
            initial = cache_get_state().get('version')
            logging.info(f"[SSE] CLIENT {client_addr} connected (version={initial})")
            trains, version = get_cached_trains()
            payload = {'version': initial, 'timestamp': time.time(), 'trains': trains}
            logging.debug(f"[SSE] CLIENT {client_addr} initial: {len(trains['nyct'])} NYCT, {len(trains['lirr'])} LIRR trains")
            yield f"data: {json.dumps(payload)}\n\n"
            last_version = initial
            while True:
                new_version = cache_wait_for_version(last_version, timeout=30)
                if new_version > last_version:
                    # New data available — build and push all trains at once
                    trains, version = get_cached_trains()
                    payload = {'version': new_version, 'timestamp': time.time(), 'trains': trains}
                    logging.info(f"[SSE] CLIENT {client_addr} UPDATE v{new_version}: {len(trains['nyct'])} NYCT, {len(trains['lirr'])} LIRR")
                    yield f"data: {json.dumps(payload)}\n\n"
                    last_version = new_version
                else:
                    # keep connection alive (no new data yet)
                    yield ': heartbeat\n\n'
        finally:
            # unregister client when generator exits (client disconnected)
            try:
                client_disconnected()
                logging.info(f"[SSE] CLIENT {client_addr} disconnected")
            except Exception:
                pass
    # Use stream_with_context so the generator has request context
    rv = Response(stream_with_context(gen()), content_type='text/event-stream')
    rv.headers['Cache-Control'] = 'no-cache'
    rv.headers['X-Accel-Buffering'] = 'no'

    return rv


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
    if content_type.startswith(('application/json', 'text/')):
        try:
            data = response.get_data()
            gz = gzip.compress(data)
            response.set_data(gz)
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Content-Length'] = str(len(gz))
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

def get_cached_trains():
    global _LAST_BUILT_VERSION, _LAST_BUILT_TRAINS

    state = cache_get_state()
    version = state['version']

    if _LAST_BUILT_VERSION == version:
        return _LAST_BUILT_TRAINS, version

    with _BUILD_LOCK:
        if _LAST_BUILT_VERSION != version:
            trains = build_all_trains()
            _LAST_BUILT_TRAINS = trains
            _LAST_BUILT_VERSION = version

    return _LAST_BUILT_TRAINS, version


def build_all_trains():
    """Build complete train data for all lines (called when update arrives)."""
    try:
        nyct_feed = NYCTFeed("ALL")
        nyct_trains = []
        if nyct_feed and nyct_feed.feed:
            for trip in nyct_feed.trips:
                color_info = NYCT_STATIC.get_colors(trip.trip.route_id)
                route_details = NYCT_STATIC.get_route_details(trip.trip.route_id)
                if trip.stop_time_updates:
                    stu = trip.stop_time_updates[0]
                    nyct_trains.append({
                        "system": "nyct",
                        "route_id": trip.trip.route_id,
                        "route_short_name": route_details["short_name"],
                        "route_long_name": route_details["long_name"],
                        "route_desc": route_details["desc"],
                        "route_color": color_info["color"],
                        "route_text_color": color_info["text_color"],
                        "trip_name": NYCT_STATIC.get_headsign(trip.id),
                        "trip_id": trip.id,
                        "train_id": trip.nyct_trip.train_id if hasattr(trip, 'nyct_trip') else "",
                        "direction": trip.direction if hasattr(trip, 'direction') else "",
                        "current_stop": stu.stop_id,
                        "current_stop_name": stu.stop_name,
                        "next_stop": stu.stop_id,
                        "next_stop_name": stu.stop_name,
                        "departure": fmt_time(stu.departure),
                        "arrival": fmt_time(stu.arrival),
                        "actual_track": stu.actual_track if hasattr(stu, 'actual_track') else "",
                        "is_assigned": trip.assigned if hasattr(trip, 'assigned') else False,
                    })
        
        lirr_feed = LIRRFeed("ALL")
        lirr_trains = []
        if lirr_feed and lirr_feed.feed:
            for trip in lirr_feed.trips:
                color_info = LIRR_STATIC.get_colors(trip.trip.route_id)
                if trip.stop_time_updates:
                    stu = [s.to_dict(trip) for s in trip.stop_time_updates]
                    lirr_trains.append({
                        "system": "lirr",
                        "route_name": LIRR_STATIC.get_route(trip.trip.route_id),
                        "route_color": color_info["color"],
                        "route_text_color": color_info["text_color"],
                        "trip_id": trip.id,
                        "headsign": LIRR_STATIC.get_headsign(trip.id),
                        "service_id": LIRR_STATIC.get_service_id(trip.id),
                        "stu": stu,
                    })
        
        return {"nyct": nyct_trains, "lirr": lirr_trains}
    except Exception as e:
        logging.error(f"Error building train data: {e}")
        return {"nyct": [], "lirr": []}
    
@app.route("/")
def index():
    logging.info("[HTTP] Serving index page")
    return render_template("index.html")

@app.route("/api/nyct/trains")
def api_nyct_trains():
    # Deprecated: use SSE /events instead
    client_addr = request.remote_addr
    line = request.args.get("line", "A").upper()
    logging.warning(f"[HTTP-DEPRECATED] CLIENT {client_addr} tried /api/nyct/trains?line={line} (should use SSE only)")
    # Return 410 Gone to signal endpoint is gone
    return jsonify({"error": "This endpoint is deprecated. Use SSE /events for all train data."}), 410

@app.route("/api/lirr/trains")
def api_lirr_trains():
    # Deprecated: use SSE /events instead
    client_addr = request.remote_addr
    logging.warning(f"[HTTP-DEPRECATED] CLIENT {client_addr} tried /api/lirr/trains (should use SSE only)")
    # Return 410 Gone to signal endpoint is gone
    return jsonify({"error": "This endpoint is deprecated. Use SSE /events for all train data."}), 410

if __name__ == "__main__":
    app.run(debug=False)