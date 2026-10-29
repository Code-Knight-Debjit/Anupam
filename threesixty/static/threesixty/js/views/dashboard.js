// Dashboard — the Admin gets the company-wide view; everyone else a personal one
// (REQ-ROLE-05). All numbers come from the server (`/360/api/dashboard/...`), so they
// follow the same permissions as the rest of the API. Click a number for the records.
import { api } from '../api.js';
import { isAdmin } from '../state.js';
import { navigate } from '../router.js';
import { el, escapeHtml, fmtMoney, fmtDateTime, toast, apiErrorMessage, openModal, closeModal, renderTable } from '../ui.js';

const tile = (label, value, attrs = '') => `<button class="stat" ${attrs} style="text-align:left;"><div class="sub">${escapeHtml(label)}</div><div style="font-size:1.6rem;font-weight:700;">${escapeHtml(value)}</div></button>`;

function calendarHtml(cal) {
  const days = Object.keys(cal).sort();
  if (!days.length) return '<p class="sub">No tasks due this month.</p>';
  return days.map((d) => `<div style="margin-bottom:6px;"><strong>${d}</strong> ${cal[d].map((t) => `<span class="badge" title="${escapeHtml(t.title)}">${escapeHtml(t.title.slice(0, 28))}</span>`).join(' ')}</div>`).join('');
}

async function renderAdmin(root, limit = 10) {
  const d = await api.get(`dashboard/admin/?activity_limit=${limit}`);
  const from = d.period.from, to = d.period.to;
  root.innerHTML = `
    <div class="card"><div class="flex-between"><h3 style="margin:0;">Pending approvals</h3><button class="btn sm" id="goApprovals">Open</button></div>
      <p style="font-size:1.4rem;font-weight:700;margin:6px 0;">${d.approvals.pending}</p>
      ${d.approvals.latest.map((a) => `<div class="sub">${escapeHtml(a.by)} — ${escapeHtml(a.type)} — ${escapeHtml(a.label)}</div>`).join('')}</div>
    <div class="stat-grid" style="margin-top:12px;">
      ${tile('Open enquiries', d.pipeline.open_enquiries, 'data-go="enquiry"')}${tile('Open quotations', d.pipeline.open_quotations, 'data-go="quotation"')}
      ${tile('Open proformas', d.pipeline.open_proformas, 'data-go="proforma"')}${tile('Pending POs', d.pipeline.pending_pos, 'data-go="po"')}
      ${tile('Challans pending invoicing', d.pipeline.challans_pending_invoicing, 'data-go="dc"')}</div>
    <div class="card" style="margin-top:12px;"><h3>Outstanding payments — ₹${fmtMoney(d.payments.outstanding_total)}</h3>
      ${renderTable(['Customer', 'Balance'], d.payments.top.map((p) => ({ Customer: escapeHtml(p.customer), Balance: '₹' + fmtMoney(p.balance) })), { empty: 'Nothing outstanding.' })}</div>
    <div class="card" style="margin-top:12px;"><h3>Employees (${from} → ${to})</h3>
      ${renderTable(['Name', 'Customers added', 'Contacts added', 'Documents raised', 'Last activity'], d.employees.map((e) => ({
        Name: escapeHtml(e.name),
        'Customers added': `<a data-drill="customers" data-user="${e.user_id}" style="cursor:pointer;color:var(--primary);font-weight:600;">${e.customers_added}</a>`,
        'Contacts added': `<a data-drill="contacts" data-user="${e.user_id}" style="cursor:pointer;color:var(--primary);font-weight:600;">${e.contacts_added}</a>`,
        'Documents raised': `<a data-drill="documents" data-user="${e.user_id}" style="cursor:pointer;color:var(--primary);font-weight:600;">${e.documents_raised}</a>`,
        'Last activity': e.last_activity ? fmtDateTime(e.last_activity) : '—' })))}</div>
    <div class="card" style="margin-top:12px;"><div class="flex-between"><h3 style="margin:0;">Recent activity</h3><button class="btn sm" id="moreActivity">${limit > 10 ? 'Show less' : 'Show more'}</button></div>
      ${d.activity.map((a) => `<div class="sub">${fmtDateTime(a.at)} — ${escapeHtml(a.text)}</div>`).join('') || '<p class="sub">Nothing yet.</p>'}</div>
    <div class="card" style="margin-top:12px;"><h3>Attendance today</h3>${Object.entries(d.attendance_today).map(([k, v]) => `<span class="badge">${escapeHtml(k)}: ${v}</span>`).join(' ')}</div>
    <div class="card" style="margin-top:12px;"><h3>Task calendar</h3>${calendarHtml(d.calendar)}</div>`;
  root.querySelector('#goApprovals').onclick = () => navigate('customers');
  root.querySelectorAll('[data-go]').forEach((b) => b.onclick = () => navigate('sales', b.dataset.go));
  root.querySelector('#moreActivity').onclick = () => renderAdmin(root, limit > 10 ? 10 : 50);
  root.querySelectorAll('[data-drill]').forEach((a) => a.onclick = async () => {
    try {
      const res = await api.get(`dashboard/admin/drill/?user_id=${a.dataset.user}&what=${a.dataset.drill}`);
      openModal(`<h2>${escapeHtml(a.dataset.drill)} (${res.count})</h2>${renderTable(['Record', 'Date'], res.items.map((i) => ({ Record: escapeHtml(i.label), Date: escapeHtml(i.date || '') })), { empty: 'Nothing.' })}
        <div class="modal-actions"><button class="btn" id="dr-close">Close</button></div>`, { onMount: (m) => { m.querySelector('#dr-close').onclick = closeModal; } });
    } catch (e) { toast(apiErrorMessage(e), 'error'); }
  });
}

async function renderPersonal(root, range = {}) {
  const qs = new URLSearchParams(range).toString();
  const d = await api.get(`dashboard/personal/${qs ? '?' + qs : ''}`);
  const a = d.activity, p = d.pending;
  root.innerHTML = `
    <div class="card"><div class="field-row"><div class="field"><label>From</label><input type="date" id="pd-from" value="${d.period.from}"></div>
      <div class="field"><label>To</label><input type="date" id="pd-to" value="${d.period.to}"></div></div></div>
    <h3>Tasks</h3><div class="stat-grid">${tile('Pending', d.tasks.pending, 'data-nav="tasks"')}${tile('Due today', d.tasks.due_today, 'data-nav="tasks"')}${tile('Overdue', d.tasks.overdue, 'data-nav="tasks"')}${tile('Outreach calls pending', d.outreach_pending, 'data-nav="callinglist"')}</div>
    <h3>My activity</h3><div class="stat-grid">${tile('Calls done', a.calls_done)}${tile('Appointments taken', a.appointments_taken)}${tile('Visits made', a.visits_made)}${tile('Appointments not visited', a.appointments_not_visited)}${tile('Appointment → visit', a.visit_pct + '%')}</div>
    <h3>My open documents</h3><div class="stat-grid">${tile('Enquiries', p.enquiries, 'data-go="enquiry"')}${tile('Quotations', p.quotations, 'data-go="quotation"')}${tile('Proformas', p.proformas, 'data-go="proforma"')}${tile('Challans', p.challans, 'data-go="dc"')}${tile('Pending POs', p.pos, 'data-go="po"')}</div>
    <h3>My payments</h3><div class="stat-grid">${tile('Pending', d.payments.pending, 'data-nav="payments"')}${tile('Completed', d.payments.completed)}</div>
    <div class="card" style="margin-top:12px;"><h3>Attendance</h3><p class="sub">Today: in ${d.attendance.today.check_in || '—'} · out ${d.attendance.today.check_out || '—'}</p>
      ${Object.entries(d.attendance.month).map(([k, v]) => `<span class="badge">${escapeHtml(k)}: ${v}</span>`).join(' ')}</div>
    <div class="card" style="margin-top:12px;"><h3>Task calendar</h3>${calendarHtml(d.calendar)}</div>`;
  root.querySelectorAll('[data-nav]').forEach((b) => b.onclick = () => navigate(b.dataset.nav));
  root.querySelectorAll('[data-go]').forEach((b) => b.onclick = () => navigate('sales', b.dataset.go));
  const change = () => renderPersonal(root, { from: root.querySelector('#pd-from').value, to: root.querySelector('#pd-to').value });
  root.querySelector('#pd-from').onchange = change;
  root.querySelector('#pd-to').onchange = change;
}

export async function mountDashboard(root) {
  try { await (isAdmin() ? renderAdmin(root) : renderPersonal(root)); }
  catch (e) { root.innerHTML = `<div class="empty-state">${escapeHtml(apiErrorMessage(e))}</div>`; }
}
