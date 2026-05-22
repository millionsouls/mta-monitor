import { escHtml, normalizeColor, getContrastColor } from './utils.js';

export class MapManager {
    constructor() {
        this.map = null;
        this.trainLayer = null;
        this.movingLayer = null;
        this.stationLayer = null;
        this.movingMarkers = {}; // trip_id - marker
        this.visibleTrains = {}; // trip_id - train info with coords
        this._interval = null;
    }

    initMap() {
        try {
            this.map = L.map('map', { preferCanvas: true }).setView([40.7128, -74.0060], 11);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '© OpenStreetMap contributors'
            }).addTo(this.map);
            this.trainLayer = L.layerGroup().addTo(this.map);
            this.movingLayer = L.layerGroup().addTo(this.map);
            this.stationLayer = L.layerGroup().addTo(this.map);
        } catch (e) {
            console.warn('Leaflet init failed', e);
        }
    }

    easeInOutQuad(t) {
        return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    }

    updateMapMarkers(trains, stopsMap, trackedTripId = null) {
        if (!this.map || !this.trainLayer || !Array.isArray(trains)) return;
        this.trackedTripId = trackedTripId ? String(trackedTripId) : null;
        try { this.trainLayer.clearLayers(); } catch (e) { }

        this.visibleTrains = {};

        const byStop = {};

        trains.forEach(train => {
            const stopIdRaw = train.current_stop || train.current_stop_name || '';
            let stopId = (stopIdRaw + '').trim();
            if (!stopId) return;
            const key = stopId;
            if (!byStop[key]) byStop[key] = [];
            byStop[key].push(train);
        });

        Object.keys(byStop).forEach(key => {
            const trainsHere = byStop[key];
            trainsHere.forEach(t => {
                const tripId = t.trip_id !== undefined && t.trip_id !== null ? String(t.trip_id) : Math.random().toString(36).slice(2, 8);
                const tryCurr = stopsMap[t.current_stop] || stopsMap[(t.current_stop || '').slice(0, -1)];
                const tryNext = stopsMap[t.next_stop] || stopsMap[(t.next_stop || '').slice(0, -1)];
                if (!tryCurr || !tryNext) {
                    this.visibleTrains[tripId] = Object.assign({}, t, { currLat: tryCurr ? parseFloat(tryCurr.lat) : null, currLon: tryCurr ? parseFloat(tryCurr.lon) : null, nextLat: tryNext ? parseFloat(tryNext.lat) : null, nextLon: tryNext ? parseFloat(tryNext.lon) : null });
                } else {
                    this.visibleTrains[tripId] = Object.assign({}, t, { currLat: parseFloat(tryCurr.lat), currLon: parseFloat(tryCurr.lon), nextLat: parseFloat(tryNext.lat), nextLon: parseFloat(tryNext.lon) });
                }
            });
        });
    }

    createTrainIcon(routeShort, color, textColor, arrowClass, arrow, isTracked) {
        const html = `<div class="map-marker${isTracked ? ' tracked-marker' : ''}"><div class="map-circle" style="background:${color};color:${textColor}">${escHtml(routeShort)}</div><div class="map-arrow ${arrowClass}">${arrow}</div></div>`;
        return L.divIcon({ className: 'moving-train-icon', html: html, iconSize: [24, 24], iconAnchor: [12, 12] });
    }

    updateMovingTrains() {
        const now = Math.floor(Date.now() / 1000);
        Object.keys(this.movingMarkers).forEach(tripId => {
            if (!this.visibleTrains[tripId]) {
                try { document.querySelectorAll(`.map-item[data-tripid="${tripId}"]`).forEach(el => el.style.display = ''); } catch (e) { }
                this.movingLayer.removeLayer(this.movingMarkers[tripId]);
                delete this.movingMarkers[tripId];
            }
        });

        Object.keys(this.visibleTrains).forEach(tripId => {
            const info = this.visibleTrains[tripId];
            const currTs = info.current_departure_ts || info.current_arrival_ts;
            const nextTs = info.next_arrival_ts;
            
            const hasCoords = Number.isFinite(info.currLat) && Number.isFinite(info.currLon) && Number.isFinite(info.nextLat) && Number.isFinite(info.nextLon);
            if (!currTs || !nextTs || !hasCoords) {
                if (this.movingMarkers[tripId]) {
                    this.movingLayer.removeLayer(this.movingMarkers[tripId]);
                    delete this.movingMarkers[tripId];
                }
                return;
            }
            const total = nextTs - currTs;
            if (total <= 0) {
                if (this.movingMarkers[tripId]) { this.movingLayer.removeLayer(this.movingMarkers[tripId]); delete this.movingMarkers[tripId]; }
                return;
            }

            const elapsed = now - currTs;
            const frac = Math.max(0, Math.min(1, elapsed / total));
            const easedFrac = this.easeInOutQuad(frac);
            const lat = info.currLat + (info.nextLat - info.currLat) * easedFrac;
            const lon = info.currLon + (info.nextLon - info.currLon) * easedFrac;

            let marker = this.movingMarkers[tripId];

            const color = normalizeColor(info.route_color || '#888');
            const routeShort = info.route_short_name || info.route_id || '';
            const dirRaw = (info.direction || '').toString().toLowerCase();

            let arrow = '•';
            let arrowClass = 'unknown';

            if (
                dirRaw.includes('north') || dirRaw === 'n' || dirRaw.includes('uptown') || dirRaw.includes('up')) {
                arrow = 'N'; arrowClass = 'uptown';

            } else if (
                dirRaw.includes('south') || dirRaw === 's' || dirRaw.includes('downtown') || dirRaw.includes('down')) {
                arrow = 'S'; arrowClass = 'downtown';
            }

            const textColor = getContrastColor(color);
            const isTracked = this.trackedTripId && tripId === this.trackedTripId;

            if (!marker) {
                const icon = this.createTrainIcon(routeShort, color, textColor, arrowClass, arrow, isTracked);
                marker = L.marker([lat, lon], { icon: icon }).addTo(this.movingLayer);
                marker._tracked = isTracked;
                marker.on('click', () => {
                    if (window.onTrackTrain) window.onTrackTrain(tripId);
                });
                
                try { document.querySelectorAll(`.map-item[data-tripid="${tripId}"]`).forEach(el => el.style.display = 'none'); } catch (e) { }
                let etaDisplay = '';
                
                if (nextTs && currTs) {
                    const etaSec = Math.max(0, Math.floor(nextTs - now));
                    const mins = Math.floor(etaSec / 60); const secs = etaSec % 60;
                    etaDisplay = ` — ETA ${mins}:${secs.toString().padStart(2, '0')}`;
                }

                marker.bindTooltip(`${routeShort} ${tripId}${etaDisplay}`, { permanent: false, direction: 'top' });
                this.movingMarkers[tripId] = marker;
            } else {
                if (marker._tracked !== isTracked) {
                    marker.setIcon(this.createTrainIcon(routeShort, color, textColor, arrowClass, arrow, isTracked));
                    marker._tracked = isTracked;
                }
                marker.setLatLng([lat, lon]);
                try {
                    let etaDisplay = '';
                    if (nextTs && currTs) {
                        const etaSec = Math.max(0, Math.floor(nextTs - now));
                        const mins = Math.floor(etaSec / 60); const secs = etaSec % 60;
                        etaDisplay = ` — ETA ${mins}:${secs.toString().padStart(2, '0')}`;
                    }
                    marker.unbindTooltip();
                    marker.bindTooltip(`${routeShort} ${tripId}${etaDisplay}`, { permanent: false, direction: 'top' });
                } catch (e) { }
            }
            if (frac >= 1) {
                this.movingLayer.removeLayer(marker);
                try { document.querySelectorAll(`.map-item[data-tripid="${tripId}"]`).forEach(el => el.style.display = ''); } catch (e) { }
                delete this.movingMarkers[tripId];
            }
        });
    }

    updateStationLabels(stations) {
        if (!this.map || !this.stationLayer) return;
        try {
            this.stationLayer.clearLayers();
        } catch (e) { }
        if (!Array.isArray(stations)) return;

        stations.forEach(station => {
            if (!station || String(station.location_type || '') !== '1') return;
            const lat = parseFloat(station.stop_lat);
            const lon = parseFloat(station.stop_lon);
            if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

            const icon = L.divIcon({
                className: 'station-label-icon',
                html: `<div class="station-label">${escHtml(station.stop_name)}</div>`,
                iconSize: [120, 24],
                iconAnchor: [60, 24]
            });
            L.marker([lat, lon], { icon: icon, interactive: false, keyboard: false, zoomAnimation: false }).addTo(this.stationLayer);
        });
    }

    clearStationLabels() {
        if (!this.map || !this.stationLayer) return;
        try {
            this.stationLayer.clearLayers();
        } catch (e) { }
    }

    startMovingInterval() {
        if (this._interval) {
            return;
        }
        this._interval = setInterval(() => {
            this.updateMovingTrains();
        }, 1000);
    }

    stopMovingInterval() {
        if (this._interval) {
            clearInterval(this._interval);
        }
        this._interval = null;
    }
}
