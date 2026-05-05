

let lastData = [];
let lastLirrData = [];
let lastUpdateTs = null; // unix seconds
let searchQuery = '';
let sortByArrival = true; // default on
let sortAsc = true;

// Cache all train data from SSE
let allNyctTrains = [];
let allLirrTrains = [];
let sseConnected = false;  // Track if SSE has connected with data

function showAlert(msg) {
    const alertDiv = document.getElementById('alert');
    alertDiv.textContent = msg;
    alertDiv.style.display = 'block';
    setTimeout(() => { alertDiv.style.display = 'none'; }, 3000);
}

function diffData(newData, oldData) {
    let changed = [];
    newData.forEach((row, i) => {
        if (!oldData[i] ||
            row.trip_id !== oldData[i].trip_id ||
            row.current_stop !== oldData[i].current_stop ||
            row.next_stop !== oldData[i].next_stop ||
            row.arrival !== oldData[i].arrival) {
            changed.push(i);
        }
    });
    return changed;
}

function fuzzyMatch(needle, hay) {
    if (!needle) return true;
    needle = needle.toLowerCase();
    hay = (hay||'').toLowerCase();
    // simple fuzzy
    let i = 0, j = 0;
    while (i < needle.length && j < hay.length) {
        if (needle[i] === hay[j]) i++;
        j++;
    }
    return i === needle.length;
}

function getContrastColor(hex) {
    if (!hex) return '#000';
    if (hex[0] === '#') hex = hex.slice(1);
    if (hex.length === 3) hex = hex.split('').map(c=>c+c).join('');
    const r = parseInt(hex.substr(0,2),16);
    const g = parseInt(hex.substr(2,2),16);
    const b = parseInt(hex.substr(4,2),16);
    // relative luminance
    const yiq = (r*299 + g*587 + b*114) / 1000;
    return yiq >= 128 ? '#000' : '#fff';
}

// Decode NYCT train ID format
// Format: XY ZZZZ+/- ORIGIN|DESTINATION
// X = trip type (0=scheduled, =,/,$ = variations)
// Y = route line number
// ZZZZ+ = origin time (last char can be blank or +)
// ORIGIN|DESTINATION = 3 char codes
function decodeNYCTTrainId(trainId) {
    if (!trainId || trainId.length < 6) return trainId;
    const parts = trainId.split(' ');
    if (parts.length < 2) return trainId;
    
    const typeId = parts[0];
    const timeOriginDest = parts.slice(1).join(' ');
    
    const tripTypeMap = {
        '0': 'Scheduled Trip',
        '=': 'Reroute',
        '/': 'Skip Stop',
        '$': 'Turn Train'
    };
    
    const tripType = tripTypeMap[typeId[0]] || 'Unknown';
    const routeLine = typeId[1] || '?';
    
    return `Route ${routeLine} - ${tripType}`;
}

function renderTable(mode, trains) {
    const thead = document.getElementById('table-head');
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = '';
    
    // ensure trains is an array
    if (!Array.isArray(trains)) {
        console.error('[CLIENT] renderTable received non-array trains:', trains);
        trains = [];
    }
    
    if (mode === 'subway') {
        thead.innerHTML = `<tr>
            <th>Route</th>
            <th>Route Long Name</th>
            <th>Direction</th>
            <th>Current Stop</th>
            <th>Next Stop</th>
            <th>Departure</th>
            <th>Arrival</th>
            <th>Actual Track</th>
            <th>Assigned</th>
        </tr>`;
    } else {
        thead.innerHTML = `<tr>
            <th>Route</th>
            <th>Headsign</th>
            <th>Service ID</th>
            <th>Trip ID</th>
            <th>Delay</th>
            <th>Schedule</th>
        </tr>`;

        // Only sort if trains is actually an array
        if (Array.isArray(trains)) {
            trains.sort((a, b) => a.route_name.localeCompare(b.route_name));
        }
    }

    // apply fuzzy search filter
    if (!Array.isArray(trains)) {
        trains = [];
    }
    let filtered = trains.filter(t => {
        if (!searchQuery) return true;
        const hay = [t.trip_name, t.trip_id, t.current_stop_name, t.next_stop_name, t.route_name, t.route_id].join(' ');
        return fuzzyMatch(searchQuery, hay);
    });

    // apply sort by arrival
    if (sortByArrival) {
        filtered.sort((a,b)=>{
            const ta = (a.arrival && a.arrival.length>0) ? a.arrival : '99:99:99';
            const tb = (b.arrival && b.arrival.length>0) ? b.arrival : '99:99:99';
            if (ta === tb) return 0;
            if (sortAsc) return ta < tb ? -1 : 1;
            return ta < tb ? 1 : -1;
        });
    }

    const changedRows = diffData(filtered, lastData);
    filtered.forEach((train, i) => {
        const row = document.createElement('tr');
        if (changedRows.includes(i)) row.classList.add('updated');
        if (mode === 'subway') {
            const routeShortName = train.route_short_name || train.route_id || '';
            const routeDesc = train.route_desc || '';
            const pillColor = (train.route_color || '#888').replace(/^[^#]/, '#');
            const pillTextColor = getContrastColor(pillColor.replace('#',''));
            
            // Train ID with hover tooltip (if available)
            let trainIdCell = '';
            if (train.train_id) {
                const decodedTrainId = decodeNYCTTrainId(train.train_id);
                trainIdCell = `<span class="train-id-tooltip" title="${train.train_id}\n${decodedTrainId}">${train.train_id}</span>`;
            }
            
            // Route pill with description as title/hover
            const routeCell = `<span class="route-pill" style="background:${pillColor};color:${pillTextColor}" title="${routeDesc}">${routeShortName}</span>`;
            const routeLongName = train.route_long_name || '';
            
            row.innerHTML = `<td>${routeCell}${trainIdCell ? ` <span style="margin-left:8px">${trainIdCell}</span>` : ''}</td>
                <td class="col-long-name">${routeLongName}</td>
                <td class="col-direction">${train.direction||''}</td>
                <td>${train.current_stop_name||''}</td>
                <td>${train.next_stop_name||''}</td>
                <td class="col-departure">${train.departure||''}</td>
                <td>${train.arrival||''}</td>
                <td class="col-actual-track">${train.actual_track || ''}</td>
                <td class="col-assigned"><input type="checkbox" disabled ${train.is_assigned ? 'checked' : ''}></td>`;
        } else {
            const pillColor = (train.route_color || '#888').replace(/^[^#]/, '#');
            const pillTextColor = getContrastColor(pillColor.replace('#',''));
            // Calculate delay from first stop
            let delayStr = '0';
            if (train.stu && Array.isArray(train.stu) && train.stu.length > 0) {
                const firstStop = train.stu[0];
                const delay = firstStop.ddelay || 0;
                delayStr = delay > 0 ? `+${delay}s` : (delay === 0 ? '0s' : `${delay}s`);
            }
            let color = parseInt(delayStr, 10) > 0 ? "rgb(255,0,0)" : "rgb(0,128,0)";
            row.innerHTML = `<td><span class="route-pill" style="background:${pillColor};color:${pillTextColor}">${train.route_name||''}</span></td>
                <td>${train.headsign||''}</td>
                <td>${train.service_id||''}</td>
                <td class="col-trainid">${train.trip_id||''}</td>
                <td class="col-delay" style="color: ${color}">${delayStr}</td>
                <td>
                    <button onclick="showSchedule(${i})">View Schedule</button>
                </td>`;
        }
        tbody.appendChild(row);
    });
    if (changedRows.length > 0 && lastData.length > 0) {
        showAlert('Train data updated!');
    }
    lastData = filtered;
    if (mode !== 'subway') {
        lastLirrData = trains; // Save for popup access
    }
}

function loadTrains() {
    const mode = document.getElementById('mode').value;
    let trains = [];
    
    // Wait for SSE to connect and provide initial data
    if (!sseConnected) {
        console.warn('[CLIENT] No data available yet - waiting for SSE connection');
        // Show empty table with message
        const tbody = document.getElementById('table-body');
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#999;">Waiting for real-time data...</td></tr>';
        return;
    }
    
    if (mode === 'subway') {
        const line = document.getElementById('line').value;
        // Filter NYCT trains from cached data by line
        trains = allNyctTrains.filter(t => {
            if (line === 'ALL') return true;
            return t.route_id === line;
        });
        console.log(`[CLIENT] Subway line="${line}" -> ${trains.length}/${allNyctTrains.length} trains (from cache only)`);
    } else {
        // Use all cached LIRR trains
        trains = allLirrTrains;
        console.log(`[CLIENT] LIRR mode -> ${trains.length}/${allLirrTrains.length} trains (from cache only)`);
    }
    
    if (trains.length === 0 && (allNyctTrains.length > 0 || allLirrTrains.length > 0)) {
        console.warn('[CLIENT] Filter returned 0 results but data is cached');
    }
    
    renderTable(mode, trains);
    // mark last update time as now (client-side)
    if (lastUpdateTs) {
        updateLastUpdatedDisplay();
    }
}

function onSearchInput(){
    const v = document.getElementById('search-input').value || '';
    searchQuery = v.trim();
}

function toggleSort(){
    // toggles between arrival sorting on/off and asc/desc
    if (!sortByArrival) {
        sortByArrival = true; sortAsc = true;
        document.getElementById('sort-arrival').textContent = 'Sort: Arrival ↓';
    } else if (sortByArrival && sortAsc) {
        sortAsc = false; document.getElementById('sort-arrival').textContent = 'Sort: Arrival ↑';
    } else {
        sortByArrival = false; sortAsc = true; document.getElementById('sort-arrival').textContent = 'Sort: Off';
    }
    // re-render current view
    loadTrains();
}

function toggleLineInput() {
    const mode = document.getElementById('mode').value;
    document.getElementById('subway-line-span').style.display = (mode === 'subway') ? 'inline' : 'none';
}

function showSchedule(index) {
    const train = lastLirrData[index];
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
                <td>${stop.stop_sequence}</td>
                <td>${stop.stop_id}</td>
                <td>${stop.stop_name}</td>
                <td>${stop.scheduled}</td>
                <td>${formatTime(stop.arrival)}</td>
                <td>${arrDelay}</td>
                <td>${formatTime(stop.departure)}</td>
                <td>${depDelay}</td>
                <td>${stop.track || ''}</td>
                <td>${stop.train_status || ''}</td>
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

// Helper to format Unix timestamps
function formatTime(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString();
}

// Initialize on page load
toggleLineInput();

// Display last update
function updateLastUpdatedDisplay() {
    const el = document.getElementById('last-updated');
    if (!el) return;
    if (!lastUpdateTs) {
        el.textContent = 'Updated: N/A';
        return;
    }
    const now = Math.floor(Date.now() / 1000);
    const delta = now - lastUpdateTs;
    let text = '';
    if (delta < 60) {
        text = 'Updated: less than a minute ago';
    } else if (delta < 3600) {
        const mins = Math.floor(delta / 60);
        text = `Updated: ${mins} minute${mins===1? '': 's'} ago`;
    } else if (delta < 7200) {
        text = 'Updated: an hour ago';
    } else if (delta < 86400) {
        const hours = Math.floor(delta / 3600);
        text = `Updated: ${hours} hours ago`;
    } else {
        const days = Math.floor(delta / 86400);
        text = `Updated: ${days} day${days===1? '': 's'} ago`;
    }
    el.textContent = text;
}

// refresh displayed relative time every 15 seconds
setInterval(updateLastUpdatedDisplay, 15000);

// SSE listener to auto-refresh when server cache updates
(() => {
    let es;
    const statusEl = document.createElement('div');
    statusEl.id = 'sse-status';
    statusEl.style.cssText = 'position:fixed;right:8px;bottom:8px;padding:6px 10px;background:#222;color:#fff;border-radius:6px;font-size:12px;opacity:0.9';
    statusEl.textContent = 'SSE: connecting...';
    document.body.appendChild(statusEl);

    function connect() {
        try {
            es = new EventSource('/events');
        } catch (err) {
            console.warn('SSE connection error', err);
            statusEl.textContent = 'SSE: error';
            // retry after a delay
            setTimeout(connect, 5000);
            return;
        }

        es.onopen = () => {
            console.log('[SSE] Connection established - waiting for data');
            statusEl.textContent = 'SSE: connected';
        };
        es.onmessage = (e) => {
            try {
                const d = JSON.parse(e.data);
                
                // Cache train data from server
                if (d.trains) {
                    allNyctTrains = Array.isArray(d.trains.nyct) ? d.trains.nyct : [];
                    allLirrTrains = Array.isArray(d.trains.lirr) ? d.trains.lirr : [];
                    sseConnected = true;  // Mark that we've received data
                    console.log(`[SSE] DATA UPDATE v${d.version}: Cached ${allNyctTrains.length} NYCT + ${allLirrTrains.length} LIRR trains`);
                }
                
                // Update timestamp if provided
                if (d.timestamp) {
                    lastUpdateTs = Math.floor(d.timestamp);
                    updateLastUpdatedDisplay();
                }
            } catch (err) {
                // heartbeat or non-json
                console.debug('[SSE] Heartbeat');
            }
            
            // When server notifies refresh visible data from cache
            console.log('[CLIENT] Re-rendering from cache (NO server fetch)');
            loadTrains();
            
            // briefly flash status
            statusEl.textContent = 'SSE: updated';
            setTimeout(()=> statusEl.textContent = 'SSE: connected', 1000);
        };
        es.onerror = (err) => {
            console.warn('[SSE] Error - attempting reconnection', err);
            statusEl.textContent = 'SSE: reconnecting...';
            es.close();
            // exponential backoff with 3-10 second delay
            const delay = Math.min(10000, 3000 + Math.random() * 7000);
            setTimeout(connect, delay);
        };
    }

    // start connection
    connect();
})();