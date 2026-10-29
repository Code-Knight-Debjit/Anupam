// Sales documents — Enquiry / Quotation / Proforma Invoice / Delivery
// Challan / Pending PO. One shared list+form+items-editor UI parameterised
// by `TYPES[type]`, since the server (`views_sales.py`) treats all five as
// one `SalesDocument` model discriminated by `type`. Totals/amounts are
// always server-computed (`services/totals.py`) — the client only shows a
// live preview using the same formula, never sends `amount`/`value`/
// `sub_total`/`total_amount` itself. Full PDF/print export (the original's
// `computeQuotationDocData` print layout) is out of scope here — this view
// covers data entry/approval only; printing uses the browser's own print.
import { api } from '../api.js';
import { state, isAdmin, isBranchManager, isSalesManager, isBranchStaff } from '../state.js';
import {
  el, escapeHtml, fmtDate, fmtDateTime, fmtMoney, toast, apiErrorMessage, openModal, closeModal,
  confirmDialog, renderTable, badge,
} from '../ui.js';

const TYPES = {
  enquiry: { label: 'Enquiry', hasItems: false, hasDiscount: false, hasTax: false, hasCharges: false, refType: null },
  quotation: { label: 'Quotation', hasItems: true, hasDiscount: true, hasTax: true, hasCharges: true, refType: 'enquiry' },
  proforma: { label: 'Proforma Invoice', hasItems: true, hasDiscount: true, hasTax: true, hasCharges: true, refType: 'quotation' },
  dc: { label: 'Delivery Challan', hasItems: true, hasDiscount: true, hasTax: true, hasCharges: true, refType: 'po' },
  po: { label: 'Pending PO', hasItems: true, hasDiscount: true, hasTax: false, hasCharges: false, refType: null },
};
const STATUS_OPTIONS = ['Pending', 'Win', 'Lose', 'Hold', 'Completed', 'Regretted'];

let customersCache = null;
let contactsCache = {};

async function getCustomers() {
  if (!customersCache) customersCache = await api.all('customers/');
  return customersCache;
}
async function getContacts(customerId) {
  if (!customerId) return [];
  if (!contactsCache[customerId]) contactsCache[customerId] = await api.all(`customers/${customerId}/contacts/`);
  return contactsCache[customerId];
}
function customerName(id, customers) {
  const c = customers.find((x) => x.id === id);
  return c ? c.name : `#${id}`;
}

function computeItemPreview(type, item) {
  const cfg = TYPES[type];
  const qty = Number(item.qty) || 0, rate = Number(item.rate) || 0, discount = Number(item.discount) || 0, tax = Number(item.tax) || 0;
  if (cfg.hasDiscount) {
    let unitFinal = rate * (1 - discount / 100);
    if (cfg.hasTax) unitFinal *= (1 + tax / 100);
    return { amount: unitFinal, value: qty * unitFinal };
  }
  if (cfg.hasItems) return { amount: qty * rate, value: qty * rate };
  return { amount: 0, value: 0 };
}

function itemRowHtml(type, item, idx) {
  const cfg = TYPES[type];
  const it = item || {};
  return `<tr data-row="${idx}">
    <td><input class="it-name" value="${escapeHtml(it.item_name || '')}" placeholder="Item"></td>
    <td><input class="it-make" value="${escapeHtml(it.make || '')}" placeholder="Make" style="width:80px;"></td>
    <td><input class="it-qty" type="number" step="any" value="${it.qty || ''}" style="width:70px;"></td>
    <td><input class="it-unit" value="${escapeHtml(it.unit || '')}" style="width:60px;"></td>
    <td><input class="it-rate" type="number" step="any" value="${it.rate || ''}" style="width:85px;"></td>
    ${cfg.hasDiscount ? `<td><input class="it-discount" type="number" step="any" value="${it.discount || ''}" style="width:65px;"></td>` : ''}
    ${cfg.hasTax ? `<td><input class="it-tax" type="number" step="any" value="${it.tax || ''}" style="width:65px;"></td>` : ''}
    <td class="it-amount sub">0.00</td>
    <td><button type="button" class="btn sm danger" data-remove-row>×</button></td>
  </tr>`;
}

function readItemsEditor(tbody, type) {
  return Array.from(tbody.querySelectorAll('tr')).map((tr) => ({
    item_name: tr.querySelector('.it-name').value.trim(),
    make: tr.querySelector('.it-make').value.trim(),
    qty: tr.querySelector('.it-qty').value || 0,
    unit: tr.querySelector('.it-unit').value.trim(),
    rate: tr.querySelector('.it-rate').value || 0,
    discount: tr.querySelector('.it-discount') ? (tr.querySelector('.it-discount').value || 0) : 0,
    tax: tr.querySelector('.it-tax') ? (tr.querySelector('.it-tax').value || 0) : 0,
  })).filter((it) => it.item_name || Number(it.qty) || Number(it.rate));
}

function wireItemsEditor(container, type) {
  const cfg = TYPES[type];
  const tbody = container.querySelector('tbody');
  const addRow = (item) => { tbody.insertAdjacentHTML('beforeend', itemRowHtml(type, item, tbody.children.length)); wireRow(tbody.lastElementChild); recalc(); };
  const wireRow = (tr) => {
    tr.querySelectorAll('input').forEach((inp) => inp.addEventListener('input', recalc));
    tr.querySelector('[data-remove-row]').addEventListener('click', () => { tr.remove(); recalc(); });
  };
  const recalc = () => {
    let subTotal = 0;
    tbody.querySelectorAll('tr').forEach((tr) => {
      const item = {
        qty: tr.querySelector('.it-qty').value, rate: tr.querySelector('.it-rate').value,
        discount: tr.querySelector('.it-discount') ? tr.querySelector('.it-discount').value : 0,
        tax: tr.querySelector('.it-tax') ? tr.querySelector('.it-tax').value : 0,
      };
      const { value } = computeItemPreview(type, item);
      tr.querySelector('.it-amount').textContent = fmtMoney(value);
      subTotal += value;
    });
    const subEl = container.querySelector('#items-subtotal');
    if (subEl) subEl.textContent = fmtMoney(subTotal);
  };
  tbody.querySelectorAll('tr').forEach(wireRow);
  container.querySelector('[data-add-row]').addEventListener('click', () => addRow());
  recalc();
  return { addRow, recalc };
}

function itemsEditorHtml(type, items) {
  const cfg = TYPES[type];
  if (!cfg.hasItems) return '';
  return `
    <h3 style="margin:16px 0 8px;">Items</h3>
    <div class="table-scroll">
      <table class="report" id="itemsTable">
        <thead><tr>
          <th>Item</th><th>Make</th><th>Qty</th><th>Unit</th><th>Rate</th>
          ${cfg.hasDiscount ? '<th>Disc %</th>' : ''}${cfg.hasTax ? '<th>Tax %</th>' : ''}
          <th>Value</th><th></th>
        </tr></thead>
        <tbody>${(items && items.length ? items : [{}]).map((it, i) => itemRowHtml(type, it, i)).join('')}</tbody>
      </table>
    </div>
    <button type="button" class="btn sm" data-add-row style="margin-top:6px;">+ Add item</button>
    <div class="sub" style="margin-top:6px;">Sub-total (preview): ₹<span id="items-subtotal">0.00</span></div>`;
}

async function docForm(type, doc, customers) {
  const cfg = TYPES[type];
  const d = doc || {};
  const myBranchId = (state.branches.find((b) => (state.me.branch_ids || []).includes(b.id)) || state.branches[0] || {}).id;
  const contacts = d.customer_id ? await getContacts(d.customer_id) : [];
  let refOptions = [];
  if (cfg.refType && d.customer_id) refOptions = await api.all('sales-documents/', { type: cfg.refType, customer_id: d.customer_id });

  return `
    <div class="field-row">
      <div class="field"><label>Branch</label><select id="df-branch">${state.branches.map((b) => `<option value="${b.id}" ${(d.branch_id || myBranchId) === b.id ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('')}</select></div>
      <div class="field"><label>Customer *</label><select id="df-customer"><option value="">— select —</option>${customers.map((c) => `<option value="${c.id}" ${d.customer_id === c.id ? 'selected' : ''}>${escapeHtml(c.name)}</option>`).join('')}</select></div>
      <div class="field"><label>Contact</label><select id="df-contact"><option value="">—</option>${contacts.map((c) => `<option value="${c.id}" ${d.contact_id === c.id ? 'selected' : ''}>${escapeHtml(c.name)}</option>`).join('')}</select></div>
    </div>
    ${cfg.refType ? `<div class="field"><label>Reference ${TYPES[cfg.refType].label}</label><select id="df-reference"><option value="">— none —</option>${refOptions.map((r) => `<option value="${r.id}" ${d.reference_id === r.id ? 'selected' : ''}>${escapeHtml(r.doc_number)}</option>`).join('')}</select></div>` : ''}
    <div class="field-row">
      <div class="field"><label>Date *</label><input type="date" id="df-date" value="${d.date || new Date().toISOString().slice(0, 10)}"></div>
      <div class="field"><label>Status</label><select id="df-status">${STATUS_OPTIONS.map((s) => `<option ${((d.order_status || 'Pending') === s) ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
      <div class="field"><label>Sales person</label><select id="df-salesperson"><option value="">—</option>${state.salesPersons.map((p) => `<option value="${p.id}" ${String(d.sales_person_id) === String(p.id) ? 'selected' : ''}>${escapeHtml(p.name)}</option>`).join('')}</select></div>
    </div>
    ${type === 'enquiry' ? `<div class="field"><label>Source</label><input id="df-source" value="${escapeHtml(d.source || '')}"></div>` : ''}
    ${type === 'dc' ? `<div class="field-row">
      <div class="field"><label>Vehicle</label><input id="df-vehicle" value="${escapeHtml(d.vehicle || '')}"></div>
      <div class="field"><label>Transport</label><input id="df-transport" value="${escapeHtml(d.transport || '')}"></div>
    </div>` : ''}
    ${itemsEditorHtml(type, d.items)}
    ${cfg.hasCharges ? `
      <h3 style="margin:16px 0 8px;">Charges</h3>
      <div class="field-row">
        <div class="field"><label>Packing</label><input type="number" step="any" id="df-packing" value="${d.packing_charges || 0}"></div>
        <div class="field"><label>Packing tax %</label><input type="number" step="any" id="df-packing-tax" value="${d.packing_tax || 0}"></div>
      </div>
      <div class="field-row">
        <div class="field"><label>Freight</label><input type="number" step="any" id="df-freight" value="${d.freight_charges || 0}"></div>
        <div class="field"><label>Freight tax %</label><input type="number" step="any" id="df-freight-tax" value="${d.freight_tax || 0}"></div>
      </div>
      <div class="field-row">
        <div class="field"><label>Other charges</label><input type="number" step="any" id="df-other" value="${d.other_charges || 0}"></div>
        <div class="field"><label>Other charges tax %</label><input type="number" step="any" id="df-other-tax" value="${d.other_charges_tax || 0}"></div>
        <div class="field"><label>Round off</label><input type="number" step="any" id="df-roundoff" value="${d.round_off || 0}"></div>
      </div>
      <div class="field"><label><input type="checkbox" id="df-show-discount" style="width:auto;display:inline;" ${d.show_discount_in_pdf ? 'checked' : ''}> Show discount in PDF</label></div>
      <div class="field-row">
        <div class="field"><label>Valid till</label><input type="date" id="df-valid-till" value="${d.valid_till || ''}"></div>
        <div class="field"><label>Payment terms</label><input id="df-payment-terms" value="${escapeHtml(d.payment_terms || '')}"></div>
      </div>
      <div class="field"><label>Terms &amp; conditions (one per line)</label><textarea id="df-terms" rows="3">${escapeHtml((d.terms || []).join('\n'))}</textarea></div>
    ` : ''}
    <div class="field"><label>Remarks</label><textarea id="df-remarks" rows="2">${escapeHtml(d.remarks || '')}</textarea></div>
    <div class="modal-actions">
      <button class="btn" id="df-cancel">Cancel</button>
      <button class="btn primary" id="df-save">${doc ? 'Save changes' : 'Create ' + cfg.label}</button>
    </div>`;
}

async function openForm(type, doc, onSaved) {
  const cfg = TYPES[type];
  const customers = await getCustomers();
  openModal(`<h2>${doc ? 'Edit' : 'New'} ${cfg.label}${doc ? ' — ' + escapeHtml(doc.doc_number) : ''}</h2>${await docForm(type, doc, customers)}`, {
    onMount: (modal) => {
      if (cfg.hasItems) wireItemsEditor(modal, type);
      modal.querySelector('#df-cancel').onclick = closeModal;
      const customerSel = modal.querySelector('#df-customer');
      customerSel.addEventListener('change', async () => {
        const contacts = await getContacts(customerSel.value);
        modal.querySelector('#df-contact').innerHTML = `<option value="">—</option>${contacts.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('')}`;
        if (cfg.refType) {
          const refs = customerSel.value ? await api.all('sales-documents/', { type: cfg.refType, customer_id: customerSel.value }) : [];
          const refSel = modal.querySelector('#df-reference');
          if (refSel) refSel.innerHTML = `<option value="">— none —</option>${refs.map((r) => `<option value="${r.id}">${escapeHtml(r.doc_number)}</option>`).join('')}`;
        }
      });

      modal.querySelector('#df-save').onclick = async () => {
        const customerId = customerSel.value;
        if (!customerId) { toast('Customer is required.', 'error'); return; }
        const data = {
          branch_id: modal.querySelector('#df-branch').value,
          customer_id: customerId,
          contact_id: modal.querySelector('#df-contact').value || null,
          date: modal.querySelector('#df-date').value,
          order_status: modal.querySelector('#df-status').value,
          sales_person_id: modal.querySelector('#df-salesperson').value || null,
          remarks: modal.querySelector('#df-remarks').value.trim(),
        };
        if (cfg.refType) data.reference_id = modal.querySelector('#df-reference').value || null;
        if (type === 'enquiry') data.source = modal.querySelector('#df-source').value.trim();
        if (type === 'dc') { data.vehicle = modal.querySelector('#df-vehicle').value.trim(); data.transport = modal.querySelector('#df-transport').value.trim(); }
        if (cfg.hasCharges) {
          data.packing_charges = modal.querySelector('#df-packing').value || 0;
          data.packing_tax = modal.querySelector('#df-packing-tax').value || 0;
          data.freight_charges = modal.querySelector('#df-freight').value || 0;
          data.freight_tax = modal.querySelector('#df-freight-tax').value || 0;
          data.other_charges = modal.querySelector('#df-other').value || 0;
          data.other_charges_tax = modal.querySelector('#df-other-tax').value || 0;
          data.round_off = modal.querySelector('#df-roundoff').value || 0;
          data.show_discount_in_pdf = modal.querySelector('#df-show-discount').checked;
          data.valid_till = modal.querySelector('#df-valid-till').value || null;
          data.payment_terms = modal.querySelector('#df-payment-terms').value.trim();
          data.terms = modal.querySelector('#df-terms').value.split('\n').map((s) => s.trim()).filter(Boolean);
        }
        if (cfg.hasItems) data.items = readItemsEditor(modal.querySelector('#itemsTable tbody'), type);

        try {
          if (doc) {
            const res = await api.patch(`sales-documents/${doc.id}/`, { ...data, version: doc.version });
            toast(res && res.approval_requested ? 'Edit sent for approval.' : 'Saved.', res && res.approval_requested ? 'info' : 'success');
          } else {
            data.type = type;
            await api.post('sales-documents/', data);
            toast(`${cfg.label} created.`, 'success');
          }
          closeModal();
          onSaved();
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

async function openCallLog(doc) {
  const calls = await api.all(`sales-documents/${doc.id}/calls/`);
  openModal(`
    <h2>Call log — ${escapeHtml(doc.doc_number)}</h2>
    <div style="max-height:260px;overflow-y:auto;margin-bottom:12px;">
      ${calls.length ? calls.map((c) => `<div class="card" style="margin-bottom:6px;padding:8px 12px;">
        <div class="sub">${escapeHtml(c.user ? c.user.full_name : '—')} · ${fmtDateTime(c.timestamp)}</div>
        <div>${escapeHtml(c.message)}</div></div>`).join('') : '<p class="sub">No calls logged yet.</p>'}
    </div>
    <div class="field"><textarea id="cl-msg" rows="2" placeholder="Log a call..."></textarea></div>
    <div class="modal-actions"><button class="btn" id="cl-close">Close</button><button class="btn primary" id="cl-add">Add entry</button></div>`, {
    onMount: (modal) => {
      modal.querySelector('#cl-close').onclick = closeModal;
      modal.querySelector('#cl-add').onclick = async () => {
        const message = modal.querySelector('#cl-msg').value.trim();
        if (!message) return;
        try { await api.post(`sales-documents/${doc.id}/calls/`, { message }); closeModal(); openCallLog(doc); } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

async function deleteDoc(doc, onDone) {
  if (!await confirmDialog(`Remove ${doc.doc_number}? This cannot be undone.`)) return;
  try {
    const res = await api.delete(`sales-documents/${doc.id}/`);
    toast(res && res.approval_requested ? 'Delete sent for approval.' : 'Removed.', res && res.approval_requested ? 'info' : 'success');
    onDone();
  } catch (e) { toast(apiErrorMessage(e), 'error'); }
}

async function renderList(root, type) {
  const cfg = TYPES[type];
  const [docs, customers] = await Promise.all([api.all('sales-documents/', { type }), getCustomers()]);
  docs.sort((a, b) => b.date.localeCompare(a.date));
  root.innerHTML = `
    <div class="flex-between"><h2 style="margin:0;">${cfg.label}</h2><button class="btn primary" id="newDocBtn">+ New ${cfg.label}</button></div>
    ${renderTable(['Doc #', 'Customer', 'Date', 'Status', cfg.hasCharges ? 'Total' : '', ''], docs.map((d) => ({
      'Doc #': `<a data-open="${d.id}" style="cursor:pointer;color:var(--primary);font-weight:600;">${escapeHtml(d.doc_number)}</a>`,
      Customer: escapeHtml(customerName(d.customer_id, customers)),
      Date: fmtDate(d.date), Status: badge(d.order_status || 'Pending'),
      Total: cfg.hasCharges ? `₹${fmtMoney(d.total_amount)}` : '',
      '': `<button class="btn sm" data-calls="${d.id}">Calls</button> <button class="btn sm danger" data-delete="${d.id}">Remove</button>`,
    })), { empty: `No ${cfg.label.toLowerCase()} records yet.` })}`;

  root.querySelector('#newDocBtn').onclick = () => openForm(type, null, () => renderList(root, type));
  root.querySelectorAll('[data-open]').forEach((a) => a.onclick = () => openForm(type, docs.find((d) => String(d.id) === a.dataset.open), () => renderList(root, type)));
  root.querySelectorAll('[data-calls]').forEach((btn) => btn.onclick = () => openCallLog(docs.find((d) => String(d.id) === btn.dataset.calls)));
  root.querySelectorAll('[data-delete]').forEach((btn) => btn.onclick = () => deleteDoc(docs.find((d) => String(d.id) === btn.dataset.delete), () => renderList(root, type)));
}

export async function mountSales(root, subtab) {
  const type = TYPES[subtab] ? subtab : 'enquiry';
  await renderList(root, type);
}
