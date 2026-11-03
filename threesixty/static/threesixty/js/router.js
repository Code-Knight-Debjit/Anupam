// Hash-based client router — mirrors the original's single `switchView(view, subtab)`
// dispatcher, but keeps the view+subtab in the URL hash (`#/sales/quotation`)
// so back/forward and page refresh land on the right screen.
const routes = {};

export function registerView(name, mountFn) {
  routes[name] = mountFn;
}

export function navigate(view, subtab, ...rest) {
  const hash = '#/' + [view, subtab, ...rest].filter((x) => x !== undefined && x !== null && x !== '').join('/');
  if (window.location.hash === hash) renderCurrentRoute();
  else window.location.hash = hash;
}

function parseHash() {
  const raw = (window.location.hash || '').replace(/^#\/?/, '');
  const [view, subtab, ...rest] = raw.split('/');
  return { view: view || 'dashboard', subtab: subtab || null, rest };
}

// Pages that belong to a sidebar entry without having one of their own (the reference keeps "Customer" lit on them).
const NAV_OWNER = { customerview: 'customers', customerform: 'customers', person: 'customers', salesform: 'sales', paymentform: 'payments', paymenthistory: 'payments', paymentlog: 'payments' };

let currentCleanup = null;
async function renderCurrentRoute() {
  const { view, subtab, rest } = parseHash();
  const mountFn = routes[view] || routes.dashboard;
  if (currentCleanup) { try { currentCleanup(); } catch (e) { /* ignore */ } currentCleanup = null; }
  document.querySelectorAll('.nav-item[data-view]').forEach((btn) => {
    const owner = NAV_OWNER[view] || view;
    const match = btn.dataset.view === owner && (!btn.dataset.subtab || btn.dataset.subtab === subtab);
    btn.classList.toggle('active', match);
  });
  const root = document.getElementById('app-view');
  root.innerHTML = '<div class="empty">Loading…</div>';
  window.scrollTo(0, 0);
  try {
    currentCleanup = await mountFn(root, subtab, rest);
  } catch (e) {
    root.innerHTML = `<div class="empty-state">Something went wrong loading this page.<br>${(e && e.message) || ''}</div>`;
    console.error(e);
  }
}

export function startRouter() {
  window.addEventListener('hashchange', renderCurrentRoute);
  renderCurrentRoute();
}
