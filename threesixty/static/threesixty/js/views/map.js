// Map & Nearby — the reference's page: a toolbar (what to show, state, assignee, "Near me", radius), the map on the left
// and the list of pins on the right. Leaflet is vendored; tiles come from OpenStreetMap, and the list works without them.
import { api } from '../api.js';
import { state } from '../state.js';
import { el, escapeHtml, customAlert, loadScript } from '../ui.js';
import { navigate } from '../router.js';
import { mountRefView, geoDist, geoFmtDist, geoDirLink, pinOf } from '../customer_common.js';
import { getLocation } from '../attendance_actions.js';

let mapObj = null, mapLayer = null, me = null, cards = [];

function items() {
  const show = el('mapShow').value, st = el('mapState').value, as = el('mapAssigned').value;
  const comps = cards.filter((c) => (!st || c.state === st) && (!as || c.assigned_to.some((a) => a.full_name === as)));
  const out = [];
  comps.forEach((c) => {
    const plant = pinOf(c, 'plant'), ho = pinOf(c, 'ho');
    if (show === 'missing') { if (!plant && !ho) out.push({ c, kind: 'none' }); return; }
    if (show !== 'ho' && plant) out.push({ c, kind: 'plant', g: plant });
    if (show !== 'plant' && ho) out.push({ c, kind: 'ho', g: ho });
  });
  return { items: out, missing: comps.filter((c) => !pinOf(c, 'plant') && !pinOf(c, 'ho')).length };
}

async function refresh(fit) {
  const { items: all, missing } = items();
  const radius = +el('mapRadius').value;
  all.forEach((it) => { it.d = (me && it.g) ? geoDist(me, it.g) : null; });
  let list = all;
  if (me && radius) list = list.filter((it) => it.d == null || it.d <= radius * 1000);
  list.sort((a, b) => (me && a.d != null && b.d != null ? a.d - b.d : (a.c.name || '').localeCompare(b.c.name || '')));
  el('mapCount').textContent = `${list.length} shown · ${missing} customer${missing === 1 ? '' : 's'} without any pin`;
  el('mapList').innerHTML = list.length ? list.map((it, i) => `<div class="map-item">
      <b>${escapeHtml(it.c.name)}</b>${it.kind === 'plant' ? '<span class="map-badge">Plant</span>' : it.kind === 'ho' ? '<span class="map-badge ho">Head office</span>' : '<span class="map-badge">No pin</span>'}
      <div class="mi-meta">${escapeHtml([it.c.area, it.c.city, it.c.state].filter(Boolean).join(', ') || '—')}${it.d != null ? ' · <b>' + geoFmtDist(it.d) + ' away</b>' : ''}</div>
      <div class="cv-geo-links"><a href="#" data-open="${it.c.id}">Open customer</a>${it.g ? `<a href="${geoDirLink(it.g)}" target="_blank" rel="noopener">Directions</a>` : `<a href="#" data-pin="${it.c.id}">Add pin</a>`}</div>
    </div>`).join('') : '<div class="map-item" style="color:var(--text-dim);">Nothing to show for these filters.</div>';
  el('mapList').querySelectorAll('[data-open]').forEach((a) => a.onclick = (e) => { e.preventDefault(); navigate('customerview', a.dataset.open); });
  el('mapList').querySelectorAll('[data-pin]').forEach((a) => a.onclick = (e) => { e.preventDefault(); navigate('customerform', a.dataset.pin); });
  const box = el('mapBox');
  let L = window.L;
  if (!L) { try { await loadScript(window.THREESIXTY_VENDOR.leaflet); L = window.L; } catch (e) { L = null; } }
  if (!L) { box.textContent = 'The map couldn’t load (it needs an internet connection). The list on the right still works, and each row has a Directions link.'; return; }
  if (!mapObj || mapObj._container !== box) {
    box.textContent = ''; box.style.display = 'block';
    mapObj = L.map('mapBox').setView([20.5937, 78.9629], 5);
    // OpenStreetMap's tile policy refuses requests that carry no Referer. This site sends none by default
    // (Referrer-Policy: same-origin), so the tiles ask for the site's origin only — never the path or any data.
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, referrerPolicy: 'origin', attribution: '&copy; OpenStreetMap contributors' }).addTo(mapObj);
    let failed = 0;
    tiles.on('tileerror', () => {
      if (++failed === 3) { const n = document.createElement('div'); n.className = 'map-tile-warn'; n.textContent = 'Map tiles could not be loaded (check the internet connection). The list on the right still works.'; box.appendChild(n); }
    });
    mapLayer = L.layerGroup().addTo(mapObj);
  }
  setTimeout(() => mapObj.invalidateSize(), 50);
  mapLayer.clearLayers();
  const pts = [];
  list.filter((it) => it.g).forEach((it) => {
    const m = L.circleMarker([it.g.lat, it.g.lng], { radius: 8, weight: 2, color: '#fff', fillOpacity: 0.95, fillColor: it.kind === 'plant' ? '#e8702a' : '#2f6fd1' }).addTo(mapLayer);
    m.bindPopup(`<b>${escapeHtml(it.c.name)}</b><br>${it.kind === 'plant' ? 'Plant' : 'Head office'}${it.d != null ? ' · ' + geoFmtDist(it.d) + ' away' : ''}<br><a href="${geoDirLink(it.g)}" target="_blank" rel="noopener">Directions</a>`);
    pts.push([it.g.lat, it.g.lng]);
  });
  if (me) { L.circleMarker([me.lat, me.lng], { radius: 9, weight: 3, color: '#fff', fillColor: '#1a9a4a', fillOpacity: 1 }).addTo(mapLayer).bindPopup('You are here'); pts.push([me.lat, me.lng]); }
  if (fit && pts.length) mapObj.fitBounds(pts, { padding: [30, 30], maxZoom: 15 });
}

export async function mountMap(root) {
  mapObj = null; me = null;
  mountRefView(root, 'view-map');
  cards = (await api.get('customers/cards/')).results;
  el('mapState').innerHTML = '<option value="">All states</option>' + [...new Set(cards.map((c) => c.state).filter(Boolean))].sort().map((s) => `<option>${escapeHtml(s)}</option>`).join('');
  el('mapAssigned').innerHTML = '<option value="">All assignees</option>' + state.employees.map((e) => `<option>${escapeHtml(e.full_name)}</option>`).join('');
  ['mapShow', 'mapState', 'mapAssigned', 'mapRadius'].forEach((id) => el(id).addEventListener('change', () => refresh(true)));
  el('mapNearBtn').addEventListener('click', async () => {
    el('mapNearBtn').textContent = 'Locating…';
    try { me = await getLocation(); } catch (err) { await customAlert(err.message); me = null; }
    el('mapNearBtn').textContent = me ? '📍 Near me ✓' : '📍 Near me';
    refresh(true);
  });
  await refresh(true);
}
