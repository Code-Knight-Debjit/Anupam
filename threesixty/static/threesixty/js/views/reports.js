// Reports — the reference's page: eight tabs, a filter row per tab, Export Excel / PDF / Print / Watermark, and the
// drill-down dialog. The data comes from the scoped list endpoints (a user only reports on what they may see) and each
// report is built the way the reference builds it. The larger reports live in reports_x.js (Sales / Customer Reports) and
// reports_up.js (User Performance).
import { state, isAdmin, isBranchManager, isSalesManager, roleLabel } from '../state.js';
import { navigate } from '../router.js';
import { el, escapeHtml, fmtMoney, daysSinceDate, customAlert, exportRowsToExcel, exportRowsToPdf, printRowsTable } from '../ui.js';
import { mountRefView, useOverlays, openOverlay, closeOverlay } from '../customer_common.js';
import { loadReportData, companyBranches } from '../report_data.js';
import { exportSheetsToExcel } from '../report_export.js';
import { getXlsx } from '../ui.js';
import { openDocView } from './sales_pages.js';
import { openWatermark } from './sales.js';
import { renderSalesX, renderCustX, drawXFilters, SALESX_REPORTS, CUSTX_REPORTS } from './reports_x.js';
import { renderUserPerformance, renderUpFilters, upState } from './reports_up.js';

const INTERACTION_TYPES = ['Call', 'Visit', 'Appointment', 'Sales Log', 'Payment Log', 'Outreach'];
const num = (v) => Number(v) || 0;

// ---- state shared with the report modules ------------------------------------------------------------------------------------------
export const R = {
  tab: 'sales', data: null,
  filters: { from: '', to: '', branch: '', interactionType: '', user: '' },
  rows: [], title: 'Anupam 360 — Report', prefix: 'anupam360-report', sections: null, legend: null, subtitle: '', sheets: null,
  salesXSub: 'followup', custXSub: 'industry',
};
export const canSeeAll = () => isAdmin() || isBranchManager();
export const reportUser = () => (canSeeAll() ? R.filters.user : String(state.me.user_id));
export const xDate = (d) => (d ? new Date(d).toLocaleDateString('en-IN') : '—');
export function inDateRange(dateStr, from, to) {
  if (!from && !to) return true;
  if (!dateStr) return false;
  const d = new Date(dateStr);
  if (from && d < new Date(from)) return false;
  if (to) { const t = new Date(to); t.setHours(23, 59, 59, 999); if (d > t) return false; }
  return true;
}
const sameUser = (id, user) => !user || String(id) === String(user);

/** A table for the on-screen report that is also what the Excel / PDF / Print buttons export. */
export function xTable(cols, rows, opts = {}) {
  const html = `<div class="table-scroll"><table class="report">
    <tr>${cols.map((c) => `<th>${escapeHtml(c)}</th>`).join('')}</tr>
    ${rows.map((r) => `<tr${r._id ? ` style="cursor:pointer;" data-open="${opts.open || 'doc'}:${r._id}"` : ''}>${cols.map((c) => `<td>${escapeHtml(String(r[c] === undefined || r[c] === null ? '—' : r[c]))}</td>`).join('')}</tr>`).join('') || `<tr><td colspan="${cols.length}">${escapeHtml(opts.empty || 'Nothing to show.')}</td></tr>`}
  </table></div>`;
  R.rows = rows.length ? rows.map((r) => { const o = {}; cols.forEach((c) => { o[c] = r[c]; }); return o; }) : [Object.fromEntries(cols.map((c) => [c, '—']))];
  return html;
}
export const xCards = (list) => `<div class="dash-grid" style="margin-bottom:18px;">${list.map(([n, l, c]) => `<div class="dash-card ${c || 'pipe-1'}"><div class="n">${n}</div><div class="l">${escapeHtml(l)}</div></div>`).join('')}</div>`;

/** Rows opened from a report: a document opens its overview, a customer its page. */
export function wireOpeners(root) {
  root.querySelectorAll('[data-open]').forEach((tr) => {
    tr.onclick = () => { const [kind, id] = tr.dataset.open.split(':'); if (kind === 'customer') navigate('customerview', id); else openDocView(id); };
  });
}

// ---- drill-down dialog -----------------------------------------------------------------------------------------------------------------
let drillRows = [], drillName = 'details';
/** Opens the dialog with a table; a cell can be a link to a document (`Doc No.`) or a customer (`Customer`) via the row's hidden ids. */
export function openDrill(title, sub, cols, rows, name) {
  useOverlays('drillOverlay');
  el('drillTitle').textContent = title; el('drillSub').textContent = sub;
  drillRows = rows.map((r) => { const o = {}; cols.forEach((c) => { o[c] = r[c] == null ? '' : r[c]; }); return o; });
  drillName = name;
  el('drillTable').innerHTML = `<tr>${cols.map((c) => `<th>${escapeHtml(c)}</th>`).join('')}</tr>` + (rows.length ? rows.map((r) => `<tr>${cols.map((c) => {
    const v = r[c] === undefined || r[c] === null || r[c] === '' ? '—' : String(r[c]);
    if (c === 'Doc No.' && r._id) return `<td><a href="#" data-doc="${r._id}">${escapeHtml(v)}</a></td>`;
    if (c === 'Customer' && r._cid) return `<td><a href="#" data-cust="${r._cid}">${escapeHtml(v)}</a></td>`;
    return `<td>${escapeHtml(v)}</td>`;
  }).join('')}</tr>`).join('') : `<tr><td colspan="${cols.length}">Nothing here.</td></tr>`);
  el('drillTable').querySelectorAll('[data-doc]').forEach((a) => { a.onclick = (e) => { e.preventDefault(); closeOverlay('drillOverlay'); openDocView(a.dataset.doc); }; });
  el('drillTable').querySelectorAll('[data-cust]').forEach((a) => { a.onclick = (e) => { e.preventDefault(); closeOverlay('drillOverlay'); navigate('customerview', a.dataset.cust); }; });
  el('drillCloseBtn').onclick = () => closeOverlay('drillOverlay');
  el('drillDoneBtn').onclick = () => closeOverlay('drillOverlay');
  el('drillExcelBtn').onclick = async () => {
    if (!drillRows.length) { await customAlert('Nothing to download.'); return; }
    const XLSX = await getXlsx(); const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(drillRows), 'Details');
    XLSX.writeFile(wb, `anupam360-${drillName || 'details'}-${Date.now()}.xlsx`);
  };
  openOverlay('drillOverlay');
}

// ---- filter rows -------------------------------------------------------------------------------------------------------------------------
const branchOptions = (cur) => state.branches.map((b) => `<option value="${escapeHtml(b.name)}" ${cur === b.name ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('');
function renderFilters() {
  if (R.tab === 'gap') { renderGapFilters(); return; }
  if (R.tab === 'userperf') { renderUpFilters(redrawBody); return; }
  if (R.tab === 'salesx' || R.tab === 'custx') { drawXFilters(R, redrawBody); return; }
  const wrap = el('reportFilterRow');
  const showType = R.tab === 'interactions';
  wrap.innerHTML = `
    <input type="date" id="rptFrom" value="${escapeHtml(R.filters.from)}" title="From date">
    <input type="date" id="rptTo" value="${escapeHtml(R.filters.to)}" title="To date">
    <select id="rptBranch"><option value="">All branches</option>${branchOptions(R.filters.branch)}</select>
    ${canSeeAll() ? `<select id="rptUser"><option value="">All users</option>${state.employees.map((e) => `<option value="${e.user_id}" ${String(R.filters.user) === String(e.user_id) ? 'selected' : ''}>${escapeHtml(e.full_name)}</option>`).join('')}</select>` : ''}
    ${showType ? `<select id="rptInteractionType"><option value="">All types</option>${INTERACTION_TYPES.map((t) => `<option value="${escapeHtml(t)}" ${R.filters.interactionType === t ? 'selected' : ''}>${escapeHtml(t)}</option>`).join('')}</select>` : ''}
    <button class="btn" id="rptClear">Clear filters</button>`;
  el('rptFrom').addEventListener('change', (e) => { R.filters.from = e.target.value; redrawBody(); });
  el('rptTo').addEventListener('change', (e) => { R.filters.to = e.target.value; redrawBody(); });
  el('rptBranch').addEventListener('change', (e) => { R.filters.branch = e.target.value; redrawBody(); });
  if (el('rptUser')) el('rptUser').addEventListener('change', (e) => { R.filters.user = e.target.value; redrawBody(); });
  if (showType) el('rptInteractionType').addEventListener('change', (e) => { R.filters.interactionType = e.target.value; redrawBody(); });
  el('rptClear').addEventListener('click', () => { R.filters = { from: '', to: '', branch: '', interactionType: '', user: '' }; renderFilters(); redrawBody(); });
}

// ---- Not Contacted -----------------------------------------------------------------------------------------------------------------------
let gap = { days: '15', mode: 'both', branch: '', user: '', state: '', area: '' };
let gapOpen = false;
const gapActive = () => (gap.days !== '15' ? 1 : 0) + (gap.mode !== 'both' ? 1 : 0) + ['branch', 'user', 'state', 'area'].filter((k) => gap[k]).length;
function renderGapFilters() {
  const wrap = el('reportFilterRow');
  const opts = (arr, cur, all) => `<option value="">${all}</option>` + arr.map((v) => `<option value="${escapeHtml(v)}" ${cur === v ? 'selected' : ''}>${escapeHtml(v)}</option>`).join('');
  const base = R.data.companies;
  const states = [...new Set(base.map((c) => c.state).filter(Boolean))].sort();
  const areas = [...new Set(base.filter((c) => !gap.state || c.state === gap.state).map((c) => c.area).filter(Boolean))].sort();
  const n = gapActive();
  const modeText = ({ both: 'Neither called nor visited', call: 'Not called', visit: 'Not visited', either: 'Not called or not visited' })[gap.mode];
  wrap.innerHTML = `
    <button class="btn" id="gapToggle" type="button">⚙ Filters${n ? ` <span class="gap-badge">${n}</span>` : ''} <span style="opacity:.7;">${gapOpen ? '▴' : '▾'}</span></button>
    <span class="gap-summary">Last ${gap.days} days · ${modeText}${gap.state ? ' · ' + escapeHtml(gap.state) : ''}${gap.area ? ' · ' + escapeHtml(gap.area) : ''}${gap.branch ? ' · ' + escapeHtml(gap.branch) : ''}${gap.user ? ' · ' + escapeHtml(gap.user) : ''}</span>
    <div class="gap-panel" style="display:${gapOpen ? 'flex' : 'none'};">
      <select id="gapDays">${['7', '15', '30', '60', '90'].map((d) => `<option value="${d}" ${gap.days === d ? 'selected' : ''}>Last ${d} days</option>`).join('')}</select>
      <select id="gapMode">
        <option value="both" ${gap.mode === 'both' ? 'selected' : ''}>Neither called nor visited</option>
        <option value="call" ${gap.mode === 'call' ? 'selected' : ''}>Not called</option>
        <option value="visit" ${gap.mode === 'visit' ? 'selected' : ''}>Not visited</option>
        <option value="either" ${gap.mode === 'either' ? 'selected' : ''}>Not called OR not visited</option>
      </select>
      <select id="gapState">${opts(states, gap.state, 'All states')}</select>
      <select id="gapArea">${opts(areas, gap.area, 'All areas')}</select>
      <select id="gapBranch">${opts(state.branches.map((b) => b.name), gap.branch, 'All branches')}</select>
      ${canSeeAll() ? `<select id="gapUser">${opts(state.employees.map((e) => e.full_name), gap.user, 'All users')}</select>` : ''}
      <button class="btn" id="gapClear" type="button">Clear</button>
    </div>`;
  el('gapToggle').addEventListener('click', () => { gapOpen = !gapOpen; renderGapFilters(); });
  ['Days', 'Mode', 'State', 'Area', 'Branch', 'User'].forEach((k) => {
    const x = el('gap' + k);
    if (x) x.addEventListener('change', (ev) => { gap[k.toLowerCase()] = ev.target.value; if (k === 'State') gap.area = ''; renderGapFilters(); redrawBody(); });
  });
  el('gapClear').addEventListener('click', () => { gap = { days: '15', mode: 'both', branch: '', user: '', state: '', area: '' }; renderGapFilters(); redrawBody(); });
}
const assignedNames = (c) => c.assignedTo || [];
function renderNotContacted() {
  const n = Number(gap.days);
  let custs = R.data.companies;
  if (gap.branch) custs = custs.filter((c) => companyBranches(c).includes(gap.branch));
  if (gap.state) custs = custs.filter((c) => c.state === gap.state);
  if (gap.area) custs = custs.filter((c) => c.area === gap.area);
  if (!canSeeAll()) custs = custs.filter((c) => c.createdById === state.me.user_id || (c.assignedIds || []).includes(state.me.user_id));
  else if (gap.user) custs = custs.filter((c) => assignedNames(c).includes(gap.user) || c.createdByName === gap.user);
  const rows = [];
  custs.forEach((c) => {
    const dc = c.lastCall ? daysSinceDate(c.lastCall) : Infinity, dv = c.lastVisit ? daysSinceDate(c.lastVisit) : Infinity;
    const noCall = dc > n, noVisit = dv > n;
    const hit = gap.mode === 'call' ? noCall : gap.mode === 'visit' ? noVisit : gap.mode === 'either' ? (noCall || noVisit) : (noCall && noVisit);
    if (!hit) return;
    const fmt = (d) => (d ? new Date(d).toLocaleDateString('en-IN') : 'Never');
    const ds = (d) => (d === Infinity ? '—' : d);
    const ct = c.contacts[0] || {};
    rows.push({ _sort: Math.max(dc === Infinity ? 99999 : dc, dv === Infinity ? 99999 : dv), Customer: c.name + (c.plant ? ' — ' + c.plant : ''), Area: c.area || '—', City: c.city || '—', State: c.state || '—',
      'Assigned To': assignedNames(c).join(', ') || '—', Contact: ct.name || '—', Phone: ct.phone || '—', 'Last Call': fmt(c.lastCall), 'Days Since Call': ds(dc), 'Last Visit': fmt(c.lastVisit), 'Days Since Visit': ds(dv), _id: c.id });
  });
  rows.sort((a, b) => b._sort - a._sort);
  const cols = ['Customer', 'Area', 'City', 'State', 'Assigned To', 'Contact', 'Phone', 'Last Call', 'Days Since Call', 'Last Visit', 'Days Since Visit'];
  const label = { both: 'neither called nor visited', call: 'not called', visit: 'not visited', either: 'not called or not visited' }[gap.mode];
  const never = rows.filter((r) => r['Last Call'] === 'Never' && r['Last Visit'] === 'Never').length;
  el('reportBody').innerHTML = `
    <div class="dash-grid" style="margin-bottom:18px;">
      <div class="dash-card alert"><div class="n">${rows.length}</div><div class="l">Customers ${label} in ${n} days</div></div>
      <div class="dash-card pipe-1"><div class="n">${custs.length}</div><div class="l">Customers checked</div></div>
      <div class="dash-card pipe-2"><div class="n">${never}</div><div class="l">Never called or visited</div></div>
    </div>
    <div class="table-scroll"><table class="report">
      <tr>${cols.map((c) => `<th>${c}</th>`).join('')}</tr>
      ${rows.map((r) => `<tr style="cursor:pointer;" data-open="customer:${r._id}">${cols.map((c) => `<td>${escapeHtml(String(r[c]))}</td>`).join('')}</tr>`).join('') || `<tr><td colspan="${cols.length}">Every customer has been contacted in the last ${n} days.</td></tr>`}
    </table></div>`;
  wireOpeners(el('reportBody'));
  R.rows = rows.length ? rows.map((r) => { const o = {}; cols.forEach((c) => { o[c] = r[c]; }); return o; }) : [Object.fromEntries(cols.map((c) => [c, '—']))];
  R.title = `Anupam 360 — Customers ${label} in last ${n} days`; R.prefix = `anupam360-not-contacted-${n}d`;
}

// ---- Sales Performance ---------------------------------------------------------------------------------------------------------------
let sp = null;
function spDrill(kind, empId, branchName) {
  let docs = kind === 'enquiry' ? sp.enquiries : kind === 'proforma' ? sp.proformas : sp.quotations;
  if (kind === 'won') docs = docs.filter((d) => d.orderStatus === 'Win');
  else if (kind === 'lost') docs = docs.filter((d) => d.orderStatus === 'Lose');
  else if (kind === 'pending') docs = docs.filter((d) => (d.orderStatus || 'Pending') === 'Pending');
  if (empId) docs = docs.filter((d) => String(d.createdById) === String(empId));
  if (branchName) docs = docs.filter((d) => d.branch === branchName);
  const label = { enquiry: 'Enquiries', quotation: 'Quotations', proforma: 'Proforma Invoices', won: 'Quotations won', lost: 'Quotations lost', pending: 'Quotations pending' }[kind];
  const who = empId ? ((state.employees.find((e) => String(e.user_id) === String(empId)) || {}).full_name || '') : '';
  const f = sp.filters;
  const typeLabel = { enquiry: 'Enquiry', quotation: 'Quotation', proforma: 'Proforma Invoice' };
  const rows = [...docs].sort((a, b) => new Date(b.date || b.createdAt || 0) - new Date(a.date || a.createdAt || 0)).map((d) => {
    const co = R.data.companies.find((c) => c.id === d.customerId) || {};
    const ct = (co.contacts || []).find((c) => c.id === d.contactId) || {};
    return { _id: d.id, _cid: d.customerId || '', Date: d.date ? xDate(d.date) : '—', Type: typeLabel[d.type] || d.type, 'Doc No.': d.docNumber || '—', Customer: d.customerName || co.name || '—',
      Contact: d.contactName || ct.name || '—', Phone: ct.phone || ct.phone2 || '—', City: [co.area, co.city].filter(Boolean).join(', ') || '—',
      Status: d.orderStatus || (d.type === 'quotation' ? 'Pending' : '—'), 'Value (₹)': (d.type === 'quotation' || d.type === 'proforma') ? fmtMoney(d.value) : '—',
      'Created By': d.createdByName || '—', Branch: d.branch || '—' };
  });
  const cols = ['Date', 'Type', 'Doc No.', 'Customer', 'Contact', 'Phone', 'City', 'Status', 'Value (₹)', 'Created By', 'Branch'];
  openDrill(label + (who ? ' — ' + who : '') + (branchName ? ' — ' + branchName : ''),
    `${docs.length} record${docs.length === 1 ? '' : 's'}` + ((f.from || f.to) ? ` · ${f.from ? xDate(f.from) : 'start'} to ${f.to ? xDate(f.to) : 'today'}` : ''), cols, rows, label.toLowerCase().replace(/\s+/g, '-'));
}
function renderSalesPerformance() {
  const { from, to, branch } = R.filters, user = reportUser();
  const mine = (type) => R.data.salesDocs.filter((d) => d.type === type && inDateRange(d.date, from, to) && (!branch || d.branch === branch) && sameUser(d.createdById, user));
  const enquiries = mine('enquiry'), quotations = mine('quotation'), proformas = mine('proforma');
  const won = quotations.filter((d) => d.orderStatus === 'Win'), lost = quotations.filter((d) => d.orderStatus === 'Lose'), pending = quotations.filter((d) => (d.orderStatus || 'Pending') === 'Pending');
  const sum = (l) => l.reduce((s, d) => s + d.value, 0);
  const e2q = enquiries.length ? Math.round(quotations.length / enquiries.length * 100) : 0, q2w = quotations.length ? Math.round(won.length / quotations.length * 100) : 0;
  el('reportBody').innerHTML = `
    <div class="dash-grid" style="margin-bottom:22px;">
      <div class="dash-card pipe-1 drillable" data-sp="enquiry" title="Click to see the customers"><div class="n">${enquiries.length}</div><div class="l">Enquiries</div></div>
      <div class="dash-card pipe-2 drillable" data-sp="quotation" title="Click to see the customers"><div class="n">${quotations.length}</div><div class="l">Quotations</div></div>
      <div class="dash-card pipe-3 drillable" data-sp="won" title="Click to see the customers"><div class="n">${won.length}</div><div class="l">Orders won</div></div>
      <div class="dash-card"><div class="n">${e2q}%</div><div class="l">Enquiry &rarr; Quotation</div></div>
      <div class="dash-card"><div class="n">${q2w}%</div><div class="l">Quotation &rarr; Win</div></div>
    </div>
    <div class="dash-grid" style="margin-bottom:22px;">
      <div class="dash-card"><div class="n">₹${fmtMoney(sum(quotations))}</div><div class="l">Quotation value</div></div>
      <div class="dash-card" style="border-color:var(--teal-line); background:var(--teal-bg);"><div class="n" style="color:var(--teal);">₹${fmtMoney(sum(won))}</div><div class="l">Won value</div></div>
      <div class="dash-card alert"><div class="n">₹${fmtMoney(sum(lost))}</div><div class="l">Lost value</div></div>
      <div class="dash-card"><div class="n">₹${fmtMoney(sum(pending))}</div><div class="l">Pending value</div></div>
    </div>
    <h2 style="margin-bottom:10px;">By branch</h2>
    <div class="table-scroll" style="margin-bottom:26px;"><table class="report" id="reportByBranchTable"></table></div>
    <h2 style="margin-bottom:10px;">Person wise</h2>
    <div class="table-scroll"><table class="report" id="reportByEmpTable"></table></div>`;
  sp = { enquiries, quotations, proformas, filters: { from, to, branch } };
  const cell = (k, v, emp, br) => (v ? `<td class="drill-num" data-sp="${k}" data-emp="${emp || ''}" data-br="${escapeHtml(br || '')}">${v}</td>` : `<td>${v}</td>`);
  el('reportByBranchTable').innerHTML = `
    <tr><th>Branch</th><th>Enquiries</th><th>Quotations</th><th>Won</th><th>Lost</th><th>Pending</th><th>Quotation Value</th><th>Won Value</th></tr>
    ${state.branches.map((b) => {
    const bq = quotations.filter((d) => d.branch === b.name), be = enquiries.filter((d) => d.branch === b.name);
    const bw = bq.filter((d) => d.orderStatus === 'Win'), bl = bq.filter((d) => d.orderStatus === 'Lose'), bp = bq.filter((d) => (d.orderStatus || 'Pending') === 'Pending');
    return `<tr><td>${escapeHtml(b.name)}</td>${cell('enquiry', be.length, '', b.name)}${cell('quotation', bq.length, '', b.name)}${cell('won', bw.length, '', b.name)}${cell('lost', bl.length, '', b.name)}${cell('pending', bp.length, '', b.name)}<td>₹${fmtMoney(sum(bq))}</td><td>₹${fmtMoney(sum(bw))}</td></tr>`;
  }).join('')}`;
  const empRows = state.employees.map((emp) => {
    const eq = quotations.filter((d) => d.createdById === emp.user_id), ee = enquiries.filter((d) => d.createdById === emp.user_id), ep = proformas.filter((d) => d.createdById === emp.user_id);
    const ew = eq.filter((d) => d.orderStatus === 'Win');
    return { _id: emp.user_id, Employee: emp.full_name, Role: roleLabel(emp.role), Enquiries: ee.length, Quotations: eq.length, 'Proforma Invoices': ep.length, Won: ew.length, 'Won Value': fmtMoney(sum(ew)) };
  }).filter((r) => r.Enquiries || r.Quotations || r['Proforma Invoices']);
  el('reportByEmpTable').innerHTML = `
    <tr><th>Employee</th><th>Role</th><th>Enquiries</th><th>Quotations</th><th>Proforma Invoices</th><th>Won</th><th>Won Value</th></tr>
    ${empRows.map((r) => `<tr><td>${escapeHtml(r.Employee)}</td><td>${escapeHtml(r.Role)}</td>${cell('enquiry', r.Enquiries, r._id)}${cell('quotation', r.Quotations, r._id)}${cell('proforma', r['Proforma Invoices'], r._id)}${cell('won', r.Won, r._id)}<td>₹${r['Won Value']}</td></tr>`).join('') || '<tr><td colspan="7">No activity in this period.</td></tr>'}`;
  el('reportBody').querySelectorAll('[data-sp]').forEach((n) => { n.onclick = () => spDrill(n.dataset.sp, n.dataset.emp, n.dataset.br); });
  R.rows = empRows.length ? empRows.map(({ _id, ...rest }) => rest) : [{ Employee: '—', Role: '—', Enquiries: 0, Quotations: 0, 'Proforma Invoices': 0, Won: 0, 'Won Value': '0' }];
  R.title = 'Anupam 360 — Sales Performance Person Wise'; R.prefix = 'anupam360-sales-performance-personwise';
}

// ---- Customer Activity ---------------------------------------------------------------------------------------------------------------
function reportCustomers() {
  const { branch } = R.filters, user = reportUser();
  let custs = R.data.companies;
  if (branch) custs = custs.filter((c) => companyBranches(c).includes(branch));
  if (user) custs = custs.filter((c) => String(c.createdById) === String(user));
  return custs;
}
function renderCustomerActivity() {
  const { from, to, branch } = R.filters, user = reportUser();
  const custs = reportCustomers();
  const inRange = custs.filter((c) => inDateRange(c.createdAt, from, to));
  const quotations = R.data.salesDocs.filter((d) => d.type === 'quotation' && (!branch || d.branch === branch) && sameUser(d.createdById, user));
  const byCust = {};
  quotations.filter((d) => d.orderStatus === 'Win').forEach((d) => { byCust[d.customerName] = (byCust[d.customerName] || 0) + d.value; });
  const top = Object.entries(byCust).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const cutoff = Date.now() - 90 * 24 * 60 * 60 * 1000, last = {};
  R.data.salesDocs.forEach((d) => { const t = new Date(d.date || d.createdAt || 0).getTime(); if (!last[d.customerId] || t > last[d.customerId]) last[d.customerId] = t; });
  const inactive = custs.filter((c) => !last[c.id] || last[c.id] < cutoff);
  el('reportBody').innerHTML = `
    <div class="dash-grid" style="margin-bottom:22px;">
      <div class="dash-card pipe-1"><div class="n">${custs.length}</div><div class="l">Total customers</div></div>
      <div class="dash-card pipe-2"><div class="n">${inRange.length}</div><div class="l">New in this period</div></div>
      <div class="dash-card alert"><div class="n">${inactive.length}</div><div class="l">Inactive (90+ days)</div></div>
    </div>
    <h2 style="margin-bottom:10px;">Top customers by won value</h2>
    <div class="table-scroll" style="margin-bottom:26px;"><table class="report" id="reportTopCustTable"></table></div>
    <h2 style="margin-bottom:10px;">New customers in this period</h2>
    <div class="table-scroll"><table class="report" id="reportNewCustTable"></table></div>`;
  el('reportTopCustTable').innerHTML = `<tr><th>Customer</th><th>Won Value</th></tr>${top.map(([n, v]) => `<tr><td>${escapeHtml(n)}</td><td>₹${fmtMoney(v)}</td></tr>`).join('') || '<tr><td colspan="2">No won orders yet.</td></tr>'}`;
  const newRows = inRange.map((c) => ({ Customer: c.name || '—', City: c.city || '—', 'Added By': c.createdByName || '—', 'Added On': c.createdAt ? new Date(c.createdAt).toLocaleDateString('en-IN') : '—' }));
  el('reportNewCustTable').innerHTML = `<tr><th>Customer</th><th>City</th><th>Added By</th><th>Added On</th></tr>${newRows.map((r) => `<tr><td>${escapeHtml(r.Customer)}</td><td>${escapeHtml(r.City)}</td><td>${escapeHtml(r['Added By'])}</td><td>${escapeHtml(r['Added On'])}</td></tr>`).join('') || '<tr><td colspan="4">No new customers in this period.</td></tr>'}`;
  R.rows = newRows.length ? newRows : [{ Customer: '—', City: '—', 'Added By': '—', 'Added On': '—' }];
  R.title = 'Anupam 360 — New Customers'; R.prefix = 'anupam360-customer-activity';
}

// ---- Payment Collection --------------------------------------------------------------------------------------------------------------
function renderPaymentCollection() {
  const { from, to, branch } = R.filters, user = reportUser();
  let list = R.data.payments.filter((p) => inDateRange(p.date, from, to));
  if (branch) list = list.filter((p) => companyBranches(R.data.companies.find((c) => c.id === p.customerId) || {}).includes(branch));
  if (user) list = list.filter((p) => String(p.createdById) === String(user));
  const invoiced = list.reduce((s, p) => s + p.amount, 0), collected = list.reduce((s, p) => s + p.received, 0), outstanding = list.reduce((s, p) => s + p.balance, 0);
  const pct = invoiced ? Math.round(collected / invoiced * 100) : 0;
  const now = Date.now();
  const buckets = [{ label: '0-30 days', min: 0, max: 30, count: 0, amount: 0 }, { label: '31-60 days', min: 31, max: 60, count: 0, amount: 0 }, { label: '61-90 days', min: 61, max: 90, count: 0, amount: 0 }, { label: '90+ days', min: 91, max: Infinity, count: 0, amount: 0 }];
  list.filter((p) => p.balance > 0).forEach((p) => {
    const days = Math.floor((now - new Date(p.date || p.createdAt || now).getTime()) / (24 * 60 * 60 * 1000));
    const b = buckets.find((bk) => days >= bk.min && days <= bk.max) || buckets[buckets.length - 1];
    b.count++; b.amount += p.balance;
  });
  el('reportBody').innerHTML = `
    <div class="dash-grid" style="margin-bottom:22px;">
      <div class="dash-card pipe-1"><div class="n">₹${fmtMoney(invoiced)}</div><div class="l">Total invoiced</div></div>
      <div class="dash-card" style="border-color:var(--teal-line); background:var(--teal-bg);"><div class="n" style="color:var(--teal);">₹${fmtMoney(collected)}</div><div class="l">Collected</div></div>
      <div class="dash-card alert"><div class="n">₹${fmtMoney(outstanding)}</div><div class="l">Outstanding</div></div>
      <div class="dash-card"><div class="n">${pct}%</div><div class="l">Collection rate</div></div>
    </div>
    <h2 style="margin-bottom:10px;">Outstanding by age</h2>
    <div class="table-scroll" style="margin-bottom:26px;"><table class="report" id="reportAgingTable"></table></div>
    <h2 style="margin-bottom:10px;">By customer</h2>
    <div class="table-scroll"><table class="report" id="reportByCustPayTable"></table></div>`;
  el('reportAgingTable').innerHTML = `<tr><th>Age</th><th>Customers</th><th>Outstanding Amount</th></tr>${buckets.map((b) => `<tr><td>${b.label}</td><td>${b.count}</td><td>₹${fmtMoney(b.amount)}</td></tr>`).join('')}`;
  const rows = list.map((p) => ({ Customer: p.customerName || '—', Invoiced: fmtMoney(p.amount), Received: fmtMoney(p.received), Balance: fmtMoney(p.balance), Date: p.date ? new Date(p.date).toLocaleDateString('en-IN') : '—' }));
  el('reportByCustPayTable').innerHTML = `<tr><th>Customer</th><th>Invoiced</th><th>Received</th><th>Balance</th><th>Date</th></tr>${rows.map((r) => `<tr><td>${escapeHtml(r.Customer)}</td><td>₹${r.Invoiced}</td><td>₹${r.Received}</td><td>₹${r.Balance}</td><td>${r.Date}</td></tr>`).join('') || '<tr><td colspan="5">No payments in this period.</td></tr>'}`;
  R.rows = rows.length ? rows : [{ Customer: '—', Invoiced: '0', Received: '0', Balance: '0', Date: '—' }];
  R.title = 'Anupam 360 — Payment Collection'; R.prefix = 'anupam360-payment-collection';
}

// ---- Interaction Log -----------------------------------------------------------------------------------------------------------------
function renderInteractionLog() {
  const { from, to, branch, interactionType } = R.filters, user = reportUser();
  const custs = R.data.companies, ids = new Set(custs.map((c) => c.id));
  const inBranch = (customerId) => { if (!branch) return true; const co = custs.find((c) => c.id === customerId); return !co || companyBranches(co).includes(branch); };
  let rows = [];
  custs.forEach((c) => {
    if (branch && !companyBranches(c).includes(branch)) return;
    c.contacts.forEach((ct) => ct.interactions.forEach((i) => {
      if (i.isCopy) return;
      // The Call logged automatically when an Outreach call is completed is shown as an Outreach row instead.
      if (i.type === 'Call' && R.data.assignments.some((a) => a.status === 'Called' && a.contactId === ct.id && a.calledById === i.userId && (a.calledAt || '').slice(0, 10) === i.date
        && ((i.notes || '') === (a.remarks || 'Outreach — call completed.') || (!a.remarks && (i.notes || '') === 'Weekly calling list — call completed.')))) return;
      rows.push({ companyId: c.id, companyName: c.name || '—', contactName: (ct.name || '—') + ((i.alsoMet && i.alsoMet.length) ? ' (+ ' + i.alsoMet.map((o) => o.name).join(', ') + ')' : ''),
        type: i.type || '—', date: i.date || i.createdAt || '', notes: i.notes || '', userId: i.userId, jointIds: (i.jointWith || []).map((j) => j.id),
        userName: (i.userName || '—') + ((i.jointWith && i.jointWith.length) ? ' (joint: ' + i.jointWith.map((j) => j.name).join(', ') + ')' : ''), followupDate: i.followupDate || '', location: i.location });
    }));
  });
  const SALES_LABEL = { enquiry: 'Enquiry', quotation: 'Quotation', proforma: 'Proforma Invoice', dc: 'Delivery Challan', po: 'Pending PO' };
  R.data.salesDocs.forEach((d) => {
    if (!ids.has(d.customerId) || !inBranch(d.customerId)) return;
    d.callLog.forEach((m) => rows.push({ companyId: d.customerId, companyName: d.customerName || '—', contactName: d.contactName || '—', type: 'Sales Log', typeLabel: `${SALES_LABEL[d.type] || 'Sales'} ${d.docNumber || ''}`.trim(),
      date: m.timestamp || '', notes: (m.message || '') + (m.callLaterDate ? ` (Call back on ${new Date(m.callLaterDate).toLocaleDateString('en-IN')})` : ''), userId: m.userId, jointIds: [], userName: m.userName || '—', followupDate: m.callLaterDate || '', location: null }));
  });
  R.data.assignments.forEach((a) => {
    if (!ids.has(a.customerId) || !inBranch(a.customerId)) return;
    const called = a.status === 'Called';
    a.attempts.forEach((t) => rows.push({ companyId: a.customerId, companyName: a.customerName || '—', contactName: a.contactName || '—', type: 'Outreach', typeLabel: `Outreach — Not reached (${t.reason})`,
      date: t.at || '', notes: (t.note || '—') + (t.callAgainDate ? ` (Call again on ${new Date(t.callAgainDate).toLocaleDateString('en-IN')})` : ''), userId: t.byId || a.assignedToId, jointIds: [], userName: t.byName || a.assignedToName || '—', followupDate: t.callAgainDate || '', location: null }));
    rows.push({ companyId: a.customerId, companyName: a.customerName || '—', contactName: a.contactName || '—', type: 'Outreach', typeLabel: called ? 'Outreach — Called' : 'Outreach — Pending',
      date: called ? (a.calledAt || a.weekOf || '') : (a.weekOf || ''), notes: called ? (a.remarks || 'Call completed.') : `Pending — week of ${a.weekOf ? new Date(a.weekOf).toLocaleDateString('en-IN') : '—'}, assigned to ${a.assignedToName || '—'}`,
      userId: called ? (a.calledById || a.assignedToId) : a.assignedToId, jointIds: [], userName: called ? (a.calledByName || a.assignedToName || '—') : (a.assignedToName || '—'), followupDate: '', location: null });
  });
  R.data.payments.forEach((p) => {
    if (!ids.has(p.customerId) || !inBranch(p.customerId)) return;
    p.paymentLog.forEach((m) => rows.push({ companyId: p.customerId, companyName: p.customerName || '—', contactName: p.contactName || '—', type: 'Payment Log', typeLabel: `Payment ₹${fmtMoney(p.amount || 0)}`,
      date: m.timestamp || '', notes: (m.message || '') + (m.callLaterDate ? ` (Call back on ${new Date(m.callLaterDate).toLocaleDateString('en-IN')})` : ''), userId: m.userId, jointIds: [], userName: m.userName || '—', followupDate: m.callLaterDate || '', location: null }));
  });
  rows = rows.filter((r) => inDateRange(r.date, from, to));
  if (interactionType) rows = rows.filter((r) => r.type === interactionType);
  if (user) rows = rows.filter((r) => String(r.userId) === String(user) || (r.jointIds || []).map(String).includes(String(user)));
  rows.sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));
  const count = {}; INTERACTION_TYPES.forEach((t) => { count[t] = 0; }); rows.forEach((r) => { count[r.type] = (count[r.type] || 0) + 1; });
  // Appointments taken that have no Visit logged on or after the appointment date for the same contact.
  const pending = [];
  custs.forEach((c) => {
    if (branch && !companyBranches(c).includes(branch)) return;
    c.contacts.forEach((ct) => ct.interactions.filter((i) => i.type === 'Appointment' && !i.isCopy && (!user || String(i.userId) === String(user) || (i.jointWith || []).some((j) => String(j.id) === String(user)))).forEach((ap) => {
      const apDate = ap.date || ap.createdAt || '';
      if (!ct.interactions.some((v) => v.type === 'Visit' && new Date(v.date || v.createdAt || 0) >= new Date(apDate || 0))) pending.push({ companyName: c.name || '—', contactName: ct.name || '—', date: apDate, apptDate: ap.followupDate || '', userName: ap.userName || '—' });
    }));
  });
  pending.sort((x, y) => new Date(x.apptDate || x.date || 0) - new Date(y.apptDate || y.date || 0));
  const tile = (cls, t, n, l) => `<div class="dash-card ${cls} drillable" data-il="${t}" title="Click to filter the list below"><div class="n">${n}</div><div class="l">${l}</div></div>`;
  el('reportBody').innerHTML = `
    <div class="dash-grid" style="margin-bottom:22px;">
      ${tile('pipe-1', '', rows.length, 'Total logged')}${tile('pipe-2', 'Call', count.Call, 'Calls')}${tile('pipe-3', 'Visit', count.Visit, 'Visits')}${tile('', 'Appointment', count.Appointment, 'Appointments')}
      ${tile('', 'Sales Log', count['Sales Log'], 'Sales panel logs')}${tile('', 'Payment Log', count['Payment Log'], 'Payment logs')}${tile('', 'Outreach', count.Outreach, 'Outreach')}
      <div class="dash-card"><div class="n">${pending.length}</div><div class="l">Appointments not yet visited</div></div>
    </div>
    ${pending.length ? `<h2 style="margin-bottom:10px;">Appointments not yet visited</h2>
    <div class="table-scroll" style="margin-bottom:22px;"><table class="report"><tr><th>Appointment date</th><th>Logged on</th><th>Customer</th><th>Contact</th><th>Logged By</th></tr>
      ${pending.map((p) => `<tr><td>${p.apptDate ? new Date(p.apptDate).toLocaleDateString('en-IN') : '—'}</td><td>${p.date ? new Date(p.date).toLocaleDateString('en-IN') : '—'}</td><td>${escapeHtml(p.companyName)}</td><td>${escapeHtml(p.contactName)}</td><td>${escapeHtml(p.userName)}</td></tr>`).join('')}
    </table></div>` : ''}
    <h2 style="margin-bottom:10px;">Logged interactions</h2>
    <div class="table-scroll"><table class="report" id="reportInteractionTable"></table></div>`;
  el('reportInteractionTable').innerHTML = `
    <tr><th>Date</th><th>Type</th><th>Customer</th><th>Contact</th><th>Logged By</th><th>Location</th><th>Notes</th></tr>
    ${rows.map((r) => `<tr><td>${r.date ? new Date(r.date).toLocaleDateString('en-IN') : '—'}</td><td>${escapeHtml(r.typeLabel || r.type)}</td><td>${escapeHtml(r.companyName)}</td><td>${escapeHtml(r.contactName)}</td><td>${escapeHtml(r.userName)}</td>
      <td>${r.location ? `<a href="https://www.google.com/maps?q=${r.location.lat},${r.location.lng}" target="_blank" rel="noopener">View</a>` : '—'}</td><td>${escapeHtml(r.notes || '—')}</td></tr>`).join('') || '<tr><td colspan="7">No interactions logged for this period.</td></tr>'}`;
  el('reportBody').querySelectorAll('[data-il]').forEach((t) => {
    t.onclick = () => { R.filters.interactionType = t.dataset.il; renderFilters(); redrawBody(); setTimeout(() => { const h = [...document.querySelectorAll('#reportBody h2')].find((x) => /Logged interactions/.test(x.textContent)); if (h) h.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 50); };
  });
  const out = rows.map((r) => ({ Date: r.date ? new Date(r.date).toLocaleDateString('en-IN') : '', Type: r.typeLabel || r.type, Customer: r.companyName, Contact: r.contactName, 'Logged By': r.userName,
    Location: r.location ? `https://www.google.com/maps?q=${r.location.lat},${r.location.lng}` : '', Notes: r.notes }));
  R.rows = out.length ? out : [{ Date: '—', Type: '—', Customer: '—', Contact: '—', 'Logged By': '—', Location: '—', Notes: '—' }];
  R.title = 'Anupam 360 — Interaction Log'; R.prefix = 'anupam360-interaction-log';
}

// ---- page ------------------------------------------------------------------------------------------------------------------------------
async function redrawBody() {
  R.sections = null; R.legend = null; R.subtitle = ''; R.sheets = null;
  switch (R.tab) {
    case 'sales': renderSalesPerformance(); break;
    case 'customers': renderCustomerActivity(); break;
    case 'gap': renderNotContacted(); break;
    case 'userperf': await renderUserPerformance(R); break;
    case 'salesx': renderSalesX(R); break;
    case 'custx': renderCustX(R); break;
    case 'interactions': renderInteractionLog(); break;
    default: renderPaymentCollection();
  }
  wireOpeners(el('reportBody'));
}

function docOpts() {
  const cards = [...document.querySelectorAll('#reportBody .dash-card')].map((c) => [(c.querySelector('.n') || {}).textContent || '', (c.querySelector('.l') || {}).textContent || '']).filter((c) => c[0] !== '');
  const parts = [];
  if (R.subtitle) parts.push(R.subtitle);
  else if (R.tab === 'gap') {
    parts.push(`Customers with no ${({ both: 'call or visit', call: 'call', visit: 'visit', either: 'call or visit (either)' })[gap.mode]} in the last ${gap.days} days`);
    ['state', 'area', 'branch', 'user'].forEach((k) => { if (gap[k]) parts.push(k.charAt(0).toUpperCase() + k.slice(1) + ': ' + gap[k]); });
  } else {
    const lab = R.tab === 'salesx' ? (SALESX_REPORTS.find((r) => r[0] === R.salesXSub) || [])[1] : R.tab === 'custx' ? (CUSTX_REPORTS.find((r) => r[0] === R.custXSub) || [])[1] : '';
    if (lab) parts.push(lab);
    if (R.filters.from || R.filters.to) parts.push('Period: ' + (R.filters.from ? xDate(R.filters.from) : 'start') + ' to ' + (R.filters.to ? xDate(R.filters.to) : 'today'));
    if (R.filters.branch) parts.push('Branch: ' + R.filters.branch);
    const u = canSeeAll() && R.filters.user ? (state.employees.find((e) => String(e.user_id) === String(R.filters.user)) || {}).full_name : '';
    if (u) parts.push('User: ' + u);
    if (R.filters.interactionType) parts.push('Type: ' + R.filters.interactionType);
  }
  return { subtitle: parts.join('   |   '), cards, sections: R.sections, legend: R.legend, branch: R.tab === 'gap' ? gap.branch : R.tab === 'userperf' ? upState.branch : R.filters.branch };
}

export async function mountReports(root) {
  mountRefView(root, 'view-reports');
  useOverlays('drillOverlay', 'empActivityOverlay', 'wmOverlay');
  R.data = await loadReportData({ interactions: true, tasks: true, assignments: true });
  // Sales Managers don't see Sales Performance or Customer Activity; every other report is limited to their own data.
  const hide = isSalesManager() ? ['sales', 'customers'] : [];
  const tabs = document.querySelectorAll('#reportTabs button');
  tabs.forEach((b) => { b.style.display = hide.includes(b.dataset.rtab) ? 'none' : ''; });
  if (hide.includes(R.tab)) R.tab = 'gap';
  const paint = () => { tabs.forEach((b) => b.classList.toggle('active', b.dataset.rtab === R.tab)); renderFilters(); redrawBody(); };
  tabs.forEach((b) => { b.onclick = () => { R.tab = b.dataset.rtab; paint(); }; });
  el('reportExportExcelBtn').onclick = () => (R.sheets ? exportSheetsToExcel(R.sheets, R.prefix) : exportRowsToExcel(R.rows, R.prefix, 'Report'));
  el('reportExportPdfBtn').onclick = () => exportRowsToPdf(R.rows, R.title, R.prefix, docOpts());
  el('reportPrintBtn').onclick = () => printRowsTable(R.rows, R.title, docOpts());
  const wm = [...document.querySelectorAll('#view-reports .select-row button')].find((b) => /Watermark/.test(b.textContent));
  if (wm) { wm.removeAttribute('onclick'); wm.onclick = () => openWatermark(); }
  paint();
}
