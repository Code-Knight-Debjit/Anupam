// Helpers shared by the Customer pages (list, form, view, person profile). Ported from the reference's top-level helpers.
import { state } from './state.js';
import { el, escapeHtml, customAlert, openModal, closeModal, loadScript } from './ui.js';
import { VIEWS, OVERLAYS } from './ref_html.js';
import { DOT_PALETTE } from './india.js';

export const titleCaseWords = (str) => (str || '').replace(/(^|[\s\-/(&.,])([a-z])/g, (m, pre, ch) => pre + ch.toUpperCase());
export const initialsOf = (name) => { const p = (name || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
export const normPlant = (v) => (v || '').toString().trim().toLowerCase().replace(/\s+/g, ' ');
export const companyLabel = (c) => { if (!c) return ''; const plant = (c.plant || '').trim(); return plant ? `${c.name} — ${plant}` : (c.name || ''); };
export const fmtD = (iso) => new Date(iso).toLocaleDateString('en-IN');
export function waLink(phone) {
  let digits = (phone || '').replace(/\D/g, '');
  if (digits.length === 10) digits = '91' + digits;
  return digits ? `https://wa.me/${digits}?text=${encodeURIComponent('Hi, ')}` : null;
}
export const webUrl = (w) => (String(w).startsWith('http') ? w : 'https://' + w);
export function dotColorForTitle(title) {
  const list = state.lookups.job_title || [];
  const idx = list.findIndex((j) => j.name === title);
  return DOT_PALETTE[idx >= 0 ? idx % DOT_PALETTE.length : 0];
}

export const CALL_ICON_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"></path></svg>';
export const EMAIL_ICON_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;"><path d="M4 4h16v16H4z"></path><path d="M22 6l-10 7L2 6"></path></svg>';
export const WHATSAPP_ICON_SVG = '<svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" style="vertical-align:middle;"><path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2.05 22l5.25-1.38a9.9 9.9 0 0 0 4.74 1.2h.01c5.46 0 9.91-4.45 9.91-9.91C21.96 6.45 17.5 2 12.04 2zm5.8 14.11c-.24.68-1.4 1.3-1.93 1.38-.5.08-1.12.11-1.8-.11-.42-.13-.96-.31-1.65-.6-2.9-1.25-4.8-4.17-4.95-4.37-.14-.2-1.18-1.57-1.18-3 0-1.43.75-2.13 1.01-2.42.26-.29.57-.36.76-.36l.55.01c.18.01.42-.07.65.5.24.58.82 2 .89 2.15.07.14.12.31.02.5-.1.2-.15.31-.29.48-.15.17-.31.38-.44.51-.15.14-.3.3-.13.59.17.29.76 1.25 1.63 2.03 1.12 1 2.06 1.31 2.35 1.46.29.14.46.12.63-.07.17-.2.73-.85.92-1.14.2-.29.39-.24.66-.15.27.1 1.7.8 1.99.95.29.15.49.22.56.34.07.12.07.7-.17 1.38z"/></svg>';

// ---- reference markup ---------------------------------------------------------------------------------------------------
/** Mounts one of the reference's static views (copied verbatim) into the page and marks it active. */
export function mountRefView(root, name) {
  root.innerHTML = VIEWS[name];
  const view = root.firstElementChild;
  view.classList.add('active');
  return view;
}
/** The reference's dialogs are static markup too; each is added to the page the first time a screen needs it. */
export function useOverlays(...ids) {
  ids.forEach((id) => {
    if (document.getElementById(id) || !OVERLAYS[id]) return;
    document.body.insertAdjacentHTML('beforeend', OVERLAYS[id]);
    const overlay = document.getElementById(id);
    overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) overlay.classList.remove('open'); });
  });
}
export const openOverlay = (id) => el(id).classList.add('open');
export const closeOverlay = (id) => el(id).classList.remove('open');

// ---- row "Actions ▾" menus (inline handlers in the reference markup) ---------------------------------------------------------
window.closeRowMenus = () => document.querySelectorAll('.row-menu-dropdown.open').forEach((d) => d.classList.remove('open'));
window.toggleRowMenu = (btn) => {
  const dd = btn.parentElement.querySelector('.row-menu-dropdown');
  const wasOpen = dd.classList.contains('open');
  window.closeRowMenus();
  if (wasOpen) return;
  const r = btn.getBoundingClientRect();
  dd.style.top = `${r.bottom + 4}px`;
  dd.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - 190))}px`;
  dd.classList.add('open');
};
document.addEventListener('click', (e) => { if (!e.target.closest('.row-menu-wrap')) window.closeRowMenus(); });
window.el = el;                      // the reference markup calls el('…') inline

// ---- multi-select dropdown (reference: msBuild) -------------------------------------------------------------------------------
export function msBuild(id, items, cls, placeholder) {
  const host = el(id); if (!host) return;
  host.classList.add('ms-dd'); host.dataset.ph = placeholder;
  const keep = new Set([...host.querySelectorAll('.' + cls + ':checked')].map((c) => c.value));
  host.innerHTML = `
    <button type="button" class="ms-btn"><span class="ms-lab ph">${escapeHtml(placeholder)}</span><i>&#9662;</i></button>
    <div class="ms-panel" style="display:none;">
      <div class="ms-tools">${items.length > 6 ? '<input type="text" class="ms-search" placeholder="Search…" autocomplete="off">' : ''}<button type="button" class="ms-all">Select all</button><button type="button" class="ms-none">Clear</button></div>
      <div class="ms-list">${items.length ? items.map((it) => `<label class="ms-item" data-s="${escapeHtml(String(it.label).toLowerCase())}"><input type="checkbox" class="${cls}" value="${escapeHtml(String(it.value))}" data-label="${escapeHtml(it.label)}"${keep.has(String(it.value)) ? ' checked' : ''}><span class="nm">${escapeHtml(it.label)}${it.sub ? `<small>${escapeHtml(it.sub)}</small>` : ''}</span></label>`).join('') : '<div class="ms-empty">Nothing to choose from yet.</div>'}</div>
    </div>`;
  msRefresh(host);
}
export function msRefresh(host) {
  const lab = host.querySelector('.ms-lab'); if (!lab) return;
  const names = [...host.querySelectorAll('input[type=checkbox]:checked')].map((c) => c.dataset.label || c.value);
  lab.textContent = !names.length ? (host.dataset.ph || 'Select') : (names.length <= 2 ? names.join(', ') : names.slice(0, 2).join(', ') + ' +' + (names.length - 2) + ' more');
  lab.classList.toggle('ph', !names.length);
  host.classList.toggle('has', names.length > 0);
}
export const msRefreshAll = () => document.querySelectorAll('.ms-dd').forEach(msRefresh);
if (!window.__msWired) {
  window.__msWired = true;
  document.addEventListener('click', (e) => {
    const t = e.target; if (!t.closest) return;
    const host = t.closest('.ms-dd');
    document.querySelectorAll('.ms-dd .ms-panel').forEach((p) => { if (!host || p.parentElement !== host) p.style.display = 'none'; });
    if (!host) return;
    if (t.closest('.ms-btn')) { const p = host.querySelector('.ms-panel'); p.style.display = p.style.display === 'none' ? 'flex' : 'none'; return; }
    if (t.closest('.ms-all') || t.closest('.ms-none')) {
      const on = !!t.closest('.ms-all');
      host.querySelectorAll('.ms-item').forEach((it) => { if (it.style.display !== 'none') it.querySelector('input').checked = on; });
      msRefresh(host);
    }
  });
  document.addEventListener('change', (e) => { const h = e.target.closest && e.target.closest('.ms-dd'); if (h) msRefresh(h); });
  document.addEventListener('input', (e) => {
    if (!e.target.classList || !e.target.classList.contains('ms-search')) return;
    const q = e.target.value.trim().toLowerCase();
    e.target.closest('.ms-dd').querySelectorAll('.ms-item').forEach((it) => { it.style.display = !q || it.dataset.s.includes(q) ? '' : 'none'; });
  });
}

// ---- copying (reference: copyTextToClipboard / showManualCopy) --------------------------------------------------------------
function legacyCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text; ta.setAttribute('readonly', '');
  Object.assign(ta.style, { position: 'fixed', top: '0', left: '0', opacity: '0', fontSize: '16px' });
  document.body.appendChild(ta); ta.focus(); ta.select(); ta.setSelectionRange(0, text.length);
  let ok = false; try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
  document.body.removeChild(ta); return ok;
}
export async function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText && window.isSecureContext !== false) {
    try { await navigator.clipboard.writeText(text); return; } catch (e) { /* fall through */ }
  }
  if (legacyCopy(text)) return;
  throw new Error('copy-failed');
}
export const showManualCopy = (text) => customAlert(`${text}\n\nTouch and hold (or select) the text above to copy it.`, "Couldn't copy automatically");
window.copyEmailToClipboard = async (node) => {
  const email = node.dataset.email, original = node.innerHTML;
  try { await copyText(email); node.innerHTML = 'Copied!'; node.classList.add('copied'); setTimeout(() => { node.innerHTML = original; node.classList.remove('copied'); }, 1200); }
  catch (e) { showManualCopy(email); }
};
/** Tap a number: Copy or Call (reference: showPhoneOptions). */
window.showPhoneOptions = (phone) => {
  if (!phone) return;
  openModal(`<h2>Phone number</h2><p class="modal-sub" style="white-space:pre-wrap;">${escapeHtml(phone)}</p>
    <div class="modal-actions"><button class="btn" id="phCopy">Copy</button><button class="btn btn-primary" id="phCall">Call</button></div>`, {
    size: 'narrow',
    onMount: (m) => {
      m.querySelector('#phCopy').onclick = async () => { closeModal(); try { await copyText(phone); customAlert('Number copied to clipboard.'); } catch (e) { showManualCopy(phone); } };
      m.querySelector('#phCall').onclick = () => { closeModal(); window.location.href = 'tel:' + phone; };
    },
  });
};

// ---- map pins ----------------------------------------------------------------------------------------------------------------
export function geoParse(s) {
  s = (s || '').trim(); if (!s) return null;
  let t = s; try { t = decodeURIComponent(s); } catch (e) { /* keep as typed */ }
  const num = '(-?\\d+(?:\\.\\d+)?)';
  const res = [new RegExp('!3d' + num + '!4d' + num), new RegExp('[?&](?:q|ll|query|destination|center)=' + num + '\\s*,\\s*' + num), new RegExp('@' + num + ',\\s*' + num), new RegExp('^\\s*' + num + '\\s*[,;\\s]\\s*' + num + '\\s*$')];
  for (const re of res) {
    const m = t.match(re); if (!m) continue;
    const lat = +m[1], lng = +m[2];
    if (Math.abs(lat) <= 90 && Math.abs(lng) <= 180) return { lat: +lat.toFixed(6), lng: +lng.toFixed(6) };
  }
  return null;
}
export const geoLink = (g) => (g && g.lat != null ? `https://www.google.com/maps?q=${g.lat},${g.lng}` : '');
export const geoDirLink = (g) => `https://www.google.com/maps/dir/?api=1&destination=${g.lat},${g.lng}`;
export function geoDist(a, b) {
  const R = 6371000, r = (x) => x * Math.PI / 180;
  const dLat = r(b.lat - a.lat), dLng = r(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(r(a.lat)) * Math.cos(r(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
export const geoFmtDist = (m) => (m < 1000 ? Math.round(m) + ' m' : (m / 1000).toFixed(m < 10000 ? 1 : 0) + ' km');
/** The customer payload's pin as the reference shaped it: {lat, lng, by, at} or null. */
export function pinOf(c, which) {
  const lat = c[`${which}_geo_lat`], lng = c[`${which}_geo_lng`];
  if (lat === null || lat === undefined) return null;
  const by = c[`${which}_geo_set_by`];
  return { lat, lng, by: by ? by.full_name : '', at: c[`${which}_geo_set_at`] };
}
export { loadScript };
