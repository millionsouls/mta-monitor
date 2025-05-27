import proto.gtfs_realtime_pb2 as gtfs_realtime_pb2
import proto.gtfs_realtime_NYCT_pb2 as gtfs_realtime_nyct_pb2
from datetime import datetime
import csv
import os
import requests

def fmt_time(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    except Exception:
        return str(ts)

def load_stop_names(filepath="static/nyct/stops.txt"):
    stop_names = {}
    if not os.path.exists(filepath):
        return stop_names
    with open(filepath, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            stop_names[row["stop_id"].strip()] = row["stop_name"].strip()
    return stop_names

def get_station_name(stop_id, stop_names):
    stop_id = stop_id.strip()
    if stop_id in stop_names:
        return stop_names[stop_id]
    if stop_id[:-1] in stop_names:
        return stop_names[stop_id[:-1]]
    return stop_id

def get_direction_name(direction_id, trip_id="", stop_id=""):
    if direction_id == "0":
        return "Northbound"
    if direction_id == "1":
        return "Southbound"
    if trip_id.endswith("N"):
        return "Northbound"
    if trip_id.endswith("S"):
        return "Southbound"
    if trip_id.endswith("E"):
        return "Eastbound"
    if trip_id.endswith("W"):
        return "Westbound"
    if stop_id and stop_id[-1] in "NSEW":
        return {
            "N": "Northbound",
            "S": "Southbound",
            "E": "Eastbound",
            "W": "Westbound"
        }[stop_id[-1]]
    return "Unknown"

class NYCTFeed:
    def __init__(self, feed_bytes):
        self.feed = gtfs_realtime_pb2.FeedMessage()
        self.feed.ParseFromString(feed_bytes)

    @property
    def trips(self):
        trips = []
        for entity in self.feed.entity:
            if entity.HasField("trip_update"):
                trips.append(NYCTTrip(entity.trip_update))
        return trips

    @property
    def vehicles(self):
        vehicles = []
        for entity in self.feed.entity:
            if entity.HasField("vehicle"):
                vehicles.append(NYCTVehicle(entity.vehicle))
        return vehicles

    @property
    def alerts(self):
        alerts = []
        for entity in self.feed.entity:
            if entity.HasField("alert"):
                alerts.append(NYCTAlert(entity.alert))
        return alerts

class NYCTTrip:
    def __init__(self, trip_update):
        self.trip_update = trip_update
        self.trip = trip_update.trip
        self.stop_time_updates = [NYCTStopTimeUpdate(stu) for stu in trip_update.stop_time_update]

    @property
    def id(self):
        return self.trip.trip_id

    @property
    def direction_id(self):
        return getattr(self.trip, "direction_id", "")

    @property
    def start_time(self):
        return getattr(self.trip, "start_time", "")

class NYCTStopTimeUpdate:
    def __init__(self, stu):
        self.stu = stu
        self.stop_id = stu.stop_id
        self.arrival = stu.arrival.time if stu.HasField("arrival") else None
        self.departure = stu.departure.time if stu.HasField("departure") else None
        self.track = getattr(stu, "track", "")
        print(self.track)
        self.is_assigned = getattr(stu, "is_assigned", False)
        if stu.HasExtension(gtfs_realtime_nyct_pb2.nyct_stop_time_update):
            nyct_update = stu.Extensions[gtfs_realtime_nyct_pb2.nyct_stop_time_update]
            self.actual_track = getattr(nyct_update, "actual_track", "")
            self.is_assigned = getattr(nyct_update, "is_assigned", "")

class NYCTVehicle:
    def __init__(self, vehicle):
        self.vehicle = vehicle
        self.trip_id = vehicle.trip.trip_id
        self.current_status = vehicle.current_status
        self.stop_id = vehicle.stop_id
        self.timestamp = vehicle.timestamp

class NYCTAlert:
    def __init__(self, alert):
        self.alert = alert
        self.header_text = alert.header_text.translation[0].text if alert.header_text.translation else ""
        self.description_text = alert.description_text.translation[0].text if alert.description_text.translation else ""
        self.effect = alert.effect

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

class NYCTStaticData:
    def __init__(self, routes_fp="static/nyct/routes.txt", trips_fp="static/nyct/trips.txt"):
        self.routes = self._load_routes(routes_fp)
        self.trips = self._load_trips(trips_fp)

    def _load_routes(self, filepath):
        routes = {}
        if not os.path.exists(filepath):
            return routes
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                routes[row["route_id"].strip()] = row["route_long_name"].strip()
        return routes

    def _load_trips(self, filepath):
        trip_to_route = {}
        if not os.path.exists(filepath):
            return trip_to_route
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                trip_to_route[row["trip_id"].strip()] = row["route_id"].strip()
        return trip_to_route

    def get_route_long_name_by_trip(self, trip_id):
        route_id = self.trips.get(trip_id)
        if not route_id:
            # Fallback: find a trip_id that ends with the given trip_id
            for k, v in self.trips.items():
                if k.endswith(trip_id):
                    route_id = v
                    break
        return self.routes.get(route_id, "Unknown")