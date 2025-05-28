let lastData = [];
let lastLirrData = [];

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
            row.next_stop !== oldData[i].next_stop ||
            row.arrival !== oldData[i].arrival) {
            changed.push(i);
        }
    });
    return changed;
}

function renderTable(mode, trains) {
    const thead = document.getElementById('table-head');
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = '';
    if (mode === 'subway') {
        thead.innerHTML = `<tr>
            <th>Route</th>
            <th>Trip ID</th>
            <th>Train ID</th>
            <th>Direction</th>
            <th>Next Stop</th>
            <th>Departure</th>
            <th>Arrival</th>
            <th>Actual Track</th>
            <th>Assigned</th>
        </tr>`;
    } else {
        thead.innerHTML = `<tr>
            <th>Route</th>
            <th>Trip ID</th>
            <th>Next Stop</th>
            <th>Departure</th>
            <th>Arrival</th>
            <th>Track</th>
            <th>Status</th>
        </tr>`;
        trains.sort((a, b) => a.route_name.localeCompare(b.route_name));
    }
    const changedRows = diffData(trains, lastData);
    trains.forEach((train, i) => {
        const row = document.createElement('tr');
        if (changedRows.includes(i)) row.classList.add('updated');
        if (mode === 'subway') {
            row.innerHTML = `<td>${train.trip_name}</td>
                <td>${train.trip_id}</td>
                <td>${train.train_id}</td>
                <td>${train.direction}</td>
                <td>${train.next_stop_name}</td>
                <td>${train.departure}</td>
                <td>${train.arrival}</td>
                <td>${train.actual_track || ''}</td>
                <td><input type="checkbox" disabled ${train.is_assigned ? 'checked' : ''}></td>`;
        } else {
            row.innerHTML = `<td>${train.route_name}</td>
                <td>${train.trip_id}</td>
                <td>
                    <button onclick="showSchedule(${i})">View Schedule</button>
                </td>`;
        }
        tbody.appendChild(row);
        // Color the row AFTER appending
        if (mode !== 'subway') {
            row.style.setProperty('background-color', train.route_color.startsWith('#') ? train.route_color : ('#' + train.route_color), 'important');
            row.style.setProperty('color', train.route_text_color.startsWith('#') ? train.route_text_color : ('#' + train.route_text_color), 'important');
        } else {
            row.style.setProperty('background-color', train.route_color, 'important');
            row.style.setProperty('color', train.route_text_color, 'important');
        }
    });
    if (changedRows.length > 0 && lastData.length > 0) {
        showAlert('Train data updated!');
    }
    lastData = trains;
    if (mode !== 'subway') {
        lastLirrData = trains; // Save for popup access
    }
}

function loadTrains() {
    const mode = document.getElementById('mode').value;
    let url = '';
    if (mode === 'subway') {
        const line = document.getElementById('line').value;
        url = `/api/nyct/trains?line=${encodeURIComponent(line)}`;
    } else {
        url = `/api/lirr/trains`;
    }
    fetch(url)
        .then(r => r.json())
        .then(data => {
            renderTable(mode, data);
        });
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
            row.innerHTML = `
                <td>${stop.stop_sequence}</td>
                <td>${stop.stop_id}</td>
                <td>${stop.stop_name}</td>
                <td>${formatTime(train.stu.scheduled)}</td>
                <td>${formatTime(stop.arrival)}</td>
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