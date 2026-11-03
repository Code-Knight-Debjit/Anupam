// Dashboard — same screen as the reference: greeting banner with the attendance strip, then either the company view
// (Admin: approvals, sales-pipeline tiles, payment collection, team activity, recent activity) or the personal view
// (everyone else: period picker + tiles + "My last 7 days"). Numbers come from the server (`/360/api/dashboard/…`),
// so they follow the same permissions as the rest of the API.
import { api } from '../api.js';
import { state, roleLabel } from '../state.js';
import { navigate } from '../router.js';
import { el, escapeHtml, fmtMoney, fmtDate, fmtDateTime, customAlert, apiErrorMessage, openModal, closeModal, renderTable } from '../ui.js';
import { approvalsHtml, wireApprovals } from '../approvals_ui.js';
import { checkIn, checkOut, fmtTime, fmtDur } from '../attendance_actions.js';

// Period state survives navigating away and back, like the reference's module-level variables.
let period = 'month';
let from = '', to = '';
let activityShowAll = false;

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

/** Presets become a from/to pair (the API only knows dates); "all" is a deliberately wide window. */
function periodRange() {
  const now = new Date(); now.setHours(0, 0, 0, 0);
  if (period === 'custom') return { from: from || '2000-01-01', to: to || iso(now) };
  if (period === 'today') return { from: iso(now), to: iso(now) };
  if (period === 'week') { const d = new Date(now); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return { from: iso(d), to: iso(now) }; }
  if (period === 'month') return { from: iso(new Date(now.getFullYear(), now.getMonth(), 1)), to: iso(now) };
  return { from: '2000-01-01', to: iso(now) };
}

// ---- greeting banner -------------------------------------------------------------------------------------------
async function renderAttStrip(box) {
  const h = await api.get('dashboard/home/');
  const hr = new Date().getHours();
  const greet = hr < 12 ? 'Good morning' : hr < 17 ? 'Good afternoon' : 'Good evening';
  const dateTxt = new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  const { due_today: due, overdue: late } = h.tasks;
  let msg, btn = '';
  if (!h.today.check_in) { msg = 'Not checked in yet'; btn = '<button class="btn" id="dashCheckInBtn">Check in</button>'; }
  else if (!h.today.check_out) { msg = `Checked in at ${fmtTime(h.today.check_in)}${h.today.late ? ' (late)' : ''}`; btn = '<button class="btn" id="dashCheckOutBtn">Check out</button>'; }
  else msg = `${fmtTime(h.today.check_in)} – ${fmtTime(h.today.check_out)} · worked ${fmtDur(h.today.worked_minutes)}`;
  const sub = h.team ? `<small>Team: ${h.team.in} of ${h.team.total} checked in${h.team.leave_waiting ? ` · ${h.team.leave_waiting} leave request(s) waiting` : ''}</small>` : '';
  box.innerHTML = `<div class="dash-hero">
    <div class="hi"><div class="g">${greet}</div><div class="n">${escapeHtml(h.name)}</div><div class="d">${dateTxt}</div>
      <div class="chips">
        <span class="hchip" data-go="tasks">${due} task${due === 1 ? '' : 's'} due today</span>
        <span class="hchip" data-go="tasks">${late} overdue</span>
      </div></div>
    <div class="att"><div class="t"><b>Attendance</b> · ${msg}</div>${sub}<div class="btns">${btn}<button class="btn ghost" data-go="attendance">Open attendance</button></div></div>
  </div>`;
  box.querySelectorAll('[data-go]').forEach((n) => n.onclick = () => navigate(n.dataset.go));
  const ci = el('dashCheckInBtn'); if (ci) ci.onclick = async () => { if (await checkIn()) renderAttStrip(box); };
  const co = el('dashCheckOutBtn'); if (co) co.onclick = async () => { if (await checkOut()) renderAttStrip(box); };
}

const tile = (n, label, cls, go, ic) =>
  `<div class="dash-card ${cls}${go ? ' clickable' : ''}${n ? '' : ' zero'}" ${go ? `data-go="${go}"` : ''}><span class="ic">${ic || ''}</span><div class="n">${n}</div><div class="l">${label}</div></div>`;
const section = (title, hint, tiles) =>
  `<div class="dash-sec"><div class="dash-sec-title">${title}<small>${hint}</small></div><div class="dash-grid">${tiles.join('')}</div></div>`;
const goTo = (target) => { const [view, sub] = target.split(':'); navigate(view, sub); };

// ---- company view (Admin) ----------------------------------------------------------------------------------------
async function drill(userId, what, name) {
  const res = await api.get(`dashboard/admin/drill/?user_id=${userId}&what=${what}`);
  const customers = what === 'customers';
  const table = customers
    ? renderTable(['Customer Name', 'City', 'Contacts', 'Added On'], res.items.map((i) => ({ 'Customer Name': escapeHtml(i.name), City: escapeHtml(i.city || '—'), Contacts: i.contact_count, 'Added On': fmtDate(i.added_on) })), { empty: 'No customers added yet.' })
    : renderTable(['Contact Name', 'Job Title', 'Company', 'Phone', 'Email'], res.items.map((i) => ({ 'Contact Name': escapeHtml(i.name), 'Job Title': escapeHtml(i.job_title || '—'), Company: escapeHtml(i.company), Phone: escapeHtml(i.phone || '—'), Email: escapeHtml(i.email || '—') })), { empty: 'No contacts added yet.' });
  openModal(`<h2>${customers ? 'Customers added' : 'Contacts added'}</h2>
    <p class="modal-sub">${res.count} ${customers ? 'customer(s)' : 'contact(s)'} added by ${escapeHtml(name)}</p>
    ${table}<div class="modal-actions"><button class="btn" id="eaClose">Close</button></div>`, { onMount: (m) => { m.querySelector('#eaClose').onclick = closeModal; } });
}

async function renderFull(root) {
  const limit = activityShowAll ? 500 : 10;
  const [d, pending] = await Promise.all([api.get(`dashboard/admin/?activity_limit=${limit}`), api.all('approvals/', { status: 'pending' })]);
  const p = d.pipeline;
  el('dashApprovals').innerHTML = approvalsHtml(pending);
  wireApprovals(el('dashApprovals'), pending, () => renderFull(root));
  const pipe = (n, label, cls, go, ic) => tile(n, label, cls, go, ic);
  el('dashPipeline').innerHTML =
    pipe(p.open_enquiries, 'Open enquiries', 'pipe-1', 'sales:enquiry', '🔍') + pipe(p.open_quotations, 'Open quotations', 'pipe-2', 'sales:quotation', '📝') +
    pipe(p.open_proformas, 'Open proforma invoices', 'pipe-3', 'sales:proforma', '🧾') + pipe(p.pending_pos, 'Pending PO', 'pipe-4', 'sales:po', '🛒') +
    pipe(p.challans_pending_invoicing, 'Delivery challans pending', 'pipe-5', 'sales:dc', '🚚');
  const top = d.payments.top;
  el('dashPayments').innerHTML = top.length ? `
    <div class="activity-item"><div class="a-name">Total outstanding</div><div class="a-name" style="color:#c24d3f;">₹${fmtMoney(d.payments.outstanding_total)}</div></div>
    ${top.map((x) => `<div class="activity-item">
        <div><div class="a-name">${escapeHtml(x.customer || '—')}</div><div class="a-meta">${escapeHtml(x.contact || '')}</div></div>
        <div class="a-meta" style="font-weight:600;">₹${fmtMoney(x.balance)}</div></div>`).join('')}` : '<p class="sub">No pending collections.</p>';
  const link = (n, uid, what, name) => n ? `<span class="link-btn" style="text-decoration:underline; cursor:pointer;" data-drill="${what}" data-user="${uid}" data-name="${escapeHtml(name)}">${n}</span>` : n;
  el('dashTable').innerHTML = `<tr><th>Employee</th><th>Role</th><th>Customers added</th><th>Contacts added</th><th>Sales docs raised</th><th>Last activity</th></tr>
    ${d.employees.map((e) => `<tr><td>${escapeHtml(e.name)}</td>
        <td><span class="role-tag ${escapeHtml(roleLabel(e.role).replace(/\s/g, ''))}">${escapeHtml(roleLabel(e.role))}</span></td>
        <td>${link(e.customers_added, e.user_id, 'customers', e.name)}</td><td>${link(e.contacts_added, e.user_id, 'contacts', e.name)}</td>
        <td>${e.documents_raised}</td><td>${e.last_activity ? fmtDate(e.last_activity) : '—'}</td></tr>`).join('') || '<tr><td colspan="6">No employees yet.</td></tr>'}`;
  el('dashTable').querySelectorAll('[data-drill]').forEach((a) => a.onclick = () => drill(a.dataset.user, a.dataset.drill, a.dataset.name).catch((e) => customAlert(apiErrorMessage(e))));
  const feed = d.activity;
  el('dashActivity').innerHTML = feed.length
    ? `<div style="${activityShowAll ? 'max-height:520px; overflow-y:auto;' : ''}">${feed.map((r) => `
        <div class="activity-item"><div><div class="a-name">${escapeHtml(r.label)}</div><div class="a-meta">${escapeHtml(r.meta)}</div></div>
        <div class="a-meta">${fmtDateTime(r.at)}</div></div>`).join('')}</div>`
      + (d.activity_total > 10 ? `<div style="margin-top:10px;"><button type="button" class="btn" id="dashActivityMoreBtn">${activityShowAll ? 'Show less' : `View more (${d.activity_total - 10} more)`}</button></div>` : '')
    : '<p class="sub">No activity yet.</p>';
  const more = el('dashActivityMoreBtn'); if (more) more.onclick = () => { activityShowAll = !activityShowAll; renderFull(root); };
  el('dashFull').querySelectorAll('[data-go]').forEach((n) => n.onclick = () => goTo(n.dataset.go));
  // Opening the company view marks today's customer count as seen (the sidebar badge shows what is new since).
  localStorage.setItem(`360:dashSeen:${state.me.user_id}`, String(d.customers_total));
  document.getElementById('dashBadge').style.display = pending.length ? '' : 'none';
}

// ---- personal view (Branch Manager / Branch Staff / Sales Manager) -----------------------------------------------------
function weekChartHtml(week) {
  const colors = { Call: '#2f6fb5', Visit: '#1f8a6a', Appointment: '#8a4fb8' };
  const totals = week.map((d) => d.Call + d.Visit + d.Appointment);
  const max = Math.max(4, ...totals);
  const sum = totals.reduce((a, b) => a + b, 0);
  const cols = week.map((d, i) => {
    const h = 100 / max;
    const [y, m, day] = d.date.split('-').map(Number);
    const seg = ['Call', 'Visit', 'Appointment'].map((k) => (d[k] ? `<i title="${d[k]} ${k}" style="height:${d[k] * h}px;background:${colors[k]}"></i>` : '')).join('');
    return `<div class="wk-col${i === 6 ? ' today' : ''}"><div class="v">${totals[i] || ''}</div><div class="stack" style="height:${Math.max(totals[i] * h, 0)}px">${seg}</div><div class="dn">${i === 6 ? 'Today' : new Date(y, m - 1, day).toLocaleDateString('en-IN', { weekday: 'short' })}</div></div>`;
  }).join('');
  return `<div class="dash-sec"><div class="dash-sec-title">My last 7 days<small>${sum} call${sum === 1 ? '' : 's'}, visits &amp; appointments logged</small></div>
    <div class="wk-chart"><div class="wk-bars">${cols}</div>
    <div class="wk-leg"><span><i style="background:${colors.Call}"></i>Calls</span><span><i style="background:${colors.Visit}"></i>Visits</span><span><i style="background:${colors.Appointment}"></i>Appointments</span></div></div></div>`;
}

async function renderPersonal(root) {
  el('dashPeriodSelect').value = period;
  el('dashFrom').value = from; el('dashTo').value = to;
  el('dashRangeClear').style.display = (from || to) ? '' : 'none';
  const showApprovals = !!state.flags.is_branch_manager;
  el('dashPersonalApprovalsWrap').style.display = showApprovals ? '' : 'none';
  if (showApprovals) {
    const pending = await api.all('approvals/', { status: 'pending' });
    el('dashPersonalApprovals').innerHTML = approvalsHtml(pending);
    wireApprovals(el('dashPersonalApprovals'), pending, () => renderPersonal(root));
  }
  const r = periodRange();
  const d = await api.get(`dashboard/personal/?from=${r.from}&to=${r.to}${period === 'custom' ? '&custom=1' : ''}`);
  const a = d.activity, pe = d.pending;
  const periodLabel = { today: 'today', week: 'this week', month: 'this month', all: 'all time', custom: 'selected dates' }[period];
  el('dashPersonalGrid').innerHTML =
    section('Needs your attention', 'tap a card to open it', [
      tile(d.tasks.pending, 'Tasks pending', 'pipe-1', 'tasks', '📋'),
      tile(d.outreach_pending, 'Outreach calls pending', 'pipe-4', 'callinglist', '📲'),
      tile(a.appointments_not_visited, 'Appointments not yet visited', 'alert', '', '⏰'),
      tile(d.payments.pending, 'Payments to collect', 'alert', 'payments', '💸'),
    ]) +
    section('My activity', periodLabel, [
      tile(a.calls_done, 'Calls done', 'pipe-3', '', '📞'),
      tile(a.appointments_taken, 'Appointments taken', 'pipe-2', '', '🗓️'),
      tile(a.visits_made, 'Appointments visited', 'pipe-5', '', '🤝'),
      tile(d.payments.completed, 'Payments collected', 'pipe-3', 'paymenthistory', '💵'),
    ]) +
    section('My sales pipeline', 'open items', [
      tile(pe.enquiries, 'Enquiries pending', 'pipe-1', 'sales:enquiry', '🔍'),
      tile(pe.quotations, 'Quotations pending', 'pipe-2', 'sales:quotation', '📝'),
      tile(pe.proformas, 'Proforma invoices pending', 'pipe-3', 'sales:proforma', '🧾'),
      tile(pe.pos, 'POs pending', 'pipe-4', 'sales:po', '🛒'),
      tile(pe.challans, 'Delivery challans pending', 'pipe-5', 'sales:dc', '🚚'),
    ]) + weekChartHtml(d.week);
  el('dashPersonalGrid').querySelectorAll('[data-go]').forEach((n) => n.onclick = () => goTo(n.dataset.go));
}

export async function mountDashboard(root) {
  root.innerHTML = `
    <div class="view active glassv" id="view-dashboard">
      <div class="view-head"><div>
        <p class="brand-eyebrow">Overview</p><h1>Dashboard</h1>
        <p class="sub" id="dashSubline"></p>
      </div></div>
      <div id="dashAttStrip"></div>
      <div id="dashPersonal" style="display:none;">
        <div id="dashPersonalApprovalsWrap" style="display:none;">
          <h2 style="margin-bottom:10px;">Pending edit &amp; delete approvals</h2>
          <div class="panel-box" style="max-width:none; margin-bottom:26px;" id="dashPersonalApprovals"></div>
        </div>
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px; flex-wrap:wrap;">
          <h2 style="margin:0;">Show my activity for</h2>
          <select id="dashPeriodSelect" title="Presets apply to the Done / Taken / Visited counts. Custom dates apply to every number.">
            <option value="today">Today</option><option value="week">This week</option><option value="month">This month</option>
            <option value="all">All time</option><option value="custom">Custom dates</option>
          </select>
          <label style="display:inline-flex; align-items:center; gap:6px; font-size:12.5px; color:var(--text-dim);">From <input type="date" id="dashFrom"></label>
          <label style="display:inline-flex; align-items:center; gap:6px; font-size:12.5px; color:var(--text-dim);">To <input type="date" id="dashTo"></label>
          <button type="button" class="btn btn-icon" id="dashRangeClear" style="display:none;">Clear dates</button>
        </div>
        <div id="dashPersonalGrid" style="margin-bottom:26px;"></div>
      </div>
      <div id="dashFull">
        <h2 style="margin-bottom:10px;">Pending edit &amp; delete approvals</h2>
        <div class="panel-box" style="max-width:none; margin-bottom:26px;" id="dashApprovals"></div>
        <h2 style="margin-bottom:10px;">Sales pipeline</h2>
        <div class="dash-grid" id="dashPipeline" style="margin-bottom:26px;"></div>
        <h2 style="margin-bottom:10px;">Payment collection</h2>
        <div class="panel-box" style="max-width:none; margin-bottom:26px;" id="dashPayments"></div>
        <h2 style="margin-bottom:10px;">Team activity</h2>
        <div class="table-scroll" style="margin-bottom:26px;"><table class="report" id="dashTable"></table></div>
        <h2 style="margin-bottom:10px;">Recent activity</h2>
        <div class="panel-box" style="max-width:none;" id="dashActivity"></div>
      </div>
    </div>`;
  const personal = !!state.flags.uses_personal_dashboard;
  el('dashPersonal').style.display = personal ? '' : 'none';
  el('dashFull').style.display = personal ? 'none' : '';
  el('dashSubline').textContent = personal ? 'Your own pending work and activity at a glance.' : 'Balance overview of everything — approvals, pipeline, and collections.';
  await renderAttStrip(el('dashAttStrip'));
  if (personal) {
    el('dashPeriodSelect').addEventListener('change', (e) => {
      period = e.target.value;
      if (period !== 'custom') { from = ''; to = ''; }
      renderPersonal(root);
    });
    const onDates = () => { from = el('dashFrom').value; to = el('dashTo').value; period = (from || to) ? 'custom' : 'month'; renderPersonal(root); };
    el('dashFrom').addEventListener('change', onDates);
    el('dashTo').addEventListener('change', onDates);
    el('dashRangeClear').addEventListener('click', () => { from = ''; to = ''; period = 'month'; renderPersonal(root); });
    await renderPersonal(root);
  } else {
    await renderFull(root);
  }
}
