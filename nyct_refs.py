from proto import gtfs_realtime_pb2
from proto import gtfs_realtime_NYCT_pb2
import logging
from cache_manager import get_state as cache_get_state
import csv
import os
from cache_manager import get_nyct_feed

'''
FeedMessage
- header
    - gtfs_realtime_version
    - incrementality (enum Incrementality)
    - timestamp
- entity[] (FeedEntity)
    - id
    - alert
    - is_deleted [not used]
    - trip_update (TripUpdate)
        - trip (TripDescriptor)
            - trip_ud
            - route_id
            - start_time
            - start_date
            - schedule_relationship (enum ScheduleRelationship)
            - Extensions[nyct_trip_descriptor] (NYCTTripDescriptor)
                - is_assigned
                - train_id
                - direction (enum Direction)
        - stop_time_update[] (StopTimeUpdate)
                - stop_sequence [not used]
                - stop_id
                - arrival
                - departure
                - scheduled_relationship
            - Extensions[nyct_stop_time_update] (NYCTStopTimeUpdate)
                - scheduled_track
                - actual_track
        - vehicle [not used]
    - vehicle (VehiclePosition) [not used]
    - Extension[nyct_feed_header]
        - nyct_subway_version
        - trip_replacement_period
            - route_id
            - replacement_period
'''
TRIPS = {}
STOP_NAMES = {}
ROUTE_COLORS = {}
ROUTE_DETAILS = {}  # Store route_short_name and route_desc
_CACHED_ALL_VERSION = None
_CACHED_ALL_FEED = None

def get_station_name(stop_id):
    stop_id = stop_id.strip()
    if stop_id in STOP_NAMES:
        return STOP_NAMES[stop_id]
    if stop_id[:-1] in STOP_NAMES:
        return STOP_NAMES[stop_id[:-1]]
    return stop_id

def fetch_nyct_feed(line):
    cached = get_nyct_feed(line)
    if not cached:
        logging.warning("NYCT feed not available in cache")
    return cached


class NYCTFeed:
    def __init__(self, line):
        if line.upper() == "ALL":
            # Use cached parsed FeedMessage tied to the cache manager's version
            state = cache_get_state()
            version = state.get('version')
            global _CACHED_ALL_VERSION, _CACHED_ALL_FEED
            if _CACHED_ALL_FEED is not None and _CACHED_ALL_VERSION == version:
                # reuse previously parsed FeedMessage
                self.feed = _CACHED_ALL_FEED
                return

            logging.info("Fetching all NYCT feeds...")
            feeds_bytes = fetch_nyct_feed(line)
            combined = gtfs_realtime_pb2.FeedMessage()
            combined.entity.extend([])

            for feed_bytes in feeds_bytes:
                # Debug: detect likely HTML/JSON error responses
                if not feed_bytes:
                    continue
                if feed_bytes[:1] == b'{' or feed_bytes[:1] == b'<':
                    # skip non-protobuf responses
                    logging.debug("NYCT: skipping non-protobuf feed chunk")
                    continue

                try:
                    temp_feed = gtfs_realtime_pb2.FeedMessage()
                    temp_feed.ParseFromString(feed_bytes)
                    combined.entity.extend(temp_feed.entity)
                except Exception as e:
                    logging.debug(f"NYCT: Failed to parse feed chunk, skipping: {e}")
                    continue

            logging.info(f"Fetched {len(combined.entity)} entities from all feeds.")
            # cache parsed combined feed
            _CACHED_ALL_FEED = combined
            _CACHED_ALL_VERSION = version
            self.feed = combined
        else:
            bytes = fetch_nyct_feed(line)
            self.feed = gtfs_realtime_pb2.FeedMessage()
            if bytes:
                self.feed.ParseFromString(bytes)
            else:
                self.feed = None

    @property
    def trips(self):
        trips = []
        for entity in self.feed.entity:
            if entity.HasField("trip_update"):
                trips.append(NYCTTrip(entity.trip_update))
        return trips

    # NOT USED PER DOCUMENTATION
    @property
    def vehicles(self):
        # TODO
        pass

# Defiend in GTFS-realtime spec
class NYCTTrip:
    def __init__(self, trip_update):
        self.trip_update = trip_update
        self.trip = trip_update.trip
        self.stop_time_updates = [NYCTStopTimeUpdate(stu) for stu in trip_update.stop_time_update]

        # Access NYCT extension fields
        # Train_ID: 06 0123+ PEL/BBR is decoded as follows:
        #   - The first character represents the trip type designator. '0' identifies a scheduled revenue trip.
        #     Other revenue trip values that are a result of a change to the base schedule include:
        #     '=' (reroute), '/' (skip stop), '$' (turn train, aka shortly lined service).
        #   - The second character '6' represents the trip line (e.g., number 6 train).
        #   - The third set of characters identify the decoded origin time. The last character may be blank (“on the whole minute”) or '+' (“30 seconds”).
        #     Note: Origin times will not change when there is a trip type change.
        #   - This is followed by a three character “Origin Location” / “Destination Location”.
        # See: https://www.mta.info/document/134521
        if self.trip.HasExtension(gtfs_realtime_NYCT_pb2.nyct_trip_descriptor):
            self.nyct_trip = self.trip.Extensions[gtfs_realtime_NYCT_pb2.nyct_trip_descriptor]
            self.direction = gtfs_realtime_NYCT_pb2.NyctTripDescriptor.Direction.Name(self.nyct_trip.direction)
            self.assigned = self.nyct_trip.is_assigned
            # self.direction = self.nyct_trip.direction
            # self.train_id = self.nyct_trip.train_id
        else:
            pass
            # self.direction = None
            # self.train_id = None

    @property
    def id(self):
        return self.trip.trip_id

# All future stop times for trip, past stoptimes are omitted. 
# First StopTime in seuqence is the stop the train is currently approaching, stopped at or about to leave
# Stop is dropped from sequence when train departs station
class NYCTStopTimeUpdate:
    def __init__(self, stu):
        self.stu = stu
        self.stop_id = stu.stop_id
        self.stop_name = get_station_name(stu.stop_id)
        self.arrival = stu.arrival.time if stu.HasField("arrival") else None
        self.departure = stu.departure.time if stu.HasField("departure") else None

        if stu.HasExtension(gtfs_realtime_NYCT_pb2.nyct_stop_time_update):
            self.nyct_update = stu.Extensions[gtfs_realtime_NYCT_pb2.nyct_stop_time_update]
            self.actual_track = self.nyct_update.actual_track

# PLACEHOLDER
class NYCTVehicle:
    def __init__(self, vehicle):
        # TODO
        pass
    
class NYCTStaticData:
    def __init__(self):
        self._load_trips()
        self._load_stop_names()
        self._load_route_colors()
        self._load_route_details()

    def _load_trips(self, filepath="data/nyct/trips.txt"):
        if not os.path.exists(filepath):
            logging.info("Failed to find trips.txt for NYCT")
            return
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                TRIPS[row['trip_id'].strip()] = row['trip_headsign'].strip()
        logging.info("Trips loaded for NYCT: %d", len(TRIPS))

    def _load_stop_names(self, filepath="data/nyct/stops.txt"):
        if not os.path.exists(filepath):
            logging.info("Failed to find stops.txt for NYCT")
            return
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                STOP_NAMES[row["stop_id"].strip()] = row["stop_name"].strip()

            logging.info("Station names loaded for NYCT: %d", len(STOP_NAMES))

    def _load_route_colors(self, filepath="data/nyct/routes.txt"):
        if not os.path.exists(filepath):
            logging.info("Failed to find routes.txt for NYCT")
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
    
    def _load_route_details(self, filepath="data/nyct/routes.txt"):
        if not os.path.exists(filepath):
            logging.info("Failed to find routes.txt for NYCT")
            return
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                route_id = row["route_id"].strip()
                ROUTE_DETAILS[route_id] = {
                    "short_name": row["route_short_name"].strip(),
                    "long_name": row["route_long_name"].strip(),
                    "desc": row["route_desc"].strip()
                }
        logging.info("Route details loaded for NYCT: %d", len(ROUTE_DETAILS))
    
    def get_headsign(self, trip_id):
        return TRIPS.get(trip_id, trip_id)

    
    def get_colors(self, route_id):
        return ROUTE_COLORS.get(route_id, {"color": "#FFFFFF", "text_color": "#000000"})
    
    def get_route_details(self, route_id):
        return ROUTE_DETAILS.get(route_id, {"short_name": route_id, "long_name": "", "desc": ""})
