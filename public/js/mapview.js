import { LEVELS } from './levels.js';

const L = window.L;
const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'; // free, no API key
// Static, trusted markup only (no user data ever goes into divIcon html).
const GLYPH = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3v6a2.5 2.5 0 005 0V3M10.5 3v18M18 3c-2.4 1.4-3.5 4-3.5 7H18v11"/></svg>';

function pinIcon(level, active, selected, kind) {
  const css = LEVELS[level].css;
  const shape = kind === 'restaurant' ? '' : ' pin-sq'; // circle = restaurant, square = street vendor
  const cls = `pin pin-${css}${shape}${active && level === 'OUTBREAK' ? ' pin-pulse' : ''}${selected ? ' is-selected' : ''}`;
  return L.divIcon({ className: 'pin-wrap', html: `<span class="${cls}">${GLYPH}</span>`, iconSize: [34, 34], iconAnchor: [17, 17] });
}

function metresBetween(a, b) {
  const rad = (d) => (d * Math.PI) / 180;
  const x = Math.sin(rad(b[0] - a[0]) / 2) ** 2
    + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(rad(b[1] - a[1]) / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(x));
}

export class MapView {
  constructor(el, center, handlers) {
    this.handlers = handlers;
    this.markers = new Map();
    this.selectedId = null;
    this.pinMode = false;
    this.dropMarker = null;
    this.userMarker = null;

    this.map = L.map(el, { zoomControl: false, center, zoom: 16, minZoom: 11, maxZoom: 19 });
    this.map.attributionControl.setPrefix(false);
    this.dark = window.matchMedia('(prefers-color-scheme: dark)');
    this.applyTheme();
    this.dark.addEventListener('change', () => this.applyTheme());
    this.map.on('click', (e) => {
      if (this.pinMode) this.handlers.onPin(e.latlng);
    });
  }

  applyTheme() {
    if (this.tiles) this.tiles.remove();
    this.tiles = L.tileLayer(TILE_URL, {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(this.map);
    this.map.getContainer().classList.toggle('map-dark', this.dark.matches);
  }

  setStalls(stalls) {
    const seen = new Set();
    for (const s of stalls) {
      seen.add(s.id);
      const key = `${s.level}|${s.active}|${s.kind}`;
      let entry = this.markers.get(s.id);
      if (!entry) {
        const marker = L.marker([s.lat, s.lng], {
          icon: pinIcon(s.level, s.active, s.id === this.selectedId, s.kind),
          title: s.name,
          riseOnHover: true,
          zIndexOffset: s.level_value * 100,
        }).addTo(this.map);
        marker.on('click', () => this.handlers.onSelect(s.id));
        marker.on('add', () => marker.getElement()?.setAttribute('role', 'button'));
        marker.getElement()?.setAttribute('role', 'button');
        marker.getElement()?.setAttribute('aria-label', `${s.name}, ${LEVELS[s.level].label}`);
        entry = { marker, key };
        this.markers.set(s.id, entry);
      } else if (entry.key !== key) {
        entry.marker.setIcon(pinIcon(s.level, s.active, s.id === this.selectedId, s.kind));
        entry.marker.setZIndexOffset(s.level_value * 100);
        entry.marker.getElement()?.setAttribute('aria-label', `${s.name}, ${LEVELS[s.level].label}`);
        entry.key = key;
      }
      entry.stall = s;
    }
    for (const [id, entry] of this.markers) {
      if (!seen.has(id)) {
        entry.marker.remove();
        this.markers.delete(id);
      }
    }
  }

  /** Zoom so the pins around the town centre are all visible, clear of the panel. */
  fitTown(center, radiusM = 4000) {
    const stalls = [...this.markers.values()].map((e) => e.stall).filter(Boolean);
    const near = stalls.filter((s) => metresBetween(center, [s.lat, s.lng]) <= radiusM);
    const pts = (near.length >= 3 ? near : stalls).map((s) => [s.lat, s.lng]);
    if (!pts.length) return;
    const { bottom = 0, left = 0 } = this.handlers.insets();
    this.map.fitBounds(pts, {
      paddingTopLeft: [left + 40, 90],
      paddingBottomRight: [40, bottom + 40],
      maxZoom: 16,
      animate: false,
    });
  }

  select(id) {
    const previous = this.markers.get(this.selectedId);
    if (previous) previous.marker.getElement()?.firstElementChild?.classList.remove('is-selected');
    this.selectedId = id;
    const current = this.markers.get(id);
    if (current) current.marker.getElement()?.firstElementChild?.classList.add('is-selected');
  }

  /** Fly to a point, shifting the centre so it lands in the visible area beside the sheet. */
  focus(lat, lng, zoom = 17) {
    const { bottom = 0, left = 0 } = this.handlers.insets();
    const target = this.map.project([lat, lng], zoom).add([-left / 2, bottom / 2]);
    this.map.flyTo(this.map.unproject(target, zoom), zoom, { duration: 0.6 });
  }

  setUser(lat, lng) {
    if (!this.userMarker) {
      this.userMarker = L.marker([lat, lng], {
        interactive: false,
        keyboard: false,
        icon: L.divIcon({ className: 'pin-wrap', html: '<span class="user-dot"></span>', iconSize: [18, 18], iconAnchor: [9, 9] }),
        zIndexOffset: -500,
      }).addTo(this.map);
    } else {
      this.userMarker.setLatLng([lat, lng]);
    }
  }

  enablePinDrop() {
    this.pinMode = true;
    document.body.classList.add('pin-mode');
  }

  dropAt(latlng) {
    this.clearDrop();
    this.dropMarker = L.marker(latlng, {
      interactive: false,
      icon: L.divIcon({ className: 'pin-wrap', html: '<span class="drop-pin"></span>', iconSize: [22, 22], iconAnchor: [11, 22] }),
    }).addTo(this.map);
  }

  clearDrop() {
    if (this.dropMarker) this.dropMarker.remove();
    this.dropMarker = null;
  }

  disablePinDrop() {
    this.pinMode = false;
    document.body.classList.remove('pin-mode');
  }
}
