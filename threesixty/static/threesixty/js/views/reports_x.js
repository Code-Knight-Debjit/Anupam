// The "Sales Reports" and "Customer Reports" tabs: a drop-down of sub-reports, each a few cards and one table (the table is
// also what Export Excel / PDF / Print take). Built the way the reference builds them, from the scoped lists.
import { state } from '../state.js';
import { el, escapeHtml, fmtMoney, daysSinceDate } from '../ui.js';
import { canSeeAll, reportUser, inDateRange, xDate, xTable, xCards } from './reports.js';
import { companyBranches } from '../report_data.js';

export const SALESX_REPORTS = [
  ['followup', 'Quotation follow-up (pending ageing)'], ['lost', 'Lost quotations — reasons'], ['custwise', 'Customer-wise sales'],
  ['itemwise', 'Item-wise quotations'], ['pendingpo', 'Pending purchase orders'], ['enquiry', 'Enquiry report (source & status)'], ['monthly', 'Monthly trend'],
];
export const CUSTX_REPORTS = [
  ['industry', 'By industry type'], ['source', 'By source'], ['potential', 'By potential'], ['state', 'By state'], ['area', 'By area'], ['city', 'By city'],
  ['assigned', 'By assigned to'], ['addedby', 'By added by'], ['brand', 'By interested brand'], ['product', 'By interested product'],
  ['language', 'By preferred language'], ['transport', 'By transport preference'], ['courier', 'By courier preference'], ['missing', 'Missing details (data quality)'],
];

/** The filter row for both tabs: the sub-report picker, (Sales only) a date range, branch, user and Clear. */
export function drawXFilters(R, redraw) {
  const isS = R.tab === 'salesx';
  const list = isS ? SALESX_REPORTS : CUSTX_REPORTS, cur = isS ? R.salesXSub : R.custXSub;
  el('reportFilterRow').innerHTML = `
    <select id="xSub" style="font-weight:700; min-width:240px;">${list.map(([v, l]) => `<option value="${v}" ${cur === v ? 'selected' : ''}>${escapeHtml(l)}</option>`).join('')}</select>
    ${isS ? `<input type="date" id="xFrom" value="${escapeHtml(R.filters.from)}" title="From date"><input type="date" id="xTo" value="${escapeHtml(R.filters.to)}" title="To date">` : ''}
    <select id="xBranch"><option value="">All branches</option>${state.branches.map((b) => `<option value="${escapeHtml(b.name)}" ${R.filters.branch === b.name ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('')}</select>
    ${canSeeAll() ? `<select id="xUser"><option value="">All users</option>${state.employees.map((e) => `<option value="${e.user_id}" ${String(R.filters.user) === String(e.user_id) ? 'selected' : ''}>${escapeHtml(e.full_name)}</option>`).join('')}</select>` : ''}
    <button class="btn" id="xClear" type="button">Clear filters</button>`;
  el('xSub').addEventListener('change', (e) => { if (isS) R.salesXSub = e.target.value; else R.custXSub = e.target.value; redraw(); });
  if (isS) {
    el('xFrom').addEventListener('change', (e) => { R.filters.from = e.target.value; redraw(); });
    el('xTo').addEventListener('change', (e) => { R.filters.to = e.target.value; redraw(); });
  }
  el('xBranch').addEventListener('change', (e) => { R.filters.branch = e.target.value; redraw(); });
  if (el('xUser')) el('xUser').addEventListener('change', (e) => { R.filters.user = e.target.value; redraw(); });
  el('xClear').addEventListener('click', () => { R.filters = { from: '', to: '', branch: '', interactionType: '', user: '' }; drawXFilters(R, redraw); redraw(); });
}

function xDocs(R, type) {
  const { from, to, branch } = R.filters, user = reportUser();
  return R.data.salesDocs.filter((d) => d.type === type && inDateRange(d.date, from, to) && (!branch || d.branch === branch) && (!user || String(d.createdById) === String(user)));
}
const pct = (a, b) => (b ? Math.round(a / b * 100) + '%' : '0%');

export function renderSalesX(R) {
  const sub = R.salesXSub, today = new Date(); today.setHours(0, 0, 0, 0);
  const ageOf = (d) => daysSinceDate(d.date || d.createdAt);
  const label = (SALESX_REPORTS.find((r) => r[0] === sub) || [])[1] || 'Sales report';
  let body = '';
  if (sub === 'followup') {
    const pend = xDocs(R, 'quotation').filter((d) => (d.orderStatus || 'Pending') === 'Pending');
    const rows = pend.map((d) => {
      const log = d.callLog.slice().sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));
      const last = log[0];
      const nextDates = d.callLog.map((l) => l.callLaterDate).filter(Boolean).sort();
      const next = nextDates[nextDates.length - 1];
      const overdue = next && new Date(next) < today;
      return { _id: d.id, _age: ageOf(d), 'Quotation No.': d.docNumber || '—', Date: xDate(d.date), Customer: d.customerName || '—', 'Value (₹)': fmtMoney(d.value),
        'Age (days)': ageOf(d), 'Last Follow-up': last ? xDate(last.timestamp) : 'None', 'Next Call On': next ? xDate(next) : '—',
        Status: !last ? 'No follow-up yet' : overdue ? 'Overdue' : next ? 'Scheduled' : 'Follow-up logged', Owner: d.createdByName || '—' };
    }).sort((a, b) => b._age - a._age);
    const val = pend.reduce((s, d) => s + d.value, 0);
    body = xCards([[rows.length, 'Pending quotations'], [`₹${fmtMoney(val)}`, 'Pending value', 'pipe-2'], [rows.filter((r) => r.Status === 'Overdue').length, 'Overdue follow-ups', 'alert'],
      [rows.filter((r) => r.Status === 'No follow-up yet').length, 'No follow-up yet', 'pipe-4'], [rows.filter((r) => r._age > 30).length, 'Older than 30 days', 'pipe-5']])
      + xTable(['Quotation No.', 'Date', 'Customer', 'Value (₹)', 'Age (days)', 'Last Follow-up', 'Next Call On', 'Status', 'Owner'], rows);
  } else if (sub === 'lost') {
    const lost = xDocs(R, 'quotation').filter((d) => d.orderStatus === 'Lose'), by = {};
    lost.forEach((d) => { const k = (d.lostReason || '').trim() || '(No reason given)'; by[k] = by[k] || { n: 0, v: 0 }; by[k].n++; by[k].v += d.value; });
    const total = lost.length;
    const rows = Object.entries(by).sort((a, b) => b[1].v - a[1].v).map(([k, x]) => ({ 'Lost Reason': k, Quotations: x.n, '% of Lost': pct(x.n, total), 'Lost Value (₹)': fmtMoney(x.v) }));
    body = xCards([[total, 'Lost quotations', 'alert'], [`₹${fmtMoney(lost.reduce((s, d) => s + d.value, 0))}`, 'Lost value', 'pipe-2'], [rows.length, 'Distinct reasons', 'pipe-1']])
      + xTable(['Lost Reason', 'Quotations', '% of Lost', 'Lost Value (₹)'], rows);
  } else if (sub === 'custwise') {
    const m = {};
    const g = (d) => (m[d.customerName || '—'] = m[d.customerName || '—'] || { e: 0, q: 0, w: 0, l: 0, p: 0, wv: 0, qv: 0 });
    xDocs(R, 'enquiry').forEach((d) => { g(d).e++; });
    xDocs(R, 'quotation').forEach((d) => { const x = g(d); x.q++; x.qv += d.value; if (d.orderStatus === 'Win') { x.w++; x.wv += d.value; } else if (d.orderStatus === 'Lose') x.l++; else x.p++; });
    const rows = Object.entries(m).map(([k, x]) => ({ Customer: k, Enquiries: x.e, Quotations: x.q, Won: x.w, Lost: x.l, Pending: x.p, 'Quotation Value (₹)': fmtMoney(x.qv), 'Won Value (₹)': fmtMoney(x.wv), _wv: x.wv })).sort((a, b) => b._wv - a._wv);
    body = xCards([[rows.length, 'Customers with activity'], [rows.filter((r) => r.Won).length, 'Customers who ordered', 'pipe-3']])
      + xTable(['Customer', 'Enquiries', 'Quotations', 'Won', 'Lost', 'Pending', 'Quotation Value (₹)', 'Won Value (₹)'], rows);
  } else if (sub === 'itemwise') {
    const m = {};
    xDocs(R, 'quotation').forEach((d) => d.items.forEach((it) => {
      const k = String(it.itemName || '').trim(); if (!k) return;
      const x = (m[k] = m[k] || { n: 0, q: 0, v: 0, wq: 0, wv: 0 });
      x.n++; x.q += it.qty; x.v += it.value; if (d.orderStatus === 'Win') { x.wq += it.qty; x.wv += it.value; }
    }));
    const rows = Object.entries(m).map(([k, x]) => ({ Item: k, 'Quoted In': x.n, 'Qty Quoted': x.q, 'Quoted Value (₹)': fmtMoney(x.v), 'Qty Won': x.wq, 'Won Value (₹)': fmtMoney(x.wv), 'Win % (Qty)': pct(x.wq, x.q), _v: x.v })).sort((a, b) => b._v - a._v);
    body = xCards([[rows.length, 'Distinct items quoted']]) + xTable(['Item', 'Quoted In', 'Qty Quoted', 'Quoted Value (₹)', 'Qty Won', 'Won Value (₹)', 'Win % (Qty)'], rows);
  } else if (sub === 'pendingpo') {
    const rows = xDocs(R, 'po').filter((d) => d.orderStatus !== 'Completed').map((d) => ({ _id: d.id, _age: ageOf(d), 'PO No.': d.docNumber || '—', Date: xDate(d.date), Customer: d.customerName || '—', Status: d.orderStatus || 'Pending',
      'Ordered Qty': d.items.reduce((a, it) => a + it.qty, 0), 'Balance Qty': d.items.reduce((a, it) => a + it.balance, 0), 'Value (₹)': fmtMoney(d.value), 'Age (days)': ageOf(d) })).sort((a, b) => b._age - a._age);
    body = xCards([[rows.length, 'Open purchase orders'], [rows.reduce((a, r) => a + r['Balance Qty'], 0), 'Total balance qty', 'pipe-2'], [rows.filter((r) => r._age > 30).length, 'Older than 30 days', 'alert'], [rows.filter((r) => r.Status === 'Hold').length, 'On hold', 'pipe-4']])
      + xTable(['PO No.', 'Date', 'Customer', 'Status', 'Ordered Qty', 'Balance Qty', 'Value (₹)', 'Age (days)'], rows);
  } else if (sub === 'enquiry') {
    const enq = xDocs(R, 'enquiry'), quoted = new Set(R.data.salesDocs.filter((d) => d.type === 'quotation' && d.refId).map((d) => d.refId)), by = {};
    enq.forEach((d) => { const k = d.source || '(No source)'; const x = (by[k] = by[k] || { n: 0, c: 0, p: 0, r: 0, q: 0 }); x.n++; if (d.orderStatus === 'Completed') x.c++; else if (d.orderStatus === 'Regretted') x.r++; else x.p++; if (quoted.has(d.id)) x.q++; });
    const rows = Object.entries(by).sort((a, b) => b[1].n - a[1].n).map(([k, x]) => ({ Source: k, Enquiries: x.n, Pending: x.p, Completed: x.c, Regretted: x.r, Quoted: x.q, 'Quoted %': pct(x.q, x.n) }));
    const noQuo = enq.filter((d) => !quoted.has(d.id) && d.orderStatus !== 'Regretted' && d.orderStatus !== 'Completed').length;
    body = xCards([[enq.length, 'Enquiries'], [enq.filter((d) => (d.orderStatus || 'Pending') === 'Pending').length, 'Pending', 'pipe-4'], [enq.filter((d) => d.orderStatus === 'Completed').length, 'Completed', 'pipe-3'],
      [enq.filter((d) => d.orderStatus === 'Regretted').length, 'Regretted', 'alert'], [noQuo, 'Open, no quotation yet', 'pipe-2']])
      + xTable(['Source', 'Enquiries', 'Pending', 'Completed', 'Regretted', 'Quoted', 'Quoted %'], rows);
  } else {
    const m = {}, mk = (d) => (d.date || d.createdAt || '').toString().slice(0, 7);
    const g = (k) => (m[k] = m[k] || { e: 0, q: 0, pi: 0, w: 0, wv: 0, qv: 0 });
    xDocs(R, 'enquiry').forEach((d) => { if (mk(d)) g(mk(d)).e++; });
    xDocs(R, 'proforma').forEach((d) => { if (mk(d)) g(mk(d)).pi++; });
    xDocs(R, 'quotation').forEach((d) => { if (!mk(d)) return; const x = g(mk(d)); x.q++; x.qv += d.value; if (d.orderStatus === 'Win') { x.w++; x.wv += d.value; } });
    const rows = Object.keys(m).sort().reverse().map((k) => { const x = m[k]; return { Month: new Date(k + '-01').toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }), Enquiries: x.e, Quotations: x.q, Proforma: x.pi, Won: x.w,
      'Quotation Value (₹)': fmtMoney(x.qv), 'Won Value (₹)': fmtMoney(x.wv), 'Win %': pct(x.w, x.q) }; });
    body = xTable(['Month', 'Enquiries', 'Quotations', 'Proforma', 'Won', 'Quotation Value (₹)', 'Won Value (₹)', 'Win %'], rows);
  }
  el('reportBody').innerHTML = `<h2 style="margin-bottom:10px;">${escapeHtml(label)}</h2>` + body;
  R.title = 'Anupam 360 — ' + label; R.prefix = 'anupam360-sales-' + sub;
}

function xCustomers(R) {
  const { branch } = R.filters, user = reportUser();
  let custs = R.data.companies;
  if (branch) custs = custs.filter((c) => companyBranches(c).includes(branch));
  if (!canSeeAll()) custs = custs.filter((c) => c.createdById === state.me.user_id || (c.assignedIds || []).includes(state.me.user_id));
  else if (user) custs = custs.filter((c) => String(c.createdById) === String(user) || (c.assignedIds || []).map(String).includes(String(user)));
  return custs;
}

export function renderCustX(R) {
  const sub = R.custXSub, custs = xCustomers(R);
  const label = (CUSTX_REPORTS.find((r) => r[0] === sub) || [])[1] || 'Customer report';
  let body = '';
  if (sub === 'missing') {
    const checks = [['GST', (c) => c.gstNumber], ['Website', (c) => c.website], ['Area', (c) => c.area], ['City', (c) => c.city], ['State', (c) => c.state], ['Pincode', (c) => c.pincode], ['Industry', (c) => c.industry],
      ['Phone', (c) => c.contacts.some((k) => k.phone)], ['Email', (c) => c.contacts.some((k) => k.email)]];
    const rows = custs.map((c) => {
      const miss = checks.filter(([, f]) => !f(c)).map((x) => x[0]);
      return { _id: c.id, Customer: c.name + (c.plant ? ' — ' + c.plant : ''), 'Missing Count': miss.length, Missing: miss.join(', ') || 'Complete', 'Assigned To': (c.assignedTo || []).join(', ') || '—', 'Added By': c.createdByName || '—' };
    }).filter((r) => r['Missing Count']).sort((a, b) => b['Missing Count'] - a['Missing Count']);
    const counts = checks.map(([n, f]) => [custs.filter((c) => !f(c)).length, 'No ' + n, 'pipe-1']);
    body = xCards([[custs.length, 'Customers checked'], [rows.length, 'With missing details', 'alert'], ...counts.slice(0, 3)])
      + xTable(['Customer', 'Missing Count', 'Missing', 'Assigned To', 'Added By'], rows.map((r) => ({ ...r })), { open: 'customer', empty: 'All customers have complete details.' });
    body += `<p class="sub" style="margin-top:8px;">Missing counts per field: ${counts.map((c) => `${c[1]}: ${c[0]}`).join(' · ')}</p>`;
  } else {
    const keyFns = {
      industry: (c) => [c.industry], source: (c) => [c.source], potential: (c) => [c.potential], state: (c) => [c.state], area: (c) => [c.area], city: (c) => [c.city],
      assigned: (c) => c.assignedTo || [], addedby: (c) => [c.createdByName], brand: (c) => c.interestedBrands || [], product: (c) => c.interestedProducts || [],
      language: (c) => c.preferredLanguages || [], transport: (c) => [c.transportPreference], courier: (c) => [c.courierPreference],
    };
    const qBy = {};
    R.data.salesDocs.filter((d) => d.type === 'quotation').forEach((d) => { const x = (qBy[d.customerId] = qBy[d.customerId] || { q: 0, w: 0, wv: 0 }); x.q++; if (d.orderStatus === 'Win') { x.w++; x.wv += d.value; } });
    const grp = {}; let unset = 0;
    custs.forEach((c) => {
      let keys = (keyFns[sub](c) || []).filter(Boolean); if (!keys.length) { keys = ['(Not set)']; unset++; }
      keys.forEach((k) => { const x = (grp[k] = grp[k] || { n: 0, q: 0, w: 0, wv: 0 }); x.n++; const y = qBy[c.id]; if (y) { x.q += y.q; x.w += y.w; x.wv += y.wv; } });
    });
    const rows = Object.entries(grp).sort((a, b) => b[1].n - a[1].n).map(([k, x]) => ({ Group: k, Customers: x.n, '% of Customers': pct(x.n, custs.length), Quotations: x.q, Won: x.w, 'Won Value (₹)': fmtMoney(x.wv) }));
    const col = label.replace(/^By /, '').replace(/^./, (m) => m.toUpperCase());
    rows.forEach((r) => { r[col] = r.Group; });
    body = xCards([[custs.length, 'Customers'], [rows.length, 'Groups', 'pipe-2'], [unset, 'Not set', 'pipe-4']]) + xTable([col, 'Customers', '% of Customers', 'Quotations', 'Won', 'Won Value (₹)'], rows);
    if (['brand', 'product', 'language', 'assigned'].includes(sub)) body += '<p class="sub" style="margin-top:8px;">A customer with several selections is counted once under each, so group totals can add up to more than the number of customers.</p>';
  }
  el('reportBody').innerHTML = `<h2 style="margin-bottom:10px;">${escapeHtml(label)}</h2>` + body;
  R.title = 'Anupam 360 — Customers ' + label.toLowerCase(); R.prefix = 'anupam360-customers-' + sub;
}
