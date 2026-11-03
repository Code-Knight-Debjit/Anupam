// Attendance — the reference's page: subline with my hours, Today card, My month (stats + table), Holidays, Leave,
// then (Admin / Branch Manager) leave requests to approve, the team month grid (click a cell to correct a day) and
// the check-in / check-out times for one date. Day statuses, the 10-minute grace and the month tallies are worked out
// on the server (services/attendance.py); the page lays them out as the reference does.
import { api } from '../api.js';
import { state, isAdmin, isBranchManager } from '../state.js';
import { el, escapeHtml, customAlert, customConfirm, customPrompt, apiErrorMessage, openModal, closeModal, exportRowsToExcel } from '../ui.js';
import { checkIn, checkOut, fmtTime, fmtDur } from '../attendance_actions.js';

const COLORS = { P: '#1f8a4c', L: '#d9822b', H: '#b7791f', A: '#c0392b', LV: '#2f6fb5', O: '#8a94a0' };
const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const LV_COLOR = { Pending: '#d9822b', Approved: '#1f8a4c', Rejected: '#c0392b' };

const me = () => state.me.user_id;
const isApprover = () => isAdmin() || isBranchManager();
const localISO = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const fmtDate = (iso) => { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }); };
const dowOf = (iso) => { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d).getDay(); };
const leaveDays = (l) => Math.round((new Date(l.date_to) - new Date(l.date_from)) / 86400000) + 1;
const range = (l) => fmtDate(l.date_from) + (l.date_to !== l.date_from ? ' – ' + fmtDate(l.date_to) : '');

function chip(code, label) {
  if (!code) return '<span style="color:var(--text-faint);">—</span>';
  return `<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11.5px;font-weight:600;color:#fff;background:${COLORS[code] || '#888'};">${escapeHtml(label || code)}</span>`;
}
const stat = (label, val) => `<div class="stat-card" style="background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px;"><div style="font-size:11px;color:var(--text-faint);text-transform:uppercase;letter-spacing:.05em;">${label}</div><div style="font-size:22px;font-weight:600;margin-top:4px;">${val}</div></div>`;
const locLink = (loc, label) => (loc ? `<a href="https://www.google.com/maps?q=${loc.lat},${loc.lng}" target="_blank" rel="noopener">${label}</a>` : '');
function locCell(day) {
  const parts = [locLink(day.in_location, 'In'), locLink(day.out_location, 'Out')].filter(Boolean);
  return parts.length ? '📍 ' + parts.join(' · ') : '—';
}

let teamInit = false;
let holChipsBuilt = false;

async function render() {
  const today = localISO();
  const myMonth = el('attMyMonth').value || (el('attMyMonth').value = today.slice(0, 7));
  const [mine, leaves, holidays] = await Promise.all([
    api.get(`attendance/month/?month=${myMonth}${isApprover() ? '' : ''}`), api.all('leave-requests/'), api.all('holidays/')]);
  const meRow = mine.people.find((p) => p.user_id === me());
  const offs = (meRow.weekly_off === '' ? [] : String(meRow.weekly_off).split(',').map(Number)).map((d) => DOW[d]).join(' & ') || 'none';
  el('attSubline').textContent = `Your hours: ${fmtTime(meRow.work_start)} – ${fmtTime(meRow.work_end)} · Weekly off: ${offs}`;

  // Today card — always today's record, whatever month is picked below.
  const todayData = myMonth === today.slice(0, 7) ? meRow : (await api.get(`attendance/month/?month=${today.slice(0, 7)}`)).people.find((p) => p.user_id === me());
  const t = todayData.days.find((d) => d.date === today);
  const approvedLeaveToday = leaves.some((l) => l.user && l.user.id === me() && l.status === 'Approved' && l.date_from <= today && today <= l.date_to);
  const head = `<div style="flex:1;min-width:200px;"><div style="font-size:12px;color:var(--text-faint);text-transform:uppercase;letter-spacing:.05em;">Today · ${fmtDate(today)}</div>`;
  let body;
  if (!t.check_in) body = `${head}<div style="font-size:16px;margin-top:4px;">${approvedLeaveToday ? 'You are on approved leave today.' : 'You have not checked in yet.'}</div></div><button class="btn btn-primary" id="attCheckInBtn">Check in</button>`;
  else if (!t.check_out) body = `${head}<div style="font-size:16px;margin-top:4px;">Checked in at <b>${fmtTime(t.check_in)}</b> ${t.late ? chip('L', 'Late ' + fmtDur(t.late)) : chip('P', 'On time')}</div></div><button class="btn btn-primary" id="attCheckOutBtn">Check out</button>`;
  else body = `${head}<div style="font-size:16px;margin-top:4px;">In <b>${fmtTime(t.check_in)}</b> · Out <b>${fmtTime(t.check_out)}</b> · Worked <b>${fmtDur(t.worked)}</b> ${t.late ? chip('L', 'Late') : ''}</div></div><button class="btn" id="attCheckOutBtn" title="Update your check-out time">Update check-out</button>`;
  el('attTodayCard').innerHTML = `<div class="card" style="align-items:center;flex-wrap:wrap;">${body}</div><p class="sub" style="margin:6px 2px 0;">📍 Your location is recorded when you check in and check out. Your browser will ask for permission.</p>`;
  const ci = el('attCheckInBtn'); if (ci) ci.onclick = async () => { if (await checkIn()) render(); };
  const co = el('attCheckOutBtn'); if (co) co.onclick = async () => { if (await checkOut()) render(); };

  // My month
  const tl = meRow.tally;
  el('attMyStats').innerHTML = stat('Present', tl.present) + stat('Late', tl.late) + stat('Half days', tl.half) + stat('Absent', tl.absent) + stat('Leave', tl.leave) + stat('Hours worked', fmtDur(tl.worked));
  const rows = meRow.days.filter((d) => d.date <= today || d.code).map((d) => `<tr><td>${fmtDate(d.date)}</td><td>${DOW[dowOf(d.date)]}</td><td>${chip(d.code, d.label)}</td><td>${d.check_in ? fmtTime(d.check_in) : '—'}</td><td>${d.check_out ? fmtTime(d.check_out) : '—'}</td><td>${d.worked !== null && d.worked !== undefined ? fmtDur(d.worked) : '—'}</td><td>${locCell(d)}</td><td>${d.note ? escapeHtml(d.note) : ''}</td></tr>`).reverse().join('');
  el('attMyTable').innerHTML = `<div style="overflow-x:auto;"><table class="report"><tr><th>Date</th><th>Day</th><th>Status</th><th>In</th><th>Out</th><th>Worked</th><th>Location</th><th>Note</th></tr>${rows || '<tr><td colspan="8">Nothing to show for this month.</td></tr>'}</table></div>`;

  // My leaves
  const mineLeaves = leaves.filter((l) => l.user && l.user.id === me()).sort((a, b) => (b.requested_at || '').localeCompare(a.requested_at || ''));
  el('attMyLeaves').innerHTML = mineLeaves.length ? `<div style="overflow-x:auto;"><table class="report"><tr><th>Dates</th><th>Days</th><th>Reason</th><th>Status</th><th></th></tr>${mineLeaves.map((l) => `<tr><td>${range(l)}</td><td>${leaveDays(l)}</td><td>${escapeHtml(l.reason || '')}</td><td><span style="color:${LV_COLOR[l.status]};font-weight:600;">${l.status}</span>${l.decided_by ? `<div class="sub" style="margin:0;font-size:11.5px;">by ${escapeHtml(l.decided_by.full_name)}${l.decision_note ? ' — ' + escapeHtml(l.decision_note) : ''}</div>` : ''}</td><td>${l.status === 'Pending' ? `<button class="btn-danger-text" data-cancel="${l.id}">Cancel</button>` : ''}</td></tr>`).join('')}</table></div>` : '<p class="sub">No leave requests yet.</p>';
  el('attMyLeaves').querySelectorAll('[data-cancel]').forEach((b) => b.onclick = async () => {
    if (!await customConfirm('Cancel this leave request?')) return;
    try { await api.delete(`leave-requests/${b.dataset.cancel}/`); } catch (e) { await customAlert(apiErrorMessage(e)); }
    render();
  });

  renderHolidays(holidays, today);
  el('attTeamSection').style.display = isApprover() ? '' : 'none';
  if (isApprover()) await renderTeam(leaves, today);
  refreshAttBadge(leaves);
}

function refreshAttBadge(leaves) {
  const n = isApprover() ? leaves.filter((l) => l.status === 'Pending' && l.user && l.user.id !== me()).length : 0;
  const b = el('attBadge'); if (b) { b.textContent = n > 99 ? '99+' : n; b.style.display = n ? 'inline-block' : 'none'; }
}

// ---- holidays --------------------------------------------------------------------------------------------------------------
const myBranchIds = () => state.me.branch_ids || [];
function canManageHoliday(h) {
  if (isAdmin()) return true;
  if (!isBranchManager() || h.is_all_branches) return false;
  return h.branch_ids.length > 0 && h.branch_ids.every((b) => myBranchIds().includes(b));
}
function renderHolidays(holidays, today) {
  const card = el('holFormCard');
  card.style.display = isApprover() ? 'flex' : 'none';
  if (isApprover() && !holChipsBuilt) {
    const mine = isAdmin() ? state.branches : state.branches.filter((b) => myBranchIds().includes(b.id));
    el('holBranchChips').innerHTML = (isAdmin() ? '<label class="chip-check"><input type="checkbox" id="hol-all"><span>All branches</span></label>' : '')
      + mine.map((b) => `<label class="chip-check"><input type="checkbox" class="hol-branch-check" value="${b.id}"><span>${escapeHtml(b.name)}</span></label>`).join('');
    holChipsBuilt = true;
  }
  const names = (h) => (h.is_all_branches ? 'All branches' : h.branch_ids.map((id) => (state.branches.find((b) => b.id === id) || {}).name).filter(Boolean).join(', '));
  const sorted = [...holidays].sort((a, b) => a.date.localeCompare(b.date));
  const upcoming = sorted.filter((h) => h.date_to >= today), past = sorted.filter((h) => h.date_to < today).reverse();
  const row = (h) => `<tr><td>${fmtDate(h.date)}${h.date_to !== h.date ? ' – ' + fmtDate(h.date_to) : ''}</td><td>${escapeHtml(h.name)}</td><td>${escapeHtml(names(h))}</td><td class="sub" style="font-size:11.5px;">${escapeHtml((h.created_by && h.created_by.full_name) || '')}</td><td>${canManageHoliday(h) ? `<button class="btn-danger-text" data-delhol="${h.id}">Remove</button>` : ''}</td></tr>`;
  const tbl = (rows) => `<div style="overflow-x:auto;"><table class="report"><tr><th>Date</th><th>Holiday</th><th>Branch(es)</th><th>Added by</th><th></th></tr>${rows.map(row).join('')}</table></div>`;
  el('attHolidays').innerHTML = (upcoming.length ? tbl(upcoming) : '<p class="sub">No upcoming holidays for your branch.</p>')
    + (past.length ? `<details style="margin-top:8px;"><summary class="sub" style="cursor:pointer;">Past holidays (${past.length})</summary>${tbl(past.slice(0, 40))}</details>` : '');
  el('attHolidays').querySelectorAll('[data-delhol]').forEach((b) => b.onclick = async () => {
    const h = holidays.find((x) => String(x.id) === b.dataset.delhol);
    if (!await customConfirm(`Remove the holiday "${h.name}"? Those days will count as normal working days again.`)) return;
    try { await api.delete(`holidays/${h.id}/`); } catch (e) { await customAlert(apiErrorMessage(e)); }
    render();
  });
}

// ---- team ------------------------------------------------------------------------------------------------------------------
let teamData = null;
async function renderTeam(leaves, today) {
  const tm = el('attTeamMonth'); if (!tm.value) tm.value = today.slice(0, 7);
  const bsel = el('attTeamBranch');
  if (!teamInit || !bsel.options.length) {
    const prev = bsel.value;
    bsel.innerHTML = '<option value="">All branches</option>' + state.branches.map((b) => `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join('');
    bsel.value = prev; teamInit = true;
  }
  const pend = leaves.filter((l) => l.status === 'Pending' && l.user && (isAdmin() || l.user.id !== me()));
  el('attApprovals').innerHTML = pend.length ? `<div style="overflow-x:auto;"><table class="report"><tr><th>Person</th><th>Dates</th><th>Days</th><th>Reason</th><th></th></tr>${pend.map((l) => `<tr><td>${escapeHtml(l.user.full_name)}</td><td>${range(l)}</td><td>${leaveDays(l)}</td><td>${escapeHtml(l.reason || '')}</td><td style="white-space:nowrap;"><button class="btn btn-primary" style="height:32px;" data-decide="${l.id}:approve">Approve</button> <button class="btn" style="height:32px;" data-decide="${l.id}:reject">Reject</button></td></tr>`).join('')}</table></div>` : '<p class="sub">No pending leave requests.</p>';
  if (isBranchManager() && leaves.some((l) => l.user && l.user.id === me() && l.status === 'Pending')) el('attApprovals').innerHTML += '<p class="sub">Your own leave request goes to an Admin for approval.</p>';
  el('attApprovals').querySelectorAll('[data-decide]').forEach((b) => b.onclick = async () => {
    const [id, action] = b.dataset.decide.split(':');
    let note = '';
    if (action === 'reject') { const r = await customPrompt('Reason for rejecting (optional):', '', 'Reject leave'); if (r === null) return; note = (r || '').trim(); }
    try { await api.post(`leave-requests/${id}/${action}/`, { note }); } catch (e) { await customAlert(apiErrorMessage(e)); }
    render();
  });
  teamData = await api.get(`attendance/month/?month=${tm.value}${bsel.value ? '&branch=' + bsel.value : ''}`);
  const days = teamData.people[0] ? teamData.people[0].days.map((d) => d.date) : [];
  const headRow = '<tr><th style="position:sticky;left:0;background:var(--panel-2);">Name</th>' + days.map((d) => `<th style="padding:6px 4px;text-align:center;min-width:26px;">${+d.slice(8)}</th>`).join('') + '<th>P</th><th>A</th><th>LV</th><th>Late</th><th>Hours</th></tr>';
  const body = teamData.people.map((p) => {
    const cells = p.days.map((d) => {
      const bg = d.code ? COLORS[d.code] : 'transparent';
      const tip = `${p.name} · ${fmtDate(d.date)} · ${d.label || (d.date > today ? 'Upcoming' : '—')}` + (d.check_in ? ` · ${fmtTime(d.check_in)}–${fmtTime(d.check_out)}` : '');
      return `<td data-att-u="${p.user_id}" data-att-d="${d.date}" title="${escapeHtml(tip)}" style="padding:4px 2px;text-align:center;cursor:pointer;font-size:11px;font-weight:600;color:${d.code ? '#fff' : 'var(--text-faint)'};background:${bg};border-left:1px solid var(--line-soft);">${d.code || ''}</td>`;
    }).join('');
    const t2 = p.tally;
    return `<tr><td style="position:sticky;left:0;background:var(--panel);white-space:nowrap;font-weight:500;">${escapeHtml(p.name)}</td>${cells}<td>${t2.present + t2.half * 0.5}</td><td>${t2.absent}</td><td>${t2.leave}</td><td>${t2.late}</td><td style="white-space:nowrap;">${fmtDur(t2.worked)}</td></tr>`;
  }).join('');
  el('attTeamGrid').innerHTML = teamData.people.length ? `<table class="report" style="font-size:12px;">${headRow}${body}</table>` : '<p class="sub">No team members to show.</p>';
  el('attTeamGrid').querySelectorAll('td[data-att-u]').forEach((td) => td.addEventListener('click', () => openDay(Number(td.dataset.attU), td.dataset.attD)));
  const dd = el('attDayDate'); if (!dd.value) dd.value = today;
  // the check-in / check-out table for one date may fall in another month than the grid
  const dayMonth = dd.value.slice(0, 7);
  const dayData = dayMonth === tm.value ? teamData : await api.get(`attendance/month/?month=${dayMonth}${bsel.value ? '&branch=' + bsel.value : ''}`);
  const dayRows = dayData.people.map((p) => {
    const d = p.days.find((x) => x.date === dd.value) || {};
    return `<tr><td style="font-weight:500;">${escapeHtml(p.name)}</td><td>${fmtTime(p.work_start)} – ${fmtTime(p.work_end)}</td><td>${chip(d.code, d.label)}</td><td>${d.check_in ? fmtTime(d.check_in) : '—'}${d.late ? ` <span style="color:#d9822b;font-size:11.5px;">(late ${fmtDur(d.late)})</span>` : ''}</td><td>${d.check_out ? fmtTime(d.check_out) : '—'}</td><td>${d.worked !== null && d.worked !== undefined ? fmtDur(d.worked) : '—'}</td><td>${locCell(d)}</td></tr>`;
  }).join('');
  el('attDayTable').innerHTML = dayData.people.length ? `<table class="report"><tr><th>Name</th><th>Work hours</th><th>Status</th><th>Check-in</th><th>Check-out</th><th>Worked</th><th>Location</th></tr>${dayRows}</table>` : '<p class="sub">No team members to show.</p>';
}

function openDay(userId, date) {
  if (!isApprover()) return;
  const person = teamData.people.find((p) => p.user_id === userId); if (!person) return;
  const d = person.days.find((x) => x.date === date) || {};
  const statusNow = d.manual ? ({ P: 'Present', H: 'Half day', A: 'Absent', LV: 'Leave', O: 'Off / Holiday' }[d.code] || '') : '';
  openModal(`
    <h2>Correct attendance</h2>
    <p class="modal-sub">${escapeHtml(person.name)} · ${fmtDate(date)}${d.in_location || d.out_location ? ' · ' + locCell(d) : ''}</p>
    <div class="field"><label>Status</label><select id="attDayStatus"><option value="">Automatic (from check-in)</option><option>Present</option><option>Half day</option><option>Absent</option><option>Leave</option><option>Off / Holiday</option></select></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
      <div class="field"><label>Check-in</label><input type="time" id="attDayIn" value="${d.check_in || ''}"></div>
      <div class="field"><label>Check-out</label><input type="time" id="attDayOut" value="${d.check_out || ''}"></div>
    </div>
    <div class="field"><label>Note</label><input type="text" id="attDayNote" placeholder="Optional" value="${escapeHtml(d.note || '')}"></div>
    <div class="modal-actions"><button class="btn" id="attDayCancel">Cancel</button><button class="btn btn-primary" id="attDaySave">Save</button></div>`, {
    size: 'narrow',
    onMount: (m) => {
      m.querySelector('#attDayStatus').value = statusNow;
      m.querySelector('#attDayCancel').onclick = closeModal;
      m.querySelector('#attDaySave').onclick = async () => {
        const ci = m.querySelector('#attDayIn').value, co = m.querySelector('#attDayOut').value;
        if (ci && co && co < ci) { await customAlert('Check-out cannot be before check-in.'); return; }
        try { await api.post('attendance/correct/', { user_id: userId, date, status: m.querySelector('#attDayStatus').value, check_in: ci || null, check_out: co || null, note: m.querySelector('#attDayNote').value.trim() }); }
        catch (e) { await customAlert(apiErrorMessage(e)); return; }
        closeModal(); render();
      };
    },
  });
}

export async function mountAttendance(root) {
  teamInit = false; holChipsBuilt = false;
  root.innerHTML = `
    <div class="view active" id="view-attendance">
      <div class="view-head"><div><p class="brand-eyebrow">Work</p><h1>Attendance</h1><p class="sub" id="attSubline"></p></div></div>
      <div id="attTodayCard"></div>
      <div class="select-row" style="margin:18px 0 10px;"><h2 style="margin:0;font-size:16px;">My month</h2><input type="month" id="attMyMonth" style="max-width:170px;"></div>
      <div class="dash-grid" id="attMyStats"></div>
      <div id="attMyTable"></div>

      <h2 style="margin:26px 0 10px;font-size:16px;">Holidays</h2>
      <div class="card" id="holFormCard" style="display:none;flex-direction:column;align-items:stretch;">
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;">
          <div class="field"><label>From</label><input type="date" id="hol-from"></div>
          <div class="field"><label>To (optional)</label><input type="date" id="hol-to"></div>
          <div class="field" style="grid-column:span 2;min-width:200px;"><label>Holiday name</label><input type="text" id="hol-name" placeholder="e.g. Pongal, Ugadi, Diwali"></div>
        </div>
        <div class="field" style="margin-top:10px;"><label>Applies to branch(es)</label><div class="chip-group" id="holBranchChips"></div></div>
        <div style="display:flex;gap:10px;align-items:center;margin-top:10px;"><button class="btn btn-primary" id="holAddBtn">Add holiday</button><span class="sub" id="holHint" style="margin:0;"></span></div>
      </div>
      <div id="attHolidays" style="margin-top:12px;"></div>

      <h2 style="margin:26px 0 10px;font-size:16px;">Leave</h2>
      <div class="card" style="flex-direction:column;align-items:stretch;">
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;">
          <div class="field"><label>From</label><input type="date" id="lv-from"></div>
          <div class="field"><label>To</label><input type="date" id="lv-to"></div>
          <div class="field" style="grid-column:span 2;min-width:200px;"><label>Reason</label><input type="text" id="lv-reason" placeholder="e.g. Family function, medical, personal"></div>
        </div>
        <div style="display:flex;gap:10px;align-items:center;margin-top:10px;"><button class="btn btn-primary" id="lvSubmitBtn">Request leave</button><span class="sub" id="lvHint" style="margin:0;"></span></div>
      </div>
      <div id="attMyLeaves" style="margin-top:12px;"></div>

      <div id="attTeamSection" style="display:none;">
        <h2 style="margin:26px 0 10px;font-size:16px;">Leave requests to approve</h2>
        <div id="attApprovals"></div>
        <div class="select-row" style="margin:26px 0 10px;">
          <h2 style="margin:0;font-size:16px;">Team attendance</h2>
          <input type="month" id="attTeamMonth" style="max-width:170px;">
          <select id="attTeamBranch" style="max-width:190px;"></select>
          <button class="btn" id="attExportBtn">Export to Excel</button>
        </div>
        <p class="sub" style="margin:0 0 8px;">P present &middot; L late &middot; H half day &middot; A absent &middot; LV leave &middot; O weekly off or holiday. Click a cell to correct a day.</p>
        <div id="attTeamGrid" style="overflow-x:auto;"></div>
        <div class="select-row" style="margin:26px 0 10px;"><h2 style="margin:0;font-size:16px;">Check-in &amp; check-out times</h2><input type="date" id="attDayDate" style="max-width:170px;"></div>
        <div id="attDayTable" style="overflow-x:auto;"></div>
      </div>
    </div>`;
  el('attMyMonth').addEventListener('change', render);
  ['attTeamMonth', 'attDayDate', 'attTeamBranch'].forEach((id) => el(id).addEventListener('change', render));
  el('lvSubmitBtn').onclick = async () => {
    const hint = el('lvHint');
    const from = el('lv-from').value, to = el('lv-to').value || from, reason = el('lv-reason').value.trim();
    try { await api.post('leave-requests/', { date_from: from || null, date_to: to || null, reason }); }
    catch (e) { hint.textContent = apiErrorMessage(e); return; }
    hint.textContent = '';
    el('lv-from').value = ''; el('lv-to').value = ''; el('lv-reason').value = '';
    render();
  };
  el('holAddBtn').onclick = async () => {
    const hint = el('holHint');
    const all = !!(el('hol-all') && el('hol-all').checked);
    const ids = all ? [] : [...document.querySelectorAll('.hol-branch-check:checked')].map((c) => Number(c.value));
    try { await api.post('holidays/', { date: el('hol-from').value || null, date_to: el('hol-to').value || null, name: el('hol-name').value.trim(), is_all_branches: all, branch_ids: ids }); }
    catch (e) { hint.textContent = apiErrorMessage(e); return; }
    hint.textContent = '';
    el('hol-from').value = ''; el('hol-to').value = ''; el('hol-name').value = '';
    document.querySelectorAll('.hol-branch-check, #hol-all').forEach((c) => { c.checked = false; });
    render();
  };
  el('attExportBtn').onclick = async () => {
    if (!teamData || !teamData.people.length) { await customAlert('Nothing to export.'); return; }
    const rows = teamData.people.map((p) => {
      const r = { Name: p.name, 'Emp code': p.emp_code, Branch: p.branches.join(', '), 'Work hours': fmtTime(p.work_start) + ' – ' + fmtTime(p.work_end) };
      p.days.forEach((d) => { r[String(+d.date.slice(8))] = d.code; });
      r.Present = p.tally.present + p.tally.half * 0.5; r.Absent = p.tally.absent; r.Leave = p.tally.leave; r.Late = p.tally.late; r['Hours worked'] = Math.round(p.tally.worked / 6) / 10;
      return r;
    });
    exportRowsToExcel(rows, 'Attendance-' + teamData.month, 'Attendance');
  };
  await render();
}
