// SPA entry point — shell wiring (sidebar nav, role-based nav visibility,
// notification bell, badges) + router bootstrap. Ported from the original's
// `afterLogin()`/`setNavBadge`/`renderNotifBadge`/`renderNotifList`
// (contact_management.html ~L4560-4660, ~L13560-13630).
import { api } from './api.js';
import { loadBootstrap, state } from './state.js';
import { registerView, navigate, startRouter } from './router.js';
import { el, escapeHtml, fmtDateTime, toast, initials } from './ui.js';

import { mountDashboard } from './views/dashboard.js';
import { mountTasks } from './views/tasks.js';
import { mountOutreach } from './views/outreach.js';
import { mountAttendance } from './views/attendance.js';
import { mountCustomers } from './views/customers.js';
import { mountMap } from './views/map.js';
import { mountSales } from './views/sales.js';
import { mountPayments } from './views/payments.js';
import { mountLabels } from './views/labels.js';
import { mountReports } from './views/reports.js';
import { mountManageLists } from './views/managelists.js';
import { mountImportExcel } from './views/importexcel.js';
import { mountUsers } from './views/users.js';
import { mountBranches } from './views/branches.js';
import { mountBackup, mountAuditLog } from './views/backup.js';
import { mountApprovals } from './views/approvals.js';
import { initA11y } from './a11y.js';

const ROLE_LABELS = { ADMIN: 'Admin', BRANCH_MANAGER: 'Branch Manager', BRANCH_STAFF: 'Branch Staff', SALES_MANAGER: 'Sales Manager' };

// Menu visibility comes from the server (`me.nav`, REQ-ROLE-03/04) — the endpoints behind each menu enforce the
// same rules, this only tidies the UI. Group headings with nothing visible under them are hidden too (the
// reference shows e.g. no "Main panel" heading to a non-admin).
function applyRoleVisibility() {
  document.querySelectorAll('#app-sidebar .nav-item').forEach((btn) => {
    const label = (btn.querySelector('span') || btn).textContent.trim();
    btn.style.display = state.nav.includes(label) ? '' : 'none';
  });
  document.querySelectorAll('#app-sidebar .nav-group').forEach((group) => {
    const anyVisible = Array.from(group.querySelectorAll('.nav-item')).some((b) => b.style.display !== 'none');
    group.style.display = anyVisible ? '' : 'none';
  });
  const name = state.me.full_name || state.me.username;
  el('curAvatar').textContent = initials(name);
  el('curName').textContent = name;
  el('curRole').textContent = ROLE_LABELS[state.me.role] || (state.me.role || '').replace(/_/g, ' ');
}

function setNavBadge(selector, count) {
  document.querySelectorAll(selector).forEach((b) => {
    if (count > 0) { b.textContent = count > 99 ? '99+' : String(count); b.style.display = 'inline-block'; }
    else b.style.display = 'none';
  });
}

async function updateSalesNavBadges() {
  try {
    const [enquiries, quotations, proformas, dcs, pos, payments] = await Promise.all([
      api.all('sales-documents/', { type: 'enquiry' }),
      api.all('sales-documents/', { type: 'quotation' }),
      api.all('sales-documents/', { type: 'proforma' }),
      api.all('sales-documents/', { type: 'dc' }),
      api.all('sales-documents/', { type: 'po' }),
      api.all('payment-collections/'),
    ]);
    setNavBadge('#navBadgeEnquiry', enquiries.filter((d) => (d.order_status || 'Pending') === 'Pending').length);
    setNavBadge('#navBadgeQuotation', quotations.filter((d) => (d.order_status || 'Pending') === 'Pending').length);
    setNavBadge('#navBadgeProforma', proformas.filter((d) => (d.order_status || 'Pending') === 'Pending').length);
    setNavBadge('#navBadgeDC', dcs.filter((d) => (d.items || []).some((it) => Number(it.qty) > 0)).length);
    setNavBadge('#navBadgePO', pos.filter((d) => d.order_status !== 'Completed').length);
    setNavBadge('#navBadgePayments', payments.filter((p) => Number(p.balance) > 0).length);
  } catch (e) { /* badges are best-effort */ }
}

async function updateTaskBadge() {
  try {
    const open = await api.all('tasks/', { status: 'Open' });
    const mine = open.filter((t) => t.assigned_to.id === state.me.user_id || (t.joint_with_user_ids || []).includes(state.me.user_id));
    setNavBadge('#taskBadge', mine.length);
  } catch (e) { /* ignore */ }
}

async function updateCallingListBadge() {
  try {
    const all = await api.all('call-assignments/');
    const mine = all.filter((a) => a.assigned_to && a.assigned_to.id === state.me.user_id && a.status !== 'Called');
    setNavBadge('#callingListBadge', mine.length);
  } catch (e) { /* ignore */ }
}

async function updateAttBadge() {
  try {
    const pending = await api.all('leave-requests/');
    setNavBadge('#attBadge', pending.filter((l) => l.status === 'Pending').length);
  } catch (e) { /* ignore */ }
}

async function refreshNotifBadge() {
  try {
    const unread = await api.all('notifications/', { unread: '1' });
    setNavBadge('#notifBadge, #notifBadgeMobile', unread.length);
  } catch (e) { /* ignore */ }
}

async function renderNotifList() {
  const list = await api.all('notifications/');
  const html = list.length
    ? list.map((n) => `
      <div class="notif-item ${n.read ? '' : 'unread'}" data-id="${n.id}">
        <div class="ni-text">${escapeHtml(n.text || '')}</div>
        <div class="ni-meta">${fmtDateTime(n.created_at)}</div>
      </div>`).join('')
    : '<div class="notif-empty">No notifications yet.</div>';
  ['notifList', 'notifListMobile'].forEach((id) => {
    const box = el(id);
    box.innerHTML = html;
    box.querySelectorAll('.notif-item').forEach((node) => {
      node.addEventListener('click', async () => {
        const n = list.find((x) => String(x.id) === node.dataset.id);
        await api.patch(`notifications/${node.dataset.id}/`, { read: true });
        closeNotifDropdowns();
        refreshNotifBadge();
        if (n && n.type === 'leave') navigate('attendance');
        else if (n && n.related_document_id) navigate('sales');
        else navigate('tasks');
      });
    });
  });
}

function closeNotifDropdowns() {
  el('notifDropdown').classList.remove('open');
  el('notifDropdownMobile').classList.remove('open');
}

function wireNotifBell() {
  [['notifBellBtn', 'notifDropdown'], ['notifBellBtnMobile', 'notifDropdownMobile']].forEach(([btnId, ddId]) => {
    el(btnId).addEventListener('click', async (e) => {
      e.stopPropagation();
      const dd = el(ddId);
      const opening = !dd.classList.contains('open');
      closeNotifDropdowns();
      if (opening) { dd.classList.add('open'); await renderNotifList(); }
    });
  });
  ['notifMarkAllBtn', 'notifMarkAllBtnMobile'].forEach((id) => el(id).addEventListener('click', async (e) => {
    e.stopPropagation();
    const unread = await api.all('notifications/', { unread: '1' });
    await Promise.all(unread.map((n) => api.patch(`notifications/${n.id}/`, { read: true })));
    refreshNotifBadge();
    renderNotifList();
  }));
  document.addEventListener('click', closeNotifDropdowns);
}

function wireSidebarMobile() {
  const burger = el('topbarBurger'), sidebar = el('app-sidebar'), backdrop = el('sidebarBackdrop');
  const close = () => { sidebar.classList.remove('open'); backdrop.classList.remove('open'); };
  burger.addEventListener('click', () => { sidebar.classList.add('open'); backdrop.classList.add('open'); });
  backdrop.addEventListener('click', close);
  document.querySelectorAll('.nav-item[data-view]').forEach((btn) => {
    btn.addEventListener('click', () => { navigate(btn.dataset.view, btn.dataset.subtab); close(); });
  });
}

function refreshBadges() {
  updateTaskBadge();
  updateCallingListBadge();
  updateAttBadge();
  updateSalesNavBadges();
  refreshNotifBadge();
}

async function boot() {
  await loadBootstrap();
  initA11y();
  applyRoleVisibility();
  wireNotifBell();
  wireSidebarMobile();
  const logout = () => { window.location.href = '/360/logout/'; };
  ['logoutBtn', 'mobileLogoutBtn', 'switchUserBtn'].forEach((id) => el(id).addEventListener('click', logout));

  registerView('dashboard', mountDashboard);
  registerView('tasks', mountTasks);
  registerView('callinglist', mountOutreach);
  registerView('attendance', mountAttendance);
  registerView('customers', mountCustomers);
  registerView('map', mountMap);
  registerView('sales', mountSales);
  registerView('payments', mountPayments);
  registerView('labels', mountLabels);
  registerView('reports', mountReports);
  registerView('managelists', mountManageLists);
  registerView('import', mountImportExcel);
  registerView('users', mountUsers);
  registerView('branches', mountBranches);
  registerView('backup', mountBackup);
  registerView('auditlog', mountAuditLog);
  registerView('approvals', mountApprovals);

  startRouter();
  refreshBadges();
  setInterval(refreshBadges, 60000);
}

boot().catch((e) => {
  console.error(e);
  toast('Failed to load Anupam 360 — please refresh.', 'error');
});
