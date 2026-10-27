// Outreach / Calling list — weekly customer call assignments. Ported from
// the original's calling-list screen. Assigning is Admin/Branch Manager
// only (AUDIT.md §3); the assignee marks status / logs "not reached"
// attempts on their own rows.
import { api } from '../api.js';
import { state, isAdmin, isBranchManager } from '../state.js';
import { el, escapeHtml, fmtDate, fmtDateTime, toast, apiErrorMessage, openModal, closeModal, renderTable, badge } from '../ui.js';

let allCustomers = [];
let assignments = [];
let weekOf = mondayOf(new Date());

function mondayOf(d) {
  const date = new Date(d);
  const day = date.getDay();
  const diff = (day === 0 ? -6 : 1) - day;
  date.setDate(date.getDate() + diff);
  return date.toISOString().slice(0, 10);
}

function customerName(id) {
  const c = allCustomers.find((x) => x.id === id);
  return c ? c.name : `#${id}`;
}

function userOptions(selected) {
  return state.salesPersons.map((u) => `<option value="${u.id}" ${String(selected) === String(u.id) ? 'selected' : ''}>${escapeHtml(u.full_name)}</option>`).join('');
}

function customerOptions() {
  return allCustomers.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
}

function openAssignModal(onSaved) {
  openModal(`
    <h2>Assign outreach call</h2>
    <div class="field"><label>Customer *</label><select id="af-customer">${customerOptions()}</select></div>
    <div class="field-row">
      <div class="field"><label>Assign to *</label><select id="af-assignee">${userOptions(state.me.user_id)}</select></div>
      <div class="field"><label>Week of</label><input type="date" id="af-week" value="${weekOf}"></div>
    </div>
    <div class="field"><label>Remarks</label><input id="af-remarks"></div>
    <div class="modal-actions"><button class="btn" id="af-cancel">Cancel</button><button class="btn primary" id="af-save">Assign</button></div>`, {
    onMount: (modal) => {
      modal.querySelector('#af-cancel').onclick = closeModal;
      modal.querySelector('#af-save').onclick = async () => {
        try {
          await api.post('call-assignments/', {
            customer_id: modal.querySelector('#af-customer').value,
            assigned_to_id: modal.querySelector('#af-assignee').value,
            week_of: modal.querySelector('#af-week').value,
            remarks: modal.querySelector('#af-remarks').value.trim(),
          });
          toast('Assigned.', 'success');
          closeModal();
          onSaved();
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

function openAttemptModal(assignment, onSaved) {
  openModal(`
    <h2>Log attempt — ${escapeHtml(customerName(assignment.customer_id))}</h2>
    <div class="field"><label>Reason not reached *</label><input id="at-reason" placeholder="e.g. No answer, switched off"></div>
    <div class="field"><label>Note</label><textarea id="at-note" rows="2"></textarea></div>
    <div class="field"><label>Call again on</label><input type="date" id="at-again"></div>
    <div class="modal-actions"><button class="btn" id="at-cancel">Cancel</button><button class="btn primary" id="at-save">Log attempt</button></div>`, {
    onMount: (modal) => {
      modal.querySelector('#at-cancel').onclick = closeModal;
      modal.querySelector('#at-save').onclick = async () => {
        const reason = modal.querySelector('#at-reason').value.trim();
        if (!reason) { toast('Reason is required.', 'error'); return; }
        try {
          await api.post(`call-assignments/${assignment.id}/attempts/`, {
            reason, note: modal.querySelector('#at-note').value.trim(),
            call_again_date: modal.querySelector('#at-again').value || null,
          });
          toast('Attempt logged.', 'success');
          closeModal();
          onSaved();
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

async function markCalled(assignment, rerender) {
  try {
    await api.patch(`call-assignments/${assignment.id}/`, { status: 'Called' });
    rerender();
  } catch (e) { toast(apiErrorMessage(e), 'error'); }
}

async function removeAssignment(assignment, rerender) {
  try {
    await api.delete(`call-assignments/${assignment.id}/`);
    rerender();
  } catch (e) { toast(apiErrorMessage(e), 'error'); }
}

async function render(root) {
  const canAssign = isAdmin() || isBranchManager();
  [allCustomers, assignments] = await Promise.all([
    allCustomers.length ? Promise.resolve(allCustomers) : api.all('customers/'),
    api.all('call-assignments/', { week_of: weekOf }),
  ]);

  root.innerHTML = `
    <div class="flex-between">
      <div class="field" style="max-width:200px;margin-bottom:0;"><label>Week of</label><input type="date" id="weekPicker" value="${weekOf}"></div>
      ${canAssign ? '<button class="btn primary" id="assignBtn">+ Assign call</button>' : ''}
    </div>
    ${renderTable(['Customer', 'Assigned to', 'Status', 'Last attempt', 'Remarks', ''], assignments.map((a) => ({
      Customer: escapeHtml(customerName(a.customer_id)),
      'Assigned to': escapeHtml(a.assigned_to ? a.assigned_to.full_name : '—'),
      Status: badge(a.status),
      'Last attempt': (a.attempts && a.attempts.length) ? `${escapeHtml(a.attempts[a.attempts.length - 1].reason)} · ${fmtDateTime(a.attempts[a.attempts.length - 1].at)}` : '—',
      Remarks: escapeHtml(a.remarks),
      '': a.status === 'Called' ? '' : `
        <button class="btn sm" data-attempt="${a.id}">Log attempt</button>
        <button class="btn sm primary" data-called="${a.id}">Mark called</button>
        ${canAssign ? `<button class="btn sm danger" data-remove="${a.id}">Remove</button>` : ''}`,
    })), { empty: 'No outreach assigned for this week.' })}`;

  root.querySelector('#weekPicker').onchange = (e) => { weekOf = mondayOf(e.target.value); render(root); };
  if (canAssign) root.querySelector('#assignBtn').onclick = () => openAssignModal(() => render(root));
  root.querySelectorAll('[data-attempt]').forEach((btn) => btn.onclick = () => openAttemptModal(assignments.find((a) => String(a.id) === btn.dataset.attempt), () => render(root)));
  root.querySelectorAll('[data-called]').forEach((btn) => btn.onclick = () => markCalled(assignments.find((a) => String(a.id) === btn.dataset.called), () => render(root)));
  root.querySelectorAll('[data-remove]').forEach((btn) => btn.onclick = () => removeAssignment(assignments.find((a) => String(a.id) === btn.dataset.remove), () => render(root)));
}

export async function mountOutreach(root) {
  await render(root);
}
