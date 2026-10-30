// Task Manager — ported from the original's task list/kanban view. API
// only filters by `status` server-side (`views_tasks.py::TaskResource`);
// everything else (assignee/priority filters) is client-side.
import { api } from '../api.js';
import { state, isAdmin, isBranchManager, userOptionsHtml } from '../state.js';
import { el, escapeHtml, fmtDate, toast, apiErrorMessage, openModal, closeModal, renderTable, badge } from '../ui.js';

let tasks = [];
let filterStatus = 'Open';

const userOptions = userOptionsHtml;

function taskForm(task) {
  const t = task || {};
  return `
    <div class="field"><label>Title *</label><input id="tf-title" value="${escapeHtml(t.title || '')}"></div>
    <div class="field"><label>Description</label><textarea id="tf-desc" rows="3">${escapeHtml(t.description || '')}</textarea></div>
    <div class="field-row">
      <div class="field"><label>Assigned to</label><select id="tf-assignee">${userOptions(t.assigned_to ? t.assigned_to.id : state.me.user_id)}</select></div>
      <div class="field"><label>Priority</label><select id="tf-priority">
        <option ${t.priority === 'Low' ? 'selected' : ''}>Low</option>
        <option ${!t.priority || t.priority === 'Medium' ? 'selected' : ''}>Medium</option>
        <option ${t.priority === 'High' ? 'selected' : ''}>High</option>
      </select></div>
      <div class="field"><label>Due date</label><input type="date" id="tf-due" value="${t.due_date || ''}"></div>
    </div>
    <div class="modal-actions">
      <button class="btn" id="tf-cancel">Cancel</button>
      <button class="btn primary" id="tf-save">${task ? 'Save changes' : 'Create task'}</button>
    </div>`;
}

function openTaskForm(task, onSaved) {
  openModal(`<h2>${task ? 'Edit task' : 'New task'}</h2>${taskForm(task)}`, {
    onMount: (modal) => {
      modal.querySelector('#tf-cancel').onclick = closeModal;
      modal.querySelector('#tf-save').onclick = async () => {
        const data = {
          title: modal.querySelector('#tf-title').value.trim(),
          description: modal.querySelector('#tf-desc').value.trim(),
          assigned_to_id: modal.querySelector('#tf-assignee').value,
          priority: modal.querySelector('#tf-priority').value,
          due_date: modal.querySelector('#tf-due').value || null,
        };
        if (!data.title) { toast('Title is required.', 'error'); return; }
        try {
          if (task) await api.patch(`tasks/${task.id}/`, { ...data, version: task.version });
          else await api.post('tasks/', data);
          toast('Saved.', 'success');
          closeModal();
          onSaved();
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

async function toggleStatus(task, rerender) {
  try {
    await api.patch(`tasks/${task.id}/`, { status: task.status === 'Completed' ? 'Open' : 'Completed', version: task.version });
    rerender();
  } catch (e) { toast(apiErrorMessage(e), 'error'); }
}

async function render(root) {
  tasks = await api.all('tasks/', filterStatus ? { status: filterStatus } : {});
  tasks.sort((a, b) => (a.due_date || '9999').localeCompare(b.due_date || '9999'));
  root.innerHTML = `
    <div class="flex-between">
      <div class="tabbar">
        <button data-f="Open" class="${filterStatus === 'Open' ? 'active' : ''}">Open</button>
        <button data-f="Completed" class="${filterStatus === 'Completed' ? 'active' : ''}">Completed</button>
        <button data-f="" class="${filterStatus === '' ? 'active' : ''}">All</button>
      </div>
      <button class="btn primary" id="newTaskBtn">+ New Task</button>
    </div>
    ${renderTable(['Done', 'Title', 'Assigned to', 'Priority', 'Due', ''], tasks.map((t) => ({
      Done: `<input type="checkbox" data-toggle="${t.id}" ${t.status === 'Completed' ? 'checked' : ''}>`,
      Title: `<strong>${escapeHtml(t.title)}</strong>${t.description ? `<div class="sub">${escapeHtml(t.description)}</div>` : ''}`,
      'Assigned to': escapeHtml(t.assigned_to ? t.assigned_to.full_name : '—'),
      Priority: badge(t.priority),
      Due: fmtDate(t.due_date),
      '': `<button class="btn sm" data-edit="${t.id}">Edit</button>`,
    })), { empty: 'No tasks found.' })}`;

  root.querySelectorAll('[data-f]').forEach((btn) => btn.onclick = () => { filterStatus = btn.dataset.f; render(root); });
  root.querySelector('#newTaskBtn').onclick = () => openTaskForm(null, () => render(root));
  root.querySelectorAll('[data-toggle]').forEach((cb) => cb.onchange = () => toggleStatus(tasks.find((t) => String(t.id) === cb.dataset.toggle), () => render(root)));
  root.querySelectorAll('[data-edit]').forEach((btn) => btn.onclick = () => openTaskForm(tasks.find((t) => String(t.id) === btn.dataset.edit), () => render(root)));
}

export async function mountTasks(root) {
  await render(root);
}
