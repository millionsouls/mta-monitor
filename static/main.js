import { escHtml, parseCSV, formatTime, showAlert } from './utils.js';
import { MapManager } from './mapManager.js';
import { TableRenderer } from './tableRenderer.js';
import { SSEClient } from './SSEClient.js';

// central data
const state = {
    lastData: [],
    lastLirrData: [],
    lastUpdateTs: null,
    searchQuery: '',
    sortByArrival: true,
    sortAsc: true,
    allNyctTrains: [],
    allLirrTrains: [],
    sseConnected: false,
    stopsMap: {},
    currentStationLine: null,
    trackedTripId: null
};

window.stopsMap = state.stopsMap;
window.showAlert = showAlert;

const mapManager = new MapManager();
const tableRenderer = new TableRenderer();
let sseClient = null;

function loadStopsCSV() {
    return fetch('/static/stops.txt')
        .then(function (r) {
            if (!r.ok) {
                throw new Error('stops.txt fetch failed');
            }
            return r.text();
        })
        .then(function (text) {
            const rows = parseCSV(text);
            rows.forEach(function (row) {
                if (!row.stop_id) return;
                state.stopsMap[row.stop_id] = {
                    lat: row.stop_lat,
                    lon: row.stop_lon,
                    name: row.stop_name,
                    location_type: row.location_type,
                    parent_station: row.parent_station
                };
            });
            console.log('[CLIENT] Loaded stops:', Object.keys(state.stopsMap).length);
        })
        .catch(function (err) {
            console.warn('[CLIENT] Failed to load stops.txt', err);
        });
}

function getStationLabelsForLine(line) {
    if (!line || line === 'ALL') return [];
    const seen = new Set();
    const stations = [];
    state.allNyctTrains.forEach(train => {
        if (train.route_id !== line) return;
        [train.current_stop, train.next_stop].forEach(stopIdRaw => {
            if (!stopIdRaw) return;
            const stopId = String(stopIdRaw).trim();
            const stopInfo = state.stopsMap[stopId];
            if (!stopInfo) return;
            let parentId = stopInfo.parent_station;
            if (parentId && state.stopsMap[parentId] && state.stopsMap[parentId].location_type === '1') {
                seen.add(parentId);
            } else if (stopInfo.location_type === '1') {
                seen.add(stopId);
            } else if (parentId && state.stopsMap[parentId]) {
                seen.add(parentId);
            }
        });
    });

    seen.forEach(stopId => {
        const info = state.stopsMap[stopId];
        if (!info || String(info.location_type) !== '1') return;
        const lat = parseFloat(info.lat);
        const lon = parseFloat(info.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
        stations.push({
            stop_id: stopId,
            stop_name: info.name,
            stop_lat: info.lat,
            stop_lon: info.lon,
            location_type: info.location_type,
            parent_station: info.parent_station || ''
        });
    });

    return stations;
}

function loadTrains() {
    const mode = document.getElementById('mode').value;
    let trains = [];
    if (!state.sseConnected) {
        console.warn('[CLIENT] No data available yet - waiting for SSE connection');
        const tbody = document.getElementById('table-body');
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#999;">Waiting for real-time data...</td></tr>';
        return;
    }
    if (mode === 'subway') {
        const line = document.getElementById('line').value;
        trains = state.allNyctTrains.filter(function (t) {
            if (line === 'ALL') return true;
            return t.route_id === line;
        });
    } else {
        trains = state.allLirrTrains;
    }
    tableRenderer.renderTable(mode, trains, {
        searchQuery: state.searchQuery,
        sortByArrival: state.sortByArrival,
        sortAsc: state.sortAsc,
        onShowSchedule: showSchedule,
        onTrackTrain: trackTrain,
        trackedTripId: state.trackedTripId,
        mapManager
    });
    if (mode === 'subway') {
        const line = document.getElementById('line').value;
        if (line === 'ALL') {
            if (state.currentStationLine !== 'ALL') {
                mapManager.clearStationLabels();
                state.currentStationLine = 'ALL';
            }
        } else {
            const stations = getStationLabelsForLine(line);
            mapManager.updateStationLabels(stations);
            state.currentStationLine = line;
        }
    } else {
        if (state.currentStationLine !== null) {
            mapManager.clearStationLabels();
            state.currentStationLine = null;
        }
    }
    updateTrackedButton();
    if (state.lastUpdateTs) updateLastUpdatedDisplay();
}

function onSearchInput() {
    const v = document.getElementById('search-input').value || '';
    state.searchQuery = v.trim();
}

function toggleSort() {
    if (!state.sortByArrival) {
        state.sortByArrival = true;
        state.sortAsc = true;
        document.getElementById('sort-arrival').textContent = 'Sort: Arrival ↓';
    } else if (state.sortByArrival && state.sortAsc) {
        state.sortAsc = false;
        document.getElementById('sort-arrival').textContent = 'Sort: Arrival ↑';
    } else {
        state.sortByArrival = false;
        state.sortAsc = true;
        document.getElementById('sort-arrival').textContent = 'Sort: Off';
    }
    loadTrains();
}

function toggleLineInput() {
    const mode = document.getElementById('mode').value;
    document.getElementById('subway-line-span').style.display = (mode === 'subway') ? 'inline' : 'none';
}

function showSchedule(index) {
    const train = tableRenderer.lastLirrData[index] || null;
    const modal = document.getElementById('schedule-modal');
    const backdrop = document.getElementById('modal-backdrop');
    const tbody = document.getElementById('schedule-table').querySelector('tbody');
    tbody.innerHTML = '';
    if (train && train.stu && Array.isArray(train.stu)) {
        train.stu.forEach(stop => {
            const row = document.createElement('tr');
            const arrDelay = stop.adelay !== undefined && stop.adelay !== null ? stop.adelay : '--';
            const depDelay = stop.ddelay !== undefined && stop.ddelay !== null ? stop.ddelay : '--';
            row.innerHTML = `
                <td>${escHtml(stop.stop_sequence)}</td>
                <td>${escHtml(stop.stop_id)}</td>
                <td>${escHtml(stop.stop_name)}</td>
                <td>${escHtml(stop.scheduled)}</td>
                <td>${escHtml(formatTime(stop.arrival))}</td>
                <td>${escHtml(arrDelay)}</td>
                <td>${escHtml(formatTime(stop.departure))}</td>
                <td>${escHtml(depDelay)}</td>
                <td>${escHtml(stop.track || '')}</td>
                <td>${escHtml(stop.train_status || '')}</td>
            `;
            tbody.appendChild(row);
        });
    }
    modal.style.display = 'block';
    backdrop.style.display = 'block';
}
function closeSchedule() {
    document.getElementById('schedule-modal').style.display = 'none';
    document.getElementById('modal-backdrop').style.display = 'none';
}

function updateTrackedButton() {
    const btn = document.getElementById('clear-tracked');
    if (!btn) return;
    btn.disabled = !state.trackedTripId;
    if (state.trackedTripId) {
        btn.textContent = 'Clear tracked train';
    } else {
        btn.textContent = 'Clear tracked train';
    }
}

function trackTrain(tripId) {
    if (!tripId) return;
    state.trackedTripId = String(tripId);
    loadTrains();
}

function clearTrackedTrain() {
    state.trackedTripId = null;
    loadTrains();
}

function updateLastUpdatedDisplay() {
    const el = document.getElementById('last-updated');
    if (!el) return;
    if (!state.lastUpdateTs) {
        el.textContent = 'Updated: N/A';
        return;
    }
    const now = Math.floor(Date.now() / 1000);
    const delta = now - state.lastUpdateTs;
    let text = '';
    if (delta < 60) {
        text = 'Updated: less than a minute ago';
    } else if (delta < 3600) {
        const mins = Math.floor(delta / 60);
        text = `Updated: ${mins} minute${mins === 1 ? '' : 's'} ago`;
    } else if (delta < 7200) {
        text = 'Updated: an hour ago';
    } else if (delta < 86400) {
        const hours = Math.floor(delta / 3600);
        text = `Updated: ${hours} hours ago`;
    } else {
        const days = Math.floor(delta / 86400);
        text = `Updated: ${days} day${days === 1 ? '' : 's'} ago`;
    }
    el.textContent = text;
}
setInterval(updateLastUpdatedDisplay, 15000);

// attach to window for compatibility where needed
window.decodeNYCTTrainId = function (trainId) {
    if (!trainId || trainId.length < 2) return trainId;
    const parts = String(trainId).split(' ');
    const typeId = parts[0] || '';
    const tripTypeMap = {
        '0': 'Scheduled Trip',
        '=': 'Reroute',
        '/': 'Skip Stop',
        '$': 'Turn Train'
    };
    const tripType = tripTypeMap[typeId[0]] || 'Unknown';
    const routeLine = typeId[1] || '?';
    return `Route ${routeLine} - ${tripType}`;
};

// initialize
toggleLineInput();
mapManager.initMap();
mapManager.startMovingInterval();
loadStopsCSV();

// start SSE
sseClient = new SSEClient((d) => {
    try {
        if (d.trains) {
            state.allNyctTrains = Array.isArray(d.trains.nyct) ? d.trains.nyct : [];
            state.allLirrTrains = Array.isArray(d.trains.lirr) ? d.trains.lirr : [];
            state.sseConnected = true;
        }
        if (d.timestamp) {
            state.lastUpdateTs = Math.floor(d.timestamp);
            updateLastUpdatedDisplay();
        }
    } catch (e) { console.debug('[SSE] malformed data'); }
    loadTrains();
});

// wire DOM controls referenced by HTML
window.loadTrains = loadTrains;
window.onSearchInput = function () {
    onSearchInput();
    loadTrains();
};
window.toggleSort = toggleSort;
window.toggleLineInput = toggleLineInput;
window.showSchedule = showSchedule;
window.closeSchedule = closeSchedule;
window.clearTrackedTrain = clearTrackedTrain;
window.onTrackTrain = function (tripId) {
    trackTrain(tripId);
};

// expose state for debugging
window.__mta_state = state;

export { state, mapManager, tableRenderer };
