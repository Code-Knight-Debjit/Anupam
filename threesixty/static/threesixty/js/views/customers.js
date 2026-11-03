// Customer list — the reference's page: orange hero with the customer / contact counts and "+ Add customer", a search box
// and Filters panel, a sticky selection bar with the Actions menu, and one colour-coded card per customer (two columns)
// with its contacts. The page markup is the reference's own (js/ref_html.js); this file is the behaviour. The data comes
// from one call (`customers/cards/`) and is filtered in the browser exactly as the reference does, so the numbers,
// filters and selection behave the same. What each role may do is enforced by the server as well.
import { api } from '../api.js';
import { state, isAdmin, isBranchManager, isBranchStaff } from '../state.js';
import { navigate } from '../router.js';
import { el, escapeHtml, customAlert, customConfirm, apiErrorMessage, exportRowsToExcel, exportRowsToPdf, printRowsTable, downloadText, initials } from '../ui.js';
import {
  mountRefView, useOverlays, openOverlay, closeOverlay, waLink, webUrl, dotColorForTitle, initialsOf, companyLabel, geoLink, pinOf, fmtD,
  CALL_ICON_SVG, EMAIL_ICON_SVG, WHATSAPP_ICON_SVG, copyText, showManualCopy,
} from '../customer_common.js';

const FILTER_IDS = ['designationFilter', 'stateFilter', 'areaFilter', 'industryFilter', 'sourceFilter', 'potentialFilter', 'brandFilter', 'productFilter', 'assignedFilter', 'addedByFilter', 'languageFilter', 'lastCallFilter', 'lastVisitFilter'];
const canDirect = () => isAdmin() || isBranchManager();                  // reference: canDirectEditDelete()
const canDeleteDirect = () => isAdmin() || isBranchManager();

let cards = [];
let selectedIds = new Set();
let selectedContactIds = new Set();
const expandedContacts = new Set();

const names = (key) => (state.lookups[key] || []).map((x) => x.name);
const opts = (list, ph) => `<option value="">${ph}</option>` + list.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join('');

// ---- filtering (reference: matchesFilters) -----------------------------------------------------------------------------------
const daysSince = (d) => (d ? Math.floor((Date.now() - new Date(d).getTime()) / 86400000) : Infinity);
function matchesDays(date, value) {
  if (!value) return true;
  if (value === 'never') return !date;
  if (!date) return false;
  return value === '90plus' ? daysSince(date) > 90 : daysSince(date) <= Number(value);
}
function matches(c) {
  const v = (id) => el(id).value;
  const q = v('searchInput').trim().toLowerCase();
  if (v('stateFilter') && c.state !== v('stateFilter')) return false;
  if (v('areaFilter') && c.area !== v('areaFilter')) return false;
  if (v('industryFilter') && c.industry !== v('industryFilter')) return false;
  if (v('sourceFilter') && c.source !== v('sourceFilter')) return false;
  if (v('potentialFilter') && c.potential !== v('potentialFilter')) return false;
  if (v('brandFilter') && !c.interested_brands.includes(v('brandFilter'))) return false;
  if (v('productFilter') && !c.interested_products.includes(v('productFilter'))) return false;
  if (v('assignedFilter') && !c.assigned_to.some((a) => a.full_name === v('assignedFilter'))) return false;
  if (v('addedByFilter') && c.created_by_name !== v('addedByFilter')) return false;
  if (v('languageFilter') && !c.preferred_languages.includes(v('languageFilter'))) return false;
  if (v('lastCallFilter') && !matchesDays(c.last_call, v('lastCallFilter'))) return false;
  if (v('lastVisitFilter') && !matchesDays(c.last_visit, v('lastVisitFilter'))) return false;
  if (v('designationFilter') && !c.contacts.some((k) => k.job_title === v('designationFilter'))) return false;
  if (q) {
    const hay = [c.name, c.plant, c.address, c.area, c.city, c.state, c.pincode, c.industry, c.source, c.website, ...c.assigned_to.map((a) => a.full_name),
      ...c.interested_brands, ...c.interested_products, ...c.contacts.map((k) => k.name)].join(' ').toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}
const filtered = () => cards.filter(matches);

// ---- rendering ----------------------------------------------------------------------------------------------------------------
function renderStats() {
  const total = cards.reduce((s, c) => s + c.contacts.length, 0);
  el('statCompanies').textContent = cards.length;
  el('statContacts').textContent = total;
  el('subline').textContent = cards.length ? `Tracking ${cards.length} ${cards.length === 1 ? 'customer' : 'customers'} and ${total} ${total === 1 ? 'contact' : 'contacts'}.` : 'No customers yet. Add your first one to get started.';
}
function cardHtml(c) {
  const desig = el('designationFilter').value;
  const shown = c.contacts.filter((k) => !desig || k.job_title === desig);
  const contactsHtml = shown.length ? shown.map((ct) => {
    const wa = waLink(ct.phone);
    return `
      <div class="contact-row"${ct.dnd ? ' style="background:var(--danger-bg); border-radius:8px;"' : ''}>
        <input type="checkbox" class="contact-select-box" data-ctsel="${ct.id}" ${selectedContactIds.has(ct.id) ? 'checked' : ''} style="accent-color:var(--accent); width:15px; height:15px;">
        <div class="contact-left" style="text-align:left; cursor:pointer;" data-person="${c.id}/${ct.id}" title="View profile">
          <span class="desig-dot" style="background:${dotColorForTitle(ct.job_title)}"></span>
          <div style="text-align:left;">
            <div class="c-name" style="text-decoration:underline;${ct.dnd ? ' color:var(--danger);' : ''}">${escapeHtml(ct.name || 'Unnamed')}${ct.dnd ? ' <span title="Do Not Disturb" style="font-size:10px; font-weight:700;">(DND)</span>' : ''}</div>
            <div class="c-desig">${escapeHtml(ct.job_title || 'Other')}</div>
          </div>
        </div>
        <div class="c-meta">
          ${ct.phone ? `<button type="button" class="btn btn-call c-meta-icon-btn" data-phone="${escapeHtml(ct.phone)}" title="Call ${escapeHtml(ct.phone)}">${CALL_ICON_SVG}</button>` : ''}
          ${ct.phone2 ? `<button type="button" class="btn btn-call c-meta-icon-btn" data-phone="${escapeHtml(ct.phone2)}" title="Call ${escapeHtml(ct.phone2)}">${CALL_ICON_SVG}</button>` : ''}
          ${ct.email ? `<button type="button" class="btn btn-email c-meta-icon-btn copy-email" data-email="${escapeHtml(ct.email)}" title="Copy email: ${escapeHtml(ct.email)}">${EMAIL_ICON_SVG}</button>` : `<button type="button" class="btn btn-email-missing c-meta-icon-btn" title="No email on file">${EMAIL_ICON_SVG}</button>`}
          ${wa ? `<a class="btn btn-wa c-meta-icon-btn" href="${wa}" target="_blank" rel="noopener" title="WhatsApp">${WHATSAPP_ICON_SVG}</a>` : ''}
          <button class="btn btn-icon c-meta-btn" data-person="${c.id}/${ct.id}">View Profile</button>
          <button class="btn btn-icon c-meta-btn" data-contactedit="${c.id}/${ct.id}" title="Edit this contact">Edit</button>
        </div>
      </div>`;
  }).join('') : `<div class="no-contacts">${desig ? 'No contacts with this job title here.' : 'No contact persons added.'}</div>`;
  const collapsed = !expandedContacts.has(c.id);
  const potBg = { High: '#e6f4ea', Medium: '#fdf3d9', Low: '#fbe9e7' }[c.potential] || '';
  const potBorder = { High: '#a8d5b5', Medium: '#eed48f', Low: '#f0bcb5' }[c.potential] || '';
  const potCls = c.potential ? ' pot-' + String(c.potential).replace(/[^A-Za-z]/g, '') : '';
  return `
    <div class="card${potCls}" data-cid="${c.id}" title="Click to view details">
      <input type="checkbox" class="select-box" data-id="${c.id}" ${selectedIds.has(c.id) ? 'checked' : ''}>
      <div class="card-body">
        <div class="card-top">
          <div class="co-av${c.logo_url ? ' has-logo' : ''}">${c.logo_url ? `<img alt="" src="${c.logo_url}">` : escapeHtml(initialsOf(c.name || '?'))}</div>
          <div class="co-main">
            <p class="co-name">${escapeHtml(c.name)} ${c.plant ? `<span class="tag tag-accent">${escapeHtml(c.plant)}</span>` : ''} ${c.pending_approval ? '<span class="tag" style="color:var(--danger); border-color:#f0c4c0; background:var(--danger-bg);">Pending approval</span>' : ''} ${c.potential ? `<span class="tag" style="background:${potBg || 'var(--panel-2)'}; border-color:${potBorder || 'var(--line)'};">${escapeHtml(c.potential)}</span>` : ''}</p>
            <p class="co-addr">${escapeHtml(c.address || '')}</p>
            ${c.website ? `<p class="co-addr"><a href="${escapeHtml(webUrl(c.website))}" target="_blank" rel="noopener" style="color:var(--blue);">${escapeHtml(c.website)}</a></p>` : ''}
          </div>
          <div class="card-actions">
            <button class="btn btn-icon" data-view="${c.id}">View</button>
            <button class="btn btn-icon" data-edit="${c.id}">Edit</button>
            <button class="btn-danger-text" data-delete="${c.id}">Delete</button>
          </div>
        </div>
        <div class="contacts-toggle" data-fold="${c.id}"><span>Contacts (${c.contacts.length})</span><span class="contacts-toggle-arrow">${collapsed ? 'Show &#9662;' : 'Hide &#9652;'}</span></div>
        <div class="contacts" style="${collapsed ? 'display:none;' : ''}">${contactsHtml}</div>
      </div>
    </div>`;
}
function render() {
  renderStats();
  const list = filtered();
  selectedIds = new Set([...selectedIds].filter((id) => list.some((c) => c.id === id)));
  updateSelectCount();
  const box = el('listContainer');
  if (!cards.length) { box.innerHTML = '<div class="empty"><div class="big">Start your customer list</div>Add a customer and the people you deal with there.</div>'; selectedContactIds.clear(); updateContactBar(); return; }
  if (!list.length) { box.innerHTML = '<div class="empty">No customers match your search or filters.</div>'; selectedContactIds.clear(); updateContactBar(); return; }
  box.innerHTML = `<div class="card-list">${list.map(cardHtml).join('')}</div>`;
  const visibleContactIds = new Set(list.flatMap((c) => c.contacts.map((k) => k.id)));
  selectedContactIds = new Set([...selectedContactIds].filter((id) => visibleContactIds.has(id)));
  updateContactBar();
  wireCards(box);
}
function wireCards(box) {
  box.querySelectorAll('.select-box').forEach((b) => b.onchange = () => { const id = Number(b.dataset.id); if (b.checked) selectedIds.add(id); else selectedIds.delete(id); updateSelectCount(); updateContactBar(); });
  box.querySelectorAll('[data-ctsel]').forEach((b) => b.onchange = () => { const id = Number(b.dataset.ctsel); if (b.checked) selectedContactIds.add(id); else selectedContactIds.delete(id); updateContactBar(); });
  box.querySelectorAll('[data-fold]').forEach((b) => b.onclick = () => { const id = Number(b.dataset.fold); if (expandedContacts.has(id)) expandedContacts.delete(id); else expandedContacts.add(id); render(); });
  box.querySelectorAll('[data-view]').forEach((b) => b.onclick = () => navigate('customerview', b.dataset.view));
  box.querySelectorAll('[data-edit]').forEach((b) => b.onclick = () => navigate('customerform', b.dataset.edit));
  box.querySelectorAll('[data-delete]').forEach((b) => b.onclick = () => deleteCustomer(Number(b.dataset.delete)));
  box.querySelectorAll('[data-person]').forEach((b) => b.onclick = () => { const [c, p] = b.dataset.person.split('/'); navigate('person', c, p); });
  box.querySelectorAll('[data-contactedit]').forEach((b) => b.onclick = () => { const [c, p] = b.dataset.contactedit.split('/'); openContactEdit(Number(c), Number(p)); });
  box.querySelectorAll('[data-phone]').forEach((b) => b.onclick = () => window.showPhoneOptions(b.dataset.phone));
  box.querySelectorAll('.copy-email').forEach((b) => b.onclick = () => window.copyEmailToClipboard(b));
  box.querySelectorAll('.card[data-cid]').forEach((card) => card.addEventListener('click', (e) => {
    if (e.target.closest('button, a, input, select, label, textarea, .contacts, .contacts-toggle, .row-menu-wrap')) return;
    if (window.getSelection && String(window.getSelection()).length) return;
    navigate('customerview', card.dataset.cid);
  }));
}
function updateSelectCount() {
  el('selectCountText').innerHTML = selectedIds.size > 0 ? `<span class="export-count">${selectedIds.size} selected</span> &mdash; export buttons apply to your selection`
    : '0 selected &mdash; export buttons apply to selection, or all shown if nothing is selected';
  const list = filtered();
  el('selectAllBox').checked = list.length > 0 && list.every((c) => selectedIds.has(c.id));
}
function contactsSelected() {
  const flat = [];
  if (selectedContactIds.size) filtered().forEach((c) => c.contacts.forEach((k) => { if (selectedContactIds.has(k.id)) flat.push({ ...k, companyName: c.name }); }));
  else if (selectedIds.size) cards.filter((c) => selectedIds.has(c.id)).forEach((c) => c.contacts.forEach((k) => flat.push({ ...k, companyName: c.name })));
  return flat;
}
function updateContactBar() {
  const n = el('contactSelectCount'); if (!n) return;
  if (!selectedContactIds.size && !selectedIds.size) { n.textContent = ''; return; }
  if (selectedContactIds.size) n.textContent = `${selectedContactIds.size} contact${selectedContactIds.size === 1 ? '' : 's'} selected`;
  else { const k = contactsSelected().length; n.textContent = `${selectedIds.size} compan${selectedIds.size === 1 ? 'y' : 'ies'} selected (${k} contact${k === 1 ? '' : 's'})`; }
}
function updateFilterBadge() {
  const n = FILTER_IDS.filter((id) => el(id).value).length;
  const b = el('smartFilterBadge'); b.textContent = n; b.style.display = n ? '' : 'none';
}
function populateFilters() {
  const distinct = (key) => [...new Set(cards.map((c) => c[key]).filter(Boolean))].sort();
  const prevAdded = el('addedByFilter').value;
  el('designationFilter').innerHTML = opts(names('job_title'), 'All job titles');
  el('stateFilter').innerHTML = opts(distinct('state'), 'All states');
  el('areaFilter').innerHTML = opts(distinct('area'), 'All areas');
  el('industryFilter').innerHTML = opts(names('industry'), 'All industries');
  el('sourceFilter').innerHTML = opts(names('source'), 'All sources');
  el('brandFilter').innerHTML = opts(names('brand'), 'All brands');
  el('productFilter').innerHTML = opts(names('product'), 'All products');
  el('assignedFilter').innerHTML = opts(state.employees.map((e) => e.full_name), 'All assignees');
  el('addedByFilter').innerHTML = opts(distinct('created_by_name'), 'Added by: anyone');
  el('addedByFilter').value = prevAdded;
  el('languageFilter').innerHTML = opts(names('language'), 'All languages');
}

// ---- actions ---------------------------------------------------------------------------------------------------------------------
async function deleteCustomer(id) {
  const c = cards.find((x) => x.id === id); if (!c) return;
  if (!canDeleteDirect()) {
    if (!await customConfirm(`Submit a request to delete "${c.name}" for approval?`)) return;
    try { await api.delete(`customers/${id}/`); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    await customAlert('Delete request submitted. A branch manager or admin needs to approve it.');
    await reload(); return;
  }
  if (!await customConfirm('Delete this customer and all its contacts? This cannot be undone.')) return;
  try { await api.delete(`customers/${id}/`); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
  selectedIds.delete(id);
  await reload();
}
const flattenRows = (list) => {
  const rows = [];
  list.forEach((c) => {
    const base = {
      Company: c.name, Plant: c.plant || '', Address: c.address || '', Area: c.area || '', City: c.city || '', State: c.state || '', Pincode: c.pincode || '', Website: c.website || '', 'GST Number': c.gst_number || '',
      'Plant Location': geoLink(pinOf(c, 'plant')), 'Head Office Name': c.ho_name || '', 'Head Office Address': c.ho_address || '', 'Head Office City': c.ho_city || '', 'Head Office State': c.ho_state || '',
      'Head Office Pincode': c.ho_pincode || '', 'Head Office Phone': c.ho_phone || '', 'Head Office Location': geoLink(pinOf(c, 'ho')), Industry: c.industry || '', Source: c.source || '', Potential: c.potential || '',
      'Transport Preference': c.transport_preference || '', 'Courier Preference': c.courier_preference || '', 'Preferred Languages': c.preferred_languages.join(', '),
      'Assigned To': c.assigned_to.map((a) => a.full_name).join(', '), 'Interested Brands': c.interested_brands.join(', '), 'Interested Products': c.interested_products.join(', '),
    };
    if (c.contacts.length) c.contacts.forEach((ct) => rows.push({ ...base, 'Contact Name': ct.name || '', 'Job Title': ct.job_title || '', Phone: ct.phone || '', 'Phone 2': ct.phone2 || '', Email: ct.email || '' }));
    else rows.push({ ...base, 'Contact Name': '', 'Job Title': '', Phone: '', 'Phone 2': '', Email: '' });
  });
  return rows;
};
const exportList = () => (selectedIds.size ? cards.filter((c) => selectedIds.has(c.id)) : filtered());

function assignableStaff() {
  if (isAdmin()) return state.employees;
  const mine = state.me.branch_ids || [];
  return state.employees.filter((e) => e.user_id === state.me.user_id || (e.branch_ids || []).some((b) => mine.includes(b)));
}
async function openBulkAssign(mode) {
  if (!canDirect()) { await customAlert('Only an admin or branch manager can assign customers to sales staff.'); return; }
  if (!selectedIds.size) { await customAlert('Select at least one customer first (tick the checkboxes on the customer cards, or use "Select all shown").'); return; }
  const staff = assignableStaff();
  if (!staff.length) { await customAlert('No users yet — add them from the Users page first.'); return; }
  useOverlays('bulkAssignOverlay');
  el('bulkAssignStaff').innerHTML = staff.map((e) => `<option value="${e.user_id}">${escapeHtml(e.full_name)} (${escapeHtml(({ ADMIN: 'Admin', BRANCH_MANAGER: 'Branch Manager', BRANCH_STAFF: 'Branch Staff', SALES_MANAGER: 'Sales Manager' })[e.role] || e.role)})</option>`).join('');
  el('bulkAssignSub').textContent = `${selectedIds.size} customer${selectedIds.size === 1 ? '' : 's'} selected.`;
  const remove = mode === 'deassign';
  el('bulkAssignTitle').textContent = remove ? 'De-assign from sales staff' : 'Assign to sales staff';
  el('bulkAssignHint').textContent = remove ? 'De-assign takes just this person off the selected customers, leaving any other assignees in place.' : "Assign adds this person to the selected customers' assignees, leaving any other assignees in place.";
  el('bulkAssignApplyBtn').style.display = remove ? 'none' : '';
  el('bulkAssignRemoveBtn').style.display = remove ? '' : 'none';
  el('bulkAssignContactsBox').dataset.mode = mode;
  refreshContactBox();
  el('bulkAssignStaff').onchange = refreshContactBox;
  el('baAll').onchange = () => { if (el('baAll').checked) document.querySelectorAll('.ba-ct').forEach((cb) => { cb.checked = true; }); };
  el('baContacts').onchange = (e) => { if (e.target.classList.contains('ba-ct')) el('baAll').checked = [...document.querySelectorAll('.ba-ct')].every((cb) => cb.checked); };
  el('bulkAssignCancelBtn').onclick = () => closeOverlay('bulkAssignOverlay');
  el('bulkAssignApplyBtn').onclick = () => applyBulkAssign(false);
  el('bulkAssignRemoveBtn').onclick = () => applyBulkAssign(true);
  openOverlay('bulkAssignOverlay');
}
function refreshContactBox() {
  const box = el('bulkAssignContactsBox');
  const one = selectedIds.size === 1 ? cards.find((c) => c.id === [...selectedIds][0]) : null;
  if (!one || !one.contacts.length || box.dataset.mode === 'deassign') { box.style.display = 'none'; return; }
  el('baAll').checked = true;
  el('baContacts').innerHTML = one.contacts.map((ct) => `<label style="display:flex;align-items:center;gap:8px;margin:0;"><input type="checkbox" class="ba-ct" value="${ct.id}" checked> ${escapeHtml(ct.name || 'Unnamed')}${ct.job_title ? ' — ' + escapeHtml(ct.job_title) : ''}</label>`).join('');
  box.style.display = '';
}
async function applyBulkAssign(remove) {
  const userId = Number(el('bulkAssignStaff').value); if (!userId) return;
  const staff = (state.employees.find((e) => e.user_id === userId) || {}).full_name || '';
  const ids = [...selectedIds];
  const single = ids.length === 1;
  const picked = [...document.querySelectorAll('.ba-ct:checked')].map((cb) => Number(cb.value));
  const boxShown = el('bulkAssignContactsBox').style.display !== 'none';
  if (!remove && single && boxShown && !picked.length) { await customAlert('Tick at least one contact to share, or tick "All contacts".'); return; }
  let changed = 0, sharedMsg = '';
  try {
    for (const id of ids) {
      const c = cards.find((x) => x.id === id); if (!c) continue;
      const has = c.assigned_to.some((a) => a.id === userId);
      if (remove) { if (has) { await api.delete(`customers/${id}/assign/?user_id=${userId}`); changed++; } continue; }
      const partial = single && boxShown && picked.length < c.contacts.length;
      if (!has || (single && boxShown)) {
        await api.post(`customers/${id}/assign/`, { user_id: userId, contact_ids: partial ? picked : null });
        if (!has) changed++;
        if (partial) { sharedMsg = ` Only ${picked.length} of ${c.contacts.length} contacts are shared with ${staff}.`; changed = Math.max(changed, 1); }
      }
    }
  } catch (e) { await customAlert(apiErrorMessage(e)); return; }
  closeOverlay('bulkAssignOverlay');
  await reload();
  await customAlert(remove ? `Removed ${staff} from ${changed} customer${changed === 1 ? '' : 's'}.` : `Assigned ${staff} to ${changed} customer${changed === 1 ? '' : 's'} (already assigned ones were left as-is).` + sharedMsg);
}
async function openCallAssign() {
  if (!canDirect()) { await customAlert('Only an admin or branch manager can assign an outreach list.'); return; }
  if (!selectedIds.size) { await customAlert('Select at least one customer first (tick the checkboxes on the customer cards, or use "Select all shown").'); return; }
  const staff = assignableStaff();
  if (!staff.length) { await customAlert('No users yet — add them from the Users page first.'); return; }
  useOverlays('callAssignOverlay');
  const role = (r) => ({ ADMIN: 'Admin', BRANCH_MANAGER: 'Branch Manager', BRANCH_STAFF: 'Branch Staff', SALES_MANAGER: 'Sales Manager' })[r] || r;
  el('callAssignStaff').innerHTML = staff.map((e) => `<option value="${e.user_id}">${escapeHtml(e.full_name)} (${escapeHtml(role(e.role))})</option>`).join('');
  el('callAssignSub').textContent = `${selectedIds.size} customer${selectedIds.size === 1 ? '' : 's'} selected.`;
  const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  el('callAssignWeek').value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  el('callAssignCancelBtn').onclick = () => closeOverlay('callAssignOverlay');
  el('callAssignApplyBtn').onclick = async () => {
    const userId = Number(el('callAssignStaff').value);
    const week = el('callAssignWeek').value;
    if (!week) { await customAlert('Pick a week start date.'); return; }
    let res;
    try { res = await api.post('call-assignments/assign/', { customer_ids: [...selectedIds], assigned_to_id: userId, week_of: week }); }
    catch (e) { await customAlert(apiErrorMessage(e)); return; }
    closeOverlay('callAssignOverlay');
    const who = (state.employees.find((e) => e.user_id === userId) || {}).full_name || '';
    await customAlert(`Added ${res.added} contact${res.added === 1 ? '' : 's'} to ${who}'s outreach list for the week of ${fmtD(res.week_of)}.${res.dnd_skipped ? ` ${res.dnd_skipped} Do Not Disturb contact${res.dnd_skipped === 1 ? ' was' : 's were'} left out.` : ''}${res.skipped ? ` (${res.skipped} already on that list, left as-is.)` : ''}`);
  };
  openOverlay('callAssignOverlay');
}

// ---- contact edit (without opening the whole customer) -------------------------------------------------------------------------------
export function openContactEdit(customerId, contactId, onSaved) {
  const c = cards.find((x) => x.id === customerId) || window.__cardCustomer;
  const ct = c && c.contacts.find((k) => k.id === contactId); if (!ct) return;
  useOverlays('contactEditOverlay');
  el('ceSub').textContent = c.name || '';
  el('ce-name').value = ct.name || ''; el('ce-title').value = ct.job_title || ''; el('ce-phone').value = ct.phone || ''; el('ce-phone2').value = ct.phone2 || ''; el('ce-email').value = ct.email || '';
  el('ce-title-list').innerHTML = names('job_title').map((n) => `<option value="${escapeHtml(n)}">`).join('');
  el('ceHint').textContent = '';
  el('ceCancelBtn').onclick = () => closeOverlay('contactEditOverlay');
  el('ceSaveBtn').onclick = async () => {
    const name = el('ce-name').value.trim();
    if (!name) { el('ceHint').textContent = 'Enter the contact name.'; return; }
    try {
      const res = await api.patch(`contacts/${contactId}/`, { name, job_title: el('ce-title').value.trim(), phone: el('ce-phone').value.trim(), phone2: el('ce-phone2').value.trim(), email: el('ce-email').value.trim() });
      closeOverlay('contactEditOverlay');
      if (res && res.approval_requested) await customAlert('Your changes were submitted for approval. A branch manager or admin needs to approve them before they apply.');
    } catch (e) { el('ceHint').textContent = apiErrorMessage(e); return; }
    if (onSaved) await onSaved(); else await reload();
  };
  openOverlay('contactEditOverlay');
}

async function reload() {
  cards = (await api.get('customers/cards/')).results;
  if (el('listContainer')) { populateFilters(); render(); updateFilterBadge(); }
}

export async function mountCustomers(root) {
  mountRefView(root, 'view-customers');
  // role-based Actions menu (reference: showApp)
  if (!canDirect()) ['exportExcelBtn', 'exportPdfBtn', 'bulkAssignBtn', 'bulkDeassignBtn', 'bulkAssignCallBtn', 'exportGoogleContactsBtn'].forEach((id) => { el(id).style.display = 'none'; });
  else ['exportExcelBtn', 'exportPdfBtn', 'bulkAssignBtn', 'bulkDeassignBtn', 'bulkAssignCallBtn'].forEach((id) => { el(id).style.display = ''; });
  el('openAddBtn').onclick = () => navigate('customerform', 'new');
  el('searchInput').addEventListener('input', render);
  FILTER_IDS.forEach((id) => el(id).addEventListener('change', () => { render(); updateFilterBadge(); }));
  el('smartFilterToggleBtn').onclick = () => { const p = el('smartFilterPanel'); p.style.display = p.style.display === 'none' ? 'flex' : 'none'; };
  el('smartFilterClearBtn').onclick = () => { FILTER_IDS.forEach((id) => { el(id).value = ''; }); updateFilterBadge(); render(); };
  el('selectAllBox').onchange = (e) => { const list = filtered(); list.forEach((c) => { if (e.target.checked) selectedIds.add(c.id); else selectedIds.delete(c.id); }); render(); };
  el('clearContactSelectionBtn').onclick = () => { selectedContactIds.clear(); selectedIds.clear(); render(); };
  el('exportExcelBtn').onclick = () => { const l = exportList(); if (!l.length) { customAlert('Nothing to export.'); return; } exportRowsToExcel(flattenRows(l), 'anupam360-contacts', 'Contacts'); };
  el('exportPdfBtn').onclick = () => { const l = exportList(); if (!l.length) { customAlert('Nothing to export.'); return; } exportRowsToPdf(flattenRows(l), 'Anupam 360 — Customer Export', 'anupam360-contacts', ['Company', 'Area', 'City', 'State', 'Industry', 'Source', 'Assigned To', 'Contact Name', 'Job Title', 'Phone', 'Phone 2', 'Email']); };
  el('printListBtn').onclick = () => { const l = exportList(); if (!l.length) { customAlert('Nothing to print.'); return; } printRowsTable(flattenRows(l), 'Anupam 360 — Customer List'); };
  el('bulkAssignBtn').onclick = () => openBulkAssign('assign');
  el('bulkDeassignBtn').onclick = () => openBulkAssign('deassign');
  el('bulkAssignCallBtn').onclick = openCallAssign;
  el('sendBulkEmailBtn').onclick = async () => {
    const list = contactsSelected().filter((ct) => ct.email);
    if (!list.length) { await customAlert('None of the selected contacts have an email address.'); return; }
    const emails = [...new Set(list.map((ct) => ct.email))];
    try { await copyText(emails.join(', ')); await customAlert(`Copied ${emails.length} email address${emails.length === 1 ? '' : 'es'} to your clipboard. Paste them into the To or BCC field of your email.`); }
    catch (e) { showManualCopy(emails.join(', ')); }
  };
  el('exportGoogleContactsBtn').onclick = async () => {
    const list = contactsSelected();
    if (!list.length) { await customAlert('Select at least one contact first.'); return; }
    const vcards = list.map((ct) => ['BEGIN:VCARD', 'VERSION:3.0', `FN:${ct.name || 'Unnamed'}`, ct.companyName ? `ORG:${ct.companyName}` : '', ct.job_title ? `TITLE:${ct.job_title}` : '', ct.phone ? `TEL;TYPE=CELL:${ct.phone}` : '', ct.email ? `EMAIL:${ct.email}` : '', 'END:VCARD'].filter(Boolean).join('\n')).join('\n');
    downloadText(vcards, `anupam360-contacts-${Date.now()}.vcf`, 'text/vcard');
    await customAlert('Downloaded a .vcf file. Import it at contacts.google.com → Import to add these to Gmail Contacts.');
  };
  await reload();
}
