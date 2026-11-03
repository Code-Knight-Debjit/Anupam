// The "User Performance" tab: per person, calls and visits (with the customer, contact and notes behind each), follow-up
// calls, appointments, sales, collections, tasks and attendance, over a chosen period. Built the way the reference builds it.
import { api } from '../api.js';
import { state, roleLabel } from '../state.js';
import { navigate } from '../router.js';
import { el, escapeHtml, fmtMoney, initials } from '../ui.js';
import { branchNamesOf } from '../report_data.js';
import { statusColor, isStatusCol } from '../report_export.js';
import { canSeeAll, inDateRange, xDate, openDrill } from './reports.js';

export const upState = { range: 'month', from: '', to: '', branch: '', user: '' };
let upData = null;
const num = (v) => Number(v) || 0;

// ---- small time helpers (the reference's att* functions) --------------------------------------------------------------------------
const localISO = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const toMin = (hm) => { if (!hm) return null; const p = hm.split(':'); return (+p[0]) * 60 + (+p[1]); };
const fmtTime = (hm) => { if (!hm) return '—'; const m = toMin(hm), h = Math.floor(m / 60), mm = m % 60; return ((h % 12) || 12) + ':' + String(mm).padStart(2, '0') + ' ' + (h < 12 ? 'AM' : 'PM'); };
const fmtDur = (mins) => (mins == null || mins < 0 ? '—' : Math.floor(mins / 60) + 'h ' + String(mins % 60).padStart(2, '0') + 'm');
const fmtDate = (iso) => { const p = iso.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }); };
const dow = (iso) => { const p = iso.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]).getDay(); };
const dayName = (iso) => ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][dow(iso)];
const SRC_LABEL = { quotation: 'Quotation', enquiry: 'Enquiry', proforma: 'Proforma', po: 'Pending PO', dc: 'Delivery Challan' };

function period() {
  const iso = localISO(), now = new Date(); let from, to = iso;
  if (upState.range === 'month') from = iso.slice(0, 8) + '01';
  else if (upState.range === 'lastmonth') { from = localISO(new Date(now.getFullYear(), now.getMonth() - 1, 1)); to = localISO(new Date(now.getFullYear(), now.getMonth(), 0)); }
  else if (['7', '30', '90'].includes(upState.range)) { const d = new Date(); d.setDate(d.getDate() - (+upState.range - 1)); from = localISO(d); }
  else { from = upState.from || iso.slice(0, 8) + '01'; to = upState.to || iso; }
  if (to > iso) to = iso;
  return { from, to };
}

export function renderUpFilters(redraw) {
  const R = [['month', 'This month'], ['lastmonth', 'Last month'], ['7', 'Last 7 days'], ['30', 'Last 30 days'], ['90', 'Last 90 days'], ['custom', 'Custom dates']];
  el('reportFilterRow').innerHTML = `
    <select id="upRange" style="font-weight:700;">${R.map(([v, l]) => `<option value="${v}" ${upState.range === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
    ${upState.range === 'custom' ? `<input type="date" id="upFrom" value="${escapeHtml(upState.from)}" title="From date"><input type="date" id="upTo" value="${escapeHtml(upState.to)}" title="To date">` : ''}
    <select id="upBranch"><option value="">All branches</option>${state.branches.map((b) => `<option value="${escapeHtml(b.name)}" ${upState.branch === b.name ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('')}</select>
    ${canSeeAll() ? `<select id="upUser"><option value="">All users</option>${state.employees.map((e) => `<option value="${e.user_id}" ${String(upState.user) === String(e.user_id) ? 'selected' : ''}>${escapeHtml(e.full_name)}</option>`).join('')}</select>` : ''}
    <button class="btn" id="upClear" type="button">Reset</button>`;
  el('upRange').addEventListener('change', (e) => { upState.range = e.target.value; renderUpFilters(redraw); redraw(); });
  if (el('upFrom')) el('upFrom').addEventListener('change', (e) => { upState.from = e.target.value; redraw(); });
  if (el('upTo')) el('upTo').addEventListener('change', (e) => { upState.to = e.target.value; redraw(); });
  el('upBranch').addEventListener('change', (e) => { upState.branch = e.target.value; redraw(); });
  if (el('upUser')) el('upUser').addEventListener('change', (e) => { upState.user = e.target.value; redraw(); });
  el('upClear').addEventListener('click', () => { Object.assign(upState, { range: 'month', from: '', to: '', branch: '', user: '' }); renderUpFilters(redraw); redraw(); });
}

// ---- drill-down ------------------------------------------------------------------------------------------------------------------------
function upDrill(empId, kind) {
  const d = upData; if (!d) return;
  const all = empId === 'all';
  const it = all ? { e: { user_id: 'all', full_name: 'All users' } } : d.per.find((p) => String(p.e.user_id) === String(empId)); if (!it) return;
  const tag = (arr, nm) => arr.map((r) => ({ ...r, User: nm }));
  const x = all ? { cv: d.per.flatMap((p) => tag(p.x.cv, p.e.full_name)), apRows: d.per.flatMap((p) => tag(p.x.apRows, p.e.full_name)), newRows: d.per.flatMap((p) => tag(p.x.newRows, p.e.full_name)) } : it.x;
  const LB = { calls: 'Calls', visits: 'Visits', callsvisits: 'Calls & visits', follow: 'Follow-up calls (sales)', appts: 'Appointments', apvisited: 'Appointments visited', called: 'Customers called', visited: 'Customers visited', contacted: 'Customers contacted', newcust: 'New customers added' };
  const sortD = (r) => [...r].sort((p, q) => (q._d || '').localeCompare(p._d || ''));
  const withArea = (r) => ({ ...r, 'City / Area': r['City / Area'] || [r.City, r.Area].filter((v) => v && v !== '—').join(' / ') || '—' });
  let cols, rows;
  if (['calls', 'visits', 'callsvisits', 'follow', 'appts', 'apvisited'].includes(kind)) {
    const ty = { calls: 'Call', visits: 'Visit', follow: 'Follow-up call', appts: 'Appointment' }[kind];
    rows = sortD(kind === 'appts' ? x.apRows : kind === 'apvisited' ? x.apRows.filter((r) => r.Visited === 'Yes') : x.cv.filter((r) => (kind === 'callsvisits' ? (r.Type === 'Call' || r.Type === 'Visit') : r.Type === ty))).map(withArea);
    cols = ['Date', 'Type', 'Source', 'Customer', 'Contact', 'Phone', 'City / Area', 'Notes', 'Follow-up', 'Joint with'];
    if (kind === 'appts' || kind === 'apvisited') cols.splice(2, 0, 'Visited');
    if (all) cols.unshift('User');
  } else if (kind === 'newcust') {
    rows = sortD(x.newRows); cols = ['Date', 'Customer', 'City / Area', 'State', 'Phone', 'Contacts'];
  } else {
    const okT = { called: ['Call', 'Follow-up call'], visited: ['Visit'], contacted: ['Call', 'Follow-up call', 'Visit'] }[kind];
    const g = {};
    x.cv.filter((r) => okT.includes(r.Type)).forEach((r) => {
      const k = r._cid || r.Customer;
      const o = (g[k] = g[k] || { _cid: r._cid, _d: '', Customer: r.Customer, 'City / Area': [r.City, r.Area].filter((v) => v && v !== '—').join(' / ') || '—', Calls: 0, 'Follow-up calls': 0, Visits: 0, 'Last date': '', _ct: new Set() });
      if (r.Type === 'Call') o.Calls++; else if (r.Type === 'Visit') o.Visits++; else o['Follow-up calls']++;
      if (r.Contact && r.Contact !== '—') o._ct.add(r.Contact);
      if (r._d > o._d) { o._d = r._d; o['Last date'] = r.Date; }
    });
    rows = sortD(Object.values(g)).map((o) => ({ ...o, 'Contacts reached': [...o._ct].join(', ') || '—' }));
    cols = ['Customer', 'City / Area', 'Contacts reached', 'Calls', 'Follow-up calls', 'Visits', 'Last date'];
    if (kind === 'contacted') {
      x.newRows.forEach((n) => {
        let o = rows.find((r) => r._cid === n._cid);
        if (!o) { o = { _cid: n._cid, _d: n._d, Customer: n.Customer, 'City / Area': n['City / Area'], 'Contacts reached': '—', Calls: 0, 'Follow-up calls': 0, Visits: 0, 'Last date': n.Date }; rows.push(o); }
        o['New customer'] = 'Yes';
      });
      rows = sortD(rows); cols.push('New customer');
    }
  }
  openDrill(LB[kind] + ' — ' + it.e.full_name, `${rows.length} record${rows.length === 1 ? '' : 's'} · ${xDate(d.from)} to ${xDate(d.to)}`, cols, rows, LB[kind].toLowerCase().replace(/[^a-z]+/g, '-'));
}

// ---- tables ------------------------------------------------------------------------------------------------------------------------------
function upTbl(cols, rows, drill) {
  return `<div class="table-scroll" style="margin-bottom:6px;"><table class="report"><tr>${cols.map((c) => `<th>${escapeHtml(c)}</th>`).join('')}</tr>
    ${rows.map((r, ri) => `<tr>${cols.map((c) => {
    if (drill && drill.cols[c] && Number(r[c]) > 0) return `<td class="drill-num" title="Click to see the details" data-up="${drill.ids[ri]}|${drill.cols[c]}">${escapeHtml(String(r[c]))}</td>`;
    const v = r[c] === undefined || r[c] === null || r[c] === '' ? '—' : String(r[c]);
    const col = isStatusCol(c) ? statusColor(v) : null;
    return `<td>${col ? `<span style="display:inline-block;padding:2px 9px;border-radius:10px;font-size:11.5px;font-weight:700;color:#fff;background:${col};white-space:nowrap;">${escapeHtml(v)}</span>` : escapeHtml(v)}</td>`;
  }).join('')}</tr>`).join('') || '<tr><td colspan="' + cols.length + '">Nothing logged in this period.</td></tr>'}
  </table></div>`;
}
function customerRow(c, ct, extra) {
  return { _cid: c.id, Customer: (c.name || '—') + (c.plant ? ' — ' + c.plant : ''), Contact: (ct && ct.name) || '—', 'Job Title': (ct && ct.jobTitle) || '—', Phone: (ct && ct.phone) || '—',
    City: c.city || '—', Area: c.area || '—', State: c.state || '—', Potential: c.potential || '—', Industry: c.industry || '—', ...extra };
}

function attShort(b, DPC) {
  const t = b.a.t;
  const chips = [['Present', t.present], ['Late', t.late], ['Half days', t.half], ['Absent', t.absent], ['Leave', t.leave], ['Hours worked', fmtDur(t.worked)]]
    .map(([l, v]) => `<span style="display:inline-block;background:var(--accent-bg);color:var(--text);border-radius:12px;padding:3px 10px;margin:0 6px 6px 0;font-size:12px;"><b>${escapeHtml(String(v))}</b> ${l}</span>`).join('');
  const strip = b.a.det.map((r) => `<span title="${escapeHtml(fmtDate(r.d) + ' · ' + r.label)}" style="display:inline-block;min-width:22px;padding:2px 0;margin:0 2px 3px 0;border-radius:4px;text-align:center;font-size:10.5px;font-weight:600;color:#fff;background:${DPC[r.code] || '#999'};">${+r.d.slice(8)}</span>`).join('');
  return `<div>${chips}</div><div>${strip}</div>`;
}

// ---- the report ---------------------------------------------------------------------------------------------------------------------------
export async function renderUserPerformance(R) {
  const { from, to } = period();
  const user = canSeeAll() ? upState.user : String(state.me.user_id);
  const branch = upState.branch;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  let people = [...state.employees];
  if (!canSeeAll()) people = people.filter((e) => e.user_id === state.me.user_id);
  if (branch) people = people.filter((e) => branchNamesOf(e.user_id).includes(branch));
  if (user) people = people.filter((e) => String(e.user_id) === String(user));
  people = people.sort((a, b) => a.full_name.localeCompare(b.full_name));
  const inR = (d) => inDateRange(d, from, to);
  const M = {};
  people.forEach((e) => { M[e.user_id] = { apRows: [], newRows: [], calls: 0, visits: 0, appts: 0, apVis: 0, logs: 0, cust: 0, enq: 0, quo: 0, won: 0, lost: 0, pend: 0, wv: 0, lv: 0, pv: 0, pi: 0, pay: 0, rcpt: 0, tDone: 0, tOpen: 0, tOver: 0, tOnTime: 0, contacted: new Set(), cv: [] }; });
  const companies = R.data.companies;
  companies.forEach((c) => {
    const x = M[c.createdById];
    if (x && inR(c.createdAt)) {
      x.cust++; x.contacted.add(c.id);
      x.newRows.push({ _cid: c.id, _d: String(c.createdAt).slice(0, 10), Date: xDate(c.createdAt), Customer: (c.name || '—') + (c.plant ? ' — ' + c.plant : ''), 'City / Area': [c.city, c.area].filter(Boolean).join(' / ') || '—', State: c.state || '—', Phone: (c.contacts[0] || {}).phone || '—', Contacts: c.contacts.length });
    }
  });
  companies.forEach((c) => c.contacts.forEach((ct) => ct.interactions.forEach((i) => {
    if (i.isCopy || !M[i.userId]) return;
    const dt = i.date || i.createdAt; if (!inR(dt)) return;
    const x = M[i.userId], t = i.type;
    let label = '';
    if (t === 'Call' || t === 'Cold Call') { x.calls++; label = 'Call'; }
    else if (t === 'Visit') { x.visits++; label = 'Visit'; }
    else if (t === 'Appointment') {
      x.appts++;
      const apD = new Date(dt || 0), vis = ct.interactions.some((v) => v.type === 'Visit' && !v.isCopy && new Date(v.date || v.createdAt || 0) >= apD);
      if (vis) x.apVis++;
      x.apRows.push(customerRow(c, ct, { Visited: vis ? 'Yes' : 'No', _d: String(dt).slice(0, 10), Date: xDate(dt), Type: 'Appointment', Source: 'Customer log', Notes: i.notes || '', 'Follow-up': i.followupDate ? xDate(i.followupDate) : '', 'Joint with': (i.jointWith || []).map((j) => j.name).join(', '), Location: '' }));
      return;
    } else return;
    x.contacted.add(c.id);
    x.cv.push(customerRow(c, ct, { _d: String(dt).slice(0, 10), Date: xDate(dt), Type: label, Source: 'Customer log', Notes: i.notes || '', 'Follow-up': i.followupDate ? xDate(i.followupDate) : '',
      'Joint with': (i.jointWith || []).map((j) => j.name).join(', '), Location: i.location ? `https://www.google.com/maps?q=${i.location.lat},${i.location.lng}` : '' }));
  })));
  R.data.salesDocs.forEach((d) => {
    d.callLog.forEach((l) => {
      if (!M[l.userId] || !inR(l.timestamp)) return;
      const x = M[l.userId]; x.logs++;
      const c = companies.find((k) => k.id === d.customerId); if (!c) return;
      const ct = c.contacts.find((k) => k.id === d.contactId) || c.contacts.find((k) => k.name === d.contactName) || c.contacts[0];
      x.contacted.add(c.id);
      x.cv.push(customerRow(c, ct, { _d: String(l.timestamp).slice(0, 10), Date: xDate(l.timestamp), Type: 'Follow-up call', Source: (SRC_LABEL[d.type] || 'Sales') + ' ' + (d.docNumber || ''), Notes: l.message || '', 'Follow-up': l.callLaterDate ? xDate(l.callLaterDate) : '', 'Joint with': '', Location: '' }));
    });
    const x = M[d.createdById]; if (!x || !inR(d.date || d.createdAt)) return;
    if (d.type === 'enquiry') x.enq++;
    else if (d.type === 'proforma') x.pi++;
    else if (d.type === 'quotation') { x.quo++; if (d.orderStatus === 'Win') { x.won++; x.wv += d.value; } else if (d.orderStatus === 'Lose') { x.lost++; x.lv += d.value; } else { x.pend++; x.pv += d.value; } }
  });
  R.data.payments.forEach((p) => p.receipts.forEach((r) => { if (M[r.recordedById] && inR(r.date || r.createdAt)) { M[r.recordedById].pay += r.amount; M[r.recordedById].rcpt++; } }));
  R.data.tasks.forEach((t) => t.assignees.forEach((id) => {
    const x = M[id]; if (!x) return;
    if (t.status === 'Completed') { if (inR(t.completedAt || t.dueDate || t.createdAt)) { x.tDone++; if (!t.dueDate || (t.completedAt || '').slice(0, 10) <= String(t.dueDate).slice(0, 10)) x.tOnTime++; } }
    else { x.tOpen++; if (t.dueDate && new Date(t.dueDate) < today) x.tOver++; }
  }));
  // attendance (the server decides each day's status; people outside the viewer's team come back empty)
  const days = []; { const p = from.split('-'); const d = new Date(+p[0], +p[1] - 1, +p[2]); while (localISO(d) <= to && days.length < 366) { days.push(localISO(d)); d.setDate(d.getDate() + 1); } }
  const attRows = people.length ? await api.get(`attendance/report/?from=${from}&to=${to}${people.length === 1 ? '&user_id=' + people[0].user_id : ''}`).then((r) => (Array.isArray(r) ? r : r.results || r.rows || [])).catch(() => []) : [];
  const A = {};
  people.forEach((e) => {
    const start = e.work_start || '09:30', end = e.work_end || '18:30', sched = toMin(end) - toMin(start);
    const t = { present: 0, late: 0, half: 0, absent: 0, leave: 0, off: 0, worked: 0, lateMin: 0, wdays: 0, inSum: 0, inN: 0 }, det = [];
    attRows.filter((r) => r.user_id === e.user_id && r.code).forEach((r) => {
      const code = r.code;
      if (code === 'P') t.present++; else if (code === 'L') { t.present++; t.late++; t.lateMin += r.late_minutes || 0; }
      else if (code === 'H') t.half++; else if (code === 'A') t.absent++; else if (code === 'LV') t.leave++; else if (code === 'O') t.off++;
      if (code !== 'O' && code !== 'LV') t.wdays++;
      if (r.worked_minutes) t.worked += r.worked_minutes;
      if (r.check_in) { t.inSum += toMin(r.check_in); t.inN++; }
      det.push({ d: r.date, code, label: r.label, late: r.late_minutes || 0, worked: r.worked_minutes, r, diff: r.worked_minutes != null ? r.worked_minutes - sched : null });
    });
    const pd = t.present + t.half * 0.5; t.pct = t.wdays ? Math.round(pd / t.wdays * 100) : null; t.pd = pd;
    A[e.user_id] = { h: { start, end }, t, det };
  });
  const fmtDiff = (m) => (m == null ? '—' : (m >= 0 ? '+' : '-') + fmtDur(Math.abs(m)));
  const fmtAvgIn = (t) => (t.inN ? fmtTime(String(Math.floor(t.inSum / t.inN / 60)).padStart(2, '0') + ':' + String(Math.round(t.inSum / t.inN) % 60).padStart(2, '0')) : '—');
  const winPct = (x) => (x.quo ? Math.round(x.won / x.quo * 100) + '%' : '—');
  const per = people.map((e) => ({ e, x: M[e.user_id], a: A[e.user_id] })).sort((p, q) => q.x.wv - p.x.wv || (q.x.calls + q.x.visits) - (p.x.calls + p.x.visits));
  const act = (x) => x.calls + x.visits;
  // ----- tables -----
  const T1c = ['User', 'Role', 'Calls', 'Visits', 'Customers Contacted', 'Enquiries', 'Quotations', 'Won', 'Won Value (₹)', 'Win %', 'Tasks Done', 'Overdue Tasks', 'Days Present', 'Attendance %'];
  const T1 = per.map(({ e, x, a }) => ({ User: e.full_name, Role: roleLabel(e.role) || '—', Calls: x.calls, Visits: x.visits, 'Customers Contacted': x.contacted.size, Enquiries: x.enq, Quotations: x.quo, Won: x.won, 'Won Value (₹)': fmtMoney(x.wv), 'Win %': winPct(x), 'Tasks Done': x.tDone, 'Overdue Tasks': x.tOver, 'Days Present': a.t.pd, 'Attendance %': a.t.pct == null ? '—' : a.t.pct + '%' }));
  const T2c = ['User', 'Calls', 'Visits', 'Follow-up Calls (Sales)', 'Appointments', 'Appointments Visited', 'Visit % of Appointments', 'Customers Contacted'];
  const T2 = per.map(({ e, x }) => ({ User: e.full_name, Calls: x.calls, Visits: x.visits, 'Follow-up Calls (Sales)': x.logs, Appointments: x.appts, 'Appointments Visited': x.apVis, 'Visit % of Appointments': x.appts ? Math.round(x.apVis / x.appts * 100) + '%' : '—', 'Customers Contacted': x.contacted.size }));
  const T3c = ['User', 'Enquiries', 'Quotations', 'Won', 'Lost', 'Pending', 'Win %', 'Won Value (₹)', 'Lost Value (₹)', 'Pending Value (₹)', 'Avg Won Deal (₹)', 'Proforma', 'Payments Collected (₹)', 'Receipts'];
  const T3 = per.map(({ e, x }) => ({ User: e.full_name, Enquiries: x.enq, Quotations: x.quo, Won: x.won, Lost: x.lost, Pending: x.pend, 'Win %': winPct(x), 'Won Value (₹)': fmtMoney(x.wv), 'Lost Value (₹)': fmtMoney(x.lv), 'Pending Value (₹)': fmtMoney(x.pv), 'Avg Won Deal (₹)': x.won ? fmtMoney(x.wv / x.won) : '—', Proforma: x.pi, 'Payments Collected (₹)': fmtMoney(x.pay), Receipts: x.rcpt }));
  const T4c = ['User', 'Tasks Done', 'On-time %', 'Open Tasks', 'Overdue Tasks'];
  const T4 = per.map(({ e, x }) => ({ User: e.full_name, 'Tasks Done': x.tDone, 'On-time %': x.tDone ? Math.round(x.tOnTime / x.tDone * 100) + '%' : '—', 'Open Tasks': x.tOpen, 'Overdue Tasks': x.tOver }));
  const T5c = ['Name', 'Role', 'Work hours', 'Present', 'Late', 'Avg. late by', 'Avg. check-in', 'Half days', 'Absent', 'Leave', 'Off / holiday', 'Hours worked', 'Avg hours / day', 'Attendance %'];
  const T5 = per.map(({ e, a }) => ({ Name: e.full_name, Role: roleLabel(e.role) || '—', 'Work hours': fmtTime(a.h.start) + ' - ' + fmtTime(a.h.end), Present: a.t.present, Late: a.t.late, 'Avg. late by': a.t.late ? fmtDur(Math.round(a.t.lateMin / a.t.late)) : '—',
    'Avg. check-in': fmtAvgIn(a.t), 'Half days': a.t.half, Absent: a.t.absent, Leave: a.t.leave, 'Off / holiday': a.t.off, 'Hours worked': fmtDur(a.t.worked),
    'Avg hours / day': a.t.pd && a.t.worked ? fmtDur(Math.round(a.t.worked / a.t.pd)) : '—', 'Attendance %': a.t.pct == null ? '—' : a.t.pct + '%' }));
  const CVc = ['Date', 'Type', 'Customer', 'Contact', 'Phone', 'City / Area', 'Notes', 'Follow-up'];
  const ADc = ['Date', 'Day', 'Status', 'Check-in', 'Late by', 'Check-out', 'Worked', 'vs. schedule', 'Note'];
  const sections = [{ heading: 'Overview — all users', cols: T1c, rows: T1 }, { heading: 'Activity — calls & visits', cols: T2c, rows: T2 }, { heading: 'Sales & collections', cols: T3c, rows: T3 },
    { heading: 'Tasks', cols: T4c, rows: T4 }, { heading: 'Attendance summary', cols: T5c, rows: T5 }];
  const blocks = per.map(({ e, x, a }) => {
    const cv = [...x.cv].sort((p, q) => q._d.localeCompare(p._d)).map((r) => ({ ...r, 'City / Area': [r.City, r.Area].filter((v) => v && v !== '—').join(' / ') || '—' }));
    const ad = a.det.map((r) => ({ Date: fmtDate(r.d), Day: dayName(r.d), Status: r.label, 'Check-in': r.r.check_in ? fmtTime(r.r.check_in) : '—', 'Late by': r.late ? fmtDur(r.late) : '—',
      'Check-out': r.r.check_out ? fmtTime(r.r.check_out) : '—', Worked: r.worked != null ? fmtDur(r.worked) : '—', 'vs. schedule': fmtDiff(r.diff),
      Note: [r.r.note || '', r.r.in_location || r.r.out_location ? 'GPS location recorded' : ''].filter(Boolean).join('; ') }));
    const sub = `Calls ${x.calls}  |  Visits ${x.visits}  |  Follow-up calls ${x.logs}  |  Customers contacted ${x.contacted.size}  |  Quotations ${x.quo}  |  Won ${x.won} (Rs. ${fmtMoney(x.wv)})  |  Present ${a.t.present}  |  Late ${a.t.late}  |  Absent ${a.t.absent}  |  Leave ${a.t.leave}` + (a.t.pct != null ? `  |  Attendance ${a.t.pct}%` : '');
    return { e, sub, cv, cvCalls: cv.filter((r) => r.Type === 'Call'), cvVisits: cv.filter((r) => r.Type === 'Visit'), cvFollow: cv.filter((r) => r.Type === 'Follow-up call'), ad, x, a };
  });
  // ---- export (PDF / Print): attendance first, short and visual; overview dropped for a single user ----
  const DPC = { P: '#2f9e52', L: '#c98a0b', H: '#e07a2c', A: '#d9534f', LV: '#3a7bd5', O: '#7b8794' };
  const monthName = (iso) => { const p = iso.split('-'); return new Date(+p[0], +p[1] - 1, 1).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' }); };
  const attBlock = (b) => {
    const t = b.a.t, byDay = {}; b.a.det.forEach((r) => { byDay[r.d] = r; });
    const months = [];
    days.forEach((d) => {
      const k = d.slice(0, 7); let m = months[months.length - 1];
      if (!m || m.key !== k) { m = { key: k, label: monthName(d), cells: [] }; months.push(m); }
      const r = byDay[d]; const code = r ? r.code : '';
      m.cells.push({ n: +d.slice(8), code, color: code ? DPC[code] : '' });
    });
    const exc = b.a.det.filter((r) => ['A', 'L', 'H', 'LV'].includes(r.code)).map((r) => ({ Date: fmtDate(r.d), Day: dayName(r.d), Status: r.label, 'Check-in': r.r.check_in ? fmtTime(r.r.check_in) : '—', 'Check-out': r.r.check_out ? fmtTime(r.r.check_out) : '—',
      'Late by': r.late ? fmtDur(r.late) : '—', Note: [r.r.note || '', r.r.in_location || r.r.out_location ? 'GPS recorded' : ''].filter(Boolean).join('; ') }));
    return { heading: b.e.full_name + (b.e.role ? '  -  ' + roleLabel(b.e.role) : '') + ' — attendance',
      sub: `Present ${t.present}  |  Late ${t.late}  |  Half days ${t.half}  |  Absent ${t.absent}  |  Leave ${t.leave}  |  Off ${t.off}  |  Hours worked ${fmtDur(t.worked)}` + (t.pct != null ? `  |  Attendance ${t.pct}%` : ''),
      calendar: months, cols: ['Date', 'Day', 'Status', 'Check-in', 'Check-out', 'Late by', 'Note'], rows: exc, emptyNote: 'No late, absent, half-day or leave days in this period.', excTitle: 'Days to note (late / absent / half day / leave)' };
  };
  const attSummary = { heading: 'Attendance summary', cols: ['Name', 'Present', 'Late', 'Half days', 'Absent', 'Leave', 'Off / holiday', 'Hours worked', 'Attendance %'],
    rows: per.map(({ e, a }) => ({ Name: e.full_name, Present: a.t.present, Late: a.t.late, 'Half days': a.t.half, Absent: a.t.absent, Leave: a.t.leave, 'Off / holiday': a.t.off, 'Hours worked': fmtDur(a.t.worked), 'Attendance %': a.t.pct == null ? '—' : a.t.pct + '%' })) };
  const cvSecs = [];
  blocks.forEach((b) => {
    const nm = b.e.full_name + (b.e.role ? '  -  ' + roleLabel(b.e.role) : '');
    if (b.cvCalls.length) cvSecs.push({ heading: nm + ' — calls', sub: b.sub, cols: CVc, rows: b.cvCalls });
    if (b.cvVisits.length) cvSecs.push({ heading: nm + ' — visits', sub: b.cvCalls.length ? '' : b.sub, cols: CVc, rows: b.cvVisits });
    if (b.cvFollow.length) cvSecs.push({ heading: nm + ' — follow-up calls (sales)', sub: '', cols: CVc, rows: b.cvFollow });
  });
  const perfSecs = [sections[1], sections[2], sections[3]];
  R.sections = per.length === 1 ? [attBlock(blocks[0]), ...perfSecs, ...cvSecs] : [attSummary, ...blocks.map(attBlock), sections[0], ...perfSecs, ...cvSecs];
  R.legend = [['P  Present', '#2f9e52'], ['L  Present (late)', '#c98a0b'], ['H  Half day', '#e07a2c'], ['A  Absent', '#d9534f'], ['LV  Leave', '#3a7bd5'], ['O  Off / holiday', '#7b8794']];
  R.subtitle = 'Period: ' + fmtDate(from) + ' to ' + fmtDate(to) + '   |   ' + people.length + (people.length === 1 ? ' user' : ' users') + (branch ? '   |   Branch: ' + branch : '') + '   |   Overdue and open tasks are as of today';
  // ----- Excel sheets (full customer details) -----
  const allCv = [];
  per.forEach(({ e, x }) => x.cv.slice().sort((p, q) => q._d.localeCompare(p._d)).forEach((r) => {
    const o = { User: e.full_name, Date: r.Date, Type: r.Type, Source: r.Source };
    Object.keys(r).filter((k) => k[0] !== '_').forEach((k) => { if (!(k in o)) o[k] = r[k]; });
    allCv.push(o);
  }));
  const wide = per.map((_, i) => ({ ...T1[i], ...T2[i], ...T3[i], ...T4[i], ...T5[i] }));
  const attDaily = [];
  per.forEach(({ e, a }) => a.det.forEach((r) => attDaily.push({ Name: e.full_name, Date: fmtDate(r.d), Day: dayName(r.d), Status: r.label, 'Check-in': r.r.check_in ? fmtTime(r.r.check_in) : '', 'Late by': r.late ? fmtDur(r.late) : '',
    'Check-out': r.r.check_out ? fmtTime(r.r.check_out) : '', Worked: r.worked != null ? fmtDur(r.worked) : '', 'vs. schedule': r.diff != null ? fmtDiff(r.diff) : '', Note: r.r.note || '',
    'Check-in location': r.r.in_location ? `https://www.google.com/maps?q=${r.r.in_location.lat},${r.r.in_location.lng}` : '', 'Check-out location': r.r.out_location ? `https://www.google.com/maps?q=${r.r.out_location.lat},${r.r.out_location.lng}` : '' })));
  R.sheets = [{ name: 'Overview', rows: wide }, { name: 'Calls', rows: allCv.filter((r) => r.Type === 'Call') }, { name: 'Visits', rows: allCv.filter((r) => r.Type === 'Visit') },
    { name: 'Follow-up Calls', rows: allCv.filter((r) => r.Type === 'Follow-up call') }, { name: 'Attendance Summary', rows: T5 }, { name: 'Attendance Daily', rows: attDaily }];
  R.rows = wide.length ? wide : [{ User: '—' }];
  // ----- screen -----
  const totContacted = new Set(); per.forEach(({ x }) => x.contacted.forEach((id) => totContacted.add(id)));
  const pcts = per.map(({ a }) => a.t.pct).filter((v) => v != null);
  const topSales = per.length && per[0].x.wv > 0 ? per[0].e.full_name : '—';
  const topAct = [...per].sort((p, q) => act(q.x) - act(p.x))[0];
  const totOver = per.reduce((n, { x }) => n + x.tOver, 0);
  const cards = [
    [per.length, 'Users', 'pipe-1'], [per.reduce((n, { x }) => n + act(x), 0), 'Calls & visits', 'pipe-2'], [totContacted.size, 'Customers contacted', 'pipe-4'],
    ['₹' + fmtMoney(per.reduce((n, { x }) => n + x.wv, 0)), 'Total won value', 'pipe-3'], [pcts.length ? Math.round(pcts.reduce((a, b) => a + b, 0) / pcts.length) + '%' : '—', 'Avg attendance', 'pipe-5'],
    [totOver, 'Overdue tasks', totOver ? 'alert' : 'pipe-1'], [topSales, 'Top in won value', 'pipe-3'], [topAct && act(topAct.x) ? topAct.e.full_name : '—', 'Most active', 'pipe-2'],
  ];
  const ids = per.map(({ e }) => e.user_id);
  const drillCfg = [{ Calls: 'calls', Visits: 'visits', 'Customers Contacted': 'contacted' },
    { Calls: 'calls', Visits: 'visits', Appointments: 'appts', 'Appointments Visited': 'apvisited', 'Follow-up Calls (Sales)': 'follow', 'Customers Contacted': 'contacted' }];
  upData = { per, from, to };
  const lk = (b, label, n, k) => (n > 0 ? `<a href="#" style="color:var(--accent);font-weight:600;" data-up="${b.e.user_id}|${k}">${label} ${n}</a>` : `${label} ${n}`);
  const subHtml = (b) => {
    const rest = b.sub.split('  |  ').slice(3);
    return [lk(b, 'Calls', b.x.calls, 'calls'), lk(b, 'Visits', b.x.visits, 'visits'), lk(b, 'Follow-up calls', b.x.logs, 'follow'), ...rest.map(escapeHtml)].join('  |  ');
  };
  const secHtml = sections.map((sc, si) => `<h2 style="margin:18px 0 8px;">${escapeHtml(sc.heading)}</h2>${upTbl(sc.cols, sc.rows, drillCfg[si] ? { ids, cols: drillCfg[si] } : null)}`).join('');
  const userHtml = blocks.map((b) => `
    <details class="up-user" ${blocks.length === 1 ? 'open' : ''}>
      <summary><span class="up-av">${escapeHtml(initials(b.e.full_name))}</span><span><b>${escapeHtml(b.e.full_name)}</b> <span style="color:var(--text-faint);">${escapeHtml(roleLabel(b.e.role) || '')}</span><br><span class="up-sub">${subHtml(b)}</span></span></summary>
      <div class="up-body">
        <h3>Calls <span class="up-count">${b.cvCalls.length}</span></h3>${upTbl(CVc, b.cvCalls)}
        <h3 style="margin-top:14px;">Visits <span class="up-count">${b.cvVisits.length}</span></h3>${upTbl(CVc, b.cvVisits)}
        <h3 style="margin-top:14px;">Follow-up calls (sales) <span class="up-count">${b.cvFollow.length}</span></h3>${upTbl(CVc, b.cvFollow)}
        <h3 style="margin-top:14px;">Attendance <span class="up-count">${b.a.t.pct != null ? b.a.t.pct + '%' : '—'}</span></h3>
        <div class="up-attshort">${attShort(b, DPC)}</div>
        <button class="btn" data-up-detail style="margin-top:8px;">Detailed report (${b.ad.length} days)</button>
        <div style="display:none;margin-top:8px;">${upTbl(ADc, b.ad)}</div>
      </div>
    </details>`).join('');
  el('reportBody').innerHTML = `
    <div class="dash-grid" style="margin-bottom:12px;">${cards.map(([n, l, c]) => `<div class="dash-card ${c}${l === 'Calls & visits' && n > 0 ? ' drillable' : ''}"${l === 'Calls & visits' && n > 0 ? ' data-up="all|callsvisits" title="Click to see the details"' : ''}><div class="n"${String(n).length > 8 ? ' style="font-size:18px;"' : ''}>${escapeHtml(String(n))}</div><div class="l">${escapeHtml(l)}</div></div>`).join('')}</div>
    <p class="sub" style="margin-bottom:6px;">Period: ${escapeHtml(fmtDate(from) + ' to ' + fmtDate(to))}. Sorted by won value, then calls and visits. Exports include every customer called or visited, with contact, phone, city, area and notes.</p>
    ${secHtml}
    <h2 style="margin:22px 0 8px;">Person-wise details — customers called / visited &amp; attendance</h2>
    ${userHtml || '<div class="empty">No users to show.</div>'}`;
  el('reportBody').querySelectorAll('[data-up]').forEach((n) => {
    n.onclick = (e) => { e.preventDefault(); e.stopPropagation(); const [id, k] = n.dataset.up.split('|'); upDrill(id, k); };
  });
  el('reportBody').querySelectorAll('[data-up-detail]').forEach((btn) => {
    const label = btn.textContent;
    btn.onclick = () => { const d = btn.nextElementSibling; const open = d.style.display === 'none'; d.style.display = open ? '' : 'none'; btn.textContent = open ? 'Hide detailed report' : label; };
  });
  R.title = 'Anupam 360 — User Performance Report'; R.prefix = 'anupam360-user-performance';
}
