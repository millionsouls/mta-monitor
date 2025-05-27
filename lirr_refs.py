import os
import csv
from datetime import datetime
import requests
import proto.gtfs_realtime_pb2 as gtfs_realtime_pb2
import proto.gtfs_realtime_lirr_pb2 as gtfs_realtime_lirr_pb2

def fmt_time(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    except Exception:
        return str(ts)

class LIRRStaticData:
    """Handles loading and lookup of static LIRR stop data."""
    def __init__(self, stops_fp="static/lirr/stops.txt", routes_fp="static/lirr/routes.txt", trips_fp="static/lirr/trips.txt"):
        self.stop_names = self._load_stop_names(stops_fp)
        self.routes = self._load_routes(routes_fp)
        self.trip_to_route = self._load_trip_to_route(trips_fp)

    def _load_stop_names(self, filepath):
        stop_names = {}
        if not os.path.exists(filepath):
            return stop_names
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                stop_names[row["stop_id"].strip()] = row["stop_name"].strip()
        return stop_names

    def _load_routes(self, filepath):
        routes = {}
        if not os.path.exists(filepath):
            return routes
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                routes[row["route_id"].strip()] = {
                    "name": row["route_long_name"].strip(),
                    "color": row["route_color"].strip(),
                    "text_color": row["route_text_color"].strip()
                }
        return routes

    def _load_trip_to_route(self, filepath):
        trip_to_route = {}
        if not os.path.exists(filepath):
            return trip_to_route
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                trip_to_route[row["trip_id"].strip()] = row["route_id"].strip()
        return trip_to_route

    def get_station_name(self, stop_id):
        stop_id = stop_id.strip()
        if stop_id in self.stop_names:
            return self.stop_names[stop_id]
        if stop_id[:-1] in self.stop_names:
            return self.stop_names[stop_id[:-1]]
        return stop_id

    def get_route_info_by_trip(self, trip_id):
        route_id = self.trip_to_route.get(trip_id)
        if not route_id:
            return {"route_id": "", "name": "Unknown", "color": "CCCCCC", "text_color": "000000"}
        route = self.routes.get(route_id, {})
        return {
            "route_id": route_id,
            "name": route.get("name", "Unknown"),
            "color": "#" + route.get("color", "CCCCCC"),
            "text_color": "#" + route.get("text_color", "000000")
        }

def fetch_lirr_feed():
    LIRR_FEED_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/lirr%2Fgtfs-lirr"
    response = requests.get(LIRR_FEED_URL)
    response.raise_for_status()
    return response.content

class LIRRFeed:
    def __init__(self, feed_bytes):
        self.feed = gtfs_realtime_pb2.FeedMessage()
        self.feed.ParseFromString(feed_bytes)

    @property
    def trips(self):
        return [LIRRTrip(entity.trip_update) for entity in self.feed.entity if entity.HasField("trip_update")]

    @property
    def vehicles(self):
        return [LIRRVehicle(entity.vehicle) for entity in self.feed.entity if entity.HasField("vehicle")]

    @property
    def alerts(self):
        return [LIRRAlert(entity.alert) for entity in self.feed.entity if entity.HasField("alert")]

class LIRRTrip:
    def __init__(self, trip_update):
        self.trip_update = trip_update
        self.trip = trip_update.trip
        self.stop_time_updates = [LIRRStopTimeUpdate(stu) for stu in trip_update.stop_time_update]

    @property
    def id(self):
        return self.trip.trip_id

    @property
    def direction_id(self):
        return getattr(self.trip, "direction_id", "")

    @property
    def start_time(self):
        return getattr(self.trip, "start_time", "")

class LIRRStopTimeUpdate:
    def __init__(self, stu):
        self.stu = stu
        self.stop_id = stu.stop_id
        self.arrival_time = stu.arrival.time if stu.HasField("arrival") else None
        self.departure_time = stu.departure.time if stu.HasField("departure") else None
        # LIRR Extensions
        self.track = ""
        self.train_status = ""
        if stu.HasExtension(gtfs_realtime_lirr_pb2.mta_railroad_stop_time_update):
            lirr_update = stu.Extensions[gtfs_realtime_lirr_pb2.mta_railroad_stop_time_update]
            self.track = getattr(lirr_update, "track", "")
            self.train_status = getattr(lirr_update, "trainStatus", "")

    @property
    def arrival(self):
        return fmt_time(self.arrival_time)

    @property
    def departure(self):
        return fmt_time(self.departure_time)

class LIRRVehicle:
    def __init__(self, vehicle):
        self.vehicle = vehicle
        self.trip_id = vehicle.trip.trip_id
        self.current_status = vehicle.current_status
        self.stop_id = vehicle.stop_id
        self.timestamp = vehicle.timestamp
        self.carriage_details = None
        if vehicle.HasExtension(gtfs_realtime_lirr_pb2.mta_railroad_carriage_details):
            self.carriage_details = vehicle.Extensions[gtfs_realtime_lirr_pb2.mta_railroad_carriage_details]

class LIRRAlert:
    def __init__(self, alert):
        self.alert = alert
        self.header_text = alert.header_text.translation[0].text if alert.header_text.translation else ""
        self.description_text = alert.description_text.translation[0].text if alert.description_text.translation else ""
        self.effect = alert.effect