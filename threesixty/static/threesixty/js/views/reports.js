// Reports — every number is computed on the server (`/360/api/reports/<name>/`) with the
// same role rules as the API: Admin / Branch Manager see everything and may pick a
// user, everyone else sees their own data, and a Sales Manager has no Sales Performance
// or Customer Activity tab. Click any number to see the records behind it; export to
// Excel or PDF with the filters currently on screen.
import { api } from '../api.js';
import { state } from '../state.js';
import { el, escapeHtml, fmtMoney, toast, apiErrorMessage, openModal, closeModal, renderTable } from '../ui.js';

let tabs = [];
let canPickUser = false;
let current = null;
const filters = { from: '', to: '', branch_id: '', user_id: '', days: '30', mode: 'both', interaction_type: '', type: '', status: '' };

function params(extra = {}) {
  const p = new URLSearchParams();
  Object.entries({ ...filters, ...extra }).forEach(([k, v]) => { if (v) p.set(k, v); });
  return p.toString();
}

function showItems(title, bucket) {
  if (!bucket || !bucket.count) { toast('Nothing behind this number.', 'info'); return; }
  const rows = bucket.items.map((i) => ({
    Record: escapeHtml(i.label), Customer: escapeHtml(i.customer || ''), Date: escapeHtml(i.date || ''), Detail: escapeHtml(i.by || i.status || (i.documents || []).join(', ') || ''),
  }));
  openModal(`<h2>${escapeHtml(title)} (${bucket.count})</h2><div class="table-scroll">${renderTable(['Record', 'Customer', 'Date', 'Detail'], rows, { empty: 'Nothing here.' })}</div>
    ${bucket.truncated ? '<p class="sub">Showing the first 500.</p>' : ''}<div class="modal-actions"><button class="btn" id="dr-close">Close</button></div>`,
  { onMount: (m) => { m.querySelector('#dr-close').onclick = closeModal; } });
}

const num = (label, value, bucket) => `<button class="stat" ${bucket ? `data-drill="${escapeHtml(label)}"` : ''} style="text-align:left;">
  <div class="sub">${escapeHtml(label)}</div><div style="font-size:1.5rem;font-weight:700;">${escapeHtml(value)}</div></button>`;

function bindDrill(root, result, map) {
  root.querySelectorAll('[data-drill]').forEach((b) => b.onclick = () => showItems(b.dataset.drill, result.numbers[map[b.dataset.drill]]));
}

const RENDER = {
  'sales-performance': (r) => {
    const s = r.summary;
    return `<div class="stat-grid">${num('Enquiries', s.enquiries, true)}${num('Quotations', s.quotations, true)}${num('Orders won', s.orders_won, true)}
      ${num('Enquiry → quotation %', s.enquiry_to_quotation_pct + '%')}${num('Quotation → win %', s.quotation_to_win_pct + '%')}
      ${num('Quotation value', '₹' + fmtMoney(s.quotation_value))}${num('Won value', '₹' + fmtMoney(s.won_value), false)}${num('Lost value', '₹' + fmtMoney(s.lost_value))}
      ${num('Pending value', '₹' + fmtMoney(s.pending_value))}</div>
      <h3>By branch</h3>${renderTable(['Branch', 'Enquiries', 'Quotations', 'Won', 'Won value'], r.by_branch.map((x) => ({ Branch: escapeHtml(x.branch), Enquiries: x.enquiries, Quotations: x.quotations, Won: x.won, 'Won value': '₹' + fmtMoney(x.won_value) })))}
      <h3>By person</h3>${renderTable(['Person', 'Enquiries', 'Quotations', 'Won', 'Won value'], r.by_person.map((x) => ({ Person: escapeHtml(x.person), Enquiries: x.enquiries, Quotations: x.quotations, Won: x.won, 'Won value': '₹' + fmtMoney(x.won_value) })))}`;
  },
  'customer-activity': (r) => `<h3>Top customers by won value</h3>${renderTable(['Customer', 'Orders', 'Won value'], r.top_customers.map((x) => ({ Customer: escapeHtml(x.customer), Orders: x.orders, 'Won value': '₹' + fmtMoney(x.won_value) })), { empty: 'No won orders in this period.' })}
      <div class="stat-grid">${num('New customers', r.numbers.new_customers.count, true)}</div>`,
  'not-contacted': (r) => `<div class="field-row"><div class="field"><label>Not in the last (days)</label><input type="number" id="rf-days" value="${filters.days}"></div>
      <div class="field"><label>Mode</label><select id="rf-mode">${[['both', 'Neither called nor visited'], ['call', 'Not called'], ['visit', 'Not visited'], ['either', 'Either']].map(([v, l]) => `<option value="${v}" ${filters.mode === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div></div>
      ${renderTable(['Customer', 'State', 'Area', 'Days since call', 'Days since visit'], r.results.map((x) => ({ Customer: escapeHtml(x.customer), State: escapeHtml(x.state), Area: escapeHtml(x.area), 'Days since call': x.days_since_call === null ? 'never' : x.days_since_call, 'Days since visit': x.days_since_visit === null ? 'never' : x.days_since_visit })), { empty: 'Everyone has been contacted.' })}`,
  'user-performance': (r) => renderTable(['Name', 'Calls', 'Visits', 'Appointments', 'Not visited', 'Visited %', 'Follow-up calls', 'Customers called', 'Customers visited', 'Present', 'Late', 'Absent'],
    r.results.map((x, i) => {
      const b = (k, v) => `<a data-user="${i}" data-key="${k}" style="cursor:pointer;color:var(--primary);font-weight:600;">${v}</a>`;
      return { Name: escapeHtml(x.name), Calls: b('calls', x.calls), Visits: b('visits', x.visits), Appointments: b('appointments', x.appointments),
        'Not visited': b('appointments_not_visited', x.appointments_not_visited), 'Visited %': x.visit_pct + '%', 'Follow-up calls': b('follow_up_calls', x.follow_up_calls),
        'Customers called': b('customers_called', x.customers_called), 'Customers visited': b('customers_visited', x.customers_visited),
        Present: x.attendance.present, Late: x.attendance.late, Absent: x.attendance.absent };
    }), { empty: 'No people to show.' }),
  'sales-reports': (r) => `<div class="field-row"><div class="field"><label>Type</label><select id="rf-type"><option value="">All</option>${['enquiry', 'quotation', 'proforma', 'po', 'dc'].map((t) => `<option ${filters.type === t ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
      <div class="field"><label>Status</label><input id="rf-status" value="${escapeHtml(filters.status)}"></div></div>
      <p class="sub">Total value ₹${fmtMoney(r.total_value)}</p>${renderTable(['Number', 'Date', 'Type', 'Branch', 'Customer', 'Status', 'Value', 'By'], r.results.map((x) => ({ Number: escapeHtml(x.number), Date: x.date, Type: x.type, Branch: escapeHtml(x.branch), Customer: escapeHtml(x.customer), Status: escapeHtml(x.status), Value: '₹' + fmtMoney(x.value), By: escapeHtml(x.by) })), { empty: 'No documents.' })}`,
  'customer-reports': (r) => renderTable(['Customer', 'City', 'State', 'Industry', 'Potential', 'Contacts', 'Last call', 'Last visit', 'Added'], r.results.map((x) => ({ Customer: escapeHtml(x.customer), City: escapeHtml(x.city), State: escapeHtml(x.state), Industry: escapeHtml(x.industry), Potential: escapeHtml(x.potential), Contacts: x.contacts, 'Last call': x.last_call || '—', 'Last visit': x.last_visit || '—', Added: x.added })), { empty: 'No customers.' }),
  'payment-collection': (r) => `<p class="sub">Outstanding ₹${fmtMoney(r.total_outstanding)}</p>
      <div class="stat-grid">${r.ageing.map((a) => num(a.bucket, `${a.count} · ₹${fmtMoney(a.balance)}`, true)).join('')}</div>
      <h3>By customer</h3>${renderTable(['Customer', 'Invoiced', 'Received', 'Balance'], r.by_customer.map((x) => ({ Customer: escapeHtml(x.customer), Invoiced: '₹' + fmtMoney(x.invoiced), Received: '₹' + fmtMoney(x.received), Balance: '₹' + fmtMoney(x.balance) })))}`,
  'interaction-log': (r) => `<div class="stat-grid">${Object.entries(r.tiles).map(([k, v]) => `<button class="stat" data-type="${k}" style="text-align:left;${filters.interaction_type === k ? 'outline:2px solid var(--primary);' : ''}"><div class="sub">${k}</div><div style="font-size:1.5rem;font-weight:700;">${v}</div></button>`).join('')}</div>
      ${renderTable(['Date', 'What', 'Customer', 'By'], r.results.map((x) => ({ Date: x.date, What: escapeHtml(x.label), Customer: escapeHtml(x.customer || ''), By: escapeHtml(x.by || '') })), { empty: 'Nothing logged.' })}`,
};

const DRILL_MAP = {
  'sales-performance': { Enquiries: 'enquiries', Quotations: 'quotations', 'Orders won': 'won' },
  'customer-activity': { 'New customers': 'new_customers' },
  'payment-collection': { '0-30 days': '0-30 days', '31-60 days': '31-60 days', '61-90 days': '61-90 days', '90+ days': '90+ days' },
};

async function renderReport(root, body) {
  body.innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    const result = await api.get(`reports/${current}/?${params()}`);
    body.innerHTML = RENDER[current](result);
    if (DRILL_MAP[current]) bindDrill(body, result, DRILL_MAP[current]);
    body.querySelectorAll('[data-user]').forEach((a) => a.onclick = () => showItems(a.dataset.key.replace(/_/g, ' '), result.results[Number(a.dataset.user)].numbers[a.dataset.key]));
    body.querySelectorAll('[data-type]').forEach((b) => b.onclick = () => { filters.interaction_type = filters.interaction_type === b.dataset.type ? '' : b.dataset.type; renderReport(root, body); });
    const rerun = () => renderReport(root, body);
    [['rf-days', 'days'], ['rf-mode', 'mode'], ['rf-type', 'type'], ['rf-status', 'status']].forEach(([id, key]) => { const n = body.querySelector('#' + id); if (n) n.onchange = () => { filters[key] = n.value; rerun(); }; });
  } catch (e) { body.innerHTML = `<div class="empty-state">${escapeHtml(apiErrorMessage(e))}</div>`; }
}

export async function mountReports(root) {
  const index = await api.get('reports/');
  tabs = index.reports;
  canPickUser = index.can_pick_user;
  if (!tabs.find((t) => t.key === current)) current = tabs.length ? tabs[0].key : null;
  const users = canPickUser ? state.employees : [];
  root.innerHTML = `
    <div class="tabbar">${tabs.map((t) => `<button data-tab="${t.key}" class="${t.key === current ? 'active' : ''}">${escapeHtml(t.title)}</button>`).join('')}</div>
    <div class="card"><div class="field-row">
      <div class="field"><label>From</label><input type="date" id="rf-from" value="${filters.from}"></div>
      <div class="field"><label>To</label><input type="date" id="rf-to" value="${filters.to}"></div>
      <div class="field"><label>Branch</label><select id="rf-branch"><option value="">All</option>${state.branches.map((b) => `<option value="${b.id}" ${String(filters.branch_id) === String(b.id) ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('')}</select></div>
      ${canPickUser ? `<div class="field"><label>User</label><select id="rf-user"><option value="">Everyone</option>${users.map((u) => `<option value="${u.user_id}" ${String(filters.user_id) === String(u.user_id) ? 'selected' : ''}>${escapeHtml(u.full_name)}</option>`).join('')}</select></div>` : ''}
      <div class="field" style="align-self:flex-end;"><button class="btn" id="rp-xlsx">Excel</button> <button class="btn" id="rp-pdf">PDF</button></div>
    </div></div><div id="rp-body" style="margin-top:12px;"></div>`;
  const body = root.querySelector('#rp-body');
  root.querySelectorAll('[data-tab]').forEach((b) => b.onclick = () => { current = b.dataset.tab; mountReports(root); });
  [['rf-from', 'from'], ['rf-to', 'to'], ['rf-branch', 'branch_id'], ['rf-user', 'user_id']].forEach(([id, key]) => { const n = root.querySelector('#' + id); if (n) n.onchange = () => { filters[key] = n.value; renderReport(root, body); }; });
  const exportAs = (fmt) => { window.location.href = `/360/api/reports/${current}/?${params({ format: fmt })}`; };
  root.querySelector('#rp-xlsx').onclick = () => exportAs('xlsx');
  root.querySelector('#rp-pdf').onclick = () => exportAs('pdf');
  if (current) await renderReport(root, body);
}
