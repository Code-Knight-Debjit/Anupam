// Enquiry → employees. Admin / Branch Manager / whoever raised the enquiry can give it to one or more employees; the assignment is
// a task linked to the enquiry, so it appears on each assignee's Task tab (and they are notified). Re-assigning changes the people;
// saving with nobody ticked takes the assignment back.
import { api } from '../api.js';
import { state, isAdmin, isBranchManager } from '../state.js';
import { openModal, closeModal, escapeHtml, customAlert, apiErrorMessage } from '../ui.js';
import { initialsOf } from '../customer_common.js';

export const canAssign = (d) => isAdmin() || isBranchManager() || !!(d.created_by && d.created_by.id === state.me.user_id);

/** Small "who has this" chips for a list row. */
export function assigneeChips(d) {
  const people = d.assignees || [];
  if (!people.length) return '<span class="assignee-none">Not assigned</span>';
  return `<div class="assignee-chips">${people.map((a) => `<span class="assignee-chip" title="${escapeHtml(a.full_name)}"><span class="av">${escapeHtml(initialsOf(a.full_name))}</span>${escapeHtml(a.full_name)}</span>`).join('')}</div>`;
}

export function openAssignDialog(d, onDone) {
  const current = new Set((d.assignees || []).map((a) => a.id));
  const employees = state.employees.filter((e) => e.is_active !== false || current.has(e.user_id));
  const me = state.me.user_id;
  openModal(`
    <div class="tf-hero"><div class="sdv-ico">👥</div><div><h2>Assign enquiry</h2><p class="modal-sub">${escapeHtml(d.doc_number || '')} — ${escapeHtml(d.customer_name || d.customer_label || '')}. It will show up on each person’s Task tab.</p></div></div>
    <div class="form-grid">
      <div class="field span2"><label>Assign to <span>(pick one or more)</span></label>
        ${employees.length > 6 ? '<input type="text" class="tk-dd-search" id="asgSearch" placeholder="Search people…" autocomplete="off" style="margin-bottom:6px;">' : ''}
        <div class="tk-dd-list asg-list" style="max-height:260px; border:1px solid var(--line); border-radius:10px; padding:4px;">
          ${employees.map((e) => `<label class="tk-dd-item" data-name="${escapeHtml((e.full_name || '').toLowerCase())}"><input type="checkbox" class="tk-assignee-check asg-check" value="${e.user_id}" ${current.has(e.user_id) ? 'checked' : ''}><span class="av">${escapeHtml(initialsOf(e.full_name))}</span><span class="nm">${escapeHtml(e.full_name)}${e.user_id === me ? ' (me)' : ''}</span></label>`).join('') || '<div class="sub" style="padding:8px;">No employees to choose from.</div>'}
        </div>
      </div>
      <div class="field span2"><label for="asgDue">Due date (optional)</label><input type="date" id="asgDue"></div>
    </div>
    <div class="modal-actions"><button class="btn" id="asgCancel">Cancel</button><button class="btn btn-primary" id="asgSave">Save assignment</button></div>
    <p class="field-hint" id="asgHint"></p>`, {
    size: 'narrow tform',
    onMount: (m) => {
      const search = m.querySelector('#asgSearch');
      if (search) search.addEventListener('input', () => { const q = search.value.trim().toLowerCase(); m.querySelectorAll('.asg-list .tk-dd-item').forEach((it) => { it.style.display = !q || it.dataset.name.includes(q) ? '' : 'none'; }); });
      m.querySelector('#asgCancel').onclick = closeModal;
      m.querySelector('#asgSave').onclick = async () => {
        const ids = [...m.querySelectorAll('.asg-check:checked')].map((c) => Number(c.value));
        const body = { assignee_ids: ids, due_date: m.querySelector('#asgDue').value || null };
        try { await api.post(`sales-documents/${d.id}/assign/`, body); }
        catch (e) { m.querySelector('#asgHint').textContent = apiErrorMessage(e); return; }
        closeModal();
        if (onDone) await onDone();
      };
    },
  });
}
