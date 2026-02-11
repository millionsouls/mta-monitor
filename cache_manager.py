import threading
import time
import requests
import os
import logging
from collections import deque
from updater import run_updates

# feed URLs
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

_nyct_feed_urls = [
    (['1','2','3','4','5','6','7','S'], 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs'),
    (['A','C','E','SR'], 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace'),
    (['B','D','F','M','SF'], 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm'),
    (['G'], 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g'),
    (['J','Z'], 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz'),
    (['L'], 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l'),
    (['N','Q','R','W'], 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw'),
    (['SIR'], 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-sir'),
]

_lirr_feed_url = 'https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/lirr%2Fgtfs-lirr'

# in-memory caches
_nyct_bytes = [None] * len(_nyct_feed_urls)
_lirr_bytes = None

# Build route -> index lookup once
_ROUTE_TO_INDEX = {}
for idx, (routes, _) in enumerate(_nyct_feed_urls):
    for r in routes:
        _ROUTE_TO_INDEX[r] = idx

# state for debugging/visualizer
_state = {
    'nyct': [{'last_fetch': None, 'size': 0, 'url': url} for (_, url) in _nyct_feed_urls],
    'lirr': {'last_fetch': None, 'size': 0, 'url': _lirr_feed_url},
    'version': 0,
}

# small in-memory log (most recent messages first)
_log = deque(maxlen=200)

_lock = threading.RLock()
_cond = threading.Condition(_lock)
_running = False
_client_count = 0
_notify_callback = None  # callback(payload) called when data updated

def _push_log(msg):
    ts = time.time()
    entry = {'ts': ts, 'msg': msg}
    with _lock:
        _log.appendleft(entry)
    logging.debug(msg)  # use debug to avoid log spam

def _fetch_nyct_once():
    # Fetch all NYCT sub-feeds; do NOT notify here
    for i, (_, url) in enumerate(_nyct_feed_urls):
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            content = resp.content
            with _lock:
                _nyct_bytes[i] = content
                _state['nyct'][i]['last_fetch'] = time.time()
                _state['nyct'][i]['size'] = len(content) if content is not None else 0
            size = _state['nyct'][i]['size']
            logging.debug(f"[BACKEND] NYCT feed fetched: {size} bytes")
        except Exception as e:
            logging.warning(f"[BACKEND] Failed to fetch NYCT feed {url}: {e}")

def _fetch_lirr_once():
    # Fetch LIRR; do NOT notify here
    global _lirr_bytes
    try:
        resp = requests.get(_lirr_feed_url, timeout=20)
        resp.raise_for_status()
        content = resp.content
        with _lock:
            _lirr_bytes = content
            _state['lirr']['last_fetch'] = time.time()
            _state['lirr']['size'] = len(content) if content is not None else 0
        size = _state['lirr']['size']
        logging.debug(f"[BACKEND] LIRR feed fetched: {size} bytes")
    except Exception as e:
        logging.warning(f"[BACKEND] Failed to fetch LIRR feed: {e}")

def get_nyct_feed(line):
    line = (line or '').upper()
    with _lock:
        if line == 'ALL':
            return [b for b in _nyct_bytes if b is not None]

        idx = _ROUTE_TO_INDEX.get(line)
        if idx is not None:
            return _nyct_bytes[idx]
    return None

def get_lirr_feed():
    with _lock:
        return _lirr_bytes

def get_state():
    with _lock:
        return {
            'nyct': list(_state['nyct']),
            'lirr': dict(_state['lirr']),
            'version': _state['version'],
            'logs': list(_log),
        }

def wait_for_version(last_version, timeout=None):
    # Block until _state['version'] > last_version or timeout. Returns new version
    with _cond:
        if _state['version'] > last_version:
            return _state['version']
        notified = _cond.wait(timeout=timeout)
        return _state['version']

def _realtime_loop(interval=60):
    # Run only when there are active clients. When no clients are connected,
    # wait on the condition to be notified by client_connected().
    while _running:
        # wait until a client connects or _running changes
        with _cond:
            while _client_count == 0 and _running:
                _cond.wait()
            if not _running:
                break
        # At least one client is present — perform fetch and notify once
        _fetch_nyct_once()
        _fetch_lirr_once()
        # After fetch, increment version once and notify SSE clients
        with _cond:
            _state['version'] += 1
            _cond.notify_all()
            if _notify_callback:
                try:
                    _notify_callback({'type': 'update', 'timestamp': time.time()})
                except Exception as e:
                    logging.debug(f"[BACKEND] Notify callback error: {e}")
        logging.info(f"[BACKEND] Fetch cycle complete (v{_state['version']}, {_client_count} clients)")
        next_time = time.time() + interval
        # Continue fetching at `interval` while there are clients connected
        while _running:
            with _cond:
                if _client_count == 0:
                    # stop periodic fetches and go back to waiting for clients
                    break
                remaining = next_time - time.time()
                if remaining > 0:
                    _cond.wait(timeout=remaining)
                    # re-evaluate loop conditions
                    continue
            # time elapsed, do next fetch
            if not _running:
                break
            _fetch_nyct_once()
            _fetch_lirr_once()
            # After fetch, increment version once and notify
            with _cond:
                _state['version'] += 1
                _cond.notify_all()
                if _notify_callback:
                    try:
                        _notify_callback({'type': 'update', 'timestamp': time.time()})
                    except Exception as e:
                        logging.debug(f"[BACKEND] Notify callback error: {e}")
                logging.info(f"[BACKEND] Fetch cycle complete (v{_state['version']}, {_client_count} clients)")
            next_time = time.time() + interval

def _static_loop(interval_hours=24):
    # Run once immediately to ensure data present
    try:
        _push_log("Starting static update (initial)")
        run_updates()
        _push_log("Static update complete (initial)")
        # notify watchers that static data changed
        with _cond:
            _state['version'] += 1
            _cond.notify_all()
    except Exception as e:
        _push_log(f"Static update failed: {e}")
    while _running:
        time.sleep(interval_hours * 3600)
        try:
            _push_log("Starting static update (scheduled)")
            run_updates()
            _push_log("Static update complete (scheduled)")
            # notify watchers that static data changed
            with _cond:
                _state['version'] += 1
                _cond.notify_all()
        except Exception as e:
            _push_log(f"Static update failed: {e}")

def start(realtime_interval=60, static_interval_hours=24):
    # Start background fetchers
    global _running
    if _running:
        return
    _running = True
    t1 = threading.Thread(target=_realtime_loop, args=(realtime_interval,), daemon=True)
    t2 = threading.Thread(target=_static_loop, args=(static_interval_hours,), daemon=True)
    t1.start()
    t2.start()

def client_connected():
    global _client_count
    with _cond:
        _client_count += 1
        _push_log(f"Client connected (count={_client_count})")
        _cond.notify_all()

def client_disconnected():
    global _client_count
    with _cond:
        try:
            _client_count = max(0, _client_count - 1)
        except Exception:
            _client_count = 0
        _push_log(f"Client disconnected (count={_client_count})")
        _cond.notify_all()

def get_client_count():
    with _cond:
        return _client_count

def set_notify_callback(callback):
    global _notify_callback
    with _lock:
        _notify_callback = callback

def ensure_static_present():
    # Ensure `data` directory contains expected feeds; run updater if missing.
    # quick check for data/nyct and data/lirr
    if not os.path.exists('data/nyct') or not os.path.exists('data/lirr'):
        try:
            _push_log("Static data missing; running updater")
            run_updates()
            _push_log("Static updater finished (ensure_static_present)")
        except Exception as e:
            _push_log(f"ensure_static_present failed: {e}")
            logging.warning(f"ensure_static_present failed: {e}")

