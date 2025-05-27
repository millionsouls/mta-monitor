import os
import csv
import requests
import proto.gtfs_realtime_pb2 as gtfs_realtime_pb2
import proto.gtfs_realtime_lirr_pb2 as gtfs_realtime_lirr_pb2

'''
{
  "id": "GO101_25_661_T",
  "trip_update": {
    "trip": {
      "trip_id": "GO101_25_661",
      "start_date": "20250527",
      "schedule_relationship": "SCHEDULED",
      "route_id": "10",
      "direction_id": 1
    },
    "stop_time_update": [
      {
        "stop_sequence": 1,
        "departure": { "delay": 0, "time": 1748385720 },
        "stop_id": "14",
        "schedule_relationship": "SCHEDULED",
        "mta_railroad_stop_time_update": {
          "track": "A",
          "trainStatus": ""
        }
      },
      ...
    ],
    "timestamp": 1748383135
  }
}
'''
ROUTES = {}
STOP_NAMES = {}
ROUTE_COLORS = {}
FEED_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/lirr%2Fgtfs-lirr"

def get_station_name(stop_id):
    stop_id = stop_id.strip()
    if stop_id in STOP_NAMES:
        return STOP_NAMES[stop_id]
    if stop_id[:-1] in STOP_NAMES:
        return STOP_NAMES[stop_id[:-1]]
    return stop_id

def fetch_lirr_feed():
    response = requests.get(FEED_URL)
    response.raise_for_status()
    return response.content

class LIRRFeed:
    def __init__(self, line):
        print(f"Fetching LIRR feed for line: {line}")
        feed_bytes = fetch_lirr_feed()
        self.feed = gtfs_realtime_pb2.FeedMessage()

        if feed_bytes:
            try:
                self.feed.ParseFromString(feed_bytes)
            except Exception as e:
                print("Failed to parse LIRR feed. Error:", e)
                self.feed = None
        else:
            self.feed = None

    @property
    def trips(self):
        if not self.feed:
            return []
        return [LIRRTrip(entity.trip_update) for entity in self.feed.entity if entity.HasField("trip_update")]

    @property
    def vehicles(self):
        if not self.feed:
            return []
        return [LIRRVehicle(entity.vehicle) for entity in self.feed.entity if entity.HasField("vehicle")]

class LIRRTrip:
    def __init__(self, trip_update):
        self.trip_update = trip_update
        self.trip = trip_update.trip
        self.stop_time_updates = [LIRRStopTimeUpdate(stu) for stu in trip_update.stop_time_update]
        self.direction = self.trip.direction_id

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
        self.stop_sequence = getattr(stu, "stop_sequence", None)
        self.stop_id = getattr(stu, "stop_id", "")
        self.stop_name = get_station_name(self.stop_id)
        self.arrival = stu.arrival.time if stu.HasField("arrival") else None
        self.departure = stu.departure.time if stu.HasField("departure") else None
        self.schedule_relationship = getattr(stu, "schedule_relationship", "")
        
        self.track = ""
        self.train_status = ""
        if stu.HasExtension(gtfs_realtime_lirr_pb2.mta_railroad_stop_time_update):
            lirr_update = stu.Extensions[gtfs_realtime_lirr_pb2.mta_railroad_stop_time_update]
            self.track = getattr(lirr_update, "track", "")
            self.train_status = getattr(lirr_update, "trainStatus", "")
    
    def to_dict(self):
        return {
            "stop_sequence": self.stop_sequence,
            "stop_id": self.stop_id,
            "stop_name": self.stop_name,
            "arrival": self.arrival,
            "adelay": self.stu.arrival.delay, 
            "ddelay": self.stu.departure.delay,
            "departure": self.departure,
            "schedule_relationship": self.schedule_relationship,
            "track": self.track,
            "train_status": self.train_status,
        }

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
            
class LIRRStaticData:
    def __init__(self):
        self._load_routes()
        self._load_stop_names()
        self._load_route_colors()

    def _load_routes(self, filepath="static/lirr/routes.txt"):
        if not os.path.exists(filepath):
            print("Failed to find trips.txt for LIRR")
            return
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                ROUTES[row['route_id'].strip()] = row['route_long_name'].strip()
        print("Trips loaded for LIRR:", len(ROUTES))

    def _load_stop_names(self, filepath="static/lirr/stops.txt"):
        if not os.path.exists(filepath):
            print("Failed to find stops.txt for LIRR")
            return
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                STOP_NAMES[row["stop_id"].strip()] = row["stop_name"].strip()

            print("Station names loaded for LIRR:", len(STOP_NAMES))

    
    def _load_route_colors(self, filepath="static/lirr/routes.txt"):
        if not os.path.exists(filepath):
            print("Failed to find routes.txt for LIRR")
            return
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                route_id = row["route_id"].strip()
                color = "#" + row["route_color"].strip()
                text_color = "#" + row["route_text_color"].strip()
                ROUTE_COLORS[route_id] = {
                    "color": color,
                    "text_color": text_color
                }

    def get_headsign(self, route_id):
        for id, head in ROUTES.items():
            if route_id in id:
                return head
        return route_id
    
    def get_colors(self, route_id):
        return ROUTE_COLORS.get(route_id, {"color": "#FFFFFF", "text_color": "#000000"})