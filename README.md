# Viewing MTA information from subways to LIRR

**MTA Monitor** is a web applications that displays real time train information for New York's MTA system (NYCT, LIRR, MNR). This utilizes the MTA's GTFS-RT feeds and presents the data on a webpage using Flask. 

**MTA ToS for RT Feeds:** https://www.mta.info/developers/terms-and-conditions

## Installation
```
git clone https://github.com/millionsouls/mta-monitor.git
cd mta-monitor
pip install -r requirments.txt
```

Running the app
```
python app.py
```

## Structure
### NYCT (Subway)
#### `FeedMessage`
Contains `header` `entity[]`
| Field | Type | Description |
| --- | --- | --- |
| `header`      | object    | Metadata about the feed                  |
| `entity[]`    | array     | List of trip updates or alerts           |

#### `header` (FeedHeader)
| Field | Type | Description |
| --- | --- | --- |
| `gtfs_realtime_version` | string  | GTFS-Realtime version |
| `incrementality` | enum | Specifies if the feed is a full dataset or a diff |
| `timestamp` | integer   | Time the feed was generated (UNIX time) |

#### `entity[]` (FeedEntity)
Contains `trip_update` `vehicle` `Extension`
| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Unique identifier for this entity |
| `alert` | object | Optional alert message (if present) |
| `trip_update` | object    | Trip information and stop updates         |
| `vehicle`     | object    | *(Not used)*                              |
| `is_deleted`  | boolean   | *(Not used by MTA)*                       |

#### `trip_update` (TripUpdate)
Contains `trip` `stop_time_update[]`

#### `trip` (TripDescriptor)
Contains `nyct_trip_descriptor`
| Field | Type | Description |
| --- | --- | --- |
| `trip_id` | string  | Unique trip identifier |
| `route_id` | string  | Associated subway route (e.g., `A`, `6`)|
| `start_time` string  | UNIX time service begins |
| `start_date` | string  | Service date in `YYYYMMDD` format |
| `schedule_relationship` | enum | Status of the trip |
### NYCT Extension: `nyct_trip_descriptor`
| Field | Type | Description |
| --- | --- | --- |
| `is_assigned` | boolean | Whether the trip is currently assigned to a train |
| `train_id`    | string  | Internal train identifier                         |
| `direction`   | enum    | Direction of travel (`NORTH`, `SOUTH`)           |

### `stop_time_update[]` (StopTimeUpdate)
Each object represents timing info for a stop in the trip.

| Field | Type | Description |
| --- | --- | --- |
| `stop_id`              | string  | GTFS stop identifier                    |
| `arrival`              | object  | Arrival time info (UNIX timestamp)      |
| `departure`            | object  | Departure time info (UNIX timestamp)    |
| `schedule_relationship`| string  | Status (`SCHEDULED`, `SKIPPED`, etc.)   |

### NYCT Extension: `nyct_stop_time_update`
| Field           | Type    | Description                          |
|------------------|---------|--------------------------------------|
| `scheduled_track`| string  | Planned track at the stop           |
| `actual_track`   | string  | Real-time track assignment          |

#### `vehicle` (VehiclePosition)
*This field is not used by MTA NYCT Subway in the feed.*

#### Feed Extension: `nyct_feed_header`
Attached as an extension to the `FeedHeader`.
| Field                    | Type      | Description                            |
|--------------------------|-----------|
| `nyct_subway_version`    | string    | Version of the NYCT feed specification    |
| `trip_replacement_period[]` | array | Specifies replacement periods for routes  |

#### `trip_replacement_period` fields

| Field        | Type    | Description                              |
|--------------|---------|------------------------------------------|
| `route_id`   | string  | Route affected by replacement trips      |
| `replacement_period` | object | Time range during which replacement trips apply |

---

### LIRR
#### Top-Level
| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Unique indentifer for trip |
| `trip_update` | object | Constrains trip and stop_time_update data |

#### trip_update.trip
| Field | Type | Description |
| --- | --- | --- |
| `trip_id` | string | Unique trip identifier |
| `start_date` | string | Service data |
| `schedule_relationship` | string | Status of the trip |
| `route_id` | stirng | Name of the route |
| `direction_id` | int | direction of travel |

### trip_update.stop_time_update[]
Requires protobuf extension. Array, each entry repsents one stop
| Field | Type | Description |
| --- | --- | --- |
| `stop_seuqnece` | int | Order of the stop in ascending order |
| `arrival.time` | int | UNIX time arrived at station; else scheduled time and accounts for delay |
| `arrival.delay` | int | Delay in seconds, negative if ahead of schedule |
| `departure.time` | int | UNIX time departed from station; else scheduled time and accounts for delay. |
| `departure.delay` | int | Delay in seconds, negative if ahead of schedule |
| `stop_id` | string | Station identifier, refer to [stops.txt](static/lirr/stops.txt)
| 'mta_railroad_stop_time_update' | object | Contains track and train status data |

### trip_update.timestemp
| Field | Type | Description |
| --- | --- | --- |
| `timestamp` | int | Update time |