// Accessibility and small-screen helpers, applied on top of the page without touching the markup:
//  * dialogs get role="dialog" + aria-modal, move focus in, trap Tab, close on Esc, and give focus back
//  * toasts are announced politely to screen readers
//  * form controls without a label get one from their placeholder / neighbouring label text
//  * the active menu entry is marked aria-current, icon-only buttons get names
//  * a responsive stylesheet (tables scroll, tap targets grow, the sidebar becomes a drawer)
const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
let lastFocus = null;
let uid = 0;

function enhanceDialog(modal) {
  if (!modal || modal.dataset.a11y) return;
  modal.dataset.a11y = '1';
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  const heading = modal.querySelector('h1,h2,h3');
  if (heading) { heading.id = heading.id || `dlg-title-${++uid}`; modal.setAttribute('aria-labelledby', heading.id); }
  lastFocus = document.activeElement;
  const first = modal.querySelector(FOCUSABLE);
  if (first) first.focus();
}

function labelOrphans(scope) {
  scope.querySelectorAll('input,select,textarea').forEach((control) => {
    if (control.type === 'hidden' || control.type === 'checkbox' || control.type === 'radio') return;
    if (control.getAttribute('aria-label') || control.getAttribute('aria-labelledby') || (control.id && scope.querySelector(`label[for="${control.id}"]`))) return;
    const label = control.closest('.field') && control.closest('.field').querySelector('label');
    if (label) {
      control.id = control.id || `ctl-${++uid}`;
      if (!label.htmlFor) label.htmlFor = control.id;
    } else if (control.placeholder) control.setAttribute('aria-label', control.placeholder);
    else if (control.closest('label') === null) control.setAttribute('aria-label', control.name || control.id || 'field');
  });
  scope.querySelectorAll('button:not([aria-label])').forEach((b) => { if (!b.textContent.trim() && b.title) b.setAttribute('aria-label', b.title); });
}

function markActiveNav() {
  const view = (window.location.hash || '').replace(/^#\/?/, '').split('/');
  document.querySelectorAll('#app-sidebar .nav-item').forEach((b) => {
    const on = b.dataset.view === view[0] && (!b.dataset.subtab || b.dataset.subtab === view[1]);
    if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    b.classList.toggle('active', on);
  });
}

export function initA11y() {
  const css = document.createElement('link');
  css.rel = 'stylesheet';
  css.href = new URL('../css/responsive.css', import.meta.url).href;
  document.head.appendChild(css);
  document.documentElement.lang = document.documentElement.lang || 'en';
  const main = document.getElementById('app-view');
  if (main) { main.setAttribute('role', 'main'); main.setAttribute('tabindex', '-1'); }
  document.getElementById('app-sidebar')?.setAttribute('aria-label', 'Main menu');
  const burger = document.getElementById('topbarBurger');
  if (burger) burger.setAttribute('aria-label', 'Open menu');

  new MutationObserver((mutations) => {
    for (const m of mutations) {
      m.addedNodes.forEach((node) => {
        if (node.nodeType !== 1) return;
        if (node.matches('.toast, #toast, [class*="toast"]')) { node.setAttribute('role', 'status'); node.setAttribute('aria-live', 'polite'); }
        const modal = node.matches?.('.modal') ? node : node.querySelector?.('.modal');
        if (modal) enhanceDialog(modal);
        labelOrphans(node);
      });
      m.removedNodes.forEach((node) => { if (node.nodeType === 1 && (node.matches?.('.modal-backdrop,.modal-overlay') || node.querySelector?.('.modal')) && lastFocus && document.contains(lastFocus)) { lastFocus.focus(); lastFocus = null; } });
    }
    markActiveNav();
  }).observe(document.body, { childList: true, subtree: true });

  document.addEventListener('keydown', (e) => {
    const modal = document.querySelector('.modal[role="dialog"]');
    if (!modal) return;
    if (e.key === 'Escape') { const close = modal.querySelector('[id$="cancel"],[id$="close"]'); if (close) { e.preventDefault(); close.click(); } return; }
    if (e.key !== 'Tab') return;
    const items = Array.from(modal.querySelectorAll(FOCUSABLE)).filter((n) => n.offsetParent !== null);
    if (!items.length) return;
    const [first, last] = [items[0], items[items.length - 1]];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
  window.addEventListener('hashchange', () => { markActiveNav(); main?.focus({ preventScroll: true }); });
  labelOrphans(document);
  markActiveNav();
}
