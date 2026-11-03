// Manage Lists — the reference's page: a column of lists on the left, the chosen list on the right (each entry with Rename /
// Remove, an "Add a new …" row underneath). Sales Persons carry a phone; Transport and Courier carry contact details and
// have a small form instead of the one-line add row. Only an Admin may change a list; removing an entry that records
// already use hides it from the lists and leaves those records alone.
import { api } from '../api.js';
import { state } from '../state.js';
import { el, escapeHtml, customAlert, customConfirm, customPrompt, apiErrorMessage } from '../ui.js';
import { mountRefView } from '../customer_common.js';

// tab -> [server kind, what one entry is called]
const TABS = {
  jobTitles: ['job_title', 'job title'], sources: ['source', 'source'], industries: ['industry', 'industry'], brands: ['brand', 'brand'], products: ['product', 'product'],
  categories: ['category', 'category'], units: ['unit', 'unit'], taxRates: ['tax_rate', 'tax rate'], paymentTerms: ['payment_term', 'payment term'], languages: ['language', 'language'],
  transport: ['transport', 'transporter'], courier: ['courier', 'courier'],
};
let tab = 'jobTitles';
let editingId = null;

async function refreshState(kind) {
  if (kind === 'sales_person') { state.salesPersons = await api.all('sales-persons/'); return; }
  state.lookups[kind] = (await api.all('lookups/', { kind })).filter((x) => x.is_active);
}
const items = (kind) => (state.lookups[kind] || []).slice().sort((a, b) => (a.sort_order - b.sort_order) || a.name.localeCompare(b.name));

function listHtml(rows, label, render) {
  if (!rows.length) return `<p class="modal-sub">No ${label}s yet.</p>`;
  return rows.map(render).join('');
}
const actions = (id, rename, extra = '') => `<span class="mi-actions">${extra}<button data-act="rename" data-id="${id}">${rename}</button><button class="danger" data-act="remove" data-id="${id}">Remove</button></span>`;

/** The tax % new document lines start with: the Admin's choice, else 18, else the first rate (same fallback the sales form uses). */
export function defaultTaxRate() {
  const names = items('tax_rate').map((x) => x.name);
  const chosen = String(((state.siteSettings || {}).defaultTaxRate || {}).rate || '');
  return names.includes(chosen) ? chosen : (names.includes('18') ? '18' : (names[0] || '0'));
}

function drawSimple(kind, label) {
  const isTax = kind === 'tax_rate', def = isTax ? defaultTaxRate() : '';
  el('manageBody').innerHTML = `
    ${isTax ? '<p class="modal-sub" style="margin-bottom:10px;">The <b>default</b> rate is what a new line on a Quotation or Proforma Invoice starts with. Click "Make default" to change it.</p>' : ''}
    <div class="manage-list" id="genericList">${listHtml(items(kind), label, (it) => `<div class="manage-item"><span class="mi-name">${escapeHtml(it.name)}${isTax && it.name === def ? ' <span class="tag" style="margin-left:6px;">Default</span>' : ''}</span>${actions(it.id, 'Rename', isTax && it.name !== def ? `<button data-act="default" data-id="${it.id}">Make default</button>` : '')}</div>`)}</div>
    <div class="manage-add-row"><input type="text" id="newItemInput" placeholder="Add a new ${label}&hellip;"><button class="btn" id="addItemBtn">Add</button></div>`;
  const redraw = async () => { await refreshState(kind); drawSimple(kind, label); };
  el('addItemBtn').onclick = async () => {
    const val = el('newItemInput').value.trim(); if (!val) return;
    try { await api.post('lookups/', { kind, name: val }); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    await redraw();
  };
  el('newItemInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') el('addItemBtn').click(); });
  bindRows(kind, label, async (it, act) => {
    if (act === 'default') {
      try { state.siteSettings.defaultTaxRate = await api.post('lookups/default-tax/', { rate: it.name }); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
      drawSimple(kind, label); return;
    }
    if (act === 'rename') {
      const val = await customPrompt('Rename to:', it.name); if (val === null || !val.trim()) return;
      try { await api.patch(`lookups/${it.id}/`, { name: val.trim() }); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    } else {
      if (!await customConfirm('Remove this item from the list? Customers already using it will keep the old value as free text.')) return;
      try { await api.delete(`lookups/${it.id}/`); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    }
    await redraw();
  });
}
function bindRows(kind, label, handler) {
  el('genericList').querySelectorAll('[data-act]').forEach((b) => {
    b.onclick = () => { const it = (kind === 'sales_person' ? state.salesPersons : state.lookups[kind]).find((x) => String(x.id) === b.dataset.id); if (it) handler(it, b.dataset.act); };
  });
}

function drawSalesPersons() {
  el('manageBody').innerHTML = `
    <div class="manage-list" id="genericList">${state.salesPersons.length ? state.salesPersons.map((sp) => `
      <div class="manage-item"><span class="mi-name">${escapeHtml(sp.name)}${sp.phone ? ` <span style="color:var(--text-faint); font-weight:400;">&middot; ${escapeHtml(sp.phone)}</span>` : ''}</span>${actions(sp.id, 'Edit')}</div>`).join('') : '<p class="modal-sub">No sales persons yet.</p>'}</div>
    <div class="manage-add-row" style="flex-wrap:wrap;">
      <input type="text" id="newSpNameInput" placeholder="Sales person name&hellip;" style="flex:1.4; min-width:140px;">
      <input type="text" id="newSpPhoneInput" placeholder="Contact number&hellip;" style="flex:1; min-width:120px;">
      <button class="btn" id="addSpBtn">Add</button>
    </div>`;
  const redraw = async () => { await refreshState('sales_person'); drawSalesPersons(); };
  el('addSpBtn').onclick = async () => {
    const name = el('newSpNameInput').value.trim(), phone = el('newSpPhoneInput').value.trim(); if (!name) return;
    try { await api.post('sales-persons/', { name, phone }); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    await redraw();
  };
  ['newSpNameInput', 'newSpPhoneInput'].forEach((id) => el(id).addEventListener('keydown', (e) => { if (e.key === 'Enter') el('addSpBtn').click(); }));
  bindRows('sales_person', 'sales person', async (sp, act) => {
    if (act === 'rename') {
      const name = await customPrompt('Sales person name:', sp.name); if (name === null || !name.trim()) return;
      const phone = await customPrompt('Contact number:', sp.phone || ''); if (phone === null) return;
      try { await api.patch(`sales-persons/${sp.id}/`, { name: name.trim(), phone: phone.trim() }); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    } else {
      if (!await customConfirm('Remove this sales person from the list? Quotations already using them will keep the saved name/number.')) return;
      try { await api.delete(`sales-persons/${sp.id}/`); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    }
    await redraw();
  });
}

function drawTransportCourier(kind, label) {
  editingId = null;
  el('manageBody').innerHTML = `
    <div class="manage-list" id="genericList" style="margin-bottom:18px;"></div>
    <div class="section-label" style="text-transform:none; font-size:12.5px; letter-spacing:0;">Add / edit ${label}</div>
    <div class="form-grid" style="margin-bottom:10px;">
      <div class="field"><label for="tc-name">Name</label><input type="text" id="tc-name" placeholder="e.g. ${kind === 'transport' ? 'Sri Balaji Transport' : 'Blue Dart Express'}"></div>
      <div class="field"><label for="tc-phone">Phone</label><input type="text" id="tc-phone" placeholder="Landline / office number"></div>
      <div class="field"><label for="tc-mobile">Mobile</label><input type="text" id="tc-mobile" placeholder="Mobile number"></div>
      <div class="field"><label for="tc-gst">GST Number</label><input type="text" id="tc-gst" placeholder="e.g. 29ABCDE1234F1Z5" maxlength="15" style="text-transform:uppercase;"></div>
      <div class="field span2"><label for="tc-location">Location</label><input type="text" id="tc-location" placeholder="e.g. Peenya, Bengaluru"></div>
      <div class="field span2"><label for="tc-address">Address</label><textarea id="tc-address" rows="2" placeholder="Street, building, area"></textarea></div>
    </div>
    <div class="modal-actions" style="justify-content:flex-start; margin-bottom:4px;">
      <button class="btn btn-primary" id="tcSaveBtn">Add ${label}</button>
      <button class="btn" id="tcCancelEditBtn" style="display:none;">Cancel edit</button>
    </div>`;
  const reset = () => {
    editingId = null;
    ['name', 'phone', 'mobile', 'gst', 'location', 'address'].forEach((f) => { el('tc-' + f).value = ''; });
    el('tcSaveBtn').textContent = `Add ${label}`; el('tcCancelEditBtn').style.display = 'none';
  };
  const drawList = () => {
    el('genericList').innerHTML = listHtml(items(kind), label, (it) => `
      <div class="manage-item" style="align-items:flex-start;">
        <span class="mi-name">${escapeHtml(it.name)}
          <span style="display:block; color:var(--text-faint); font-weight:400; font-size:12px; margin-top:2px;">${['phone', 'mobile', 'gst', 'location'].map((k) => (it.details || {})[k]).filter(Boolean).map(escapeHtml).join(' &middot; ') || '—'}</span>
        </span>${actions(it.id, 'Edit')}</div>`);
    bindRows(kind, label, async (it, act) => {
      if (act === 'rename') {
        editingId = it.id; const d = it.details || {};
        el('tc-name').value = it.name; ['phone', 'mobile', 'gst', 'location', 'address'].forEach((f) => { el('tc-' + f).value = d[f] || ''; });
        el('tcSaveBtn').textContent = `Save ${label}`; el('tcCancelEditBtn').style.display = ''; el('tc-name').focus();
      } else {
        if (!await customConfirm(`Remove this ${label} from the list? Customers already using it will keep the old value as free text.`)) return;
        try { await api.delete(`lookups/${it.id}/`); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
        await refreshState(kind); drawList();
      }
    });
  };
  drawList();
  el('tcSaveBtn').onclick = async () => {
    const name = el('tc-name').value.trim(); if (!name) return;
    const details = { phone: el('tc-phone').value.trim(), mobile: el('tc-mobile').value.trim(), gst: el('tc-gst').value.trim().toUpperCase(), location: el('tc-location').value.trim(), address: el('tc-address').value.trim() };
    try {
      if (editingId) await api.patch(`lookups/${editingId}/`, { name, details }); else await api.post('lookups/', { kind, name, details });
    } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    await refreshState(kind); reset(); drawList();
  };
  el('tcCancelEditBtn').onclick = reset;
}

function drawBody() {
  if (tab === 'salesPersons') { drawSalesPersons(); return; }
  const [kind, label] = TABS[tab];
  if (tab === 'transport' || tab === 'courier') drawTransportCourier(kind, label); else drawSimple(kind, label);
}

export async function mountManageLists(root) {
  mountRefView(root, 'view-managelists');
  await Promise.all([...new Set(Object.values(TABS).map(([k]) => k))].map(refreshState).concat(refreshState('sales_person')));
  document.querySelectorAll('#manageTabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
  el('manageTabs').onclick = (e) => {
    const btn = e.target.closest('button[data-tab]'); if (!btn) return;
    tab = btn.dataset.tab;
    document.querySelectorAll('#manageTabs button').forEach((b) => b.classList.toggle('active', b === btn));
    drawBody();
  };
  drawBody();
}
