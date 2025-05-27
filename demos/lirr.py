import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from lirr_refs import LIRRFeed, fmt_time, load_stop_names, get_station_name

LIRR_FEED_URL = " https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/lirr%2Fgtfs-lirr"

def fetch_lirr_feed():
    response = requests.get(LIRR_FEED_URL)
    response.raise_for_status()
    return response.content

if __name__ == "__main__":
    stop_names = load_stop_names()
    feed_bytes = fetch_lirr_feed()
    feed = LIRRFeed(feed_bytes)
    print("Upcoming LIRR trains:")
    for trip in feed.trips[:5]:  # Show only first 5 trips for brevity
        print(f"Trip ID: {trip.id}")
        for stu in trip.stop_time_updates[:2]:  # Show only first 2 stops
            print(
                f"  Next stop: {get_station_name(stu.stop_id, stop_names)} "
                f"Arr: {fmt_time(stu.arrival_time)} Dep: {fmt_time(stu.departure_time)} "
                f"Track: {stu.track} Status: {stu.train_status}"
            )