// Person profile — the reference's contact page: the contact card, Date-of-Interaction tiles, the "Log a new interaction"
// form (follow-up date, visit location, joint visit, also met, regarding a document), the interaction history in three
// columns, and the contact's sales documents. The rules (the follow-up task, joint-visit tasks, appointment closing when
// a visit is logged, copies for the people also met) are applied by the server when the interaction is saved.
import { api } from '../api.js';
import { state } from '../state.js';
import { navigate } from '../router.js';
import { el, escapeHtml, fmtMoney, customAlert, apiErrorMessage } from '../ui.js';
import { mountRefView, titleCaseWords, initialsOf, waLink, companyLabel, msBuild, msRefresh, geoDist, geoFmtDist, pinOf, fmtD } from '../customer_common.js';
import { openContactEdit } from './customers.js';

const FOLLOWUP_TYPES = ['Call', 'Visit', 'Appointment'];
const FOLLOWUP_LABEL = { Call: 'Call date', Visit: 'Appointment date', Appointment: 'Appointment date' };
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

let customer = null, contact = null, profile = null;
let followupActive = false, captured = null, docsShowAll = false;

function renderCard() {
  const ct = contact, wa = waLink(ct.phone);
  el('ppName').textContent = ct.name || 'Unnamed';
  el('ppAv').textContent = initialsOf(ct.name || '?');
  el('ppName').style.color = ct.dnd ? 'var(--danger)' : '';
  el('ppSub').textContent = `${ct.job_title || 'Contact'} at ${customer.name || '—'}`;
  el('ppTitle').textContent = ct.job_title || '—';
  el('ppCompany').innerHTML = `<span class="link-btn" style="text-decoration:underline; cursor:pointer; font-size:inherit; font-weight:inherit; color:var(--accent);" id="ppCompanyLink">${escapeHtml(companyLabel(customer))}</span>`;
  el('ppCompanyLink').onclick = () => navigate('customerview', customer.id);
  el('ppPhone').innerHTML = ct.phone ? `<a href="tel:${escapeHtml(ct.phone)}">${escapeHtml(ct.phone)}</a>` : '—';
  el('ppPhone2').innerHTML = ct.phone2 ? `<a href="tel:${escapeHtml(ct.phone2)}">${escapeHtml(ct.phone2)}</a>` : '—';
  const waBtn = wa ? `<div style="margin-top:8px;"><a class="btn btn-wa" style="padding:3px 9px; font-size:11.5px;" href="${wa}" target="_blank" rel="noopener">WhatsApp</a></div>` : '';
  el('ppEmail').innerHTML = ct.email ? `<span class="copy-email" data-email="${escapeHtml(ct.email)}" title="Click to copy">${escapeHtml(ct.email)}</span>${waBtn}` : (wa ? waBtn : '—');
  const em = el('ppEmail').querySelector('.copy-email'); if (em) em.onclick = () => window.copyEmailToClipboard(em);
  const dnd = el('ppDndBtn');
  dnd.textContent = ct.dnd ? 'Do Not Disturb: ON' : 'Do Not Disturb';
  dnd.classList.toggle('danger', !!ct.dnd);
  dnd.style.background = ct.dnd ? 'var(--danger)' : ''; dnd.style.color = ct.dnd ? '#fff' : ''; dnd.style.borderColor = ct.dnd ? 'var(--danger)' : '';
  el('ppCard').style.borderColor = ct.dnd ? 'var(--danger)' : 'var(--line)';
}
function renderSummary() {
  const last = (types) => profile.history.filter((h) => types.includes(h.type)).map((h) => h.date).sort().pop();
  const fmt = (d) => (d ? fmtD(d) : '—');
  el('doiLastCall').textContent = fmt(last(['Call', 'Cold Call']));
  el('doiLastEmail').textContent = fmt(last(['Email']));
  el('doiLastVisit').textContent = fmt(last(['Visit']));
}
function renderDocSelect() {
  el('doi-doc').innerHTML = '<option value="">— Not linked to a document —</option>' + profile.linkable.map((d) => `<option value="${d.id}">${escapeHtml(d.label)} ${escapeHtml(d.number || '')} · ${d.date ? fmtD(d.date) : '—'}${d.value ? ' · ₹' + fmtMoney(d.value) : ''}</option>`).join('');
  el('doi-doc').value = '';
}
function renderHistory() {
  const wrap = el('doiHistoryWrap');
  const list = profile.history;
  if (!list.length) { wrap.innerHTML = '<p class="sub">No interactions logged yet.</p>'; return; }
  const item = (i) => `
    <div class="activity-item"><div>
      <div class="a-name">${escapeHtml(i.type)}${i.notes ? ` — ${escapeHtml(i.notes)}` : ''}</div>
      ${i.also_met && i.also_met.length ? `<div class="a-meta">Also met: ${i.also_met.map((o) => escapeHtml(o.name)).join(', ')}</div>` : ''}
      ${i.joint_with && i.joint_with.length ? `<div class="a-meta">Joint ${escapeHtml(i.type.toLowerCase())} with: ${i.joint_with.map((o) => escapeHtml(o.name)).join(', ')}</div>` : ''}
      ${i.doc ? `<div class="a-meta">🔗 Regarding ${escapeHtml(i.doc.label)} ${escapeHtml(i.doc.number || '')}</div>` : ''}
      ${i.via ? `<div class="a-meta">Source: ${escapeHtml(i.via)}${i.followup_date ? ' · next call ' + fmtD(i.followup_date) : ''}</div>` : ''}
      ${i.is_copy ? `<div class="a-meta">Met along with ${escapeHtml(i.met_with_name || '—')}</div>` : ''}
      <div class="a-meta">${i.date ? fmtD(i.date) : '—'} &middot; Logged by ${escapeHtml(i.user_name || '—')}${i.location ? ` &middot; <a href="https://www.google.com/maps?q=${i.location.lat},${i.location.lng}" target="_blank" rel="noopener">Location</a>${i.distance ? ' (' + escapeHtml(i.distance) + ')' : ''}` : ''}</div>
    </div></div>`;
  const bucket = (i) => (i.type === 'Visit' ? 'Visit' : i.type === 'Appointment' ? 'Appointment' : 'Call');
  wrap.innerHTML = '<div class="doi-hist-grid">' + [['Visits', 'Visit'], ['Appointments', 'Appointment'], ['Calls', 'Call']].map(([title, key]) => {
    const rows = list.filter((i) => bucket(i) === key);
    return `<div class="doi-hist-col"><div class="doi-hist-head">${title} <span>${rows.length}</span></div><div class="doi-hist-body">${rows.length ? rows.map(item).join('') : '<p class="sub" style="margin:8px 4px;">None yet.</p>'}</div></div>`;
  }).join('') + '</div>';
}
function renderDocs() {
  const docs = profile.documents, shown = docsShowAll ? docs : docs.slice(0, 5);
  el('ppDocsTable').innerHTML = shown.length ? `<tr><th>Type</th><th>Doc No.</th><th>Date</th><th>Status</th><th>Value</th></tr>${shown.map((d) => `<tr><td>${escapeHtml(d.label)}</td><td>${escapeHtml(d.number || '—')}</td><td>${d.date ? fmtD(d.date) : '—'}</td><td>${escapeHtml(d.status || '—')}</td><td>₹${fmtMoney(d.value)}</td></tr>`).join('')}` : '<tr><td>No sales documents raised for this contact yet.</td></tr>';
  const more = el('ppDocsMoreBtn');
  if (docs.length > 5 && !docsShowAll) { more.style.display = 'inline-flex'; more.textContent = `More (${docs.length - 5})`; } else more.style.display = 'none';
}

// ---- the interaction form --------------------------------------------------------------------------------------------------------
function syncFollowupUi() {
  const type = el('doi-type').value, label = FOLLOWUP_LABEL[type] || 'Date';
  el('doi-followup-btn').textContent = label;
  el('doi-followup-label').innerHTML = followupActive ? escapeHtml(label) : '&nbsp;';
  el('doi-followup-btn').style.display = followupActive ? 'none' : '';
  el('doi-followup-date-wrap').style.display = followupActive ? 'flex' : 'none';
  el('doi-followup-date').setAttribute('aria-label', label);
}
function updateVisibility() {
  const type = el('doi-type').value;
  const applies = FOLLOWUP_TYPES.includes(type);
  el('doi-followup-wrap').style.display = applies ? '' : 'none';
  if (!applies) { followupActive = false; el('doi-followup-date').value = ''; }
  syncFollowupUi();
  const loc = type === 'Visit';
  el('doi-location-wrap').style.display = loc ? '' : 'none';
  if (!loc) resetLocation();
  renderJoint(); renderAlsoMet();
}
function resetLocation() { captured = null; el('doi-location-status').textContent = 'Not captured yet.'; el('doi-location-status').style.color = 'var(--text-dim)'; }
function renderJoint() {
  const wrap = el('doi-joint-wrap'), list = el('doi-joint-list');
  const keep = new Set([...document.querySelectorAll('.doi-joint-cb:checked')].map((cb) => cb.value));
  const type = el('doi-type').value;
  const others = state.employees.filter((e) => e.user_id !== state.me.user_id);
  if (!(type === 'Visit' || type === 'Appointment') || !others.length) { wrap.style.display = 'none'; return; }
  wrap.style.display = '';
  msBuild('doi-joint-list', others.map((o) => ({ value: String(o.user_id), label: o.full_name || 'User', sub: ({ ADMIN: 'Admin', BRANCH_MANAGER: 'Branch Manager', BRANCH_STAFF: 'Branch Staff', SALES_MANAGER: 'Sales Manager' })[o.role] || '' })), 'doi-joint-cb', 'Select team members');
  list.querySelectorAll('.doi-joint-cb').forEach((cb) => { cb.checked = keep.has(cb.value); });
  msRefresh(list);
}
function renderAlsoMet(extraId) {
  const wrap = el('doi-alsomet-wrap'), list = el('doi-alsomet-list');
  const keep = new Set([...document.querySelectorAll('.doi-alsomet-cb:checked')].map((cb) => cb.value));
  if (extraId) keep.add(String(extraId));
  const others = customer.contacts.filter((c) => c.id !== contact.id);
  if (el('doi-type').value !== 'Visit') { wrap.style.display = 'none'; return; }
  wrap.style.display = '';
  msBuild('doi-alsomet-list', others.map((o) => ({ value: String(o.id), label: o.name || 'Contact', sub: o.job_title || '' })), 'doi-alsomet-cb', 'Select people also met');
  list.querySelectorAll('.doi-alsomet-cb').forEach((cb) => { cb.checked = keep.has(cb.value); });
  msRefresh(list);
}
function captureLocation() {
  const st = el('doi-location-status');
  if (!navigator.geolocation) { st.textContent = 'Location isn’t supported on this device/browser.'; st.style.color = 'var(--danger)'; return; }
  st.textContent = 'Capturing your location…'; st.style.color = 'var(--text-dim)';
  navigator.geolocation.getCurrentPosition((pos) => {
    captured = { lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy };
    st.innerHTML = `Captured (&plusmn;${Math.round(pos.coords.accuracy)}m) &middot; <a href="https://www.google.com/maps?q=${pos.coords.latitude},${pos.coords.longitude}" target="_blank" rel="noopener">View on map</a>`;
    st.style.color = 'var(--green)';
    showDistance();
  }, (err) => { captured = null; st.textContent = err.code === 1 ? 'Location permission denied.' : 'Could not get location. Try again.'; st.style.color = 'var(--danger)'; }, { enableHighAccuracy: true, timeout: 15000 });
}
function showDistance() {
  if (!captured) return;
  const pins = [['Plant', pinOf(customer, 'plant')], ['Head office', pinOf(customer, 'ho')]].filter((x) => x[1]);
  const st = el('doi-location-status');
  if (!pins.length) {
    st.innerHTML += ' &middot; <em>No pin saved for this customer.</em> <a href="#" id="doi-pin-here">Save this spot as the plant pin</a>';
    el('doi-pin-here').onclick = async (ev) => {
      ev.preventDefault();
      try { await api.patch(`customers/${customer.id}/`, { plant_geo: `${captured.lat}, ${captured.lng}`, version: customer.version }); st.innerHTML += ' &middot; <b style="color:var(--green);">Plant pin saved.</b>'; }
      catch (e) { await customAlert(apiErrorMessage(e)); }
    };
    return;
  }
  const best = pins.map(([n, g]) => [n, geoDist(captured, g)]).sort((a, b) => a[1] - b[1])[0];
  const far = best[1] > 500;
  st.innerHTML += ` &middot; <b style="color:${far ? 'var(--danger)' : 'var(--green)'};">${geoFmtDist(best[1])} from ${best[0]} pin${far ? ' — are you at the right place?' : ''}</b>`;
}
async function saveInteraction() {
  const type = el('doi-type').value;
  const date = el('doi-date').value || today();
  const wantsFollowup = FOLLOWUP_TYPES.includes(type) && followupActive;
  const followupDate = el('doi-followup-date').value;
  if (wantsFollowup && !followupDate) { await customAlert('Pick the date the customer asked for.'); return; }
  if (type === 'Appointment' && !wantsFollowup) { await customAlert('Click the orange "Appointment date" button and pick the date — the appointment is added to Tasks using that date.'); return; }
  const alsoMet = type === 'Visit' ? [...document.querySelectorAll('.doi-alsomet-cb:checked')].map((cb) => Number(cb.value)) : [];
  const joint = (type === 'Visit' || type === 'Appointment') ? [...document.querySelectorAll('.doi-joint-cb:checked')].map((cb) => Number(cb.value)) : [];
  const body = { type, date, notes: el('doi-notes').value.trim(), followup_date: wantsFollowup ? followupDate : null, also_met_contact_ids: alsoMet, joint_with_user_ids: joint,
    linked_doc_id: el('doi-doc').value || null };
  if (type === 'Visit' && captured) { body.location_lat = captured.lat; body.location_lng = captured.lng; body.location_accuracy_m = Math.round(captured.accuracy || 0); }
  try { await api.post(`contacts/${contact.id}/interactions/`, body); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
  const jointNames = joint.map((id) => (state.employees.find((e) => e.user_id === id) || {}).full_name).filter(Boolean);
  const msg = (wantsFollowup ? `${type} logged${alsoMet.length ? ' for ' + (alsoMet.length + 1) + ' people' : ''}${jointNames.length ? ', a task was added for ' + jointNames.join(', ') : ''} and a follow-up task was added to Task Manager.`
    : `${type} logged${alsoMet.length ? ' for ' + (alsoMet.length + 1) + ' people' : ''}${jointNames.length ? ' and a task was added for ' + jointNames.join(', ') : ''}.`);
  el('doi-notes').value = ''; el('doi-doc').value = ''; followupActive = false; el('doi-followup-date').value = '';
  resetLocation();
  await load();
  updateVisibility();
  await customAlert(msg);
}

async function load() {
  const cards = (await api.get('customers/cards/')).results;
  customer = cards.find((c) => String(c.id) === String(customer ? customer.id : window.__ppCustomerId));
  contact = customer && customer.contacts.find((k) => String(k.id) === String(window.__ppContactId));
  if (!contact) return false;
  window.__cardCustomer = customer;
  profile = await api.get(`contacts/${contact.id}/profile/`);
  renderCard(); renderSummary(); renderDocSelect(); renderHistory(); docsShowAll = false; renderDocs();
  return true;
}

export async function mountPersonProfile(root, customerId, rest) {
  const contactId = rest && rest[0];
  window.__ppCustomerId = customerId; window.__ppContactId = contactId; customer = null;
  mountRefView(root, 'view-personprofile');
  if (!await load()) { root.innerHTML = '<div class="empty">That contact is not available.</div>'; return; }
  el('doi-type').value = 'Call'; el('doi-date').value = today(); el('doi-notes').value = '';
  followupActive = false; resetLocation(); updateVisibility();
  el('doi-type').addEventListener('change', updateVisibility);
  el('doi-followup-btn').onclick = () => { followupActive = true; syncFollowupUi(); el('doi-followup-date').focus(); };
  el('doi-followup-clear').onclick = () => { followupActive = false; el('doi-followup-date').value = ''; syncFollowupUi(); };
  el('doi-capture-location-btn').onclick = captureLocation;
  el('doi-addperson-btn').onclick = () => {
    el('doi-np-desig').innerHTML = '<option value="">Designation</option>' + (state.lookups.job_title || []).map((j) => `<option value="${escapeHtml(j.name)}">${escapeHtml(j.name)}</option>`).join('');
    el('doi-addperson-form').style.display = ''; el('doi-np-name').focus();
  };
  const closeAdd = () => { el('doi-addperson-form').style.display = 'none'; ['doi-np-name', 'doi-np-phone', 'doi-np-email'].forEach((id) => { el(id).value = ''; }); };
  el('doi-np-cancel').onclick = closeAdd;
  el('doi-np-save').onclick = async () => {
    const name = titleCaseWords(el('doi-np-name').value.trim());
    if (!name) { await customAlert('Enter the person\'s name.'); return; }
    let person;
    try { person = await api.post(`customers/${customer.id}/contacts/`, { name, job_title: el('doi-np-desig').value, phone: el('doi-np-phone').value.trim(), email: el('doi-np-email').value.trim() }); }
    catch (e) { await customAlert(apiErrorMessage(e)); return; }
    customer.contacts.push(person);
    closeAdd(); renderAlsoMet(person.id);
  };
  el('doiSaveBtn').onclick = saveInteraction;
  el('ppDocsMoreBtn').onclick = () => { docsShowAll = true; renderDocs(); };
  el('ppEditBtn').onclick = () => openContactEdit(customer.id, contact.id, load);
  el('ppDndBtn').onclick = async () => {
    try { const r = await api.patch(`contacts/${contact.id}/`, { dnd: !contact.dnd }); if (r && r.approval_requested) await customAlert('Your changes were submitted for approval. A branch manager or admin needs to approve them before they apply.'); }
    catch (e) { await customAlert(apiErrorMessage(e)); return; }
    await load();
  };
  el('personProfileBackBtn').onclick = () => { if (window.history.length > 1) window.history.back(); else navigate('customerview', customer.id); };
}
