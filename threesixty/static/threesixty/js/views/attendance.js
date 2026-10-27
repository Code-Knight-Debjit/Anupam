// Attendance — check-in/out, team day-status grid, leave requests,
// holidays. Ported from the original's `attCheckIn`/`attCheckOut`/
// `attDayStatus` (~L12281-12570) and the leave submit/approve flow.
import { api } from '../api.js';
import { state, isAdmin, isBranchManager } from '../state.js';
import { el, escapeHtml, fmtDate, fmtDateTime, toast, apiErrorMessage, openModal, closeModal, renderTable, badge } from '../ui.js';

const ATT_GRACE_MIN = 10;
let activeTab = 'mine';
let employees = [];

function todayISO() { return new Date().toISOString().slice(0, 10); }

function timeToMinutes(t) {
  if (!t) return null;
  const [h, m] = t.split(':').map(Number);
  return h * 60 + m;
}

function isLate(checkIn, workStart) {
  const a = timeToMinutes(checkIn), b = timeToMinutes(workStart || '09:30');
  return a !== null && b !== null && (a - b) > ATT_GRACE_MIN;
}

function weeklyOffDay(dateStr, emp) {
  const day = new Date(dateStr).getDay();
  const offDays = (emp.weekly_off || '0').split(',').map((s) => s.trim());
  return offDays.includes(String(day));
}

function holidayFor(dateStr, emp, holidays) {
  return (holidays || []).find((h) => h.date <= dateStr && dateStr <= h.date_to
    && (h.is_all_branches || (h.branch_ids || []).some((b) => (emp.branch_ids || []).includes(b))));
}

function approvedLeaveFor(dateStr, userId, leaves) {
  return (leaves || []).find((l) => l.user.id === userId && l.status === 'Approved' && l.date_from <= dateStr && dateStr <= l.date_to);
}

/** Priority: manual override > check-in presence (late if beyond grace) >
 * holiday > weekly-off > approved leave > past-with-no-record = Absent > blank. */
function attDayStatus(record, emp, dateStr, holidays, leaves, attendanceStart) {
  if (record && record.status) return record.status;
  if (record && record.check_in) return isLate(record.check_in, emp.work_start) ? 'Late' : 'Present';
  const holiday = holidayFor(dateStr, emp, holidays);
  if (holiday) return `Holiday (${holiday.name})`;
  if (weeklyOffDay(dateStr, emp)) return 'Weekly off';
  if (approvedLeaveFor(dateStr, emp.user_id, leaves)) return 'Leave';
  const cutoff = emp.date_of_joining && emp.date_of_joining > (attendanceStart || '') ? emp.date_of_joining : attendanceStart;
  if (dateStr < todayISO() && (!cutoff || dateStr >= cutoff)) return 'Absent';
  return '—';
}

async function getLocation() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) { resolve({}); return; }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy_m: Math.round(pos.coords.accuracy) }),
      () => resolve({}),
      { timeout: 5000 },
    );
  });
}

async function renderMine(root) {
  const [todayRecord, history] = await Promise.all([
    api.all('attendance/').then((recs) => recs.find((r) => r.date === todayISO())),
    api.all('attendance/'),
  ]);
  history.sort((a, b) => b.date.localeCompare(a.date));

  root.innerHTML = `
    <div class="card" style="margin-bottom:20px;">
      <div class="flex-between">
        <div>
          <div style="font-weight:600;">Today — ${fmtDate(todayISO())}</div>
          <div class="sub">${todayRecord && todayRecord.check_in ? `Checked in at ${todayRecord.check_in}` : 'Not checked in yet'}${todayRecord && todayRecord.check_out ? ` · Checked out at ${todayRecord.check_out}` : ''}</div>
        </div>
        <div>
          <button class="btn primary" id="checkInBtn" ${todayRecord && todayRecord.check_in ? 'disabled' : ''}>Check in</button>
          <button class="btn" id="checkOutBtn" ${!todayRecord || !todayRecord.check_in || todayRecord.check_out ? 'disabled' : ''}>Check out</button>
        </div>
      </div>
    </div>
    <h3 style="margin-bottom:10px;">My attendance history</h3>
    ${renderTable(['Date', 'Check-in', 'Check-out', 'Status', 'Note'], history.slice(0, 60).map((r) => ({
      Date: fmtDate(r.date), 'Check-in': r.check_in || '—', 'Check-out': r.check_out || '—',
      Status: badge(r.status || (r.check_in ? (isLate(r.check_in, state.me.work_start) ? 'Late' : 'Present') : '—')),
      Note: escapeHtml(r.note),
    })), { empty: 'No attendance recorded yet.' })}`;

  root.querySelector('#checkInBtn').onclick = async () => {
    try {
      const loc = await getLocation();
      await api.post('attendance/check-in/', loc);
      toast('Checked in.', 'success');
      renderMine(root);
    } catch (e) { toast(apiErrorMessage(e), 'error'); }
  };
  root.querySelector('#checkOutBtn').onclick = async () => {
    try {
      const loc = await getLocation();
      await api.post('attendance/check-out/', loc);
      toast('Checked out.', 'success');
      renderMine(root);
    } catch (e) { toast(apiErrorMessage(e), 'error'); }
  };
}

function openCorrectModal(emp, dateStr, record, onSaved) {
  const r = record || {};
  openModal(`
    <h2>Correct attendance — ${escapeHtml(emp.full_name)} · ${fmtDate(dateStr)}</h2>
    <div class="field-row">
      <div class="field"><label>Check-in</label><input type="time" id="cr-in" value="${r.check_in || ''}"></div>
      <div class="field"><label>Check-out</label><input type="time" id="cr-out" value="${r.check_out || ''}"></div>
    </div>
    <div class="field"><label>Status override</label><select id="cr-status">
      <option value="" ${!r.status ? 'selected' : ''}>— computed automatically —</option>
      <option ${r.status === 'Present' ? 'selected' : ''}>Present</option>
      <option ${r.status === 'Half day' ? 'selected' : ''}>Half day</option>
      <option ${r.status === 'Absent' ? 'selected' : ''}>Absent</option>
      <option ${r.status === 'Leave' ? 'selected' : ''}>Leave</option>
      <option ${r.status === 'Off / Holiday' ? 'selected' : ''}>Off / Holiday</option>
    </select></div>
    <div class="field"><label>Note</label><input id="cr-note" value="${escapeHtml(r.note || '')}"></div>
    <p class="sub">Leaving all fields blank removes the record for this day.</p>
    <div class="modal-actions"><button class="btn" id="cr-cancel">Cancel</button><button class="btn primary" id="cr-save">Save</button></div>`, {
    onMount: (modal) => {
      modal.querySelector('#cr-cancel').onclick = closeModal;
      modal.querySelector('#cr-save').onclick = async () => {
        try {
          await api.post('attendance/correct/', {
            user_id: emp.user_id, date: dateStr,
            check_in: modal.querySelector('#cr-in').value || null,
            check_out: modal.querySelector('#cr-out').value || null,
            status: modal.querySelector('#cr-status').value,
            note: modal.querySelector('#cr-note').value.trim(),
          });
          toast('Saved.', 'success');
          closeModal();
          onSaved();
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

async function renderTeam(root) {
  let selectedDate = root.dataset.teamDate || todayISO();
  const [allRecords, leaves] = await Promise.all([api.all('attendance/'), api.all('leave-requests/')]);
  employees = employees.length ? employees : await api.all('employees/');
  const myBranchIds = state.me.branch_ids || [];
  const scoped = isAdmin() ? employees : employees.filter((e) => e.user_id === state.me.user_id || (e.branch_ids || []).some((b) => myBranchIds.includes(b)));

  const rows = scoped.map((emp) => {
    const record = allRecords.find((r) => r.user.id === emp.user_id && r.date === selectedDate);
    return { emp, record, status: attDayStatus(record, emp, selectedDate, state.holidays, leaves, state.siteSettings.attendance_start_date) };
  });

  root.innerHTML = `
    <div class="flex-between">
      <div class="field" style="max-width:200px;margin-bottom:0;"><label>Date</label><input type="date" id="teamDate" value="${selectedDate}"></div>
    </div>
    ${renderTable(['Employee', 'Check-in', 'Check-out', 'Status', 'Note', ''], rows.map(({ emp, record, status }) => ({
      Employee: escapeHtml(emp.full_name),
      'Check-in': (record && record.check_in) || '—', 'Check-out': (record && record.check_out) || '—',
      Status: badge(status), Note: escapeHtml(record ? record.note : ''),
      '': `<button class="btn sm" data-correct="${emp.user_id}">Correct</button>`,
    })), { empty: 'No team members in scope.' })}`;

  root.querySelector('#teamDate').onchange = (e) => { root.dataset.teamDate = e.target.value; renderTeam(root); };
  root.querySelectorAll('[data-correct]').forEach((btn) => btn.onclick = () => {
    const row = rows.find((r) => String(r.emp.user_id) === btn.dataset.correct);
    openCorrectModal(row.emp, selectedDate, row.record, () => renderTeam(root));
  });
}

async function renderLeave(root) {
  const canDecide = isAdmin() || isBranchManager();
  const [mine, pending] = await Promise.all([
    api.all('leave-requests/'),
    canDecide ? api.all('leave-requests/') : Promise.resolve([]),
  ]);
  const myOnly = canDecide ? mine.filter((l) => l.user.id === state.me.user_id) : mine;
  const pendingOthers = canDecide ? pending.filter((l) => l.status === 'Pending') : [];

  root.innerHTML = `
    <div class="card" style="margin-bottom:20px;">
      <h3 style="margin-bottom:10px;">Request leave</h3>
      <div class="field-row">
        <div class="field"><label>From</label><input type="date" id="lv-from" value="${todayISO()}"></div>
        <div class="field"><label>To</label><input type="date" id="lv-to" value="${todayISO()}"></div>
      </div>
      <div class="field"><label>Reason</label><input id="lv-reason"></div>
      <button class="btn primary sm" id="lv-submit">Submit request</button>
    </div>
    ${canDecide ? `<h3 style="margin-bottom:10px;">Pending approvals</h3>
      ${renderTable(['Employee', 'From', 'To', 'Days', 'Reason', ''], pendingOthers.map((l) => ({
        Employee: escapeHtml(l.user.full_name), From: fmtDate(l.date_from), To: fmtDate(l.date_to), Days: l.days, Reason: escapeHtml(l.reason),
        '': `<button class="btn sm primary" data-approve="${l.id}">Approve</button> <button class="btn sm danger" data-reject="${l.id}">Reject</button>`,
      })), { empty: 'Nothing pending.' })}` : ''}
    <h3 style="margin:20px 0 10px;">My leave requests</h3>
    ${renderTable(['From', 'To', 'Days', 'Reason', 'Status'], myOnly.map((l) => ({
      From: fmtDate(l.date_from), To: fmtDate(l.date_to), Days: l.days, Reason: escapeHtml(l.reason), Status: badge(l.status),
    })), { empty: 'No leave requests yet.' })}`;

  root.querySelector('#lv-submit').onclick = async () => {
    const reason = root.querySelector('#lv-reason').value.trim();
    if (!reason) { toast('Reason is required.', 'error'); return; }
    try {
      await api.post('leave-requests/', {
        date_from: root.querySelector('#lv-from').value, date_to: root.querySelector('#lv-to').value, reason,
      });
      toast('Leave requested.', 'success');
      renderLeave(root);
    } catch (e) { toast(apiErrorMessage(e), 'error'); }
  };
  root.querySelectorAll('[data-approve]').forEach((btn) => btn.onclick = async () => { await api.post(`leave-requests/${btn.dataset.approve}/approve/`, {}); renderLeave(root); });
  root.querySelectorAll('[data-reject]').forEach((btn) => btn.onclick = async () => { await api.post(`leave-requests/${btn.dataset.reject}/reject/`, {}); renderLeave(root); });
}

function holidayForm(holiday) {
  const h = holiday || {};
  return `
    <div class="field-row">
      <div class="field"><label>Name *</label><input id="hf-name" value="${escapeHtml(h.name || '')}"></div>
    </div>
    <div class="field-row">
      <div class="field"><label>From</label><input type="date" id="hf-from" value="${h.date || todayISO()}"></div>
      <div class="field"><label>To</label><input type="date" id="hf-to" value="${h.date_to || h.date || todayISO()}"></div>
    </div>
    <div class="field"><label><input type="checkbox" id="hf-all" style="width:auto;display:inline;" ${h.is_all_branches ? 'checked' : ''}> Applies to all branches</label></div>
    <div class="field" id="hf-branches-wrap" style="${h.is_all_branches ? 'display:none;' : ''}">
      <label>Branches</label>
      <select id="hf-branches" multiple size="5">${state.branches.map((b) => `<option value="${b.id}" ${(h.branch_ids || []).includes(b.id) ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('')}</select>
    </div>
    <div class="modal-actions"><button class="btn" id="hf-cancel">Cancel</button><button class="btn primary" id="hf-save">${holiday ? 'Save' : 'Add holiday'}</button></div>`;
}

function openHolidayModal(holiday, onSaved) {
  openModal(`<h2>${holiday ? 'Edit holiday' : 'New holiday'}</h2>${holidayForm(holiday)}`, {
    onMount: (modal) => {
      modal.querySelector('#hf-cancel').onclick = closeModal;
      modal.querySelector('#hf-all').onchange = (e) => { modal.querySelector('#hf-branches-wrap').style.display = e.target.checked ? 'none' : ''; };
      modal.querySelector('#hf-save').onclick = async () => {
        const name = modal.querySelector('#hf-name').value.trim();
        if (!name) { toast('Name is required.', 'error'); return; }
        const isAll = modal.querySelector('#hf-all').checked;
        const branchIds = Array.from(modal.querySelector('#hf-branches').selectedOptions).map((o) => Number(o.value));
        const data = { name, date: modal.querySelector('#hf-from').value, date_to: modal.querySelector('#hf-to').value, is_all_branches: isAll, branch_ids: isAll ? [] : branchIds };
        try {
          if (holiday) await api.patch(`holidays/${holiday.id}/`, data);
          else await api.post('holidays/', data);
          toast('Saved.', 'success');
          closeModal();
          onSaved();
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

async function renderHolidays(root) {
  const holidays = await api.all('holidays/');
  holidays.sort((a, b) => a.date.localeCompare(b.date));
  root.innerHTML = `
    <div class="flex-between"><h3>Holidays</h3><button class="btn primary sm" id="newHolidayBtn">+ Add holiday</button></div>
    ${renderTable(['Name', 'From', 'To', 'Scope', ''], holidays.map((h) => ({
      Name: escapeHtml(h.name), From: fmtDate(h.date), To: fmtDate(h.date_to),
      Scope: h.is_all_branches ? 'All branches' : (h.branch_ids || []).map((id) => escapeHtml((state.branches.find((b) => b.id === id) || {}).name || '?')).join(', ') || '—',
      '': `<button class="btn sm" data-edit="${h.id}">Edit</button> <button class="btn sm danger" data-del="${h.id}">Remove</button>`,
    })), { empty: 'No holidays configured.' })}`;
  root.querySelector('#newHolidayBtn').onclick = () => openHolidayModal(null, () => renderHolidays(root));
  root.querySelectorAll('[data-edit]').forEach((btn) => btn.onclick = () => openHolidayModal(holidays.find((h) => String(h.id) === btn.dataset.edit), () => renderHolidays(root)));
  root.querySelectorAll('[data-del]').forEach((btn) => btn.onclick = async () => {
    await api.delete(`holidays/${btn.dataset.del}/`);
    renderHolidays(root);
  });
}

export async function mountAttendance(root) {
  const canSeeTeam = isAdmin() || isBranchManager();
  activeTab = (['mine', 'team', 'leave', 'holidays'].includes(root.dataset.tab) && root.dataset.tab) || 'mine';
  const tabs = { mine: renderMine, leave: renderLeave };
  if (canSeeTeam) { tabs.team = renderTeam; }
  if (isAdmin()) tabs.holidays = renderHolidays;

  const shell = document.createElement('div');
  shell.innerHTML = `
    <div class="tabbar">
      <button data-t="mine" class="active">My attendance</button>
      ${canSeeTeam ? '<button data-t="team">Team</button>' : ''}
      <button data-t="leave">Leave</button>
      ${isAdmin() ? '<button data-t="holidays">Holidays</button>' : ''}
    </div>
    <div id="attBody"></div>`;
  root.innerHTML = '';
  root.appendChild(shell);
  const body = shell.querySelector('#attBody');
  const show = (tab) => {
    shell.querySelectorAll('[data-t]').forEach((b) => b.classList.toggle('active', b.dataset.t === tab));
    tabs[tab](body);
  };
  shell.querySelectorAll('[data-t]').forEach((btn) => btn.addEventListener('click', () => show(btn.dataset.t)));
  show('mine');
}
