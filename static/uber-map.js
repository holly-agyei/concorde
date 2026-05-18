/* Shared Leaflet helpers for rider + driver Uber views. */

const OSRM = 'https://router.project-osrm.org/route/v1/driving';

function divIcon(html, className, size = [32, 32]) {
  return L.divIcon({ html, className, iconSize: size, iconAnchor: [size[0] / 2, size[1] / 2] });
}

const ICONS = {
  car: () => divIcon(
    `<div class="map-pin map-pin--car"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 17h14M6 17l-1-4 2-5h10l2 5-1 4M7 17v2M17 17v2M8 12h8"/></svg></div>`,
    'map-pin-wrap',
  ),
  pickup: () => divIcon(
    `<div class="map-pin map-pin--pickup">PU</div>`,
    'map-pin-wrap',
  ),
  drop: () => divIcon(
    `<div class="map-pin map-pin--drop"><svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M12 2a7 7 0 0 0-7 7c0 5.25 7 13 7 13s7-7.75 7-13a7 7 0 0 0-7-7zm0 9.5a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z"/></svg></div>`,
    'map-pin-wrap',
  ),
};

function initMap(elId, center = [37.7, -122.4], zoom = 11, opts = {}) {
  const map = L.map(elId, {
    zoomControl: false,
    attributionControl: false,
    ...opts,
  }).setView(center, zoom);
  L.tileLayer(
    opts.dark
      ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
      : 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    {
      maxZoom: 19,
      subdomains: opts.dark ? 'abcd' : 'abc',
      attribution: '&copy; OpenStreetMap contributors',
    },
  ).addTo(map);
  setTimeout(() => map.invalidateSize(), 100);
  setTimeout(() => map.invalidateSize(), 600);
  return map;
}

async function fetchRoute(from, to) {
  const url = `${OSRM}/${from.lng},${from.lat};${to.lng},${to.lat}?overview=full&geometries=geojson`;
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 1500);
  try {
    const res = await fetch(url, { signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) throw new Error('osrm bad status');
    const data = await res.json();
    const coords = data?.routes?.[0]?.geometry?.coordinates;
    if (!coords || !coords.length) throw new Error('no route');
    return coords.map(([lng, lat]) => [lat, lng]);
  } catch (_) {
    return [[from.lat, from.lng], [to.lat, to.lng]];
  }
}

class RouteLayer {
  constructor(map, opts = {}) {
    this.map = map;
    this.color = opts.color || '#06c167';
    this.line = null;
    this.carMarker = null;
    this.pickupMarker = null;
    this.dropMarker = null;
    this.showPickup = opts.showPickup !== false;
  }

  async render({ driver, pickup, destination }) {
    if (this.line) { this.line.remove(); this.line = null; }
    if (this.carMarker) { this.carMarker.remove(); this.carMarker = null; }
    if (this.pickupMarker) { this.pickupMarker.remove(); this.pickupMarker = null; }
    if (this.dropMarker) { this.dropMarker.remove(); this.dropMarker = null; }

    const tripStart = pickup || driver;
    const to = destination;
    if (!tripStart || !to) return;

    const path = await fetchRoute(tripStart, to);
    this.line = L.polyline(path, {
      color: this.color, weight: 5, opacity: 0.95, lineCap: 'round', lineJoin: 'round',
    }).addTo(this.map);

    if (pickup && this.showPickup) {
      this.pickupMarker = L.marker([pickup.lat, pickup.lng], { icon: ICONS.pickup() }).addTo(this.map);
    }
    this.dropMarker = L.marker([to.lat, to.lng], { icon: ICONS.drop() }).addTo(this.map);
    if (driver) {
      this.carMarker = L.marker([driver.lat, driver.lng], { icon: ICONS.car() }).addTo(this.map);
    }

    const points = [[tripStart.lat, tripStart.lng], [to.lat, to.lng]];
    if (driver) points.push([driver.lat, driver.lng]);
    const bounds = L.latLngBounds(points).pad(0.25);
    this.map.fitBounds(bounds, { animate: true, duration: 0.6 });
  }
}

window.UberMap = { initMap, fetchRoute, RouteLayer, ICONS };
