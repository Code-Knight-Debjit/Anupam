// Hash-based client router — mirrors the original's single `switchView(view, subtab)`
// dispatcher, but keeps the view+subtab in the URL hash (`#/sales/quotation`)
// so back/forward and page refresh land on the right screen.
const routes = {};

export function registerView(name, mountFn) {
  routes[name] = mountFn;
}

export function navigate(view, subtab) {
  const hash = subtab ? `#/${view}/${subtab}` : `#/${view}`;
  if (window.location.hash === hash) renderCurrentRoute();
  else window.location.hash = hash;
}

function parseHash() {
  const raw = (window.location.hash || '').replace(/^#\/?/, '');
  const [view, subtab] = raw.split('/');
  return { view: view || 'dashboard', subtab: subtab || null };
}

let currentCleanup = null;
async function renderCurrentRoute() {
  const { view, subtab } = parseHash();
  const mountFn = routes[view] || routes.dashboard;
  if (currentCleanup) { try { currentCleanup(); } catch (e) { /* ignore */ } currentCleanup = null; }
  document.querySelectorAll('.nav-item[data-view]').forEach((btn) => {
    const match = btn.dataset.view === view && (!btn.dataset.subtab || btn.dataset.subtab === subtab);
    btn.classList.toggle('active', match);
  });
  const root = document.getElementById('app-view');
  root.innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    currentCleanup = await mountFn(root, subtab);
  } catch (e) {
    root.innerHTML = `<div class="empty-state">Something went wrong loading this page.<br>${(e && e.message) || ''}</div>`;
    console.error(e);
  }
}

export function startRouter() {
  window.addEventListener('hashchange', renderCurrentRoute);
  renderCurrentRoute();
}
