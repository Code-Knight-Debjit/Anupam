// Map & Nearby — ported from `renderMapPage`/`mapRefresh` (contact_management.html
// ~L4808-4848). Uses vendored Leaflet (already linked in index.html) + OSM
// tiles, with a sortable/filterable list alongside the map pins.
import { api } from '../api.js';
import { el, escapeHtml, toast, loadScript } from '../ui.js';
import { navigate } from '../router.js';

function geoDist(a, b) {
  const R = 6371000, r = (x) => (x * Math.PI) / 180;
  const dLat = r(b.lat - a.lat), dLng = r(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(r(a.lat)) * Math.cos(r(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
function geoFmtDist(m) { return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(m < 10000 ? 1 : 0)} km`; }
function geoDirLink(g) { return `https://www.google.com/maps/dir/?api=1&destination=${g.lat},${g.lng}`; }

function getLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) { reject(new Error('This device/browser cannot share location.')); return; }
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
      (err) => reject(new Error(err && err.code === 1 ? 'Location permission was denied.' : 'Could not get your location.')),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  });
}

function mapItems(customers, show, stateFilter, assignedId) {
  const comps = customers.filter((c) => (!stateFilter || c.state === stateFilter)
    && (!assignedId || (c.assigned_to_ids || []).includes(Number(assignedId))));
  const items = [];
  let missing = 0;
  comps.forEach((c) => {
    const hasPlant = c.plant_geo_lat != null && c.plant_geo_lng != null;
    const hasHo = c.ho_geo_lat != null && c.ho_geo_lng != null;
    if (show === 'missing') { if (!hasPlant && !hasHo) items.push({ c, kind: 'none' }); return; }
    if (!hasPlant && !hasHo) missing += 1;
    if (show !== 'ho' && hasPlant) items.push({ c, kind: 'plant', g: { lat: c.plant_geo_lat, lng: c.plant_geo_lng } });
    if (show !== 'plant' && hasHo) items.push({ c, kind: 'ho', g: { lat: c.ho_geo_lat, lng: c.ho_geo_lng } });
  });
  return { items, missing };
}

let mapObj = null, mapLayer = null, mapMe = null;
let L = null;

export async function mountMap(root) {
  const [customers, employees] = await Promise.all([api.all('customers/'), api.all('employees/')]);
  const states = [...new Set(customers.map((c) => c.state).filter(Boolean))].sort();
  if (window.THREESIXTY_VENDOR && window.THREESIXTY_VENDOR.leaflet) {
    try { await loadScript(window.THREESIXTY_VENDOR.leaflet); } catch (e) { /* handled below via L==null fallback */ }
  }
  L = window.L || null;

  root.innerHTML = `
    <div class="map-layout" style="display:grid;grid-template-columns:1fr 360px;gap:16px;align-items:start;">
      <div id="mapBox" style="height:70vh;border-radius:var(--radius-md);background:var(--surface-container-low);"></div>
      <div>
        <div class="field"><label>Show</label><select id="mapShow">
          <option value="both">Plant &amp; head office</option>
          <option value="plant">Plant only</option>
          <option value="ho">Head office only</option>
          <option value="missing">Missing pin</option>
        </select></div>
        <div class="field"><label>State</label><select id="mapState"><option value="">All states</option>${states.map((s) => `<option>${escapeHtml(s)}</option>`).join('')}</select></div>
        <div class="field"><label>Assigned to</label><select id="mapAssigned"><option value="">All assignees</option>${employees.map((e) => `<option value="${e.user_id}">${escapeHtml(e.full_name)}</option>`).join('')}</select></div>
        <div class="field"><label>Within (km)</label><input type="number" id="mapRadius" min="0" placeholder="no limit"></div>
        <button class="btn sm" id="mapNearBtn">📍 Near me</button>
        <div class="sub" id="mapCount" style="margin:10px 0;"></div>
        <div id="mapList" style="max-height:48vh;overflow-y:auto;"></div>
      </div>
    </div>`;

  async function refresh(fit) {
    const show = el('mapShow').value, stFilter = el('mapState').value, as = el('mapAssigned').value;
    const { items, missing } = mapItems(customers, show, stFilter, as);
    const radius = Number(el('mapRadius').value) || 0;
    items.forEach((it) => { it.d = (mapMe && it.g) ? geoDist(mapMe, it.g) : null; });
    let list = items;
    if (mapMe && radius) list = list.filter((it) => it.d == null || it.d <= radius * 1000);
    list.sort((a, b) => (mapMe && a.d != null && b.d != null) ? a.d - b.d : (a.c.name || '').localeCompare(b.c.name || ''));

    el('mapCount').textContent = `${list.length} shown · ${missing} customer${missing === 1 ? '' : 's'} without any pin`;
    el('mapList').innerHTML = list.length ? list.map((it) => `
      <div class="card" style="margin-bottom:8px;padding:10px 14px;">
        <div><strong>${escapeHtml(it.c.name)}</strong> ${it.kind === 'plant' ? '<span class="badge">Plant</span>' : it.kind === 'ho' ? '<span class="badge">Head office</span>' : '<span class="badge">No pin</span>'}</div>
        <div class="sub">${escapeHtml([it.c.area, it.c.city, it.c.state].filter(Boolean).join(', ') || '—')}${it.d != null ? ` · <b>${geoFmtDist(it.d)} away</b>` : ''}</div>
        <div style="margin-top:4px;"><a data-open="${it.c.id}" style="cursor:pointer;color:var(--primary);">Open customer</a>${it.g ? ` · <a href="${geoDirLink(it.g)}" target="_blank" rel="noopener">Directions</a>` : ''}</div>
      </div>`).join('') : '<p class="sub">Nothing to show for these filters.</p>';
    root.querySelectorAll('[data-open]').forEach((a) => a.onclick = () => navigate('customers'));

    if (!L) { el('mapBox').textContent = 'The map couldn’t load (it needs an internet connection). The list on the right still works, and each row has a Directions link.'; return; }
    if (!mapObj) {
      mapObj = L.map('mapBox').setView([20.5937, 78.9629], 5);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(mapObj);
      mapLayer = L.layerGroup().addTo(mapObj);
    }
    setTimeout(() => mapObj.invalidateSize(), 50);
    mapLayer.clearLayers();
    const pts = [];
    list.filter((it) => it.g).forEach((it) => {
      const m = L.circleMarker([it.g.lat, it.g.lng], { radius: 8, weight: 2, color: '#fff', fillOpacity: .95, fillColor: it.kind === 'plant' ? '#e8702a' : '#2f6fd1' }).addTo(mapLayer);
      m.bindPopup(`<b>${escapeHtml(it.c.name)}</b><br>${it.kind === 'plant' ? 'Plant' : 'Head office'}${it.d != null ? ` · ${geoFmtDist(it.d)} away` : ''}<br><a href="${geoDirLink(it.g)}" target="_blank" rel="noopener">Directions</a>`);
      pts.push([it.g.lat, it.g.lng]);
    });
    if (mapMe) {
      L.circleMarker([mapMe.lat, mapMe.lng], { radius: 9, weight: 3, color: '#fff', fillColor: '#1a9a4a', fillOpacity: 1 }).addTo(mapLayer).bindPopup('You are here');
      pts.push([mapMe.lat, mapMe.lng]);
    }
    if (fit && pts.length) mapObj.fitBounds(pts, { padding: [30, 30], maxZoom: 15 });
  }

  ['mapShow', 'mapState', 'mapAssigned', 'mapRadius'].forEach((id) => el(id).addEventListener('change', () => refresh(true)));
  el('mapNearBtn').addEventListener('click', async () => {
    const btn = el('mapNearBtn');
    btn.textContent = 'Locating…';
    try { mapMe = await getLocation(); btn.textContent = '📍 Near me ✓'; } catch (e) { toast(e.message, 'error'); btn.textContent = '📍 Near me'; }
    refresh(true);
  });

  await refresh(true);

  return () => { if (mapObj) { mapObj.remove(); mapObj = null; mapLayer = null; } };
}
