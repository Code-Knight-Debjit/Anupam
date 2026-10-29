// SPA entry point — shell wiring (sidebar nav, role-based nav visibility,
// notification bell, badges) + router bootstrap. Ported from the original's
// `afterLogin()`/`setNavBadge`/`renderNotifBadge`/`renderNotifList`
// (contact_management.html ~L4560-4660, ~L13560-13630).
import { api } from './api.js';
import { loadBootstrap, state } from './state.js';
import { registerView, navigate, startRouter } from './router.js';
import { el, escapeHtml, fmtDateTime, toast } from './ui.js';

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

const PAGE_TITLES = {
  dashboard: 'Dashboard', tasks: 'Tasks', callinglist: 'Outreach', attendance: 'Attendance',
  customers: 'Customers', map: 'Map & Nearby', sales: 'Sales', payments: 'Payment Collection',
  labels: 'Print Label', reports: 'Reports', managelists: 'Manage Lists', import: 'Import Excel',
  users: 'Users', branches: 'Branches',
};

function setTitleOnNavigate() {
  window.addEventListener('hashchange', updateTitle);
  updateTitle();
}
function updateTitle() {
  const view = (window.location.hash || '').replace(/^#\/?/, '').split('/')[0] || 'dashboard';
  el('pageTitle').textContent = PAGE_TITLES[view] || 'Anupam 360';
}

// Menu visibility comes from the server (`me.nav`, REQ-ROLE-03/04) — the
// endpoints behind each menu enforce the same rules, this only tidies the UI.
function applyRoleVisibility() {
  const items = Array.from(document.querySelectorAll('#app-sidebar .nav-item'));
  items.forEach((btn) => {
    const label = (btn.querySelector('span') || btn).textContent.trim();
    btn.style.display = state.nav.includes(label) ? '' : 'none';
  });
  document.querySelectorAll('#app-sidebar .nav-label').forEach((heading) => {
    let node = heading.nextElementSibling, anyVisible = false;
    while (node && !node.classList.contains('nav-label') && !node.classList.contains('sidebar-footer')) {
      if (node.classList.contains('nav-item') && node.style.display !== 'none') anyVisible = true;
      node = node.nextElementSibling;
    }
    heading.style.display = anyVisible ? '' : 'none';
  });
  const userChipName = el('curUserName'), userChipRole = el('curUserRole');
  if (userChipName) userChipName.textContent = state.me.full_name || state.me.username;
  if (userChipRole) userChipRole.textContent = (state.me.role || '').replace(/_/g, ' ');
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
    setNavBadge('#notifBadge', unread.length);
  } catch (e) { /* ignore */ }
}

async function renderNotifList() {
  const list = await api.all('notifications/');
  const box = el('notifList');
  box.innerHTML = list.length
    ? list.map((n) => `
      <div class="notif-item" data-id="${n.id}" style="padding:10px 14px;cursor:pointer;${n.read ? '' : 'background:var(--surface-container-low);'}">
        <div style="font-size:13px;">${escapeHtml(n.text || '')}</div>
        <div class="sub" style="font-size:11px;margin-top:2px;">${fmtDateTime(n.created_at)}</div>
      </div>`).join('')
    : '<div class="empty-state">No notifications yet.</div>';
  box.querySelectorAll('.notif-item').forEach((node) => {
    node.addEventListener('click', async () => {
      const id = node.dataset.id;
      const n = list.find((x) => String(x.id) === id);
      await api.patch(`notifications/${id}/`, { read: true });
      el('notifDropdown').style.display = 'none';
      refreshNotifBadge();
      if (n && n.type === 'leave') navigate('attendance');
      else if (n && n.related_document_id) navigate('sales');
      else navigate('tasks');
    });
  });
}

function wireNotifBell() {
  const btn = el('notifBellBtn'), dd = el('notifDropdown');
  btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const opening = dd.style.display === 'none';
    dd.style.display = opening ? 'block' : 'none';
    if (opening) await renderNotifList();
  });
  el('notifMarkAllBtn').addEventListener('click', async (e) => {
    e.stopPropagation();
    const unread = await api.all('notifications/', { unread: '1' });
    await Promise.all(unread.map((n) => api.patch(`notifications/${n.id}/`, { read: true })));
    refreshNotifBadge();
    renderNotifList();
  });
  document.addEventListener('click', () => { dd.style.display = 'none'; });
}

function wireSidebarMobile() {
  const burger = el('topbarBurger'), sidebar = el('app-sidebar'), backdrop = el('sidebarBackdrop');
  burger.addEventListener('click', () => { sidebar.classList.add('open'); backdrop.classList.add('open'); });
  backdrop.addEventListener('click', () => { sidebar.classList.remove('open'); backdrop.classList.remove('open'); });
  document.querySelectorAll('.nav-item[data-view]').forEach((btn) => {
    btn.addEventListener('click', () => {
      navigate(btn.dataset.view, btn.dataset.subtab);
      sidebar.classList.remove('open'); backdrop.classList.remove('open');
    });
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
  applyRoleVisibility();
  setTitleOnNavigate();
  wireNotifBell();
  wireSidebarMobile();
  el('logoutBtn').addEventListener('click', () => { window.location.href = '/360/logout/'; });

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

  startRouter();
  refreshBadges();
  setInterval(refreshBadges, 60000);
}

boot().catch((e) => {
  console.error(e);
  toast('Failed to load Anupam 360 — please refresh.', 'error');
});
