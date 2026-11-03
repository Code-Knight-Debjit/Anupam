// New / Edit / Clone a sales document — the reference's full-page form for Enquiry, Quotation, Proforma Invoice,
// Delivery Challan and Sales Order (Pending PO). Which fields appear per type follows the reference's SALES_DOC_CONFIG.
// Totals shown here are a live preview with the reference's formula; the server recomputes and stores the real ones.
import { enablePasteTable } from '../paste_table.js';
import { api } from '../api.js';
import { state, isSalesManager } from '../state.js';
import { navigate } from '../router.js';
import { el, escapeHtml, fmtMoney, customAlert, apiErrorMessage } from '../ui.js';
import { mountRefView, titleCaseWords } from '../customer_common.js';
import { offerPrint } from './sales_legacy.js';

const CFG = {
  enquiry: {
    label: 'Enquiry', prefix: 'ENQ', hasSource: true, hasContact: true, docNumberLabel: 'Enquiry Number', besideDate: true, itemCols: [], refType: null,
    extra: [], hasStatus: false, statuses: [], hasCharges: false,
  },
  quotation: {
    label: 'Quotation', prefix: 'QUO', hasContact: true, docNumberLabel: 'Quotation Number', itemCols: ['itemName', 'qty', 'unit', 'rate', 'discount', 'tax'], hasValue: true, hasDiscount: true, hasTax: true,
    multiline: true, hasCharges: true, hasSd: true, hasMeta: true, hasTerms: true, refType: 'enquiry', extra: [], hasStatus: false, salesPerson: true, validTill: true, paymentTerms: true,
  },
  proforma: {
    label: 'Proforma Invoice', prefix: 'PI', hasContact: true, docNumberLabel: 'Proforma Invoice Number', besideDate: true, itemCols: ['itemName', 'qty', 'unit', 'rate', 'discount', 'tax'], hasValue: true, hasDiscount: true, hasTax: true,
    multiline: true, hasCharges: true, hasSd: true, hasMeta: true, hasTerms: true, refType: 'quotation', extra: [], hasStatus: false, salesPerson: true, validTill: false, paymentTerms: true,
  },
  dc: {
    label: 'Delivery Challan', prefix: 'DC', hasContact: true, docNumberLabel: 'Delivery Challan Number', besideDate: true, itemCols: ['itemName', 'qty', 'unit', 'rate', 'discount', 'tax'], hasValue: true, hasDiscount: true, hasTax: true,
    multiline: true, hasCharges: true, hasSd: true, hasMeta: true, hasTerms: true, refType: 'po', extra: ['vehicle', 'transport'], hasStatus: false, salesPerson: false, validTill: false, paymentTerms: false,
  },
  po: {
    label: 'Sales Order', prefix: 'PO', hasContact: false, docNumberLabel: 'Customer PO No.', besideDate: true, itemCols: ['itemName', 'qty', 'rate', 'discount'], hasValue: true, hasDiscount: true,
    colLabels: { qty: 'Ordered Qty' }, refType: null, extra: [], hasStatus: true, statuses: [['Pending', '#e0a30c'], ['Part Pending', '#e07a2c'], ['Hold', '#8b97a6'], ['Completed', '#2f9e52']], hasCharges: false, generated: false,
  },
};
const COLS = {
  itemName: { label: 'Item Name', type: 'text', width: 'minmax(200px,1.6fr)' }, make: { label: 'Make', type: 'text', width: '130px' },
  qty: { label: 'Qty', type: 'number', width: '85px' }, unit: { label: 'Unit', type: 'select', width: '90px' }, rate: { label: 'Rate', type: 'number', width: '95px' },
  discount: { label: 'Discount %', type: 'number', width: '95px', placeholder: '0' }, tax: { label: 'Tax %', type: 'number', width: '85px', placeholder: '0' },
};
const ENQUIRY_SOURCES = ['Telephonic', 'WhatsApp', 'Email', 'Direct'];
const DEFAULT_TERMS = [
  'Prices are exclusive of GST unless otherwise stated.', 'Delivery timeline is subject to stock availability at the time of order confirmation.',
  'Payment terms as mutually agreed upon order confirmation.', 'This quotation is valid for 15 days from the date of issue.',
];
const num = (v) => Number(v) || 0;
const lookupNames = (k) => (state.lookups[k] || []).map((x) => x.name);

let type = 'enquiry', cfg = CFG.enquiry, editing = null, cloneSrc = null, customers = [], rowCount = 0, roundManual = false, termsEdited = false, refDocs = [];

const customerLabel = (c) => [c.name, c.plant, c.area].map((v) => (v || '').toString().trim()).filter(Boolean).join(', ');
const fullAddress = (c) => [c.address, c.area, c.city, c.state, c.pincode].filter(Boolean).join(', ');
const colLabel = (c) => (cfg.colLabels && cfg.colLabels[c]) || COLS[c].label;
const gridTemplate = () => [...['50px', ...cfg.itemCols.map((c) => COLS[c].width)], ...(cfg.itemCols.includes('rate') ? ['100px'] : []), ...(cfg.hasValue ? ['100px'] : []), '44px', '40px'].join(' ');
const defaultTax = () => { const t = lookupNames('tax_rate'), chosen = String(((state.siteSettings || {}).defaultTaxRate || {}).rate || ''); return t.includes(chosen) ? chosen : (t.includes('18') ? '18' : (t[0] || '0')); };
const taxOptions = (sel, withZero) => { const t = lookupNames('tax_rate'); let h = withZero && !t.includes('0') ? `<option value="0" ${sel === '0' ? 'selected' : ''}>0%</option>` : ''; t.forEach((n) => { h += `<option value="${escapeHtml(n)}" ${sel === n ? 'selected' : ''}>${escapeHtml(n)}%</option>`; }); return h; };

function branchTerms(branchId) {
  const b = state.branches.find((x) => String(x.id) === String(branchId));
  const lines = b && b.terms ? String(b.terms).split('\n').map((t) => t.trim()).filter(Boolean) : [];
  return lines.length ? lines : DEFAULT_TERMS;
}

// ---- items --------------------------------------------------------------------------------------------------------------------------
function buildHead() {
  const head = el('salesItemHead');
  head.style.gridTemplateColumns = gridTemplate();
  head.innerHTML = '<span>S.No.</span>' + cfg.itemCols.map((c) => `<span>${colLabel(c)}</span>`).join('') + (cfg.itemCols.includes('rate') ? '<span>Amount</span>' : '') + (cfg.hasValue ? '<span>Value</span>' : '') + '<span></span><span></span>';
}
function addRow(data = {}) {
  const row = document.createElement('div');
  row.id = 'srow' + (rowCount++); row.classList.add('sales-item-row'); row.style.marginBottom = '8px';
  if (data.id) row.dataset.itemId = data.id;
  const grid = document.createElement('div');
  grid.className = 'sales-item-grid';
  grid.style.cssText = `display:grid; grid-template-columns:${gridTemplate()}; gap:8px; align-items:center;`;
  let html = '<div class="si-field" data-label="S.No."><span class="si-srno" style="font-size:13px; color:var(--text-faint); text-align:center;"></span></div>';
  cfg.itemCols.forEach((c) => {
    const meta = COLS[c], label = colLabel(c), val = data[c] !== undefined && data[c] !== null ? data[c] : '';
    let f;
    if (c === 'itemName' && cfg.multiline) f = `<textarea class="si-${c}" rows="2" placeholder="${label} (description)" style="resize:vertical; min-height:38px; font-family:inherit;">${escapeHtml(val)}</textarea>`;
    else if (c === 'unit') f = `<select class="si-${c}"><option value="">Unit</option>${lookupNames('unit').map((u) => `<option value="${escapeHtml(u)}" ${val === u ? 'selected' : ''}>${escapeHtml(u)}</option>`).join('')}</select>`;
    else if (c === 'tax') f = `<select class="si-${c}">${taxOptions(data[c] !== undefined && data[c] !== null ? String(Number(val)) : defaultTax(), false)}</select>`;
    else if (meta.type === 'number') f = `<input type="number" class="si-${c}" placeholder="${label}" min="0" ${c === 'rate' ? 'step="0.01"' : ''} value="${val === '' ? '' : Number(val)}">`;
    else f = `<input type="text" class="si-${c}" placeholder="${meta.placeholder || label}" value="${escapeHtml(val)}">`;
    html += `<div class="si-field" data-label="${escapeHtml(label)}">${f}</div>`;
  });
  if (cfg.itemCols.includes('rate')) html += '<div class="si-field" data-label="Amount"><span class="si-amount" style="font-size:13px; color:var(--text-dim);">₹0.00</span></div>';
  if (cfg.hasValue) html += '<div class="si-field" data-label="Value"><span class="si-value" style="font-size:13px; color:var(--text-dim); font-weight:600;">₹0.00</span></div>';
  html += '<div class="si-field si-move-field" data-label="Move"><div class="si-move-btns"><button type="button" class="si-move-btn" data-move="-1" title="Move up">&#9650;</button><button type="button" class="si-move-btn" data-move="1" title="Move down">&#9660;</button></div></div>';
  html += '<button type="button" class="rm-contact">&times;</button>';
  grid.innerHTML = html; row.appendChild(grid);
  el('salesItemRows').appendChild(row);
  row.querySelectorAll('input, select').forEach((i) => { i.addEventListener('input', totals); i.addEventListener('change', totals); });
  row.querySelectorAll('.si-move-btn').forEach((b) => b.onclick = () => {
    const dir = Number(b.dataset.move), parent = row.parentElement;
    if (dir === -1 && row.previousElementSibling) parent.insertBefore(row, row.previousElementSibling);
    else if (dir === 1 && row.nextElementSibling) parent.insertBefore(row.nextElementSibling, row);
    renumber();
  });
  row.querySelector('.rm-contact').onclick = () => { row.remove(); renumber(); };
  const ta = row.querySelector('textarea.si-itemName');
  if (ta) { const grow = () => { ta.style.height = 'auto'; ta.style.height = (ta.scrollHeight + 2) + 'px'; }; ta.addEventListener('input', grow); setTimeout(grow, 0); }
  renumber();
}
function renumber() {
  const rows = document.querySelectorAll('#salesItemRows > div');
  rows.forEach((row, i) => {
    row.querySelector('.si-srno').textContent = i + 1;
    const mv = row.querySelectorAll('.si-move-btn');
    if (mv[0]) mv[0].disabled = i === 0;
    if (mv[1]) mv[1].disabled = i === rows.length - 1;
  });
  totals();
}
function totals() {
  let total = 0;
  document.querySelectorAll('#salesItemRows > div').forEach((row) => {
    const amountSpan = row.querySelector('.si-amount'); if (!amountSpan) return;
    const val = (c) => { const i = row.querySelector('.si-' + c); return i ? num(i.value) : 0; };
    const qty = val('qty'), rate = val('rate');
    if (cfg.hasDiscount) {
      let base = rate * (1 - val('discount') / 100);
      if (cfg.hasSd && !el('sf-showdiscount').checked) base = Math.round(base);   // SD unchecked: the discount is folded into a whole-rupee rate
      const unit = cfg.hasTax ? base * (1 + val('tax') / 100) : base;
      amountSpan.textContent = '₹' + fmtMoney(unit);
      const vs = row.querySelector('.si-value'); if (vs) vs.textContent = '₹' + fmtMoney(qty * unit);
      total += qty * unit;
    } else { amountSpan.textContent = '₹' + fmtMoney(qty * rate); total += qty * rate; }
  });
  if (cfg.hasCharges) {
    el('salesTotalLine').style.display = 'none';
    el('sf-subtotal').textContent = '₹' + fmtMoney(total);
    const ch = (id, tax) => num(el(id).value) * (1 + num(el(tax).value) / 100);
    const pre = total + ch('sf-packing', 'sf-packing-tax') + ch('sf-freight', 'sf-freight-tax') + ch('sf-othercharges', 'sf-othercharges-tax');
    let ro;
    if (!roundManual) { ro = Math.round(pre) - pre; el('sf-roundoff').value = ro.toFixed(2); } else ro = num(el('sf-roundoff').value);
    el('sf-totalamount').textContent = '₹' + fmtMoney(pre + ro);
    return;
  }
  const line = el('salesTotalLine');
  if (cfg.itemCols.includes('rate')) { line.style.display = 'block'; line.textContent = `${cfg.label} Value: ₹${fmtMoney(total)}`; } else line.style.display = 'none';
}

// ---- header fields -----------------------------------------------------------------------------------------------------------------------
const show = (id, on) => { el(id).style.display = on ? 'flex' : 'none'; };
async function refreshNumber() {
  if (editing) { el('salesModalSub').textContent = `${cfg.prefix} document ${editing.doc_number || ''}`; return; }
  if (type === 'po') { el('salesModalSub').textContent = ''; return; }
  // Like the reference, a number is previewed before a branch is picked — for the person's own (first) branch then.
  const branch = el('sf-branch').value || (state.me.branch_ids || [])[0] || (state.branches[0] || {}).id;
  if (!branch) { el('salesModalSub').textContent = ''; el('sf-docnumber').value = ''; return; }
  try {
    const r = await api.get(`sales-documents/next-number/?type=${type}&branch_id=${branch}`);
    el('salesModalSub').textContent = `This will be numbered automatically as ${r.number}.`;
    el('sf-docnumber').value = r.number;
  } catch (e) { /* the server numbers it anyway */ }
}
function fillContacts(customerId, selected) {
  const c = customers.find((x) => String(x.id) === String(customerId));
  el('sf-contact').innerHTML = '<option value="">Select contact</option>' + (c ? c.contacts : []).map((ct) => `<option value="${ct.id}" ${String(ct.id) === String(selected) ? 'selected' : ''}>${escapeHtml(ct.name || 'Unnamed')} — ${escapeHtml(ct.job_title || '')}</option>`).join('');
}
function fillAddress() {
  const c = customers.find((x) => String(x.id) === el('sf-customer').value);
  const a = c ? fullAddress(c) : '', box = el('sf-customer-address');
  box.textContent = a; box.style.display = a ? 'block' : 'none';
}
function statusBubble() {
  const o = cfg.statuses.find(([v]) => v === el('sf-status').value);
  el('sf-status-bubble').style.background = o ? o[1] : '#8b97a6';
}

function fill() {
  const doc = editing || cloneSrc, isClone = !!cloneSrc;
  el('salesModalTitle').textContent = editing ? `Edit ${cfg.label}` : `New ${cfg.label}`;
  el('salesFormEyebrow').textContent = 'Sales';
  show('sf-branch-wrap', true);
  el('sf-branch').innerHTML = '<option value="">Select branch</option>' + state.branches.map((b) => `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join('');
  el('sf-branch').value = doc ? String(doc.branch_id) : '';
  el('sf-branch-wrap').classList.toggle('span2', !!cfg.besideDate);
  show('sf-docnumber-wrap', true);
  el('sf-docnumber-label').textContent = cfg.docNumberLabel;
  el('sf-docnumber').readOnly = false; el('sf-docnumber').style.background = 'var(--panel)'; el('sf-docnumber').style.color = 'var(--text)';
  if (editing) el('sf-docnumber').value = editing.doc_number; else if (isClone && type === 'po') el('sf-docnumber').value = '';
  el('sf-customer').innerHTML = '<option value="">Select customer</option>' + customers.map((c) => `<option value="${c.id}">${escapeHtml(customerLabel(c))}</option>`).join('');
  el('sf-customer').value = doc ? String(doc.customer_id) : '';
  if (editing) { el('sf-customer').disabled = true; }
  fillAddress();
  show('sf-contact-wrap', cfg.hasContact);
  if (cfg.hasContact) fillContacts(doc ? doc.customer_id : '', doc ? doc.contact_id : null);
  show('sf-source-wrap', !!cfg.hasSource);
  if (cfg.hasSource) { el('sf-source-label').textContent = 'Source of Enquiry'; el('sf-source').innerHTML = '<option value="">Select source</option>' + ENQUIRY_SOURCES.map((n) => `<option>${n}</option>`).join(''); el('sf-source').value = doc ? doc.source || '' : ''; }
  show('sf-status-wrap', cfg.hasStatus);
  if (cfg.hasStatus) {
    el('sf-status').innerHTML = cfg.statuses.map(([v]) => `<option value="${v}">${v}</option>`).join('');
    el('sf-status').value = doc && !isClone ? (doc.order_status || cfg.statuses[0][0]) : cfg.statuses[0][0];
    el('sf-status').disabled = isSalesManager(); statusBubble();
  }
  show('sf-manualvalue-wrap', false);
  el('sf-date').value = doc && !isClone ? doc.date || '' : new Date().toISOString().slice(0, 10);
  el('sf-remarks').value = doc ? doc.remarks || '' : ''; el('sf-remarks').rows = 2;
  enablePasteTable(el('sf-remarks'));
  const wrap = el('sf-ref-wrap');
  if (!cfg.refType) wrap.style.display = 'none';
  else {
    wrap.style.display = 'flex';
    el('sf-ref-label').textContent = `Linked ${CFG[cfg.refType].label} (optional)`;
    el('sf-ref').innerHTML = '<option value="">None</option>' + refDocs.map((d) => `<option value="${d.id}">${escapeHtml(d.doc_number)} — ${escapeHtml(d.customer_name || '')}</option>`).join('');
    el('sf-ref').value = doc && doc.reference_id ? String(doc.reference_id) : '';
  }
  show('sf-vehicle-wrap', cfg.extra.includes('vehicle')); show('sf-transport-wrap', cfg.extra.includes('transport'));
  if (cfg.extra.includes('vehicle')) el('sf-vehicle').value = doc ? doc.vehicle || '' : '';
  if (cfg.extra.includes('transport')) el('sf-transport').value = doc ? doc.transport || '' : '';
  show('sf-salesperson-wrap', !!cfg.hasMeta && cfg.salesPerson); show('sf-validtill-wrap', !!cfg.hasMeta && cfg.validTill);
  el('sf-refpair-wrap').style.display = cfg.hasMeta ? 'block' : 'none'; show('sf-paymentterms-wrap', !!cfg.hasMeta && cfg.paymentTerms);
  if (cfg.hasMeta) {
    el('sf-salesperson').innerHTML = '<option value="">Select sales person</option>' + state.salesPersons.map((sp) => `<option value="${sp.id}">${escapeHtml(sp.name)}${sp.phone ? ` (${escapeHtml(sp.phone)})` : ''}</option>`).join('');
    el('sf-salesperson').value = doc && doc.sales_person_id ? String(doc.sales_person_id) : '';
    el('sf-validtill').value = doc && !isClone ? doc.valid_till || '' : '';
    el('sf-refno').value = doc ? doc.ref_no || '' : ''; el('sf-refdate').value = doc ? doc.ref_date || '' : '';
    el('sf-paymentterms-list').innerHTML = lookupNames('payment_term').map((n) => `<option value="${escapeHtml(n)}">`).join('');
    el('sf-paymentterms').value = doc ? doc.payment_terms || '' : '';
  }
  show('sf-terms-wrap', !!cfg.hasTerms);
  if (cfg.hasTerms) {
    el('sf-terms').value = doc && Array.isArray(doc.terms) && doc.terms.length ? doc.terms.join('\n') : branchTerms(el('sf-branch').value).join('\n');
    el('sf-terms-savedefault').checked = false; termsEdited = isClone;
  }
  buildHead(); el('salesItemRows').innerHTML = '';
  if (cfg.itemCols.length) {
    el('salesItemsSection').style.display = 'block';
    if (doc && doc.items && doc.items.length) doc.items.forEach((it) => addRow({ id: isClone ? undefined : it.id, itemName: it.item_name, make: it.make, qty: it.qty, unit: it.unit, rate: it.rate, discount: it.discount, tax: it.tax }));
    else for (let i = 0; i < 5; i++) addRow();
  } else el('salesItemsSection').style.display = 'none';
  show('sf-sd-wrap', !!cfg.hasSd);
  if (cfg.hasSd) el('sf-showdiscount').checked = doc ? !!doc.show_discount_in_pdf : false;
  el('salesChargesSection').style.display = cfg.hasCharges ? 'block' : 'none';
  if (cfg.hasCharges) {
    el('sf-packing').value = doc ? num(doc.packing_charges) : 0; el('sf-freight').value = doc ? num(doc.freight_charges) : 0; el('sf-othercharges').value = doc ? num(doc.other_charges) : 0;
    el('sf-packing-tax').innerHTML = taxOptions(doc ? String(num(doc.packing_tax)) : defaultTax(), true);
    el('sf-freight-tax').innerHTML = taxOptions(doc ? String(num(doc.freight_tax)) : defaultTax(), true);
    el('sf-othercharges-tax').innerHTML = taxOptions(doc ? String(num(doc.other_charges_tax)) : defaultTax(), true);
    if (doc && !isClone) { roundManual = true; el('sf-roundoff').value = num(doc.round_off); } else { roundManual = false; el('sf-roundoff').value = 0; }
  }
  if (cfg.itemCols.length) totals();
  if (isClone) {
    el('salesModalTitle').textContent = `Clone of ${cfg.label} ${cloneSrc.doc_number || ''}`.trim();
    el('salesModalSub').textContent = `A copy of ${cloneSrc.doc_number || 'the original'} — it will be saved as a new ${cfg.label.toLowerCase()} with its own number. Check the date, items and rates, then save.`;
  } else refreshNumber();
  if (isClone) refreshNumber().then(() => { el('salesModalSub').textContent = `A copy of ${cloneSrc.doc_number || 'the original'} — it will be saved as a new ${cfg.label.toLowerCase()} with its own number. Check the date, items and rates, then save.`; });
}

// ---- save ----------------------------------------------------------------------------------------------------------------------------------------
async function save() {
  try {
    const customerId = el('sf-customer').value;
    if (!customerId) { await customAlert('Select a customer first.'); return; }
    if (!el('sf-branch').value) { await customAlert('Select a branch first.'); return; }
    const items = [];
    document.querySelectorAll('#salesItemRows > div').forEach((row) => {
      const item = {};
      cfg.itemCols.forEach((c) => {
        const i = row.querySelector('.si-' + c); if (!i) return;
        const key = { itemName: 'item_name' }[c] || c;
        item[key] = COLS[c].type === 'number' ? (i.value === '' ? 0 : Number(i.value)) : i.value.trim();
      });
      if (row.dataset.itemId) item.id = Number(row.dataset.itemId);
      if (item.item_name || item.qty) items.push(item);
    });
    if (cfg.itemCols.length && !items.length) { await customAlert('Add at least one item.'); return; }
    const data = { branch_id: Number(el('sf-branch').value), customer_id: Number(customerId), date: el('sf-date').value, remarks: el('sf-remarks').value.trim() };
    if (cfg.hasContact) data.contact_id = el('sf-contact').value ? Number(el('sf-contact').value) : null;
    const number = el('sf-docnumber').value.trim();
    if (number) data.doc_number = number;
    if (cfg.hasSource) data.source = el('sf-source').value;
    if (cfg.refType) data.reference_id = el('sf-ref').value ? Number(el('sf-ref').value) : null;
    if (cfg.extra.includes('vehicle')) data.vehicle = el('sf-vehicle').value.trim();
    if (cfg.extra.includes('transport')) data.transport = el('sf-transport').value.trim();
    if (cfg.itemCols.length) data.items = items;
    if (cfg.hasSd) data.show_discount_in_pdf = el('sf-showdiscount').checked;
    if (cfg.hasCharges) {
      Object.assign(data, { packing_charges: num(el('sf-packing').value), packing_tax: num(el('sf-packing-tax').value), freight_charges: num(el('sf-freight').value), freight_tax: num(el('sf-freight-tax').value),
        other_charges: num(el('sf-othercharges').value), other_charges_tax: num(el('sf-othercharges-tax').value), round_off: num(el('sf-roundoff').value) });
    }
    if (cfg.hasMeta) {
      if (cfg.salesPerson) data.sales_person_id = el('sf-salesperson').value ? Number(el('sf-salesperson').value) : null;
      if (cfg.validTill) data.valid_till = el('sf-validtill').value || null;
      data.ref_no = el('sf-refno').value.trim(); data.ref_date = el('sf-refdate').value || null;
      if (cfg.paymentTerms) data.payment_terms = el('sf-paymentterms').value.trim();
    }
    if (cfg.hasTerms) {
      const lines = el('sf-terms').value.split('\n').map((t) => t.trim()).filter(Boolean);
      data.terms = lines.length ? lines : branchTerms(data.branch_id);
      if (el('sf-terms-savedefault').checked) data.save_terms_as_default = true;
    }
    if (cfg.hasStatus && editing && !el('sf-status').disabled) data.order_status = el('sf-status').value;
    let saved = null, res;
    if (editing) {
      res = await api.patch(`sales-documents/${editing.id}/`, { ...data, version: editing.version });
      if (res && res.approval_requested) { await customAlert('Your changes were submitted for approval. A branch manager or admin needs to approve them before they apply.'); navigate('sales', type); return; }
      saved = res;
    } else {
      data.type = type;
      saved = await api.post('sales-documents/', data);
      if (saved.enquiry_completed) await customAlert(`Linked enquiry ${saved.enquiry_completed} has been marked as Completed.`);
    }
    navigate('sales', type);
    if (['quotation', 'dc', 'proforma'].includes(type)) setTimeout(() => offerPrint(saved), 400);
  } catch (e) { await customAlert('Could not save: ' + apiErrorMessage(e)); }
}

export async function mountSalesForm(root, docType, rest) {
  type = CFG[docType] ? docType : 'enquiry'; cfg = CFG[type];
  const idPart = rest && rest[0], clonePart = rest && rest[1];
  mountRefView(root, 'view-salesform');
  customers = (await api.get('customers/cards/')).results;
  editing = idPart && idPart !== 'new' ? await api.get(`sales-documents/${idPart}/`) : null;
  cloneSrc = !editing && clonePart ? await api.get(`sales-documents/${clonePart}/`) : null;
  refDocs = cfg.refType ? await api.all('sales-documents/', { type: cfg.refType }) : [];
  rowCount = 0;
  fill();
  const back = () => { if (window.history.length > 1) window.history.back(); else navigate('sales', type); };
  el('salesFormBackBtn').onclick = back; el('salesCancelBtn').onclick = back; el('salesSaveBtn').onclick = save;
  el('sf-customer').addEventListener('change', () => { fillContacts(el('sf-customer').value, null); fillAddress(); });
  el('sf-branch').addEventListener('change', () => { refreshNumber(); if (cfg.hasTerms && !editing && !termsEdited) el('sf-terms').value = branchTerms(el('sf-branch').value).join('\n'); });
  el('sf-status').addEventListener('change', statusBubble);
  el('sf-terms').addEventListener('input', () => { termsEdited = true; });
  el('salesAddItemBtn').onclick = () => addRow();
  ['sf-packing', 'sf-freight', 'sf-othercharges', 'sf-packing-tax', 'sf-freight-tax', 'sf-othercharges-tax', 'sf-showdiscount'].forEach((id) => { el(id).addEventListener('input', totals); el(id).addEventListener('change', totals); });
  el('sf-roundoff').addEventListener('input', () => { roundManual = true; totals(); });
  el('sf-roundoff-auto').addEventListener('click', () => { roundManual = false; totals(); });
}
