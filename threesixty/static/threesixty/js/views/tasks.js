// Task — the reference's Task page: hero + "+ New Task"; left column = stats tiles, kind tabs (All / Calls / Visits /
// Appointments / Other + scope switch + fold buttons), search + Filters, task cards grouped by when they are due
// (or one column per type on the "All" tab); right column = month calendar, upcoming tasks, "Assigned by me".
// Visibility, who may edit / complete / remove and the notifications are enforced by the server (services/tasks.py);
// the page only decides what to show, exactly as the reference does.
import { api } from '../api.js';
import { state, isAdmin, isBranchManager } from '../state.js';
import { navigate } from '../router.js';
import { WHATSAPP_ICON_SVG } from '../customer_common.js';
import { el, escapeHtml, customAlert, customConfirm, apiErrorMessage, openModal, closeModal, initials } from '../ui.js';

const KIND_META = {
  Call: { icon: '📞', label: 'Calls' }, Visit: { icon: '📍', label: 'Visits' },
  Appointment: { icon: '📅', label: 'Appointments' }, Task: { icon: '✔️', label: 'Other tasks' },
};
const KIND_ORDER = ['Call', 'Visit', 'Appointment', 'Task'];
const CAL_KIND_COLOR = { Call: '#2f6fb5', Visit: '#1f8a6a', Appointment: '#8a4fb8', Task: '#8a94a0' };
const BUCKETS = [
  { key: 'late', label: 'Overdue', color: '#c0392b' }, { key: 'today', label: 'Today', color: '#c9740f' },
  { key: 'week', label: 'Next 7 days', color: '#2f6fb5' }, { key: 'later', label: 'Later', color: '#6b7785' },
  { key: 'none', label: 'No due date', color: '#8a94a0' }, { key: 'done', label: 'Completed', color: 'var(--wa)' },
];

// Page state lives for the session, like the reference's module variables.
let filters = { scope: 'mine', status: '', priority: '', assignee: null, due: '', kind: '', from: '', to: '' };
let panelOpen = false;
let searchText = '';
let calMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
const collapsed = new Set(), expanded = new Set();
let data = { mine: [], created: [], all: null, total: 0 };
let root = null;

const me = () => state.me.user_id;
const canSeeAll = () => isAdmin() || isBranchManager();
const uiStatus = (t) => (t.status === 'Completed' ? 'Done' : t.status);
const isDone = (t) => t.status === 'Completed';
const people = (t) => (t.assignees && t.assignees.length ? t.assignees : [t.assigned_to]).filter(Boolean);
const isAssignedToMe = (t) => people(t).some((a) => a.id === me());
const assigneeNames = (t) => people(t).map((a) => a.full_name).filter(Boolean).join(', ');
const kindOf = (t) => t.kind || 'Task';
const canManage = (t) => isAdmin() || isBranchManager() || (t.created_by && t.created_by.id === me());
const canUpdateStatus = (t) => canManage(t) || isAssignedToMe(t);
// Only the person who gave the task can remove it; an old task with no recorded creator can be removed by an Admin.
const canRemove = (t) => (t.created_by ? t.created_by.id === me() : isAdmin());
const priorityColor = (p) => (p === 'High' ? 'var(--danger)' : p === 'Low' ? 'var(--text-faint)' : 'var(--accent)');
const statusColor = (s) => (s === 'Done' ? 'var(--wa)' : s === 'In Progress' ? 'var(--blue)' : 'var(--text-dim)');

function waLink(phone) {
  let digits = (phone || '').replace(/\D/g, '');
  if (digits.length === 10) digits = '91' + digits;
  return digits ? `https://wa.me/${digits}?text=${encodeURIComponent('Hi, ')}` : null;
}
const today0 = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const dueDate = (t) => (t.due_date ? new Date(t.due_date + 'T00:00:00') : null);
function daysFromToday(t) { const d = dueDate(t); return d ? Math.round((d - today0()) / 86400000) : null; }
const fmtD = (iso) => new Date(iso).toLocaleDateString('en-IN');

// ---- data ------------------------------------------------------------------------------------------------------------
async function load() {
  const [mine, created] = await Promise.all([api.all('tasks/', { scope: 'mine' }), api.all('tasks/', { scope: 'assigned_by_me' })]);
  data.mine = mine; data.created = created;
  data.all = (canSeeAll() && filters.scope === 'all') ? await api.all('tasks/', { scope: 'all' }) : null;
  // "How many tasks exist" for the empty-state sentence (the reference counts every task it can see, not just the list).
  data.total = canSeeAll() ? (data.all ? data.all.length : (await api.get('tasks/?scope=all&page_size=1')).count) : everything().length;
  updateTaskBadge();
}
const baseList = () => (data.all || data.mine);
const everything = () => {
  const seen = new Map();
  [...data.mine, ...data.created, ...(data.all || [])].forEach((t) => seen.set(t.id, t));
  return [...seen.values()];
};
function updateTaskBadge() {
  const open = data.mine.filter((t) => !isDone(t)).length;
  const b = el('taskBadge'); if (!b) return;
  b.textContent = open; b.style.display = open ? 'inline-block' : 'none';
}

// ---- filtering (every filter except the kind tab, so the tab counts reflect the other filters) -----------------------
function listFiltered(skipKind) {
  let list = baseList();
  const f = filters;
  if (f.status === 'NotDone') list = list.filter((t) => !isDone(t));
  else if (f.status) list = list.filter((t) => uiStatus(t) === f.status);
  if (f.priority) list = list.filter((t) => t.priority === f.priority);
  if (f.assignee) list = list.filter((t) => people(t).some((a) => String(a.id) === String(f.assignee)));
  if (!skipKind && f.kind) list = list.filter((t) => kindOf(t) === f.kind);
  if (f.from) list = list.filter((t) => t.due_date && t.due_date >= f.from);
  if (f.to) list = list.filter((t) => t.due_date && t.due_date <= f.to);
  const t0 = today0();
  if (f.due === 'overdue') list = list.filter((t) => !isDone(t) && dueDate(t) && dueDate(t) < t0);
  else if (f.due === 'today') list = list.filter((t) => dueDate(t) && dueDate(t).getTime() === t0.getTime());
  else if (f.due === 'upcoming') list = list.filter((t) => dueDate(t) && dueDate(t) > t0);
  const q = searchText.trim().toLowerCase();
  if (q) list = list.filter((t) => [t.title, t.description, t.related_customer_name, t.related_contact_name, assigneeNames(t), t.created_by && t.created_by.full_name].some((v) => (v || '').toLowerCase().includes(q)));
  return list;
}

// ---- chips / small renderers -----------------------------------------------------------------------------------------
function dueChip(t) {
  if (isDone(t)) return t.completed_at ? `<span class="tchip ok">✓ Completed ${fmtD(t.completed_at)}</span>` : '<span class="tchip ok">✓ Completed</span>';
  const d = daysFromToday(t);
  if (d === null) return '<span class="tchip">No due date</span>';
  const dateTxt = dueDate(t).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
  if (d < 0) return `<span class="tchip due-late">⏰ Overdue ${-d} day${d === -1 ? '' : 's'} · ${dateTxt}</span>`;
  if (d === 0) return '<span class="tchip due-today">🔔 Due today</span>';
  if (d === 1) return `<span class="tchip due-soon">Tomorrow · ${dateTxt}</span>`;
  if (d <= 7) return `<span class="tchip due-soon">In ${d} days · ${dateTxt}</span>`;
  return `<span class="tchip">📅 ${dateTxt}</span>`;
}
function bucketOf(t) {
  if (isDone(t)) return 'done';
  const d = daysFromToday(t);
  if (d === null) return 'none';
  if (d < 0) return 'late';
  if (d === 0) return 'today';
  return d <= 7 ? 'week' : 'later';
}
const initialsOf = (name) => { const p = (name || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };

function cardHtml(t, t0) {
  const overdue = !isDone(t) && dueDate(t) && dueDate(t) < t0;
  const done = isDone(t);
  const kind = kindOf(t), meta = KIND_META[kind];
  const phone = t.related_contact_phone || '';
  const wa = phone ? waLink(phone) : null;
  const st = uiStatus(t), sc = statusColor(st), pc = priorityColor(t.priority);
  const callLayout = ['Call', 'Visit', 'Appointment'].includes(kind) && t.related_contact_id && t.related_customer_id;
  const tile = (label, html, cls) => (html ? `<div class="tc-tile${cls ? ' ' + cls : ''}"><label>${label}</label><div>${html}</div></div>` : '');
  const contactName = t.related_contact_name || '';
  const personHtml = contactName ? (t.related_contact_id && t.related_customer_id
    ? `<span class="tc-link" data-person="${t.related_customer_id}/${t.related_contact_id}" title="Open contact card">${escapeHtml(contactName)}</span>` : escapeHtml(contactName)) : '';
  const doc = t.related_document;
  const tiles = [
    tile('Person', personHtml),
    tile('Phone / WhatsApp', phone ? escapeHtml(phone) : ''),
    tile('Company', t.related_customer_name ? `<span class="tc-link" data-customer="${t.related_customer_id}" title="Open customer">${escapeHtml(t.related_customer_name)}</span>` : '', 'wide'),
    tile(kind === 'Call' ? 'Reason' : 'Notes', t.description ? escapeHtml(t.description) : '', 'full'),
    tile('Status', `<span class="tchip" style="background:${sc}22; color:${sc};">${escapeHtml(st || 'Open')}</span>`),
    tile('Date', dueChip(t)),
    tile('Priority', `<span class="tchip" style="background:${pc}22; color:${pc};">● ${escapeHtml(t.priority || 'Medium')}</span>`),
    tile('Assigned to', escapeHtml(assigneeNames(t) || '—') + (people(t).length > 1 ? ` <span class="tchip" style="background:#e8f1fb;color:#2f6fb5;" title="Shared task — anyone assigned can mark it done">👥 ${people(t).length}</span>` : '')),
    tile('Completed', done ? `<b style="color:#1f8a4c;">✅ Done by ${escapeHtml((t.completed_by && t.completed_by.full_name) || assigneeNames(t) || '—')}${t.completed_at ? ' on ' + fmtD(t.completed_at) : ''}</b><br><span style="font-size:12px;color:var(--text-dim);">${t.created_by && t.created_by.id === me() ? 'Check it, then click “Mark Complete” to remove it for everyone.' : 'Stays here until ' + escapeHtml((t.created_by && t.created_by.full_name) || 'the creator') + ' marks it complete.'}</span>` : '', 'wide'),
    tile('Joint with', (t.joint_names && t.joint_names.length) ? '🤝 ' + escapeHtml(t.joint_names.join(', ')) : '', 'wide'),
    tile('Linked document', doc ? `<span class="tc-link" data-doc="${doc.id}" data-doctype="${doc.type}" title="Open the linked document">🔗 ${escapeHtml(doc.label + ' ' + (doc.number || ''))}</span>` : '', 'wide'),
  ].join('');
  const isCollapsed = collapsed.has(t.id);
  const by = escapeHtml((t.created_by && t.created_by.full_name) || '—');
  const callBtns = (phone && !done && kind === 'Call')
    ? `<a class="btn btn-primary" style="text-decoration:none;" href="tel:${escapeHtml(phone.replace(/[^\d+]/g, ''))}">📞</a>${wa ? `<a class="btn btn-wa" style="text-decoration:none; display:inline-flex; align-items:center; justify-content:center; padding:6px 9px;" href="${wa}" target="_blank" rel="noopener" title="WhatsApp">${WHATSAPP_ICON_SVG.replace('width="10" height="10"', 'width="18" height="18"')}</a>` : ''}` : '';
  return `
    <div class="tcard k-${kind}${done ? ' done' : ''}${overdue ? ' late' : ''}${isCollapsed ? ' collapsed' : ''}" data-tid="${t.id}" title="Added by ${by}">
      <div class="tc-ico" title="${kind}">${meta.icon}</div>
      <div class="tc-main">
        <div class="tc-sum"><b>${escapeHtml(callLayout ? [contactName, t.related_customer_name].filter(Boolean).join(' — ') : t.title)}</b> ${dueChip(t)} <span class="tchip" style="background:${sc}22; color:${sc};">${escapeHtml(st || 'Open')}</span> <span class="tc-who">→ ${escapeHtml(assigneeNames(t) || '—')}</span></div>
        ${callLayout ? '' : `<div class="tc-top"><span class="tc-title" title="Added by ${by}">${escapeHtml(t.title)}</span></div>`}
        <div class="tc-tiles">${tiles}</div>
      </div>
      <div class="tc-actions">
        <button type="button" class="btn btn-icon tc-fold" data-fold="${t.id}" title="Collapse / expand this task"><span class="fx">▾ Hide</span><span class="fc">▸ Show</span></button>
        ${callBtns}
        ${canUpdateStatus(t) && !done ? `<button class="btn btn-wa" data-status="${t.id}">✓ Done</button>` : ''}
        ${canManage(t) ? `<button class="btn btn-icon" data-edit="${t.id}">Edit</button>` : ''}
        ${canRemove(t) ? (done && canManage(t) ? `<button class="btn btn-wa" data-delete="${t.id}">Mark Complete</button>` : `<button class="btn-danger-text" data-delete="${t.id}">${done ? 'Remove' : 'Delete'}</button>`)
          : (done ? `<span style="font-size:12px;color:var(--text-dim);">Waiting for ${escapeHtml((t.created_by && t.created_by.full_name) || 'the creator')} to mark it complete</span>` : '')}
      </div>
    </div>`;
}

function abmRowHtml(t, t0) {
  const done = isDone(t), overdue = !done && dueDate(t) && dueDate(t) < t0, meta = KIND_META[kindOf(t)];
  const st = uiStatus(t), sc = statusColor(st);
  const who = t.related_customer_name ? ' — ' + t.related_customer_name : '';
  return `<div class="abm-row${done ? ' done' : ''}${overdue ? ' late' : ''}" style="--k:${done ? '#1f8a4f' : overdue ? '#c0392b' : '#2f6fb5'};">
    <div class="abm-top"><span class="abm-ico">${meta.icon}</span><span class="abm-title">${escapeHtml(t.title || 'Task')}${escapeHtml(who)}</span></div>
    <div class="abm-meta">→ <b>${escapeHtml(assigneeNames(t) || '—')}</b> ${dueChip(t)} <span class="tchip" style="background:${sc}22; color:${sc};">${escapeHtml(st || 'Open')}</span></div>
    <div class="abm-act">${canManage(t) ? `<button class="btn btn-icon" data-edit="${t.id}">Edit</button>` : ''}${canRemove(t) ? (done ? `<button class="btn btn-wa" data-delete="${t.id}">Mark Complete</button>` : `<button class="btn-danger-text" data-delete="${t.id}">Delete</button>`) : ''}</div>
  </div>`;
}

// ---- page sections -------------------------------------------------------------------------------------------------------
function activeFilterCount() {
  const f = filters;
  let n = 0;
  if (f.status) n++; if (f.priority) n++; if (f.due) n++;
  if (f.from || f.to) n++;
  if (canSeeAll() && f.assignee !== me()) n++;   // anything other than "my own tasks" counts as a change (reference quirk: Admin/BM start on 1)
  return n;
}
function updateFilterBadge() {
  const b = el('taskFilterBadge'); if (!b) return;
  const n = activeFilterCount();
  b.textContent = n; b.style.display = n ? '' : 'none';
}

function renderFilters() {
  const assigneeOptions = canSeeAll() ? state.employees.map((e) => `<option value="${e.user_id}">${escapeHtml(e.full_name)}</option>`).join('') : '';
  const fld = (label, inner) => `<div class="tf"><label>${label}</label>${inner}</div>`;
  el('taskFilterRow').innerHTML =
    fld('Status', '<select id="taskStatusFilter"><option value="">All statuses</option><option value="NotDone">Not completed</option><option value="Open">Open</option><option value="In Progress">In Progress</option><option value="Done">Done</option></select>') +
    fld('Priority', '<select id="taskPriorityFilter"><option value="">All priorities</option><option value="High">High</option><option value="Medium">Medium</option><option value="Low">Low</option></select>') +
    fld('Due', '<select id="taskDueFilter"><option value="">All dates</option><option value="overdue">Overdue</option><option value="today">Due today</option><option value="upcoming">Upcoming (future date)</option></select>') +
    (canSeeAll() ? fld('Assigned to', `<select id="taskAssigneeFilter"><option value="">All users</option>${assigneeOptions}</select>`) : '') +
    fld('Due from', '<input type="date" id="taskFromFilter">') + fld('Due to', '<input type="date" id="taskToFilter">') +
    '<button type="button" class="btn" id="taskFilterResetBtn">Reset filters</button>';
  el('taskFilterRow').style.display = panelOpen ? 'flex' : 'none';
  const refresh = () => { updateFilterBadge(); renderStats(); renderList(); };
  const bind = (id, key, transform = (v) => v) => { const n = el(id); if (!n) return; n.value = filters[key] || ''; n.addEventListener('change', (e) => { filters[key] = transform(e.target.value); refresh(); }); };
  bind('taskStatusFilter', 'status'); bind('taskPriorityFilter', 'priority'); bind('taskDueFilter', 'due');
  bind('taskFromFilter', 'from'); bind('taskToFilter', 'to'); bind('taskAssigneeFilter', 'assignee', (v) => (v ? Number(v) : null));
  el('taskFilterResetBtn').addEventListener('click', async () => {
    filters.status = ''; filters.priority = ''; filters.due = ''; filters.from = ''; filters.to = ''; filters.assignee = null;
    if (canSeeAll()) filters.scope = 'mine';
    await load(); renderFilters(); refresh();
  });
  updateFilterBadge();
}

function renderStats() {
  const list = baseList();
  const t0 = today0();
  const open = list.filter((t) => !isDone(t)).length;
  const overdue = list.filter((t) => !isDone(t) && dueDate(t) && dueDate(t) < t0).length;
  const upcoming = list.filter((t) => !isDone(t) && dueDate(t) && dueDate(t) > t0).length;
  const done = list.filter(isDone).length;
  const f = filters;
  const on = (k) => ({ all: !f.status && !f.due, open: f.status === 'NotDone' && !f.due, up: f.due === 'upcoming', late: f.due === 'overdue', done: f.status === 'Done' }[k] ? ' on' : '');
  el('taskStatsRow').innerHTML = `
    <div class="dash-card pipe-1 statpick${on('all')}" data-tstat="all"><span class="ic">📋</span><div class="n">${list.length}</div><div class="l">Total tasks</div></div>
    <div class="dash-card pipe-4 statpick${on('open')}" data-tstat="open"><span class="ic">⏳</span><div class="n">${open}</div><div class="l">Open</div></div>
    <div class="dash-card pipe-2 statpick${on('up')}" data-tstat="up"><span class="ic">📅</span><div class="n">${upcoming}</div><div class="l">Upcoming (future date)</div></div>
    <div class="dash-card pipe-5 statpick${on('late')}" data-tstat="late"><span class="ic">🚨</span><div class="n">${overdue}</div><div class="l">Overdue</div></div>
    <div class="dash-card pipe-3 statpick${on('done')}" data-tstat="done"><span class="ic">✅</span><div class="n">${done}</div><div class="l">Completed</div></div>`;
  el('taskStatsRow').querySelectorAll('[data-tstat]').forEach((c) => c.addEventListener('click', () => {
    const k = c.dataset.tstat;
    filters.status = ''; filters.due = '';
    if (k === 'open') filters.status = 'NotDone'; else if (k === 'up') filters.due = 'upcoming'; else if (k === 'late') filters.due = 'overdue'; else if (k === 'done') filters.status = 'Done';
    renderFilters(); renderStats(); renderList();
  }));
}

function renderKindTabs() {
  const base = listFiltered(true);
  const counts = { Call: 0, Visit: 0, Appointment: 0, Task: 0 };
  base.forEach((t) => { counts[kindOf(t)]++; });
  const tab = (key, label, n) => `<button type="button" class="task-tab${filters.kind === key ? ' active' : ''}" data-tkind="${key}">${label} <span class="c">${n}</span></button>`;
  const scopeTabs = canSeeAll() ? `<span class="task-scope" style="display:inline-flex;gap:4px;margin-right:12px;padding-right:12px;border-right:1px solid var(--line);"><button type="button" class="task-tab${filters.scope !== 'all' ? ' active' : ''}" data-tscope="mine" title="Tasks assigned to me">My tasks</button><button type="button" class="task-tab${filters.scope === 'all' ? ' active' : ''}" data-tscope="all" title="Everyone's tasks, grouped by person">Everyone</button></span>` : '';
  const fold = '<span class="task-foldall"><button type="button" class="task-tab" data-foldall="1">Collapse all</button><button type="button" class="task-tab" data-foldall="0">Expand all</button></span>';
  el('taskKindTabs').innerHTML = scopeTabs + tab('', 'All', base.length) + KIND_ORDER.map((k) => tab(k, `${KIND_META[k].icon} ${KIND_META[k].label}`, counts[k])).join('') + fold;
  el('taskKindTabs').querySelectorAll('[data-tscope]').forEach((b) => b.addEventListener('click', async () => { filters.scope = b.dataset.tscope; await load(); renderAll(); }));
  el('taskKindTabs').querySelectorAll('[data-tkind]').forEach((b) => b.addEventListener('click', () => { filters.kind = b.dataset.tkind; renderList(); }));
  el('taskKindTabs').querySelectorAll('[data-foldall]').forEach((b) => b.addEventListener('click', () => {
    const collapse = b.dataset.foldall === '1';
    document.querySelectorAll('.tcard[data-tid]').forEach((c) => { const id = Number(c.dataset.tid); if (collapse) { collapsed.add(id); expanded.delete(id); } else { collapsed.delete(id); expanded.add(id); } c.classList.toggle('collapsed', collapse); });
  }));
}

function renderAssignedByMe() {
  const t0 = today0();
  const list = [...data.created].sort((a, b) => (isDone(a) - isDone(b)) || String(a.due_date || '9999').localeCompare(String(b.due_date || '9999')));
  el('abmCount').textContent = list.length;
  el('assignedByMeList').innerHTML = list.length ? list.map((t) => abmRowHtml(t, t0)).join('') : '<div class="dash-upcoming-empty">Nothing you assigned to others.</div>';
}

function renderList() {
  renderAssignedByMe();
  renderKindTabs();
  renderCalendar();
  let list = listFiltered(false);
  const t0 = today0();
  const RANK = { High: 0, Medium: 1, Low: 2 };
  const pr = (t) => (RANK[t.priority] !== undefined ? RANK[t.priority] : 1);
  const dueOf = (t) => (dueDate(t) || new Date('9999-12-31'));
  list = [...list].sort((a, b) => {
    const da = isDone(a) ? 1 : 0, db = isDone(b) ? 1 : 0;
    if (da !== db) return da - db;
    if (da && db) return new Date(b.completed_at || 0) - new Date(a.completed_at || 0);
    return (dueOf(a) - dueOf(b)) || (pr(a) - pr(b));
  });
  const total = data.total;
  el('taskSubline').textContent = list.length ? `${list.length} task${list.length === 1 ? '' : 's'}.` : (total ? 'No tasks match your filters.' : 'No tasks yet. Create one to get started.');
  updateFilterBadge();
  const wrap = el('taskListWrap');
  wrap.classList.remove('kcols');
  if (canSeeAll() && filters.scope === 'all' && !filters.assignee && list.length) {
    // Everyone's tasks: a section per person (a shared task is listed once, under all of its people).
    const groups = []; const byKey = new Map();
    list.forEach((t) => {
      const as = people(t);
      const set = as.length ? as : [{ id: '__unassigned', full_name: 'Unassigned' }];
      const key = set.map((a) => a.id).sort().join('|');
      if (!byKey.has(key)) { const g = { name: set.map((a) => a.full_name || 'Unassigned').join(' + '), items: [] }; byKey.set(key, g); groups.push(g); }
      byKey.get(key).items.push(t);
    });
    groups.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
    wrap.innerHTML = groups.map((g) => `<div class="tsec"><span class="avatar">${escapeHtml(initialsOf(g.name))}</span><span>${escapeHtml(g.name)}</span><span class="tag" style="background:var(--panel-2); color:var(--text-faint);">${g.items.length} task${g.items.length === 1 ? '' : 's'}</span></div>${g.items.map((t) => cardHtml(t, t0)).join('')}`).join('');
    return wireCards();
  }
  if (!list.length) { wrap.innerHTML = '<p class="sub">Nothing here.</p>'; return; }
  const bucketsHtml = (items0) => BUCKETS.map((bk) => {
    const items = items0.filter((t) => bucketOf(t) === bk.key);
    if (!items.length) return '';
    return `<div class="tsec"><span style="width:10px;height:10px;border-radius:50%;background:${bk.color};display:inline-block;"></span><span>${bk.label}</span><span class="tag" style="background:var(--panel-2); color:var(--text-faint);">${items.length}</span></div>${items.map((t) => cardHtml(t, t0)).join('')}`;
  }).join('');
  if (!filters.kind) {
    // "All" tab: one vertical column per type so the page width is used.
    const cols = [['Calls', 'Call', '📞'], ['Visits', 'Visit', '📍'], ['Appointments', 'Appointment', '📅'], ['Other tasks', 'Task', '✔️']]
      .map(([label, k, ic]) => ({ label, ic, items: list.filter((t) => kindOf(t) === k) })).filter((c) => c.items.length);
    if (cols.length > 1) {
      wrap.classList.add('kcols'); wrap.style.setProperty('--kc', cols.length);
      wrap.innerHTML = cols.map((c) => `<div class="tcol"><div class="tcol-head"><span>${c.ic} ${c.label}</span><span class="tag">${c.items.length}</span></div>${bucketsHtml(c.items)}</div>`).join('');
      return wireCards();
    }
  }
  wrap.innerHTML = bucketsHtml(list);
  wireCards();
}

// ---- calendar + upcoming ---------------------------------------------------------------------------------------------------
function calendarTasks() {
  const saved = { from: filters.from, to: filters.to, due: filters.due };
  filters.from = ''; filters.to = ''; filters.due = '';
  let list;
  try { list = listFiltered(false); } finally { Object.assign(filters, saved); }
  if (filters.status !== 'Done') list = list.filter((t) => !isDone(t));
  return list.filter((t) => t.due_date);
}
function pickDay(key) {
  const same = filters.from === key && filters.to === key;
  filters.from = same ? '' : key; filters.to = same ? '' : key; filters.due = '';
  renderFilters(); renderStats(); renderList();
}
function renderCalendar() {
  const y = calMonth.getFullYear(), m = calMonth.getMonth();
  el('dashCalMonthLabel').textContent = calMonth.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
  el('dashCalWeekdays').innerHTML = ['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((w) => `<div class="mini-cal-wd">${w}</div>`).join('');
  const rel = calendarTasks();
  const byDay = {};
  rel.forEach((t) => { (byDay[t.due_date] = byDay[t.due_date] || []).push(t); });
  const firstDow = new Date(y, m, 1).getDay(), daysInMonth = new Date(y, m + 1, 0).getDate();
  const now = new Date(), todayKey = ymd(now);
  const selKey = (filters.from && filters.from === filters.to) ? filters.from : '';
  let cells = '';
  for (let i = 0; i < firstDow; i++) cells += '<div class="mini-cal-day empty"></div>';
  for (let d = 1; d <= daysInMonth; d++) {
    const key = ymd(new Date(y, m, d));
    const items = byDay[key] || [];
    const kinds = [...new Set(items.map(kindOf))].slice(0, 3);
    const tip = items.length ? `${items.length} due: ` + KIND_ORDER.map((k) => { const n = items.filter((t) => kindOf(t) === k).length; return n ? `${n} ${k === 'Task' ? 'other' : k}` : ''; }).filter(Boolean).join(', ') : 'No tasks due';
    const late = items.length && key < todayKey;
    cells += `<div class="mini-cal-day${key === todayKey ? ' today' : ''}${items.length ? ' has-event' : ''}${late ? ' late' : ''}${key === selKey ? ' sel' : ''}" title="${escapeHtml(tip)}" data-day="${key}">${d}${items.length > 1 ? `<span class="cnt">${items.length}</span>` : ''}${kinds.length ? `<span class="dots">${kinds.map((k) => `<i style="background:${CAL_KIND_COLOR[k]}"></i>`).join('')}</span>` : ''}</div>`;
  }
  el('dashCalDays').innerHTML = cells;
  const monthKey = `${y}-${String(m + 1).padStart(2, '0')}`;
  const inMonth = rel.filter((t) => t.due_date.slice(0, 7) === monthKey).length;
  el('dashCalFoot').innerHTML = `<span style="color:var(--text-faint);">${inMonth} due this month</span><span style="display:flex;gap:6px;">${selKey ? '<button type="button" class="btn btn-icon" id="calClearDayBtn" style="padding:4px 10px;">Show all days</button>' : ''}<button type="button" class="btn btn-icon" id="calTodayBtn" style="padding:4px 10px;">Today</button></span>`;
  el('calTodayBtn').onclick = () => { calMonth = new Date(now.getFullYear(), now.getMonth(), 1); renderCalendar(); };
  const cd = el('calClearDayBtn'); if (cd) cd.onclick = () => { filters.from = ''; filters.to = ''; renderFilters(); renderStats(); renderList(); };
  el('dashCalDays').querySelectorAll('[data-day]').forEach((c) => c.addEventListener('click', () => pickDay(c.dataset.day)));
  const upcoming = rel.filter((t) => t.due_date >= todayKey).sort((a, b) => a.due_date.localeCompare(b.due_date)).slice(0, 8);
  el('dashUpcomingList').innerHTML = upcoming.length ? upcoming.map((t) => `
    <div class="dash-upcoming-item" style="cursor:pointer;" data-day="${t.due_date}">
      <div class="u-title">${KIND_META[kindOf(t)].icon} ${escapeHtml(t.title || 'Task')}</div>
      <div class="u-meta">${dueDate(t).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}${t.related_customer_name ? ' &middot; ' + escapeHtml(t.related_customer_name) : ''}</div>
    </div>`).join('') : '<div class="dash-upcoming-empty">No upcoming tasks.</div>';
  el('dashUpcomingList').querySelectorAll('[data-day]').forEach((c) => c.addEventListener('click', () => pickDay(c.dataset.day)));
}

// ---- actions ---------------------------------------------------------------------------------------------------------------
const find = (id) => everything().find((t) => String(t.id) === String(id));
async function afterChange() { await load(); renderAll(); }

async function markDone(id) {
  const t = find(id); if (!t) return;
  if (!canUpdateStatus(t)) { await customAlert('You can only update the status of tasks assigned to you.'); renderList(); return; }
  try { await api.patch(`tasks/${id}/`, { status: 'Done', version: t.version }); } catch (e) { await customAlert(apiErrorMessage(e)); }
  await afterChange();
}
async function removeTask(id) {
  const t = find(id); if (!t) return;
  if (!canRemove(t)) { await customAlert(`Only the person who created this task (${(t.created_by && t.created_by.full_name) || 'the creator'}) can remove it. It stays on your panel until they do.`); return; }
  const acknowledging = isDone(t) && canManage(t);
  if (!await customConfirm(acknowledging ? 'Mark this task as complete? It will be removed from the Task panel for everyone.' : 'Remove this task?')) return;
  try { await api.delete(`tasks/${id}/`); } catch (e) { await customAlert(apiErrorMessage(e)); }
  await afterChange();
}
function wireCards() {
  const scope = (document.getElementById('taskListWrap'));
  document.querySelectorAll('#view-tasks [data-status]').forEach((b) => b.onclick = () => markDone(b.dataset.status));
  document.querySelectorAll('#view-tasks [data-delete]').forEach((b) => b.onclick = () => removeTask(b.dataset.delete));
  document.querySelectorAll('#view-tasks [data-edit]').forEach((b) => b.onclick = () => openTaskForm(find(b.dataset.edit)));
  scope.querySelectorAll('[data-fold]').forEach((b) => b.onclick = () => {
    const id = Number(b.dataset.fold), c = b.closest('.tcard');
    const now = c.classList.toggle('collapsed');
    if (now) { collapsed.add(id); expanded.delete(id); } else { collapsed.delete(id); expanded.add(id); }
  });
  scope.querySelectorAll('[data-person]').forEach((n) => n.onclick = () => { const [c, p] = n.dataset.person.split('/'); navigate('person', `${c}/${p}`); });
  scope.querySelectorAll('[data-customer]').forEach((n) => n.onclick = () => navigate('customerview', n.dataset.customer));
  scope.querySelectorAll('[data-doc]').forEach((n) => n.onclick = () => navigate('sales', n.dataset.doctype));
}

// ---- task form (modal, as in the reference) ----------------------------------------------------------------------------------
async function openTaskForm(task) {
  if (task && !canManage(task)) { await customAlert('Only the task creator or an admin can edit this task.'); return; }
  const customers = await api.all('customers/');
  const selected = task ? people(task).map((a) => a.id) : [me()];
  const employees = state.employees.filter((e) => e.is_active !== false || selected.includes(e.user_id));
  openModal(`
    <div class="tf-hero"><div class="sdv-ico">✅</div><div><h2 id="taskFormTitle">${task ? 'Edit Task' : 'New Task'}</h2><p class="modal-sub">Assign work, set a due date and link it to a customer.</p></div></div>
    <div class="form-grid">
      <div class="field span2"><label for="tk-title">Title</label><input type="text" id="tk-title" placeholder="What needs to be done?" value="${escapeHtml(task ? task.title : '')}"></div>
      <div class="field span2"><label for="tk-desc">Description</label><textarea id="tk-desc" rows="3" placeholder="Details (optional)">${escapeHtml(task ? task.description || '' : '')}</textarea></div>
      <div class="field span2"><label>Assign to <span>(pick one or more)</span></label>
        <div class="tk-dd" id="tk-assignees">
          <button type="button" class="tk-dd-btn" id="tkDdBtn"><span id="tkDdLabel">Select people</span><i>&#9662;</i></button>
          <div class="tk-dd-panel" id="tkDdPanel" style="display:none;">
            ${employees.length > 6 ? '<input type="text" class="tk-dd-search" id="tkDdSearch" placeholder="Search people…" autocomplete="off">' : ''}
            <div class="tk-dd-list">${employees.map((e) => `<label class="tk-dd-item" data-name="${escapeHtml((e.full_name || '').toLowerCase())}"><input type="checkbox" class="tk-assignee-check" value="${e.user_id}" ${selected.includes(e.user_id) ? 'checked' : ''}><span class="av">${escapeHtml(initialsOf(e.full_name))}</span><span class="nm">${escapeHtml(e.full_name)}</span></label>`).join('')}</div>
          </div>
        </div></div>
      <div class="field"><label for="tk-priority">Priority</label><select id="tk-priority"><option value="High">High</option><option value="Medium">Medium</option><option value="Low">Low</option></select></div>
      <div class="field"><label for="tk-due">Due date</label><input type="date" id="tk-due" value="${task && task.due_date ? task.due_date : ''}"></div>
      <div class="field span2"><label for="tk-customer">Related customer (optional)</label><select id="tk-customer"><option value="">None</option>${customers.map((c) => `<option value="${c.id}">${escapeHtml(c.label || c.name)}</option>`).join('')}</select></div>
    </div>
    <div class="modal-actions"><button class="btn" id="taskFormCancelBtn">Cancel</button><button class="btn btn-primary" id="taskFormSaveBtn">Save task</button></div>
    <p class="field-hint" id="taskFormHint"></p>`, {
    size: 'narrow tform',
    onMount: (m) => {
      m.querySelector('#tk-priority').value = task ? task.priority : 'Medium';
      m.querySelector('#tk-customer').value = task && task.related_customer_id ? String(task.related_customer_id) : '';
      const label = () => {
        const names = [...m.querySelectorAll('.tk-assignee-check:checked')].map((c) => c.closest('.tk-dd-item').querySelector('.nm').textContent.trim());
        const lab = m.querySelector('#tkDdLabel'); lab.textContent = names.length ? names.join(', ') : 'Select people'; lab.classList.toggle('ph', !names.length);
      };
      label();
      const panel = m.querySelector('#tkDdPanel');
      m.querySelector('#tkDdBtn').onclick = (e) => { e.stopPropagation(); panel.style.display = panel.style.display === 'none' ? 'block' : 'none'; };
      m.addEventListener('click', (e) => { if (!e.target.closest('#tkDdPanel') && !e.target.closest('#tkDdBtn')) panel.style.display = 'none'; });
      m.addEventListener('change', (e) => { if (e.target.classList.contains('tk-assignee-check')) label(); });
      const search = m.querySelector('#tkDdSearch');
      if (search) search.addEventListener('input', () => { const q = search.value.trim().toLowerCase(); panel.querySelectorAll('.tk-dd-item').forEach((it) => { it.style.display = !q || it.dataset.name.includes(q) ? '' : 'none'; }); });
      m.querySelector('#taskFormCancelBtn').onclick = closeModal;
      m.querySelector('#taskFormSaveBtn').onclick = async () => {
        const hint = m.querySelector('#taskFormHint');
        const title = m.querySelector('#tk-title').value.trim();
        if (!title) { hint.textContent = 'Enter a title.'; return; }
        // The list order of the checked boxes is the order people were listed in; the first becomes the primary assignee.
        const ids = [...m.querySelectorAll('.tk-assignee-check:checked')].map((c) => Number(c.value));
        if (!ids.length) { hint.textContent = 'Choose at least one person to assign this to.'; return; }
        const body = { title, description: m.querySelector('#tk-desc').value.trim(), assigned_to_ids: ids, priority: m.querySelector('#tk-priority').value,
          due_date: m.querySelector('#tk-due').value || null, related_customer_id: m.querySelector('#tk-customer').value || null };
        try {
          if (task) await api.patch(`tasks/${task.id}/`, { ...body, version: task.version });
          else await api.post('tasks/', body);
        } catch (e) { hint.textContent = apiErrorMessage(e); return; }
        closeModal();
        await afterChange();
      };
    },
  });
}

function renderAll() { renderFilters(); renderStats(); renderList(); }

export async function mountTasks(rootEl) {
  root = rootEl;
  filters.assignee = null;
  if (!canSeeAll()) filters.scope = 'mine';
  rootEl.innerHTML = `
    <div class="view active glassc glassp glassv" id="view-tasks">
      <div class="view-head cust-hero">
        <div><p class="brand-eyebrow">Work</p><h1>Task</h1><p class="sub" id="taskSubline">Loading&hellip;</p></div>
        <button class="btn btn-primary" id="taskNewBtn">+ New Task</button>
      </div>
      <div class="dash-layout">
        <div class="dash-main">
          <div class="dash-grid" id="taskStatsRow" style="margin-bottom:16px;"></div>
          <div class="task-tabs" id="taskKindTabs"></div>
          <div class="toolbar" style="margin-bottom:10px;">
            <div class="search"><input type="text" id="taskSearchInput" placeholder="Search task, customer, contact or person"></div>
            <button class="btn" id="taskFilterToggleBtn">Filters <span class="task-fbadge" id="taskFilterBadge" style="display:none;"></span></button>
          </div>
          <div class="task-fpanel" id="taskFilterRow" style="display:none;"></div>
          <div id="taskListWrap"></div>
        </div>
        <div class="dash-side">
          <div class="panel-box" style="max-width:none;">
            <div class="mini-cal-head">
              <button type="button" class="btn btn-icon" id="dashCalPrevBtn" style="padding:4px 9px;">&lsaquo;</button>
              <span id="dashCalMonthLabel" style="font-weight:600; font-size:13.5px;"></span>
              <button type="button" class="btn btn-icon" id="dashCalNextBtn" style="padding:4px 9px;">&rsaquo;</button>
            </div>
            <div class="mini-cal-grid" id="dashCalWeekdays"></div>
            <div class="mini-cal-grid" id="dashCalDays"></div>
            <div class="cal-legend"><span><i style="background:#2f6fb5"></i>Call</span><span><i style="background:#1f8a6a"></i>Visit</span><span><i style="background:#8a4fb8"></i>Appointment</span><span><i style="background:#8a94a0"></i>Other</span></div>
            <div id="dashCalFoot" style="display:flex; gap:8px; align-items:center; justify-content:space-between; margin-top:10px; font-size:12.5px;"></div>
          </div>
          <div class="panel-box" style="max-width:none; margin-top:16px;">
            <div class="section-label" style="text-transform:none; font-size:12.5px; letter-spacing:0; margin-bottom:8px;">Upcoming tasks</div>
            <div id="dashUpcomingList"></div>
          </div>
          <div class="panel-box" style="max-width:none; margin-top:16px;" id="assignedByMePanel">
            <div class="section-label" style="text-transform:none; font-size:12.5px; letter-spacing:0; margin-bottom:8px;">Assigned by me <span class="tag" id="abmCount" style="margin-left:6px;"></span></div>
            <div id="assignedByMeList"></div>
          </div>
        </div>
      </div>
    </div>`;
  el('taskNewBtn').onclick = () => openTaskForm(null);
  el('taskFilterToggleBtn').onclick = () => { panelOpen = !panelOpen; el('taskFilterRow').style.display = panelOpen ? 'flex' : 'none'; };
  el('taskSearchInput').value = searchText;
  el('taskSearchInput').addEventListener('input', (e) => { searchText = e.target.value; renderList(); });
  el('dashCalPrevBtn').onclick = () => { calMonth = new Date(calMonth.getFullYear(), calMonth.getMonth() - 1, 1); renderCalendar(); };
  el('dashCalNextBtn').onclick = () => { calMonth = new Date(calMonth.getFullYear(), calMonth.getMonth() + 1, 1); renderCalendar(); };
  await load();
  renderAll();
}
