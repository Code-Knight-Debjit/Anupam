// Add / Edit customer — the reference's full-page form (Company details, Head office, Business details, Preferences &
// assignment, Contact persons). The markup is the reference's own; this file fills it, validates it and saves it. The
// contacts are saved together with the customer; a Sales Manager's edit becomes one approval request (contacts included).
import { api } from '../api.js';
import { state, isAdmin, isBranchManager, isBranchStaff } from '../state.js';
import { navigate } from '../router.js';
import { el, escapeHtml, customAlert, customConfirm, apiErrorMessage, findDuplicateCustomers, normalizeCompanyNameBasic } from '../ui.js';
import { mountRefView, titleCaseWords, normPlant, msBuild, msRefreshAll, geoParse, geoLink, pinOf, WHATSAPP_ICON_SVG } from '../customer_common.js';
import { INDIA_STATES, INDIA_CITIES } from '../india.js';
import { getLocation } from '../attendance_actions.js';

const canEditDirect = () => isAdmin() || isBranchManager() || isBranchStaff();    // reference: canEditCustomerDirect()
const canAssign = () => isAdmin() || isBranchManager();
const names = (key) => (state.lookups[key] || []).map((x) => x.name);
const idsOf = (key, picked) => picked.map((n) => (state.lookups[key] || []).find((x) => x.name === n)).filter(Boolean).map((x) => x.id);
const opts = (list, ph) => `<option value="">${ph}</option>` + list.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join('');

let editing = null;          // the card payload being edited, or null for a new customer
let isRequest = false;
let formLogo = '';           // data URL shown in the preview
let logoBlob = null;         // what gets uploaded after the save (null = unchanged, false = remove)
let geoState = { plant: null, ho: null };
let contactRowCount = 0;

const setLogo = (dataUrl) => {
  formLogo = dataUrl || '';
  el('f-logo-prev').innerHTML = formLogo ? `<img alt="logo" src="${formLogo}">` : '🏢';
  el('f-logo-rm').style.display = formLogo ? '' : 'none';
};
window.setFormLogo = (d) => { setLogo(d); logoBlob = d ? logoBlob : false; };
window.onLogoPicked = (inp) => {
  const file = inp.files && inp.files[0]; inp.value = '';
  if (!file) return;
  if (!/^image\//.test(file.type)) { customAlert('Please choose an image file.'); return; }
  const rd = new FileReader();
  rd.onload = () => {
    const im = new Image();
    im.onload = () => {
      const M = 240, r = Math.min(1, M / Math.max(im.width, im.height));
      const cv = document.createElement('canvas');
      cv.width = Math.max(1, Math.round(im.width * r)); cv.height = Math.max(1, Math.round(im.height * r));
      cv.getContext('2d').drawImage(im, 0, 0, cv.width, cv.height);
      const type = file.type === 'image/png' ? 'image/png' : 'image/jpeg';
      cv.toBlob((b) => { logoBlob = b; setLogo(cv.toDataURL(type, 0.85)); }, type, 0.85);
    };
    im.onerror = () => customAlert('Could not read that image.');
    im.src = rd.result;
  };
  rd.readAsDataURL(file);
};

function addContactRow(data = {}) {
  const rowId = 'crow' + (contactRowCount++);
  const row = document.createElement('div');
  row.className = 'contact-form-row'; row.id = rowId; row.style.gridTemplateColumns = '1.1fr 1fr 0.9fr 0.9fr 1.1fr 40px';
  const jt = names('job_title').map((n) => `<option value="${escapeHtml(n)}" ${data.job_title === n ? 'selected' : ''}>${escapeHtml(n)}</option>`).join('');
  row.innerHTML = `
    <input type="text" placeholder="Contact name" class="ct-name" value="${escapeHtml(data.name || '')}">
    <select class="ct-desig">${jt}</select>
    <input type="text" placeholder="WhatsApp No." class="ct-phone" value="${escapeHtml(data.phone || '')}" inputmode="tel">
    <input type="text" placeholder="Phone 2" class="ct-phone2" value="${escapeHtml(data.phone2 || '')}" inputmode="tel">
    <input type="text" placeholder="Email" class="ct-email" value="${escapeHtml(data.email || '')}" inputmode="email">
    <button type="button" class="rm-contact">&times;</button>`;
  row.dataset.contactId = data.id || '';
  row.querySelector('.rm-contact').onclick = () => row.remove();
  el('contactRows').appendChild(row);
}

// ---- map pins -------------------------------------------------------------------------------------------------------------------
function geoNote(k) {
  const inp = el('f-geo-' + k), note = el('f-geo-' + k + '-note'), txt = inp.value.trim();
  note.classList.remove('bad');
  if (!txt) { note.textContent = 'No pin saved.'; return; }
  const p = geoParse(txt);
  if (!p) { note.textContent = 'Not a valid location — use "latitude, longitude" or a full Google Maps link.'; note.classList.add('bad'); return; }
  const g = geoState[k];
  note.textContent = (g && g.lat === p.lat && g.lng === p.lng && g.by) ? `Pin set by ${g.by}${g.at ? ' on ' + new Date(g.at).toLocaleDateString('en-IN') : ''}.` : 'Pin will be saved when you save the customer.';
}
function geoLoad(c) {
  geoState = { plant: c ? pinOf(c, 'plant') : null, ho: c ? pinOf(c, 'ho') : null };
  ['plant', 'ho'].forEach((k) => { const g = geoState[k]; el('f-geo-' + k).value = g ? `${g.lat}, ${g.lng}` : ''; geoNote(k); });
}
function wireGeo(view) {
  view.querySelectorAll('#f-geo-plant, #f-geo-ho').forEach((inp) => {
    inp.addEventListener('input', () => geoNote(inp.id.slice(6)));
    inp.addEventListener('change', () => { const p = geoParse(inp.value); if (p) inp.value = `${p.lat}, ${p.lng}`; geoNote(inp.id.slice(6)); });
  });
  view.querySelectorAll('[data-geo-here]').forEach((b) => b.onclick = async () => {
    const k = b.dataset.geoHere, note = el('f-geo-' + k + '-note');
    note.classList.remove('bad'); note.textContent = 'Getting your location…';
    try {
      const p = await getLocation();
      el('f-geo-' + k).value = `${p.lat}, ${p.lng}`;
      geoNote(k); if (p.accuracy_m) note.textContent += ` (accuracy about ${p.accuracy_m} m)`;
    } catch (err) { note.textContent = err.message; note.classList.add('bad'); }
  });
  view.querySelectorAll('[data-geo-open]').forEach((b) => b.onclick = () => {
    const p = geoParse(el('f-geo-' + b.dataset.geoOpen).value);
    if (!p) { customAlert('Enter or capture a location first.'); return; }
    window.open(geoLink(p), '_blank', 'noopener');
  });
}

// ---- duplicates --------------------------------------------------------------------------------------------------------------------
function dupeBox(match) {
  const box = el('dupeActionBox');
  if (match.has_access) {
    box.innerHTML = `<p style="margin:0 0 8px; font-size:13px;">You already have access to this customer.</p><button type="button" class="btn btn-primary" style="padding:6px 12px; font-size:12px;" id="dupeView">View "${escapeHtml(match.name)}"</button>`;
    el('dupeView').onclick = () => navigate('customerview', match.id);
  } else if (match.access_request_pending) {
    box.innerHTML = '<p style="margin:0; font-size:13px;">You\'ve already requested access to this customer &mdash; waiting on a branch manager/admin to approve it.</p>';
  } else {
    box.innerHTML = `<p style="margin:0 0 8px; font-size:13px;">This customer already exists but isn't in your list yet. Request access to view it and log a call or visit.</p><button type="button" class="btn btn-primary" style="padding:6px 12px; font-size:12px;" id="dupeReq">Request access to "${escapeHtml(match.name)}"</button>`;
    el('dupeReq').onclick = async () => {
      try { await api.post('approvals/', { type: 'customer-access', customer_id: match.id }); }
      catch (e) { await customAlert(apiErrorMessage(e)); return; }
      await customAlert('Access request submitted. A branch manager or admin needs to approve it before this customer appears in your list.');
      match.access_request_pending = true; dupeBox(match);
    };
  }
  box.style.display = 'block';
}

function fill(c) {
  el('f-addedby').textContent = (c ? c.created_by_name : state.me.full_name) || '—';
  const v = (id, val) => { el(id).value = val || ''; };
  v('f-name', c && c.name); v('f-plant', c && c.plant); v('f-address', c && c.address); v('f-area', c && c.area); v('f-website', c && c.website); v('f-gst', c && c.gst_number);
  v('f-city', c && c.city); v('f-state', c && c.state); v('f-pincode', c && c.pincode);
  v('f-ho-name', c && c.ho_name); v('f-ho-address', c && c.ho_address); v('f-ho-city', c && c.ho_city); v('f-ho-state', c && c.ho_state); v('f-ho-pincode', c && c.ho_pincode); v('f-ho-phone', c && c.ho_phone);
  v('f-industry', c && c.industry); v('f-source', c && c.source); v('f-potential', c && c.potential); v('f-transport', c && c.transport_preference); v('f-courier', c && c.courier_preference);
  geoLoad(c);
  setLogo(c && c.logo_url ? c.logo_url : '');
  logoBlob = null;
  const tick = (cls, picked) => document.querySelectorAll('.' + cls).forEach((cb) => { cb.checked = picked.includes(cb.value); });
  tick('language-check', c ? c.preferred_languages : []); tick('brand-check', c ? c.interested_brands : []); tick('product-check', c ? c.interested_products : []);
  tick('assigned-check', c ? c.assigned_to.map((a) => String(a.id)) : []);
  msRefreshAll();
  el('contactRows').innerHTML = '';
  if (c && c.contacts.length) c.contacts.forEach(addContactRow); else addContactRow();
}

async function save() {
  const name = titleCaseWords(el('f-name').value.trim());
  const fail = (msg) => { el('err-name').textContent = msg; el('f-name').classList.add('field-err'); el('err-name').classList.add('show'); el('f-name').focus(); };
  if (!name) { fail('Enter a company name.'); return; }
  const plant = el('f-plant').value.trim();
  const nameChanged = !editing || (editing.name || '').trim().toLowerCase() !== name.toLowerCase() || normPlant(editing.plant) !== normPlant(plant);
  if (nameChanged) {
    let matches = [];
    try { matches = (await api.get(`customers/duplicate-check/?name=${encodeURIComponent(name)}${editing ? '&exclude=' + editing.id : ''}`)).matches; } catch (e) { /* the server re-checks nothing here; carry on */ }
    const basic = normalizeCompanyNameBasic(name);
    const exact = matches.find((m) => normalizeCompanyNameBasic(m.name) === basic && normPlant(m.plant) === normPlant(plant));
    if (exact) {
      fail(plant ? `"${exact.name}" with plant "${exact.plant}" already exists.` : `A customer named "${exact.name}" already exists. If this is another plant / unit, fill in the Plant / Unit field.`);
      dupeBox(exact); return;
    }
    el('f-name').classList.remove('field-err'); el('err-name').classList.remove('show');
    el('dupeActionBox').style.display = 'none'; el('dupeActionBox').innerHTML = '';
    const near = matches.filter((m) => normalizeCompanyNameBasic(m.name) !== basic);
    if (near.length) {
      const list = near.slice(0, 3).map((m) => `"${m.name}"`).join(', ');
      if (!await customConfirm(`This name looks very similar to existing customer(s): ${list}. Are you sure "${name}" is a different company, and not a duplicate?`)) return;
    }
  } else { el('f-name').classList.remove('field-err'); el('err-name').classList.remove('show'); }

  const geoBad = ['plant', 'ho'].some((k) => el('f-geo-' + k).value.trim() && !geoParse(el('f-geo-' + k).value));
  if (geoBad) { await customAlert('The map location isn’t valid. Enter it as "latitude, longitude" (e.g. 13.0827, 80.2707) or paste a Google Maps link.'); return; }

  const contacts = [];
  document.querySelectorAll('#contactRows .contact-form-row').forEach((row) => {
    const cname = titleCaseWords(row.querySelector('.ct-name').value.trim());
    const phone = row.querySelector('.ct-phone').value.trim(), phone2 = row.querySelector('.ct-phone2').value.trim(), email = row.querySelector('.ct-email').value.trim();
    if (!(cname || phone || phone2 || email)) return;
    contacts.push({ id: row.dataset.contactId ? Number(row.dataset.contactId) : undefined, name: cname, job_title: row.querySelector('.ct-desig').value, phone, phone2, email });
  });
  const picked = (cls) => [...document.querySelectorAll('.' + cls + ':checked')].map((cb) => cb.value);
  const body = {
    name, plant, address: titleCaseWords(el('f-address').value.trim()), area: el('f-area').value.trim(), website: el('f-website').value.trim(),
    gst_number: el('f-gst').value.trim().toUpperCase(), city: el('f-city').value.trim(), state: el('f-state').value, pincode: el('f-pincode').value.trim(),
    plant_geo: el('f-geo-plant').value.trim(), ho_geo: el('f-geo-ho').value.trim(),
    ho_name: el('f-ho-name').value.trim(), ho_address: titleCaseWords(el('f-ho-address').value.trim()), ho_city: el('f-ho-city').value.trim(), ho_state: el('f-ho-state').value,
    ho_pincode: el('f-ho-pincode').value.trim(), ho_phone: el('f-ho-phone').value.trim(),
    industry: el('f-industry').value, source: el('f-source').value, potential: el('f-potential').value,
    transport_preference: el('f-transport').value, courier_preference: el('f-courier').value,
    preferred_language_ids: idsOf('language', picked('language-check')), interested_brand_ids: idsOf('brand', picked('brand-check')), interested_product_ids: idsOf('product', picked('product-check')),
    contacts,
  };
  if (canAssign()) body.assigned_to_ids = picked('assigned-check').map(Number);
  let res;
  try { res = editing ? await api.patch(`customers/${editing.id}/`, { ...body, version: editing.version }) : await api.post('customers/', body); }
  catch (e) { await customAlert(apiErrorMessage(e)); return; }
  if (res && res.approval_requested) {
    await customAlert('Your changes were submitted for approval. A branch manager or admin needs to approve them before they apply.');
    leave(); return;
  }
  if (logoBlob !== null) {
    try {
      if (logoBlob === false) await api.delete(`customers/${res.id}/logo/`);
      else await api.upload(`customers/${res.id}/logo/`, new File([logoBlob], 'logo.' + (logoBlob.type === 'image/png' ? 'png' : 'jpg'), { type: logoBlob.type }));
    } catch (e) { await customAlert('The customer was saved, but the logo could not be uploaded: ' + apiErrorMessage(e)); }
  }
  leave();
}
function leave() { if (window.history.length > 1) window.history.back(); else navigate('customers'); }

export async function mountCustomerForm(root, id) {
  const view = mountRefView(root, 'view-customerform');
  editing = null;
  if (id && id !== 'new') {
    editing = (await api.get('customers/cards/')).results.find((c) => String(c.id) === String(id));
    if (!editing) { root.innerHTML = '<div class="empty">That customer is not available.</div>'; return; }
  }
  isRequest = !!editing && !canEditDirect();
  el('modalTitle').textContent = editing ? (isRequest ? 'Edit customer (needs approval)' : 'Edit customer') : 'Add customer';
  el('f-state').innerHTML = opts(INDIA_STATES, 'Select state').replace('<option value="">Select state</option>', '<option value="">Select state</option>');
  el('f-ho-state').innerHTML = opts(INDIA_STATES, 'Select state');
  el('f-industry').innerHTML = opts(names('industry'), 'Select industry');
  el('f-source').innerHTML = opts(names('source'), 'Select source');
  el('f-transport').innerHTML = opts(names('transport'), 'Select transport');
  el('f-courier').innerHTML = opts(names('courier'), 'Select courier');
  el('cityListOptions').innerHTML = INDIA_CITIES.map((c) => `<option value="${escapeHtml(c)}">`).join('');
  msBuild('f-languages', names('language').map((n) => ({ value: n, label: n })), 'language-check', 'Select languages');
  msBuild('f-assigned', state.employees.map((e) => ({ value: String(e.user_id), label: e.full_name, sub: ({ ADMIN: 'Admin', BRANCH_MANAGER: 'Branch Manager', BRANCH_STAFF: 'Branch Staff', SALES_MANAGER: 'Sales Manager' })[e.role] || e.role })), 'assigned-check', 'Select people');
  if (!canAssign()) el('f-assigned').style.cssText += ';opacity:.55;pointer-events:none;';
  msBuild('f-brands', names('brand').map((n) => ({ value: n, label: n })), 'brand-check', 'Select brands');
  msBuild('f-products', names('product').map((n) => ({ value: n, label: n })), 'product-check', 'Select products');
  fill(editing);
  wireGeo(view);
  el('f-name').addEventListener('input', () => { const box = el('dupeActionBox'); if (box.style.display !== 'none') { box.style.display = 'none'; box.innerHTML = ''; } });
  // Tidy Company name, Address and Contact name as soon as the user leaves the field (reference: focusout handler).
  view.addEventListener('focusout', (e) => {
    const t = e.target;
    if (t && t.matches && t.matches('#f-name, #f-address, .ct-name')) { const v = titleCaseWords(t.value); if (v !== t.value) t.value = v; }
  });
  el('addContactRowBtn').onclick = () => addContactRow();
  el('cancelBtn').onclick = leave;
  el('customerFormBackBtn').onclick = leave;
  el('saveBtn').onclick = save;
  el('f-name').focus();
}
