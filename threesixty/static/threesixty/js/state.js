// Session-wide state loaded once at boot: current user/role flags (`me`)
// and shared reference data (`bootstrap` — branches, lookups, sales
// persons, site settings, holidays). Mirrors the original's in-memory
// `currentUser`/`branches`/`employees`-at-load pattern, just fetched from
// the API instead of localStorage.
import { api } from './api.js';

export const state = {
  me: null,
  flags: {},
  nav: [],
  reportTabs: [],
  branches: [],
  lookups: {},
  salesPersons: [],
  employees: [],
  siteSettings: {},
  holidays: [],
};

export async function loadBootstrap() {
  const [me, boot, employees] = await Promise.all([api.get('me/'), api.get('bootstrap/'), api.all('employees/')]);
  state.employees = employees.filter((e) => e.is_active);
  state.me = me.user;
  state.flags = me.flags;
  state.nav = me.nav || [];
  state.reportTabs = me.report_tabs || [];
  state.branches = boot.branches;
  state.lookups = boot.lookups;
  state.salesPersons = boot.sales_persons;
  state.siteSettings = boot.site_settings;
  state.holidays = boot.holidays;
}

export function lookup(kind) {
  return state.lookups[kind] || [];
}

export function branchName(id) {
  const b = state.branches.find((x) => x.id === id);
  return b ? b.name : '—';
}

export function isAdmin() { return !!state.flags.is_admin; }
export function isBranchManager() { return !!state.flags.is_branch_manager; }
export function isBranchStaff() { return !!state.flags.is_branch_staff; }
export function isSalesManager() { return !!state.flags.is_sales_manager; }

/** <option>s of the people tasks / outreach can be given to (login users, by user id). */
export function userOptionsHtml(selected) {
  const esc = (v) => String(v).replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
  return state.employees.map((u) => `<option value="${u.user_id}" ${String(selected) === String(u.user_id) ? 'selected' : ''}>${esc(u.full_name)}</option>`).join('');
}

const ROLE_LABELS = { ADMIN: 'Admin', BRANCH_MANAGER: 'Branch Manager', BRANCH_STAFF: 'Branch Staff', SALES_MANAGER: 'Sales Manager' };
/** "Branch Manager" for the API's BRANCH_MANAGER — the wording the reference shows everywhere. */
export const roleLabel = (role) => ROLE_LABELS[role] || String(role || '').replace(/_/g, ' ');

/** The app logo and the optional separate sidebar logo the Admin set on the Branches page (else the built-in ones). */
export function applyLogos() {
  const app = (state.siteSettings || {}).appLogo, side = (state.siteSettings || {}).sidebarLogo;
  const appUrl = app && app.url ? app.url : '';
  const mobile = document.querySelector('#logoRowMobile img'); if (mobile) { mobile.dataset.default = mobile.dataset.default || mobile.getAttribute('src'); mobile.src = appUrl || mobile.dataset.default; }
  const sidebar = document.querySelector('#logoRowApp img');
  if (sidebar) {
    sidebar.dataset.default = sidebar.dataset.default || sidebar.getAttribute('src');
    sidebar.src = (side && side.url) || appUrl || sidebar.dataset.default;
    sidebar.style.cssText = side && side.url ? 'height:56px; width:auto; max-width:164px; object-fit:contain; display:block;' : 'width:100%; max-width:170px; height:auto; display:block;';
  }
  if (appUrl) window.THREESIXTY_LOGO = appUrl;
  return { app: appUrl, sidebar: (side && side.url) || '' };
}
