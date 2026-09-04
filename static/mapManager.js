import { escHtml, normalizeColor, getContrastColor } from './utils.js';

const GRID_CELL_SIZE = 52;
const GRID_GAP = 0;
const GRID_PADDING = 2;

export class MapManager {
    constructor() {
        this.map = null;
        this.trainLayer = null;
        this.movingLayer = null;
        this.stationLayer = null;
        this.movingMarkers = {}; // trip_id - marker
        this.stationMarkers = {}; // station_id - condensed marker
        this.stationGridBackgrounds = {}; // station_id - expanded grid background
        this.expandedStations = new Set();
        this.visibleTrains = {}; // trip_id - train info with coords
        this._interval = null;
    }

    initMap() {
        try {
            this.map = L.map('map', { preferCanvas: true, zoomAnimation: false }).setView([40.7128, -74.0060], 11);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '© OpenStreetMap contributors'
            }).addTo(this.map);
            this.trainLayer = L.layerGroup().addTo(this.map);
            this.movingLayer = L.layerGroup().addTo(this.map);
            this.stationLayer = L.layerGroup().addTo(this.map);
            this.map.on('zoomend', () => this.updateMovingTrains());
            this.map.on('click', () => {
                if (this.expandedStations.size === 0) return;
                this.expandedStations.clear();
                this.updateMovingTrains();
            });
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

    createTrainIcon(routeShort, color, textColor, directionClass, isTracked) {
        const html = `<div class="map-marker${isTracked ? ' tracked-marker' : ''}"><div class="map-circle ${directionClass}" style="background:${color};color:${textColor}">${escHtml(routeShort)}</div></div>`;
        return L.divIcon({ className: 'stationary-train-icon', html: html, iconSize: [52, 52], iconAnchor: [26, 26] });
    }

    createStationClusterIcon(tripIds) {
        const cards = tripIds.slice(0, 4).map((tripId, index) => {
            const info = this.visibleTrains[tripId];
            const color = normalizeColor(info.route_color || '#888');
            const textColor = getContrastColor(color);
            const routeShort = info.route_short_name || info.route_id || '';
            return `<span class="cluster-card cluster-card-${index}" style="background:${color};color:${textColor}">${escHtml(routeShort)}</span>`;
        }).join('');
        const count = tripIds.length > 4 ? `<span class="cluster-count">+${tripIds.length - 4}</span>` : '';
        return L.divIcon({
            className: 'station-cluster-icon',
            html: `<div class="station-cluster" aria-label="${tripIds.length} trains at this station">${cards}${count}</div>`,
            iconSize: [52, 52],
            iconAnchor: [26, 26]
        });
    }

    createStationGridBackgroundIcon(columns, rows) {
        const width = columns * GRID_CELL_SIZE + (columns - 1) * GRID_GAP + GRID_PADDING * 2;
        const height = rows * GRID_CELL_SIZE + (rows - 1) * GRID_GAP + GRID_PADDING * 2;
        return L.divIcon({
            className: 'station-grid-background-icon',
            html: '<div class="station-grid-background"></div>',
            iconSize: [width, height],
            iconAnchor: [width / 2, height / 2]
        });
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
            const stationId = this.visibleTrains[tripId].stationId;
            if (!trainsByStation[stationId]) trainsByStation[stationId] = [];
            trainsByStation[stationId].push(tripId);
        });

        Object.keys(this.stationMarkers).forEach(stationId => {
            if (!trainsByStation[stationId] || this.expandedStations.has(stationId)) {
                this.movingLayer.removeLayer(this.stationMarkers[stationId]);
                delete this.stationMarkers[stationId];
            }
        });
        Object.keys(this.stationGridBackgrounds).forEach(stationId => {
            if (!trainsByStation[stationId] || !this.expandedStations.has(stationId)) {
                this.movingLayer.removeLayer(this.stationGridBackgrounds[stationId]);
                delete this.stationGridBackgrounds[stationId];
            }
        });

        Object.keys(trainsByStation).forEach(stationId => {
            const tripIds = trainsByStation[stationId];
            const firstInfo = this.visibleTrains[tripIds[0]];
            const stationPosition = [firstInfo.currLat, firstInfo.currLon];

            if (!this.expandedStations.has(stationId)) {
                Object.keys(this.movingMarkers).forEach(tripId => {
                    if (this.visibleTrains[tripId] && this.visibleTrains[tripId].stationId === stationId) {
                        this.movingLayer.removeLayer(this.movingMarkers[tripId]);
                        delete this.movingMarkers[tripId];
                    }
                });
                if (!this.stationMarkers[stationId]) {
                    const cluster = L.marker(stationPosition, {
                        icon: this.createStationClusterIcon(tripIds),
                        bubblingMouseEvents: false,
                        zoomAnimation: false
                    }).addTo(this.movingLayer);
                    cluster.on('click', (event) => {
                        if (event.originalEvent) L.DomEvent.stopPropagation(event.originalEvent);
                        this.expandedStations.add(stationId);
                        this.updateMovingTrains();
                    });
                    this.stationMarkers[stationId] = cluster;
                } else {
                    this.stationMarkers[stationId].setLatLng(stationPosition);
                    this.stationMarkers[stationId].setIcon(this.createStationClusterIcon(tripIds));
                }
                return;
            }

            const columns = Math.ceil(Math.sqrt(tripIds.length));
            const rows = Math.ceil(tripIds.length / columns);
            if (!this.stationGridBackgrounds[stationId]) {
                this.stationGridBackgrounds[stationId] = L.marker(stationPosition, {
                    icon: this.createStationGridBackgroundIcon(columns, rows),
                    interactive: false,
                    keyboard: false,
                    zIndexOffset: -1000,
                    zoomAnimation: false
                }).addTo(this.movingLayer);
            } else {
                this.stationGridBackgrounds[stationId].setLatLng(stationPosition);
                this.stationGridBackgrounds[stationId].setIcon(this.createStationGridBackgroundIcon(columns, rows));
            }
            tripIds.forEach((tripId, index) => {
            const info = this.visibleTrains[tripId];
            const row = Math.floor(index / columns);
            const column = index % columns;
            const position = this.map.layerPointToLatLng(
                this.map.latLngToLayerPoint(stationPosition).add(L.point(
                    (column - (columns - 1) / 2) * (GRID_CELL_SIZE + GRID_GAP),
                    (row - (rows - 1) / 2) * (GRID_CELL_SIZE + GRID_GAP)
                ))
            );
            let marker = this.movingMarkers[tripId];

            const color = normalizeColor(info.route_color || '#888');
            const routeShort = info.route_short_name || info.route_id || '';
            const dirRaw = (info.direction || '').toString().toLowerCase();

            let directionClass = 'direction-unknown';

            if (
                dirRaw.includes('north') || dirRaw === 'n' || dirRaw.includes('uptown') || dirRaw.includes('up')) {
                directionClass = 'direction-north';
            } else if (
                dirRaw.includes('south') || dirRaw === 's' || dirRaw.includes('downtown') || dirRaw.includes('down')) {
                directionClass = 'direction-south';
            }

            const textColor = getContrastColor(color);
            const isTracked = this.trackedTripId && tripId === this.trackedTripId;
            const tooltipText = `Next station: ${escHtml(info.nextStopName || 'Unknown')}`;

            if (!marker) {
                const icon = this.createTrainIcon(routeShort, color, textColor, directionClass, isTracked);
                marker = L.marker(position, {
                    icon: icon,
                    zIndexOffset: index,
                    bubblingMouseEvents: false,
                    zoomAnimation: false
                }).addTo(this.movingLayer);
                marker._tracked = isTracked;
                marker.on('click', (event) => {
                    if (event.originalEvent) L.DomEvent.stopPropagation(event.originalEvent);
                    marker.setZIndexOffset(10000);
                    marker.bringToFront();
                    if (window.onTrackTrain) window.onTrackTrain(tripId);
                });
                marker.bindTooltip(tooltipText, { permanent: false, direction: 'top' });
                this.movingMarkers[tripId] = marker;
            } else {
                if (marker._tracked !== isTracked) {
                    marker.setIcon(this.createTrainIcon(routeShort, color, textColor, directionClass, isTracked));
                    marker._tracked = isTracked;
                }
                marker.setLatLng(position);
                if (marker._tooltipText !== tooltipText) {
                    marker.unbindTooltip();
                    marker.bindTooltip(tooltipText, { permanent: false, direction: 'top' });
                }
            }
            marker.setZIndexOffset(index);
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
