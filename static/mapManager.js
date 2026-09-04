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
            this.map.on('zoomend', () => this.updateMovingTrains());
        } catch (e) {
            console.warn('Leaflet init failed', e);
        }
    }

    updateMapMarkers(trains, stopsMap, trackedTripId = null) {
        if (!this.map || !this.trainLayer || !Array.isArray(trains)) return;
        this.trackedTripId = trackedTripId ? String(trackedTripId) : null;
        this.visibleTrains = {};
        trains.forEach((train, index) => {
            const currentId = this.resolveStopId(stopsMap, String(train.current_stop || '').trim());
            const currentInfo = this.getStopInfo(stopsMap, currentId);
            if (!currentInfo) return;

            const stationId = this.getStationId(stopsMap, currentId, currentInfo);
            const stationInfo = this.getStopInfo(stopsMap, stationId) || currentInfo;
            const lat = parseFloat(stationInfo.lat);
            const lon = parseFloat(stationInfo.lon);
            if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

            const tripId = train.trip_id !== undefined && train.trip_id !== null
                ? String(train.trip_id)
                : `${stationId}-${index}`;
            const nextId = this.resolveStopId(stopsMap, String(train.next_stop || '').trim());
            const nextInfo = this.getStopInfo(stopsMap, nextId);
            this.visibleTrains[tripId] = Object.assign({}, train, {
                stationId,
                currLat: lat,
                currLon: lon,
                nextStopName: train.next_stop_name || (nextInfo && nextInfo.name) || nextId
            });
        });
        this.updateMovingTrains();
    }

    getStopInfo(stopsMap, stopId) {
        if (!stopId) return null;
        return stopsMap[stopId] || null;
    }

    resolveStopId(stopsMap, stopId) {
        if (!stopId) return '';
        return stopsMap[stopId] ? stopId : stopId.slice(0, -1);
    }

    getStationId(stopsMap, stopId, stopInfo) {
        if (String(stopInfo.location_type || '') === '1') return stopId;
        const parentId = String(stopInfo.parent_station || '').trim();
        if (parentId && this.getStopInfo(stopsMap, parentId)) return parentId;
        return stopId;
    }

    createTrainIcon(routeShort, color, textColor, arrowClass, arrow, isTracked) {
        const html = `<div class="map-marker${isTracked ? ' tracked-marker' : ''}"><div class="map-circle" style="background:${color};color:${textColor}">${escHtml(routeShort)}</div><div class="map-arrow ${arrowClass}">${arrow}</div></div>`;
        return L.divIcon({ className: 'stationary-train-icon', html: html, iconSize: [24, 24], iconAnchor: [12, 12] });
    }

    updateMovingTrains() {
        Object.keys(this.movingMarkers).forEach(tripId => {
            if (!this.visibleTrains[tripId]) {
                this.movingLayer.removeLayer(this.movingMarkers[tripId]);
                delete this.movingMarkers[tripId];
            }
        });

        const trainsByStation = {};
        Object.keys(this.visibleTrains).forEach(tripId => {
            const info = this.visibleTrains[tripId];
            if (!trainsByStation[info.stationId]) trainsByStation[info.stationId] = [];
            trainsByStation[info.stationId].push(tripId);
        });

        Object.keys(trainsByStation).forEach(stationId => {
            const tripIds = trainsByStation[stationId];
            const columns = Math.ceil(Math.sqrt(tripIds.length));
            const rows = Math.ceil(tripIds.length / columns);
            const spacing = 30;
            const stationPoint = this.map.latLngToLayerPoint([
                this.visibleTrains[tripIds[0]].currLat,
                this.visibleTrains[tripIds[0]].currLon
            ]);
            tripIds.forEach((tripId, index) => {
                const info = this.visibleTrains[tripId];
                const row = Math.floor(index / columns);
                const column = index % columns;
                const offset = L.point(
                    (column - (columns - 1) / 2) * spacing,
                    (row - (rows - 1) / 2) * spacing
                );
                const position = this.map.layerPointToLatLng(stationPoint.add(offset));
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
                const tooltipText = `Next station: ${escHtml(info.nextStopName || 'Unknown')}`;

                if (!marker) {
                    const icon = this.createTrainIcon(routeShort, color, textColor, arrowClass, arrow, isTracked);
                    marker = L.marker(position, { icon: icon }).addTo(this.movingLayer);
                    marker._tracked = isTracked;
                    marker.on('click', () => {
                        if (window.onTrackTrain) window.onTrackTrain(tripId);
                    });
                    marker.bindTooltip(tooltipText, { permanent: false, direction: 'top' });
                    this.movingMarkers[tripId] = marker;
                } else {
                    if (marker._tracked !== isTracked) {
                        marker.setIcon(this.createTrainIcon(routeShort, color, textColor, arrowClass, arrow, isTracked));
                        marker._tracked = isTracked;
                    }
                    marker.setLatLng(position);
                    if (marker._tooltipText !== tooltipText) {
                        marker.unbindTooltip();
                        marker.bindTooltip(tooltipText, { permanent: false, direction: 'top' });
                    }
                }
                marker._tooltipText = tooltipText;
            });
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
