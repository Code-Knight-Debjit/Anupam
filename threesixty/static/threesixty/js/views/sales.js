// Sales — the reference's list page for Enquiry / Quotation / Proforma Invoice / Delivery Challan / Pending PO: hero with
// "+ New …", the Win/Lose value tiles (quotation, proforma), search + Filters + View All + Actions, a filter row, and the
// table of the tab (one row per document, or per item for Delivery Challan and Pending PO). The page markup is the
// reference's own; permissions, numbering, totals and approvals are enforced by the server.
import { api } from '../api.js';
import { state, isAdmin, isBranchManager, isBranchStaff, isSalesManager } from '../state.js';
import { navigate } from '../router.js';
import { el, escapeHtml, fmtMoney, customAlert, customConfirm, apiErrorMessage, exportRowsToExcel, exportListPdf, printRowsTable } from '../ui.js';
import { mountRefView, useOverlays, openOverlay, closeOverlay, waLink, fmtD, WHATSAPP_ICON_SVG } from '../customer_common.js';
import { deleteDoc, docPdf, docPrint } from './sales_legacy.js';
import { openDocView } from './sales_pages.js';
import { openInvoiceDone, openPricing, openSupply } from './sales_dialogs.js';

const CFG = {
  enquiry: { label: 'Enquiry', plural: 'Enquiries', statuses: [['Pending', '#e0a30c'], ['Completed', '#2f9e52'], ['Regretted', '#d9534f']] },
  quotation: { label: 'Quotation', plural: 'Quotations', statuses: [['Pending', '#e0a30c'], ['Win', '#2f9e52'], ['Lose', '#d9534f']] },
  proforma: { label: 'Proforma Invoice', plural: 'Proforma Invoices', statuses: [['Pending', '#e0a30c'], ['Win', '#2f9e52'], ['Lose', '#d9534f']] },
  dc: { label: 'Delivery Challan', plural: 'Delivery Challans', statuses: [] },
  po: { label: 'Sales Order', plural: 'Pending PO', statuses: [['Pending', '#e0a30c'], ['Part Pending', '#e07a2c'], ['Completed', '#2f9e52']] },
};
const CALL_LOG_ICON_SVG = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';
const EMPTY_FILTERS = () => ({ customer: '', status: '', ponumber: '', date: '', itemName: '', make: '', branch: '', callLater: '', lastContact: '' });

let tab = 'enquiry';
let docs = [];
let filters = EMPTY_FILTERS();
let filtersBeforeViewAll = null;
let search = '';
let searchTab = '';
let branchDefaulted = false;

const num = (v) => Number(v) || 0;
const docValue = (d) => num(d.total_amount) || (d.items || []).reduce((s, i) => s + num(i.value), 0) || num(d.quotation_value);
const isPending = (d) => (d.order_status || 'Pending') === 'Pending';
const branchName = (d) => d.branch_name || '';
const addedBy = (d) => (d.created_by && d.created_by.full_name) || '—';
const itemBalance = (it) => num(it.balance);
const customerName = (d) => d.customer_name || d.customer_label || '—';
const lastContact = (d) => { const log = d.call_log || []; return log.length ? log[log.length - 1].timestamp : null; };
const callLater = (d) => d.call_later_date || null;

function matchesCallLater(d, v) {
  if (!v) return true;
  const cl = callLater(d);
  if (v === 'none') return !cl;
  if (!cl) return false;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const c = new Date(cl); c.setHours(0, 0, 0, 0);
  if (v === 'overdue') return c < today;
  if (v === 'today') return c.getTime() === today.getTime();
  if (v === 'upcoming') return c > today;
  return true;
}
const matchesLastContact = (d, v) => (!v ? true : v === 'contacted' ? !!lastContact(d) : v === 'notcontacted' ? !lastContact(d) : true);
const CALL_LATER_OPTS = [['', 'All'], ['overdue', 'Overdue'], ['today', 'Due Today'], ['upcoming', 'Upcoming'], ['none', 'Not Set']];
const LAST_CONTACT_OPTS = [['', 'All'], ['contacted', 'Contacted'], ['notcontacted', 'Not Contacted']];
const callLaterSelect = (id, cur) => `<select id="${id}">${CALL_LATER_OPTS.map(([v, l]) => `<option value="${v}" ${cur === v ? 'selected' : ''}>Call Me Later: ${l}</option>`).join('')}</select>`;
const lastContactSelect = (id, cur) => `<select id="${id}">${LAST_CONTACT_OPTS.map(([v, l]) => `<option value="${v}" ${cur === v ? 'selected' : ''}>Last Contact: ${l}</option>`).join('')}</select>`;

function applySearch(list) {
  const q = search.trim().toLowerCase();
  if (!q) return list;
  return list.filter((d) => [d.doc_number, customerName(d), d.contact_name, ...(d.items || []).map((i) => i.item_name)].some((v) => (v || '').toLowerCase().includes(q)));
}

// ---- cells ---------------------------------------------------------------------------------------------------------------------
const stackedFirstCell = (d) => `
  <div>${escapeHtml(d.doc_number || '—')}</div>
  <div style="font-size:11px; color:var(--text-faint); margin-top:2px;">${d.date ? fmtD(d.date) : '—'}</div>
  <div style="font-size:11px; color:var(--text-faint); margin-top:1px;">${escapeHtml(branchName(d) || '—')}</div>
  <div style="font-size:11px; color:var(--text-faint); margin-top:1px;">Added by: ${escapeHtml(addedBy(d))}</div>`;
function contactWithWa(d) {
  const name = escapeHtml(d.contact_name || '—');
  if (!d.contact_name) return name;
  const wa = waLink(d.contact_phone);
  if (!wa) return `<span style="white-space:nowrap;">${name}</span>`;
  return `<span style="display:inline-flex; align-items:center; gap:4px; white-space:nowrap;"><span>${name}</span><a class="btn btn-wa" style="display:inline-flex; align-items:center; justify-content:center; padding:3px 4px; line-height:1;" href="${wa}" target="_blank" rel="noopener" title="WhatsApp">${WHATSAPP_ICON_SVG}</a></span>`;
}
function contactCell(d, showSalesPerson, docId = d.id) {
  const wa = d.contact_name ? waLink(d.contact_phone) : null;
  const lc = lastContact(d), cl = callLater(d);
  return `<div>
    <span style="display:inline-flex; align-items:center; gap:4px; white-space:nowrap;">
      <span>${escapeHtml(d.contact_name || '—')}</span>
      ${wa ? `<a class="btn btn-wa" style="display:inline-flex; align-items:center; justify-content:center; padding:3px 4px; line-height:1;" href="${wa}" target="_blank" rel="noopener" title="WhatsApp">${WHATSAPP_ICON_SVG}</a>` : ''}
      <button type="button" class="btn btn-icon" data-calllog="${docId}" style="display:inline-flex; align-items:center; justify-content:center; padding:3px 4px; line-height:1;" title="Call Log">${CALL_LOG_ICON_SVG}</button>
    </span>
    ${showSalesPerson ? `<div style="font-size:11px; color:var(--text-faint); margin-top:3px; white-space:nowrap;">Sales Person: ${escapeHtml(d.sales_person_name || '—')}</div>` : ''}
    <div style="font-size:11px; color:var(--text-faint); margin-top:3px; white-space:nowrap;">Last contact: ${lc ? new Date(lc).toLocaleString('en-IN') : '—'}</div>
    <div style="font-size:11px; margin-top:1px; white-space:nowrap; color:${cl ? 'var(--accent)' : 'var(--text-faint)'}; font-weight:${cl ? '600' : '400'};">Call later: ${cl ? fmtD(cl) : '—'}</div>
  </div>`;
}
const statusBubble = (cfg, value) => { const o = cfg.statuses.find(([v]) => v === value); return `<span style="display:inline-flex;align-items:center;gap:6px;white-space:nowrap;"><span style="width:9px;height:9px;border-radius:50%;background:${o ? o[1] : '#8b97a6'};display:inline-block;flex-shrink:0;"></span>${escapeHtml(value || '—')}</span>`; };
function statusSelect(d, cfg) {
  const current = d.order_status || cfg.statuses[0][0];
  if (isSalesManager()) return statusBubble(cfg, current);
  const o = cfg.statuses.find(([v]) => v === current);
  return `<span style="display:inline-flex; align-items:center; gap:6px;"><span style="width:9px;height:9px;border-radius:50%;background:${o ? o[1] : '#8b97a6'};display:inline-block;flex-shrink:0;"></span>
    <select data-status="${d.id}" style="padding:5px 8px; font-size:12.5px; border-radius:7px; border:1px solid var(--line); background:var(--panel);">${cfg.statuses.map(([v]) => `<option value="${v}" ${v === current ? 'selected' : ''}>${v}</option>`).join('')}</select></span>`;
}
function menu(id, type, extra = '') {
  const canEdit = !(isSalesManager() && type === 'quotation');
  return `<div class="row-menu-wrap">
    <button type="button" class="btn btn-icon row-menu-btn" onclick="toggleRowMenu(this)" title="Actions">Menu ▾</button>
    <div class="row-menu-dropdown">
      <button type="button" data-act="view" data-id="${id}">View</button>
      <button type="button" data-act="print" data-id="${id}">Print</button>
      <button type="button" data-act="pdf" data-id="${id}">PDF</button>
      <button type="button" data-act="calllog" data-id="${id}">Call Log</button>
      ${canEdit ? `<button type="button" data-act="edit" data-id="${id}">Edit</button>
        ${['quotation', 'proforma', 'dc'].includes(type) ? `<button type="button" data-act="clone" data-id="${id}">Clone</button>` : ''}
        ${extra}
        <button type="button" class="danger" data-act="delete" data-id="${id}">Delete</button>` : ''}
    </div></div>`;
}

// ---- stats + filters ------------------------------------------------------------------------------------------------------------
function renderStats() {
  ['quotation', 'proforma'].forEach((type) => {
    const row = el(type === 'quotation' ? 'quotStatsRow' : 'pfStatsRow');
    row.style.display = tab === type ? 'grid' : 'none';
    if (tab !== type) return;
    let total = 0, win = 0, lose = 0;
    docs.forEach((d) => { total += docValue(d); if (d.order_status === 'Win') win += num(d.order_value !== null && d.order_value !== undefined ? d.order_value : docValue(d)); if (d.order_status === 'Lose') lose += docValue(d); });
    row.innerHTML = `
      <div class="dash-card"><div class="n">₹${fmtMoney(total)}</div><div class="l">Total ${CFG[type].label} Value</div></div>
      <div class="dash-card"><div class="n" style="color:var(--green);">₹${fmtMoney(win)}</div><div class="l">Win Value</div></div>
      <div class="dash-card"><div class="n" style="color:var(--danger);">₹${fmtMoney(lose)}</div><div class="l">Lose Value</div></div>`;
  });
}
function updateFilterBadge() {
  const n = [...el('salesFilterRow').querySelectorAll('select, input')].filter((e) => e.value && e.id !== 'fltClear').length;
  const b = el('salesFilterBadge'); b.textContent = n; b.style.display = n ? '' : 'none';
}
function renderFilters() {
  const wrap = el('salesFilterRow');
  const branchOptions = state.branches.map((b) => `<option value="${escapeHtml(b.name)}" ${filters.branch === b.name ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('');
  const pendingDocs = docs.filter((d) => (tab === 'po' ? d.order_status !== 'Completed' : isPending(d)));
  const customerNames = [...new Set(pendingDocs.map((d) => customerName(d)).filter(Boolean))].sort();
  const customerSelect = `<select id="fltCustomer"><option value="">All customers</option>${customerNames.map((c) => `<option value="${escapeHtml(c)}" ${filters.customer === c ? 'selected' : ''}>${escapeHtml(c)}</option>`).join('')}</select>`;
  const branchSelect = `<select id="fltBranch"><option value="">All branches</option>${branchOptions}</select>`;
  if (tab === 'quotation' || tab === 'proforma') {
    wrap.innerHTML = `${customerSelect}${branchSelect}${callLaterSelect('fltCallLater', filters.callLater)}${lastContactSelect('fltLastContact', filters.lastContact)}<button class="btn" id="fltClear">Clear filters</button>`;
  } else if (tab === 'po') {
    wrap.innerHTML = `${customerSelect}${branchSelect}<input type="text" id="fltPoNo" placeholder="PO No." value="${escapeHtml(filters.ponumber)}" style="max-width:120px;"><input type="date" id="fltDate" value="${escapeHtml(filters.date)}"><input type="text" id="fltItemName" placeholder="Item name" value="${escapeHtml(filters.itemName)}" style="max-width:130px;"><input type="text" id="fltMake" placeholder="Make" value="${escapeHtml(filters.make)}" style="max-width:110px;"><button class="btn" id="fltClear">Clear filters</button>`;
  } else {
    wrap.innerHTML = `${branchSelect}<button class="btn" id="fltClear">${tab === 'dc' || tab === 'enquiry' ? 'Clear filter' : 'Clear filters'}</button>`;
  }
  const bind = (id, key) => { const n = el(id); if (!n) return; n.addEventListener(n.tagName === 'SELECT' || n.type === 'date' ? 'change' : 'input', (e) => { filters[key] = e.target.value; renderTable(); }); };
  bind('fltCustomer', 'customer'); bind('fltBranch', 'branch'); bind('fltCallLater', 'callLater'); bind('fltLastContact', 'lastContact');
  bind('fltPoNo', 'ponumber'); bind('fltDate', 'date'); bind('fltItemName', 'itemName'); bind('fltMake', 'make');
  el('fltClear').onclick = () => { filters = EMPTY_FILTERS(); renderFilters(); renderTable(); };
}

// ---- tables -----------------------------------------------------------------------------------------------------------------------
function empty(big, small) { return `<div class="empty"><div class="big">${big}</div>${small}</div>`; }
function renderTable() {
  updateFilterBadge();
  const cfg = CFG[tab], wrap = el('salesTableWrap');
  const byDateDesc = (a, b) => (new Date(b.date || b.created_at || 0) - new Date(a.date || a.created_at || 0)) || (new Date(b.created_at || 0) - new Date(a.created_at || 0));
  const common = (list) => { let l = applySearch(list); if (filters.branch) l = l.filter((d) => branchName(d) === filters.branch); return l; };
  let html = '';
  if (tab === 'enquiry') {
    const list = common(docs.filter(isPending)).sort(byDateDesc);
    html = !list.length ? empty('No pending enquiries', 'Click "+ New Enquiry" to add one, or check Completed &amp; Regretted.') : `
      <div class="table-scroll"><table class="report">
        <tr><th>Enquiry No. / Date / Branch / Added by</th><th>Customer Name</th><th>Contact Person</th><th>Status</th><th></th></tr>
        ${list.map((d) => `<tr>
          <td data-label="Enquiry No. / Date / Branch / Added by" style="white-space:nowrap;">${stackedFirstCell(d)}</td>
          <td data-label="Customer Name">${escapeHtml(customerName(d))}</td>
          <td data-label="Contact Person">${contactWithWa(d)}</td>
          <td data-label="Status">${statusSelect(d, cfg)}</td>
          <td data-label="Actions" style="white-space:nowrap;">
            <button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-act="view" data-id="${d.id}">View</button>
            <button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-act="edit" data-id="${d.id}">Edit</button>
            <button class="btn-danger-text" data-act="delete" data-id="${d.id}">Delete</button></td></tr>`).join('')}
      </table></div>`;
  } else if (tab === 'quotation' || tab === 'proforma') {
    const isQ = tab === 'quotation';
    let list = docs.filter((d) => filtersBeforeViewAll || isPending(d));
    list = common(list);
    if (filters.customer) list = list.filter((d) => customerName(d) === filters.customer);
    if (filters.callLater) list = list.filter((d) => matchesCallLater(d, filters.callLater));
    if (filters.lastContact) list = list.filter((d) => matchesLastContact(d, filters.lastContact));
    list.sort(byDateDesc);
    html = !list.length ? empty(`No ${cfg.plural.toLowerCase()} match these filters`, `Try clearing a filter, or click "+ New ${cfg.label}" to add one.`) : `
      <div class="table-scroll"><table class="report">
        <tr><th>${isQ ? 'Quotation No.' : 'PI No.'} / Date / Branch / Added by</th><th>Company</th><th>Contact</th><th>${isQ ? 'Quotation Value' : 'Invoice Value'}</th><th>Order Status</th><th></th></tr>
        ${list.map((d) => `<tr>
          <td data-label="${isQ ? 'Quotation No.' : 'PI No.'} / Date / Branch / Added by" style="white-space:nowrap;">${stackedFirstCell(d)}</td>
          <td data-label="Company">${escapeHtml(customerName(d))}</td>
          <td data-label="Contact">${contactCell(d, isQ)}</td>
          <td data-label="${isQ ? 'Quotation Value' : 'Invoice Value'}">₹${fmtMoney(docValue(d))}</td>
          <td data-label="Order Status">${statusSelect(d, cfg)}</td>
          <td data-label="Actions" style="white-space:nowrap;">${menu(d.id, tab)}</td></tr>`).join('')}
      </table></div>`;
  } else if (tab === 'po') {
    let list = docs.filter((d) => d.order_status !== 'Completed');
    list = applySearch(list);
    if (filters.customer) list = list.filter((d) => customerName(d) === filters.customer);
    if (filters.branch) list = list.filter((d) => branchName(d) === filters.branch);
    if (filters.ponumber) list = list.filter((d) => (d.doc_number || '').toLowerCase().includes(filters.ponumber.toLowerCase()));
    if (filters.date) list = list.filter((d) => d.date === filters.date);
    let rows = [];
    list.forEach((d) => (d.items || []).forEach((it, idx) => rows.push({ d, it, idx, ordered: num(it.qty), supplied: num(it.supplied), pending: num(it.pending) })));
    if (filters.itemName) rows = rows.filter((r) => (r.it.item_name || '').toLowerCase().includes(filters.itemName.toLowerCase()));
    if (filters.make) rows = rows.filter((r) => (r.it.make || '').toLowerCase().includes(filters.make.toLowerCase()));
    rows = rows.filter((r) => r.pending > 0).sort((a, b) => new Date(b.d.date || 0) - new Date(a.d.date || 0));
    html = !rows.length ? empty('No pending sales orders match', 'Try a new Sales Order or clear your filters.') : `
      <div class="table-scroll"><table class="report">
        <tr><th>S.No.</th><th>Customer Name</th><th>PO No. / Date / Branch / Added by</th><th>Item Name</th><th>Make</th><th>Ordered Qty</th><th>Supplied Qty</th><th>Pending Qty</th><th>Order Status</th><th></th></tr>
        ${rows.map((r, i) => `<tr>
          <td data-label="S.No.">${i + 1}</td><td data-label="Customer Name">${escapeHtml(customerName(r.d))}</td>
          <td data-label="PO No. / Date / Branch / Added by" style="white-space:nowrap;">${stackedFirstCell(r.d)}</td>
          <td data-label="Item Name">${escapeHtml(r.it.item_name || '—')}</td><td data-label="Make">${escapeHtml(r.it.make || '—')}</td>
          <td data-label="Ordered Qty">${r.ordered}</td><td data-label="Supplied Qty">${r.supplied}</td>
          <td data-label="Pending Qty">${r.pending === 0 ? '<span style="color:var(--green); font-weight:600;">0</span>' : r.pending}</td>
          <td data-label="Order Status">${statusBubble(cfg, r.d.order_status)}</td>
          <td data-label="Actions" style="white-space:nowrap;">
            <button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-act="pricing" data-id="${r.d.id}" data-idx="${r.idx}">Pricing</button>
            <button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-act="supply" data-id="${r.d.id}" data-idx="${r.idx}" ${r.pending <= 0 ? 'disabled' : ''}>Supply</button>
            <button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-act="edit" data-id="${r.d.id}">Edit</button>
            <button class="btn-danger-text" data-act="delete" data-id="${r.d.id}">Delete</button></td></tr>`).join('')}
      </table></div>`;
  } else if (tab === 'dc') {
    let list = common(docs);
    let rows = [];
    list.forEach((d) => (d.items || []).forEach((it, idx) => rows.push({ d, it, idx, dcQty: num(it.qty), invQty: num(it.invoiced), balance: itemBalance(it) })));
    rows = rows.filter((r) => r.balance > 0).sort((a, b) => new Date(b.d.date || 0) - new Date(a.d.date || 0));
    html = !rows.length ? empty('No pending delivery challans', 'Click "+ New Delivery Challan" to add one, or check DC History.') : `
      <div class="table-scroll"><table class="report">
        <tr><th>DC No. / Date / Branch / Added by</th><th>Customer</th><th>Contact</th><th>Item Name</th><th>DC Qty</th><th>Inv Qty</th><th>Balance Qty</th><th></th></tr>
        ${rows.map((r) => `<tr>
          <td data-label="DC No. / Date / Branch / Added by" style="white-space:nowrap;">${stackedFirstCell(r.d)}</td>
          <td data-label="Customer">${escapeHtml(customerName(r.d))}</td><td data-label="Contact">${contactCell(r.d, false)}</td>
          <td data-label="Item Name">${escapeHtml(r.it.item_name || '—')}</td><td data-label="DC Qty">${r.dcQty}</td><td data-label="Inv Qty">${r.invQty}</td><td data-label="Balance Qty">${r.balance}</td>
          <td data-label="Actions" style="white-space:nowrap;">${menu(r.d.id, 'dc', `<button type="button" data-act="invoice" data-id="${r.d.id}" data-idx="${r.idx}">Invoice Done</button>`)}</td></tr>`).join('')}
      </table></div>`;
  }
  wrap.innerHTML = html;
  wireTable(wrap);
}

// ---- actions ------------------------------------------------------------------------------------------------------------------------
const find = (id) => docs.find((d) => String(d.id) === String(id));
async function reload() {
  docs = await api.all('sales-documents/', { type: tab });
  renderStats(); renderFilters(); renderTable();
  refreshBadges();
}
function refreshBadges() { window.dispatchEvent(new Event('hashchange-badges')); }

async function changeStatus(d, value) {
  if (!d) return;
  if (tab === 'quotation' || tab === 'proforma') {
    if (value === 'Win' || value === 'Lose') { openOutcome(d, value); return; }
    try { await api.patch(`sales-documents/${d.id}/`, { order_status: value, version: d.version }); } catch (e) { await customAlert(apiErrorMessage(e)); }
    await reload(); return;
  }
  try { await api.patch(`sales-documents/${d.id}/`, { order_status: value, version: d.version }); } catch (e) { await customAlert(apiErrorMessage(e)); await reload(); return; }
  if (value !== 'Pending') await customAlert(`Moved to ${value} — you'll find it under "View Completed & Regretted".`);
  await reload();
}
function openOutcome(d, status) {
  useOverlays('quotOutcomeOverlay');
  el('quotOutcomeTitle').textContent = status === 'Win' ? 'Mark as Win' : 'Mark as Lose';
  el('quotOutcomeSub').textContent = `${d.doc_number} — ${customerName(d)}`;
  if (status === 'Win') { el('quotOutcomeLabel').textContent = 'Order Value'; el('quotOutcomeValue').style.display = 'block'; el('quotOutcomeValue').value = d.order_value !== null && d.order_value !== undefined ? d.order_value : (docValue(d) || ''); el('quotOutcomeReason').style.display = 'none'; }
  else { el('quotOutcomeLabel').textContent = 'Reason for Lost'; el('quotOutcomeValue').style.display = 'none'; el('quotOutcomeReason').style.display = 'block'; el('quotOutcomeReason').value = d.lost_reason || ''; }
  const close = () => { closeOverlay('quotOutcomeOverlay'); renderTable(); };
  el('quotOutcomeCancelBtn').onclick = close;
  el('quotOutcomeSaveBtn').onclick = async () => {
    const body = { status };
    if (status === 'Win') { const v = el('quotOutcomeValue').value; if (v === '') { await customAlert('Enter the Order Value.'); return; } body.order_value = Number(v); }
    else { const r = el('quotOutcomeReason').value.trim(); if (!r) { await customAlert('Enter a reason for losing this quotation.'); return; } body.lost_reason = r; }
    try { await api.post(`sales-documents/${d.id}/outcome/`, body); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    closeOverlay('quotOutcomeOverlay');
    await customAlert(`Moved to ${status} — you'll find it under "View Win and Lose".`);
    await reload();
  };
  openOverlay('quotOutcomeOverlay');
}
function openCallLogPage(id) { navigate('contactlog', id); }

function wireTable(wrap) {
  wrap.querySelectorAll('[data-status]').forEach((s) => s.onchange = () => changeStatus(find(s.dataset.status), s.value));
  wrap.querySelectorAll('[data-calllog]').forEach((b) => b.onclick = () => openCallLogPage(b.dataset.calllog));
  wrap.querySelectorAll('[data-act]').forEach((b) => b.onclick = async () => {
    window.closeRowMenus();
    const d = find(b.dataset.id); if (!d) return;
    const act = b.dataset.act;
    if (act === 'view') openDocView(d.id, reload);
    else if (act === 'edit') navigate('salesform', tab, d.id);
    else if (act === 'clone') navigate('salesform', tab, 'new', d.id);
    else if (act === 'delete') deleteDoc(d, reload);
    else if (act === 'print') docPrint(d);
    else if (act === 'pdf') docPdf(d);
    else if (act === 'calllog') openCallLogPage(d.id);
    else if (act === 'invoice') openInvoiceDone(d.id, Number(b.dataset.idx), reload);
    else if (act === 'pricing') openPricing(d.id, Number(b.dataset.idx));
    else if (act === 'supply') openSupply(d.id, Number(b.dataset.idx), null, reload);
  });
  wrap.querySelectorAll('tbody tr, tr').forEach((tr) => tr.addEventListener('click', (e) => {
    if (e.target.closest('button, a, input, select, label, textarea, .row-menu-wrap, .row-menu-dropdown')) return;
    if (window.getSelection && String(window.getSelection()).length) return;
    const v = tr.querySelector('[data-act="view"]'); if (v) v.click();
  }));
}

// ---- export (the reference's buildSalesExportData: same columns, same filters) ---------------------------------------------------------------
function exportRows() {
  const addedByName = addedBy;
  const toDate = (d) => (d ? new Date(d).toLocaleDateString('en-IN') : '');
  if (tab === 'enquiry') {
    let l = docs.filter(isPending);
    if (filters.branch) l = l.filter((d) => branchName(d) === filters.branch);
    return l.map((d) => ({ Date: d.date || '', Branch: branchName(d), 'Customer Name': customerName(d), 'Contact Person': d.contact_name || '', 'Added by': addedByName(d), Status: d.order_status || 'Pending' }));
  }
  if (tab === 'proforma') {          // the reference has no special export for proformas: its generic one (number, date, customer, contact, item count)
    return docs.map((d) => ({ 'PI No': d.doc_number, Date: d.date || '', Customer: customerName(d), Contact: d.contact_name || '', Items: (d.items || []).length }));
  }
  if (tab === 'quotation') {
    let l = docs.filter(isPending);
    if (filters.customer) l = l.filter((d) => customerName(d) === filters.customer);
    if (filters.branch) l = l.filter((d) => branchName(d) === filters.branch);
    const q = true;
    return l.map((d) => ({ [q ? 'Quotation No' : 'PI No']: d.doc_number, Date: d.date || '', Branch: branchName(d), Company: customerName(d), Contact: d.contact_name || '',
      [q ? 'Quotation Value' : 'Invoice Value']: fmtMoney(docValue(d)), 'Order Status': d.order_status || 'Pending',
      'Last Contact On': lastContact(d) ? new Date(lastContact(d)).toLocaleString('en-IN') : '', 'Call Me Later': toDate(callLater(d)) }));
  }
  if (tab === 'po') {
    let l = docs.filter((d) => d.order_status !== 'Completed');
    if (filters.customer) l = l.filter((d) => customerName(d) === filters.customer);
    if (filters.branch) l = l.filter((d) => branchName(d) === filters.branch);
    let rows = [];
    l.forEach((d) => d.items.forEach((it) => { const disc = num(it.discount), rate = num(it.rate), unit = rate * (1 - disc / 100);
      rows.push({ 'Customer Name': customerName(d), 'PO No': d.doc_number, Date: d.date || '', Branch: branchName(d), 'Item Name': it.item_name || '', Make: it.make || '', 'Ordered Qty': num(it.qty),
        'Supplied Qty': num(it.supplied), 'Pending Qty': num(it.pending), Rate: rate, 'Discount %': disc, Amount: fmtMoney(unit), Value: fmtMoney(num(it.qty) * unit), 'Order Status': d.order_status || '' }); }));
    if (filters.itemName) rows = rows.filter((r) => r['Item Name'].toLowerCase().includes(filters.itemName.toLowerCase()));
    if (filters.make) rows = rows.filter((r) => r.Make.toLowerCase().includes(filters.make.toLowerCase()));
    return rows.filter((r) => r['Pending Qty'] > 0).map((r, i) => ({ 'S.No': i + 1, ...r }));
  }
  let l = docs;
  if (filters.branch) l = l.filter((d) => branchName(d) === filters.branch);
  const rows = [];
  l.forEach((d) => d.items.forEach((it) => rows.push({ 'DC No': d.doc_number, Date: d.date || '', Branch: branchName(d), Customer: customerName(d), Contact: d.contact_name || '', 'Item Name': it.item_name || '', 'DC Qty': num(it.qty), 'Inv Qty': num(it.invoiced), 'Balance Qty': num(it.balance) })));
  return rows.filter((r) => r['Balance Qty'] > 0);
}

export async function openWatermark() {
  useOverlays('wmOverlay');
  const branch = state.branches.find((b) => (state.me.branch_ids || []).includes(b.id)) || state.branches[0];
  const SIZE = { small: 30, medium: 50, large: 75 };
  const sizeKey = (n) => (n <= 40 ? 'small' : n >= 65 ? 'large' : 'medium');
  el('wmEnabled').checked = !!branch.watermark_enabled; el('wmText').value = branch.watermark_text || '';
  el('wmType').value = branch.watermark_type === 'text' ? 'text' : 'logo'; el('wmTextWrap').style.display = branch.watermark_type === 'text' ? '' : 'none';
  el('wmSize').value = sizeKey(branch.watermark_size || 50); el('wmPreset').value = '';
  el('wmType').onchange = (e) => { el('wmTextWrap').style.display = e.target.value === 'logo' ? 'none' : ''; };
  el('wmPreset').onchange = (e) => { if (e.target.value) el('wmText').value = e.target.value; };
  el('wmCancelBtn').onclick = () => closeOverlay('wmOverlay');
  el('wmSaveBtn').onclick = async () => {
    const text = el('wmText').value.trim(), enabled = el('wmEnabled').checked, kind = el('wmType').value;
    if (enabled && kind === 'text' && !text) { await customAlert('Enter the watermark text, or switch the watermark off.'); return; }
    try { await api.patch(`branches/${branch.id}/`, { watermark_enabled: enabled, watermark_type: kind, watermark_text: text || branch.watermark_text, watermark_size: SIZE[el('wmSize').value] }); }
    catch (e) { await customAlert(apiErrorMessage(e)); return; }
    Object.assign(branch, { watermark_enabled: enabled, watermark_type: kind, watermark_text: text || branch.watermark_text, watermark_size: SIZE[el('wmSize').value] });
    closeOverlay('wmOverlay');
  };
  openOverlay('wmOverlay');
}

async function renderView() {
  const cfg = CFG[tab];
  if (searchTab !== tab) { search = ''; searchTab = tab; }
  el('salesSearchInput').value = search;
  el('salesEyebrow').textContent = 'Sales';
  el('salesTitle').textContent = cfg.plural;
  el('salesSub').textContent = `Every ${cfg.label.toLowerCase()} you or your team have recorded.`;
  el('salesNewBtn').textContent = `+ New ${cfg.label}`;
  const hb = el('salesHistoryBtn');
  const hist = { po: 'Sales Order History', enquiry: 'View Completed & Regretted', quotation: 'View Win and Lose', dc: 'DC History', proforma: 'View Win and Lose' }[tab];
  hb.style.display = (isSalesManager() && (tab === 'enquiry' || tab === 'quotation')) ? 'none' : 'inline-flex';
  hb.textContent = hist;
  await reload();
}

export async function mountSales(root, subtab) {
  tab = CFG[subtab] ? subtab : 'enquiry';
  const view = mountRefView(root, 'view-sales');
  // Branch Manager / Staff land on their own branch (reference: showApp), the filter lets them look at another one.
  if ((isBranchManager() || isBranchStaff()) && !branchDefaulted) {
    const mine = (state.me.branch_ids || [])[0];
    const b = state.branches.find((x) => x.id === mine);
    if (b) filters.branch = b.name;
    branchDefaulted = true;
  }
  el('salesFilterToggleBtn').onclick = () => { const p = el('salesFilterRow'); p.style.display = p.style.display === 'none' ? 'flex' : 'none'; };
  el('salesSearchInput').addEventListener('input', (e) => { search = e.target.value; renderTable(); });
  el('salesViewAllBtn').onclick = () => {
    if (filtersBeforeViewAll) { filters = filtersBeforeViewAll; filtersBeforeViewAll = null; el('salesViewAllBtn').textContent = 'View All'; }
    else { filtersBeforeViewAll = { ...filters }; filters = EMPTY_FILTERS(); el('salesViewAllBtn').textContent = 'Undo View All'; }
    el('salesFilterRow').style.display = 'none';
    renderFilters(); renderTable();
  };
  if (filtersBeforeViewAll) el('salesViewAllBtn').textContent = 'Undo View All';
  el('salesNewBtn').onclick = () => navigate('salesform', tab, 'new');
  el('salesHistoryBtn').onclick = () => navigate({ po: 'pohistory', quotation: 'quotationhistory', dc: 'dchistory', proforma: 'proformahistory', enquiry: 'enqhistory' }[tab]);
  const title = { po: 'anupam360-sales-orders', enquiry: 'anupam360-enquiries', quotation: 'anupam360-quotations', proforma: 'anupam360-proformas', dc: 'anupam360-challans' }[tab];
  el('salesExportExcelBtn').onclick = () => exportRowsToExcel(exportRows(), title, CFG[tab].label);
  el('salesExportPdfBtn').onclick = () => exportListPdf(exportRows(), `Anupam 360 — ${CFG[tab].plural}`, title);
  el('salesPrintBtn').onclick = () => printRowsTable(exportRows(), `Anupam 360 — ${CFG[tab].plural}`);
  el('salesHistoryBtn').closest('.row-menu-dropdown').querySelectorAll('button').forEach((b) => { if (b.textContent.startsWith('Watermark')) b.onclick = () => { window.closeRowMenus(); openWatermark(); }; });
  await renderView();
}
