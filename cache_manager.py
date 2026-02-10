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

def _push_log(msg):
    ts = time.time()
    entry = {'ts': ts, 'msg': msg}
    with _lock:
        _log.appendleft(entry)
    logging.info(msg)

def _fetch_nyct_once():
    for i, (_, url) in enumerate(_nyct_feed_urls):
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            content = resp.content
            # Acquire the Condition before notifying to ensure waiters are awakened
            with _cond:
                _nyct_bytes[i] = content
                _state['nyct'][i]['last_fetch'] = time.time()
                _state['nyct'][i]['size'] = len(content) if content is not None else 0
                _state['version'] += 1
                _push_log(f"NYCT fetched {url} ({_state['nyct'][i]['size']} bytes)")
                _cond.notify_all()
            # Also print concise console debug
            print(f"[cache_manager] NYCT fetched {url} size={_state['nyct'][i]['size']}")
            try:
                downloaded = len(content) if content is not None else 0
            except Exception:
                downloaded = 0
            logging.debug(f"NYCT feed fetched from {url}: {downloaded} bytes")
        except Exception as e:
            _push_log(f"Failed to fetch NYCT feed {url}: {e}")
            logging.warning(f"Failed to fetch NYCT feed {url}: {e}")
            print(f"[cache_manager] Failed to fetch NYCT {url}: {e}")

def _fetch_lirr_once():
    global _lirr_bytes
    try:
        resp = requests.get(_lirr_feed_url, timeout=20)
        resp.raise_for_status()
        content = resp.content
        # Acquire the Condition before notifying to ensure waiters are awakened
        with _cond:
            _lirr_bytes = content
            _state['lirr']['last_fetch'] = time.time()
            _state['lirr']['size'] = len(content) if content is not None else 0
            _state['version'] += 1
            _push_log(f"LIRR fetched ({_state['lirr']['size']} bytes)")
            _cond.notify_all()
        try:
            downloaded = len(content) if content is not None else 0
        except Exception:
            downloaded = 0
        logging.debug(f"LIRR feed fetched: {downloaded} bytes")
        print(f"[cache_manager] LIRR fetched size={_state['lirr']['size']}")
    except Exception as e:
        _push_log(f"Failed to fetch LIRR feed: {e}")
        logging.warning(f"Failed to fetch LIRR feed: {e}")
        print(f"[cache_manager] Failed to fetch LIRR: {e}")

def get_nyct_feed(line):
    # Return feed bytes for line or list of bytes for 'ALL'
    line = (line or '').upper()
    with _lock:
        if line == 'ALL':
            return [b for b in _nyct_bytes if b is not None]
        for routes, url in _nyct_feed_urls:
            if line in routes:
                idx = _nyct_feed_urls.index((routes, url))
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
    # initial fetch
    _fetch_nyct_once()
    _fetch_lirr_once()
    while _running:
        time.sleep(interval)
        _fetch_nyct_once()
        _fetch_lirr_once()

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

