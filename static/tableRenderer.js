// HTML nightmare

import { escHtml, normalizeColor, getContrastColor, fuzzyMatch } from './utils.js';

export class TableRenderer {
    constructor() {
        this.lastData = [];
        this.lastLirrData = [];
    }

    diffData(newData, oldData) {
        const oldById = new Map();
        (oldData || []).forEach(o => { if (o && o.trip_id !== undefined) oldById.set(String(o.trip_id), o); });
        const changed = [];
        (newData || []).forEach((row, i) => {
            const id = row && row.trip_id !== undefined ? String(row.trip_id) : null;
            const o = id ? oldById.get(id) : null;
            if (!o) { changed.push(i); return; }
            if (row.current_stop !== o.current_stop || row.next_stop !== o.next_stop || row.arrival !== o.arrival) changed.push(i);
        });
        return changed;
    }

    renderTable(mode, trains, options = {}) {
        const { searchQuery = '', sortByArrival = true, sortAsc = true, onShowSchedule = null, onTrackTrain = null, trackedTripId = null, mapManager = null } = options;
        const thead = document.getElementById('table-head');
        const tbody = document.getElementById('table-body');
        tbody.innerHTML = '';
        if (!Array.isArray(trains)) trains = [];
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
                <th>Delay</th>
                <th>Schedule</th>
            </tr>`;
            if (Array.isArray(trains)) {
                trains.sort((a, b) => (a.route_name || '').localeCompare(b.route_name || ''));
            }
        }
        let filtered = trains.filter(t => {
            if (!searchQuery) return true;
            const hay = [t.trip_name, t.trip_id, t.current_stop_name, t.next_stop_name, t.route_name, t.route_id].join(' ');
            return fuzzyMatch(searchQuery, hay);
        });
        if (sortByArrival) {
            filtered.sort((a,b)=>{
                const ta = (a.arrival && a.arrival.length>0) ? a.arrival : '99:99:99';
                const tb = (b.arrival && b.arrival.length>0) ? b.arrival : '99:99:99';
                if (ta === tb) return 0;
                if (sortAsc) return ta < tb ? -1 : 1;
                return ta < tb ? 1 : -1;
            });
        }
        if (trackedTripId) {
            filtered.sort((a,b) => {
                const aId = a && a.trip_id !== undefined ? String(a.trip_id) : null;
                const bId = b && b.trip_id !== undefined ? String(b.trip_id) : null;
                if (aId === trackedTripId) return -1;
                if (bId === trackedTripId) return 1;
                return 0;
            });
        }
        const changedRows = this.diffData(filtered, this.lastData);
        filtered.forEach((train, i) => {
            const row = document.createElement('tr');
            const tripId = train && train.trip_id !== undefined ? String(train.trip_id) : null;
            row.dataset.tripid = tripId || '';
            if (changedRows.includes(i)) row.classList.add('updated');
            if (trackedTripId && tripId === String(trackedTripId)) {
                row.classList.add('selected-row');
            }
            if (mode === 'subway') {
                const routeShortName = train.route_short_name || train.route_id || '';
                const routeDesc = train.route_desc || '';
                const pillColor = normalizeColor(train.route_color || '#888');
                const pillTextColor = getContrastColor(pillColor);
                let trainIdCell = '';
                if (train.train_id) {
                    const decodedTrainId = (window.decodeNYCTTrainId ? window.decodeNYCTTrainId(train.train_id) : train.train_id);
                    trainIdCell = `<span class="train-id-tooltip" title="${escHtml(train.train_id)}\n${escHtml(decodedTrainId)}">${escHtml(train.train_id)}</span>`;
                }
                const routeCell = `<span class="route-pill" style="background:${pillColor};color:${pillTextColor}" title="${escHtml(routeDesc)}">${escHtml(routeShortName)}</span>`;
                const trackedLabel = (trackedTripId && tripId === String(trackedTripId)) ? '<span class="tracked-label">TRACKED</span>' : '';
                const routeLongName = train.route_long_name || '';
                row.innerHTML = `
                    <td>
                        ${routeCell}
                        ${trainIdCell ? `<span style="margin-left:8px">${trainIdCell}</span>` : ''}
                        ${trackedLabel}
                    </td>
                    <td class="col-long-name">${escHtml(routeLongName)}</td>
                    <td class="col-direction">${escHtml(train.direction || '')}</td>
                    <td>${escHtml(train.current_stop_name || '')}</td>
                    <td>${escHtml(train.next_stop_name || '')}</td>
                    <td class="col-departure">${escHtml(train.departure || '')}</td>
                    <td>${escHtml(train.arrival || '')}</td>
                    <td class="col-actual-track">${escHtml(train.actual_track || '')}</td>
                    <td class="col-assigned">
                        <input type="checkbox" disabled ${train.is_assigned ? 'checked' : ''}>
                    </td>
                `;
            } else {
                const pillColor = normalizeColor(train.route_color || '#888');
                const pillTextColor = getContrastColor(pillColor);
                let delayStr = '0';
                if (train.stu && Array.isArray(train.stu) && train.stu.length > 0) {
                    const firstStop = train.stu[0];
                    const delay = firstStop.ddelay || 0;
                    delayStr = delay > 0 ? `+${delay}s` : (delay === 0 ? '0s' : `${delay}s`);
                }
                let color = parseInt(delayStr, 10) > 0 ? "rgb(255,0,0)" : "rgb(0,128,0)";
                row.innerHTML = `<td><span class="route-pill" style="background:${pillColor};color:${pillTextColor}">${escHtml(train.route_name||'')}</span></td>
                    <td>${escHtml(train.headsign||'')}</td>
                    <td>${escHtml(train.service_id||'')}</td>
                    <td class="col-trainid">${escHtml(train.trip_id||'')}</td>
                    <td class="col-delay" style="color: ${color}">${escHtml(delayStr)}</td>
                    <td>
                        <button data-index="${i}" class="view-schedule-btn">View Schedule</button>
                    </td>`;
            }
            if (onTrackTrain && tripId) {
                row.addEventListener('click', (event) => {
                    if (event.target.closest('button')) return;
                    onTrackTrain(tripId);
                });
            }
            tbody.appendChild(row);
        });
        if (changedRows.length > 0 && this.lastData.length > 0) {
            if (window.showAlert) window.showAlert('Train data updated!');
        }
        this.lastData = filtered;
        if (mode === 'subway' && mapManager) mapManager.updateMapMarkers(filtered, window.stopsMap || {}, trackedTripId);
        if (mode !== 'subway') this.lastLirrData = trains;
        // attach schedule click handlers
        if (onShowSchedule) {
            document.querySelectorAll('.view-schedule-btn').forEach(btn => {
                btn.addEventListener('click', (e) => onShowSchedule(Number(btn.dataset.index)));
            });
        }
    }
}
