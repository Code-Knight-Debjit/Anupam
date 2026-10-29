// Users — Admin-only Employee CRUD (`EmployeeResource`). Passwords are
// never read back; creation requires one, editing offers an optional
// "set new password" field that's only ever sent, never pre-filled.
import { api } from '../api.js';
import { state } from '../state.js';
import { el, escapeHtml, fmtDate, toast, apiErrorMessage, openModal, closeModal, confirmDialog, renderTable, badge } from '../ui.js';

const ROLES = [['ADMIN', 'Admin'], ['BRANCH_MANAGER', 'Branch Manager'], ['BRANCH_STAFF', 'Branch Staff'], ['SALES_MANAGER', 'Sales Manager']];

function branchCheckboxes(selected) {
  return state.branches.map((b) => `<label style="display:block;"><input type="checkbox" value="${b.id}" ${(selected || []).includes(b.id) ? 'checked' : ''}> ${escapeHtml(b.name)}</label>`).join('');
}

function userForm(emp) {
  const e = emp || {};
  return `
    <div class="field-row">
      <div class="field"><label>Full name</label><input id="uf-fullname" value="${escapeHtml(e.full_name || '')}"></div>
      <div class="field"><label>Username *</label><input id="uf-username" value="${escapeHtml(e.username || '')}" ${emp ? 'disabled' : ''}></div>
    </div>
    <div class="field-row">
      <div class="field"><label>${emp ? 'New password (leave blank to keep)' : 'Password *'}</label><input type="password" id="uf-password"></div>
      <div class="field"><label>Role *</label><select id="uf-role">${ROLES.map((r) => `<option value="${r[0]}" ${e.role === r[0] ? 'selected' : ''}>${r[1]}</option>`).join('')}</select></div>
    </div>
    <div class="field-row">
      <div class="field"><label>Employee code</label><input id="uf-empcode" value="${escapeHtml(e.emp_code || '')}"></div>
      <div class="field"><label>Job title</label><input id="uf-title" value="${escapeHtml(e.job_title || '')}"></div>
      <div class="field"><label>Phone</label><input id="uf-phone" value="${escapeHtml(e.phone || '')}"></div>
    </div>
    <div class="field-row">
      <div class="field"><label>Date of birth</label><input type="date" id="uf-dob" value="${e.date_of_birth || ''}"></div>
      <div class="field"><label>Date of joining</label><input type="date" id="uf-doj" value="${e.date_of_joining || ''}"></div>
    </div>
    <div class="field-row">
      <div class="field"><label>Work start</label><input type="time" id="uf-workstart" value="${e.work_start || '09:30'}"></div>
      <div class="field"><label>Work end</label><input type="time" id="uf-workend" value="${e.work_end || '18:30'}"></div>
      <div class="field"><label>Weekly off (0=Sun…6=Sat, comma list)</label><input id="uf-weeklyoff" value="${escapeHtml(e.weekly_off || '0')}"></div>
    </div>
    <div class="field-row">
      <div class="field"><label>Aadhaar</label><input id="uf-aadhaar" value="${escapeHtml(e.aadhaar_number || '')}"></div>
      <div class="field"><label>PAN</label><input id="uf-pan" value="${escapeHtml(e.pan_number || '')}"></div>
    </div>
    <div class="field"><label>Branches</label>${branchCheckboxes(e.branch_ids)}</div>
    ${emp ? `<div class="field"><label><input type="checkbox" id="uf-active-account" style="width:auto;display:inline;" ${e.is_active !== false ? 'checked' : ''}> Active (can sign in)</label></div>` : ''}
    <div class="modal-actions"><button class="btn" id="uf-cancel">Cancel</button><button class="btn primary" id="uf-save">${emp ? 'Save changes' : 'Create user'}</button></div>`;
}

function openUserForm(emp, onSaved) {
  openModal(`<h2>${emp ? 'Edit user' : 'New user'}</h2>${userForm(emp)}`, {
    onMount: (modal) => {
      modal.querySelector('#uf-cancel').onclick = closeModal;
      modal.querySelector('#uf-save').onclick = async () => {
        const branchIds = Array.from(modal.querySelectorAll('.field input[type="checkbox"][value]')).filter((c) => c.checked).map((c) => Number(c.value));
        const data = {
          full_name: modal.querySelector('#uf-fullname').value.trim(),
          role: modal.querySelector('#uf-role').value,
          emp_code: modal.querySelector('#uf-empcode').value.trim(),
          job_title: modal.querySelector('#uf-title').value.trim(),
          phone: modal.querySelector('#uf-phone').value.trim(),
          date_of_birth: modal.querySelector('#uf-dob').value || null,
          date_of_joining: modal.querySelector('#uf-doj').value || null,
          work_start: modal.querySelector('#uf-workstart').value,
          work_end: modal.querySelector('#uf-workend').value,
          weekly_off: modal.querySelector('#uf-weeklyoff').value.trim() || '0',
          aadhaar_number: modal.querySelector('#uf-aadhaar').value.trim(),
          pan_number: modal.querySelector('#uf-pan').value.trim(),
          branch_ids: branchIds,
        };
        const password = modal.querySelector('#uf-password').value;
        try {
          if (emp) {
            if (password) data.new_password = password;
            const activeBox = modal.querySelector('#uf-active-account');
            if (activeBox) data.is_active = activeBox.checked;
            await api.patch(`employees/${emp.id}/`, data);
          } else {
            data.username = modal.querySelector('#uf-username').value.trim();
            if (!data.username || !password) { toast('Username and password are required.', 'error'); return; }
            data.password = password;
            await api.post('employees/', data);
          }
          toast('Saved.', 'success');
          closeModal();
          onSaved();
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

// Removing someone who owns records needs a person to hand them to (customers, tasks, documents,
// payments, outreach); the server refuses otherwise and counts the records for us.
async function removeUser(emp, onDone) {
  let counts;
  try { counts = await api.get(`employees/${emp.id}/records/`); } catch (e) { toast(apiErrorMessage(e), 'error'); return; }
  const finish = async (transferTo) => {
    try {
      await api.delete(`employees/${emp.id}/${transferTo ? `?transfer_to=${transferTo}` : ''}`);
      toast('Removed.', 'success'); closeModal(); onDone();
    } catch (e) { toast(apiErrorMessage(e), 'error'); }
  };
  if (!counts.total) {
    if (await confirmDialog(`Remove user "${emp.full_name}"? They will no longer be able to sign in.`)) finish(null);
    return;
  }
  const heirs = state.employees.filter((u) => u.user_id !== emp.user_id);
  openModal(`<h2>Remove ${escapeHtml(emp.full_name)}</h2>
    <p>This person owns <strong>${counts.total}</strong> records: ${counts.customers_created} customers created, ${counts.customers_assigned} assigned, ${counts.tasks_created + counts.tasks_assigned} tasks,
    ${counts.documents} documents, ${counts.payments} payments, ${counts.outreach_assigned + counts.outreach_given} outreach calls.</p>
    <div class="field"><label>Hand all of these to *</label><select id="rm-heir"><option value="">— choose —</option>${heirs.map((u) => `<option value="${u.user_id}">${escapeHtml(u.full_name)}</option>`).join('')}</select></div>
    <div class="modal-actions"><button class="btn" id="rm-cancel">Cancel</button><button class="btn danger" id="rm-go">Transfer and remove</button></div>`, {
    onMount: (modal) => {
      modal.querySelector('#rm-cancel').onclick = closeModal;
      modal.querySelector('#rm-go').onclick = () => {
        const heir = modal.querySelector('#rm-heir').value;
        if (!heir) { toast('Choose who takes over the records.', 'error'); return; }
        finish(heir);
      };
    },
  });
}

async function render(root) {
  const employees = await api.all('employees/');
  employees.sort((a, b) => a.full_name.localeCompare(b.full_name));
  root.innerHTML = `
    <div class="flex-between"><h2 style="margin:0;">Users</h2><button class="btn primary" id="newUserBtn">+ New user</button></div>
    ${renderTable(['Name', 'Username', 'Role', 'Branches', 'Status', ''], employees.map((e) => ({
      Name: escapeHtml(e.full_name), Username: escapeHtml(e.username), Role: badge((ROLES.find((r) => r[0] === e.role) || [])[1] || e.role),
      Branches: (e.branch_ids || []).map((id) => escapeHtml((state.branches.find((b) => b.id === id) || {}).name || '?')).join(', ') || '—',
      Status: e.is_active ? badge('Active') : badge('Inactive'),
      '': `<button class="btn sm" data-edit="${e.id}">Edit</button> <button class="btn sm danger" data-del="${e.id}">Remove</button>`,
    })), { empty: 'No users yet.' })}`;
  root.querySelector('#newUserBtn').onclick = () => openUserForm(null, () => render(root));
  root.querySelectorAll('[data-edit]').forEach((btn) => btn.onclick = () => openUserForm(employees.find((e) => String(e.id) === btn.dataset.edit), () => render(root)));
  root.querySelectorAll('[data-del]').forEach((btn) => btn.onclick = () => removeUser(employees.find((e) => String(e.id) === btn.dataset.del), () => render(root)));
}

export async function mountUsers(root) {
  await render(root);
}
