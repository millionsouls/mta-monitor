import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nyct_gtfs import NYCTFeed
from datetime import datetime

# Load the realtime feed for the A train
feed = NYCTFeed("A")

# Get all A trains currently underway
trains = feed.filter_trips(line_id=["A"], underway=True)

for train in trains:
    
    # Get the next stop update (if available)
    if train.stop_time_updates:
        next_stop = train.stop_time_updates[0]
        stop_name = getattr(next_stop, "stop_name", next_stop.stop_id)
        arrival_time = next_stop.arrival

        # Convert arrival_time to readable format if it's a timestamp
        if isinstance(arrival_time, int):
            arrival_time = datetime.fromtimestamp(arrival_time)
        print(f"Trip ID: {train.trip_id} | Next Stop: {stop_name} | Arrival: {arrival_time}")
    else:
        print(f"Trip ID: {train.trip_id} | No upcoming stops listed.")