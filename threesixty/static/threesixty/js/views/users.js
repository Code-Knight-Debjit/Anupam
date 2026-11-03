// Users — the reference's page: the list of people (role tag, branches, contact and ID details, Activate / Edit / Remove for an
// Admin) and, below it, the "Add a user" / "Edit user" form. Removing someone who owns records asks who takes them over. The
// server enforces every rule (strong passwords, unique IDs, Aadhaar / PAN, branches, the last Admin); the form repeats the
// reference's messages so the person sees them at once.
import { api } from '../api.js';
import { state, isAdmin, roleLabel, loadBootstrap } from '../state.js';
import { el, escapeHtml, customAlert, customConfirm, apiErrorMessage } from '../ui.js';
import { mountRefView, useOverlays, openOverlay, closeOverlay } from '../customer_common.js';

const ROLE_CODE = { Admin: 'ADMIN', 'Branch Manager': 'BRANCH_MANAGER', 'Branch Staff': 'BRANCH_STAFF', 'Sales Manager': 'SALES_MANAGER' };
const titleCaseWords = (s) => String(s || '').replace(/\w\S*/g, (w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase());
const when = (d) => new Date(d).toLocaleDateString('en-IN');

let employees = [];
let editingId = null;
let pendingRemove = null;

const branchLabel = (e) => {
  if (e.role === 'ADMIN') return 'All branches';
  const names = (e.branch_ids || []).map((id) => (state.branches.find((b) => b.id === id) || {}).name).filter(Boolean);
  return names.length ? names.join(', ') : 'No branch set';
};
const activeAdmins = (exceptId) => employees.filter((x) => x.id !== exceptId && x.role === 'ADMIN' && x.is_active);

async function reload() {
  employees = (await api.all('employees/')).sort((a, b) => a.full_name.localeCompare(b.full_name));
  await loadBootstrap();
  drawList();
}

function drawList() {
  const listEl = el('usersList');
  const adminMode = isAdmin();
  if (!employees.length) { listEl.innerHTML = '<p class="sub">No users yet.</p>'; return; }
  listEl.innerHTML = employees.map((e) => {
    const line1 = [e.emp_code ? 'Code: ' + escapeHtml(e.emp_code) : '', e.phone ? escapeHtml(e.phone) : '', e.email ? escapeHtml(e.email) : ''].filter(Boolean).join(' &middot; ');
    const line2 = [e.date_of_birth ? 'DOB: ' + when(e.date_of_birth) : '', e.date_of_joining ? 'Joined: ' + when(e.date_of_joining) : '', e.pan_number ? 'PAN: ' + escapeHtml(e.pan_number) : '',
      e.aadhaar_number ? 'Aadhaar: XXXX XXXX ' + escapeHtml(String(e.aadhaar_number).slice(-4)) : ''].filter(Boolean).join(' &middot; ');
    return `
      <div class="manage-item">
        <span class="mi-name">${escapeHtml(e.full_name)}
          <span style="color:var(--text-faint); font-weight:400; margin-left:6px;">ID: ${escapeHtml(e.username || '—')}</span>
          <span class="role-tag ${escapeHtml(roleLabel(e.role).replace(/\s/g, ''))}" style="margin-left:6px;">${escapeHtml(roleLabel(e.role))}</span>
          <span style="color:var(--text-faint); font-size:11.5px; margin-left:6px;">${escapeHtml(branchLabel(e))}</span>
          ${e.is_active ? '' : '<span class="tag" style="margin-left:6px; color:var(--danger); border-color:#f0c4c0; background:var(--danger-bg);">Inactive</span>'}
          ${line1 ? `<div style="color:var(--text-faint); font-size:11.5px; font-weight:400; margin-top:3px;">${line1}</div>` : ''}
          ${line2 ? `<div style="color:var(--text-faint); font-size:11.5px; font-weight:400; margin-top:2px;">${line2}</div>` : ''}
        </span>
        <span class="mi-actions">
          ${adminMode ? `
            <button data-act="toggle" data-id="${e.id}">${e.is_active ? 'Deactivate' : 'Activate'}</button>
            <button data-act="edit" data-id="${e.id}">Edit</button>
            <button class="danger" data-act="remove" data-id="${e.id}">Remove</button>` : ''}
        </span>
      </div>`;
  }).join('');
  listEl.querySelectorAll('[data-act]').forEach((b) => {
    b.onclick = () => {
      const emp = employees.find((x) => String(x.id) === b.dataset.id); if (!emp) return;
      if (b.dataset.act === 'toggle') toggleActive(emp); else if (b.dataset.act === 'edit') startEdit(emp); else removeUser(emp);
    };
  });
}

// ---- form ----------------------------------------------------------------------------------------------------------------------------
const branchBoxes = () => [...document.querySelectorAll('.u-branch-check')];
function updateBranchFields() { el('u-branch-multi-wrap').style.display = el('u-role').value === 'Admin' ? 'none' : 'block'; }
function fillForm(emp) {
  const e = emp || {};
  el('userFormTitle').textContent = emp ? `Edit user — ${emp.full_name}` : 'Add a user';
  el('u-name').value = e.full_name || ''; el('u-userid').value = e.username || ''; el('u-pass').value = '';
  el('u-pass').placeholder = emp ? 'Leave blank to keep current password' : 'At least 8 characters';
  el('u-role').value = emp ? roleLabel(emp.role) : 'Sales Manager';
  el('u-phone').value = e.phone || ''; el('u-email').value = e.email || ''; el('u-empcode').value = e.emp_code || '';
  el('u-active').value = emp && !emp.is_active ? 'inactive' : 'active';
  el('u-aadhaar').value = e.aadhaar_number ? String(e.aadhaar_number).replace(/(\d{4})(?=\d)/g, '$1 ') : ''; el('u-pan').value = e.pan_number || '';
  el('u-dob').value = e.date_of_birth || ''; el('u-doj').value = e.date_of_joining || '';
  el('u-wstart').value = e.work_start || '09:30'; el('u-wend').value = e.work_end || '18:30'; el('u-woff').value = e.weekly_off === undefined ? '0' : String(e.weekly_off);
  updateBranchFields();
  branchBoxes().forEach((cb) => { cb.checked = (e.branch_ids || []).map(String).includes(cb.value); });
  el('addUserBtn').textContent = emp ? 'Save changes' : 'Add user';
  el('cancelEditUserBtn').style.display = emp ? 'inline-flex' : 'none';
  el('userAddHint').textContent = '';
}
function startEdit(emp) {
  if (!isAdmin()) { customAlert('Only an admin can edit users.'); return; }
  editingId = emp.id; fillForm(emp); el('u-name').scrollIntoView({ behavior: 'smooth', block: 'center' });
}
const resetForm = () => { editingId = null; fillForm(null); };

async function save() {
  if (!isAdmin()) { customAlert('Only an admin can add or edit users.'); return; }
  const hint = (t) => { el('userAddHint').textContent = t; };
  const name = titleCaseWords(el('u-name').value.trim()), userId = el('u-userid').value.trim();
  const phone = el('u-phone').value.trim(), email = el('u-email').value.trim(), empCode = el('u-empcode').value.trim();
  const active = el('u-active').value !== 'inactive';
  const aadhaar = el('u-aadhaar').value.replace(/\D/g, ''), pan = el('u-pan').value.trim().toUpperCase(), dob = el('u-dob').value, doj = el('u-doj').value;
  const pw = el('u-pass').value, role = el('u-role').value;
  const others = employees.filter((e) => e.id !== editingId);

  if (!name) { hint('Enter a name.'); return; }
  if (!userId) { hint('Enter a User ID.'); return; }
  if (others.some((e) => (e.username || '').toLowerCase() === userId.toLowerCase())) { hint('That User ID is already taken.'); return; }
  if (phone && phone.replace(/\D/g, '').length < 10) { hint('Enter a valid phone number (at least 10 digits), or leave it blank.'); return; }
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { hint('Enter a valid email address, or leave it blank.'); return; }
  if (empCode && others.some((e) => (e.emp_code || '').toLowerCase() === empCode.toLowerCase())) { hint('That employee code is already used by another user.'); return; }
  if (aadhaar && aadhaar.length !== 12) { hint('Aadhaar number must be 12 digits, or leave it blank.'); return; }
  if (pan && !/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(pan)) { hint('PAN must look like ABCDE1234F (5 letters, 4 digits, 1 letter), or leave it blank.'); return; }
  if (aadhaar && others.some((e) => String(e.aadhaar_number || '') === aadhaar)) { hint('That Aadhaar number is already recorded for another user.'); return; }
  if (pan && others.some((e) => (e.pan_number || '').toUpperCase() === pan)) { hint('That PAN is already recorded for another user.'); return; }
  if (dob && dob > new Date().toISOString().slice(0, 10)) { hint('Date of birth cannot be in the future.'); return; }
  if (dob && doj && doj < dob) { hint('Date of joining cannot be before the date of birth.'); return; }
  const workStart = el('u-wstart').value || '09:30', workEnd = el('u-wend').value || '18:30', weeklyOff = el('u-woff').value;
  if (workEnd <= workStart) { hint('Work end time must be after the start time.'); return; }
  if (!editingId && !pw) { hint('Enter a password.'); return; }
  let branchIds = [];
  if (role !== 'Admin') {
    branchIds = branchBoxes().filter((cb) => cb.checked).map((cb) => Number(cb.value));
    if (!branchIds.length) { hint('Pick at least one branch for this user.'); return; }
  }
  hint('');
  const emp = editingId ? employees.find((e) => e.id === editingId) : null;
  if (emp) {
    // Never leave the app without an active admin (or lock yourself out).
    if (!active) {
      if (emp.user_id === state.me.user_id) { hint("You can't make your own account inactive."); return; }
      if (role === 'Admin' && !activeAdmins(emp.id).length) { hint('At least one active admin is required.'); return; }
    }
    if (emp.role === 'ADMIN' && role !== 'Admin' && !activeAdmins(emp.id).length) { hint('At least one active admin is required.'); return; }
  }
  const body = {
    full_name: name, role: ROLE_CODE[role], phone, email, emp_code: empCode, aadhaar_number: aadhaar, pan_number: pan, date_of_birth: dob || null, date_of_joining: doj || null,
    work_start: workStart, work_end: workEnd, weekly_off: weeklyOff, branch_ids: branchIds,
  };
  try {
    if (emp) {
      await api.patch(`employees/${emp.id}/`, { ...body, username: userId, is_active: active, ...(pw ? { new_password: pw } : {}) });
    } else {
      const created = await api.post('employees/', { ...body, username: userId, password: pw });
      if (!active) await api.patch(`employees/${created.id}/`, { is_active: false });
    }
  } catch (e) { hint(apiErrorMessage(e)); return; }
  resetForm(); await reload();
}

async function toggleActive(emp) {
  if (!isAdmin()) { customAlert("Only an admin can change a user's status."); return; }
  const makingInactive = emp.is_active;
  if (makingInactive) {
    if (emp.user_id === state.me.user_id) { customAlert("You can't make your own account inactive."); return; }
    if (emp.role === 'ADMIN' && !activeAdmins(emp.id).length) { customAlert('At least one active admin is required.'); return; }
    if (!await customConfirm(`Make ${emp.full_name} inactive? They won't be able to sign in. Their customers, tasks and records stay as they are.`)) return;
  }
  try { await api.patch(`employees/${emp.id}/`, { is_active: !makingInactive }); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
  await reload();
}

// ---- removing ------------------------------------------------------------------------------------------------------------------------
async function removeUser(emp) {
  if (!isAdmin()) { customAlert('Only an admin can remove users.'); return; }
  if (emp.user_id === state.me.user_id) { customAlert("You can't remove yourself while signed in."); return; }
  let counts;
  try { counts = await api.get(`employees/${emp.id}/records/`); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
  if (!counts.total) {
    if (!await customConfirm(`Remove ${emp.full_name}? They have no customers, tasks, documents or payments on record.`)) return;
    try { await api.delete(`employees/${emp.id}/`); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    if (editingId === emp.id) resetForm();
    await reload();
    return;
  }
  const others = employees.filter((e) => e.id !== emp.id && e.is_active);
  if (!others.length) { customAlert('There is no other user to transfer these records to. Add another user first, then remove this one.'); return; }
  pendingRemove = emp;
  useOverlays('userRemoveOverlay');
  el('userRemoveSub').textContent = `${emp.full_name} has records on file that need a new owner before they can be removed.`;
  const n = (k) => counts[k] || 0, lines = [];
  if (n('customers_created')) lines.push(`${n('customers_created')} customer(s) created`);
  if (n('customers_assigned')) lines.push(`${n('customers_assigned')} customer(s) assigned`);
  if (n('tasks_created')) lines.push(`${n('tasks_created')} task(s) created`);
  if (n('tasks_assigned')) lines.push(`${n('tasks_assigned')} task(s) assigned`);
  if (n('documents')) lines.push(`${n('documents')} sales document(s) created`);
  if (n('payments')) lines.push(`${n('payments')} payment record(s) created`);
  if (n('outreach_assigned')) lines.push(`${n('outreach_assigned')} outreach entr${n('outreach_assigned') === 1 ? 'y' : 'ies'} assigned to them`);
  if (n('outreach_given')) lines.push(`${n('outreach_given')} outreach entr${n('outreach_given') === 1 ? 'y' : 'ies'} assigned by them`);
  el('userRemoveCounts').innerHTML = lines.map((l) => `&bull; ${escapeHtml(l)}`).join('<br>');
  el('userRemoveTarget').innerHTML = others.map((e) => `<option value="${e.user_id}">${escapeHtml(e.full_name)} (${escapeHtml(roleLabel(e.role))})</option>`).join('');
  el('userRemoveCancelBtn').onclick = () => { pendingRemove = null; closeOverlay('userRemoveOverlay'); };
  el('userRemoveConfirmBtn').onclick = async () => {
    const target = others.find((e) => String(e.user_id) === el('userRemoveTarget').value);
    if (!pendingRemove || !target) return;
    if (!await customConfirm(`Transfer all of ${emp.full_name}'s customers, tasks, documents and payments to ${target.full_name}, then remove ${emp.full_name}? This can't be undone.`)) return;
    try { await api.delete(`employees/${emp.id}/?transfer_to=${target.user_id}`); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    pendingRemove = null; closeOverlay('userRemoveOverlay');
    if (editingId === emp.id) resetForm();
    await reload();
    await customAlert(`${emp.full_name}'s records were transferred to ${target.full_name} and the user was removed.`);
  };
  openOverlay('userRemoveOverlay');
}

export async function mountUsers(root) {
  mountRefView(root, 'view-users');
  editingId = null;
  el('u-branch-multi').innerHTML = state.branches.map((b) => `<label class="chip-check"><input type="checkbox" class="u-branch-check" value="${b.id}"><span>${escapeHtml(b.name)}</span></label>`).join('');
  el('u-role').onchange = updateBranchFields;
  el('u-aadhaar').addEventListener('input', (e) => { e.target.value = e.target.value.replace(/\D/g, '').slice(0, 12).replace(/(\d{4})(?=\d)/g, '$1 '); });
  el('u-pan').addEventListener('input', (e) => { e.target.value = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10); });
  el('cancelEditUserBtn').onclick = resetForm;
  el('addUserBtn').onclick = save;
  fillForm(null);
  employees = (await api.all('employees/')).sort((a, b) => a.full_name.localeCompare(b.full_name));
  drawList();
}
