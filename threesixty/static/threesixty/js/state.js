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
