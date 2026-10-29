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
  siteSettings: {},
  holidays: [],
};

export async function loadBootstrap() {
  const [me, boot] = await Promise.all([api.get('me/'), api.get('bootstrap/')]);
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
