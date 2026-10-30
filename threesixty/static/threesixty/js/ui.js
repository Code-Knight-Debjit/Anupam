// Shared formatting/DOM helpers — ported verbatim from the original's
// top-level utility functions (`contact_management.html`: `el` L4042,
// `escapeHtml` L4044, `fmtMoney` L9881-9884, `daysSinceDate` L5791-5794,
// `initials` L4046, company-name dup-detection L4054-4091).
export const el = (id) => document.getElementById(id);

export const escapeHtml = (str) =>
  str === undefined || str === null
    ? ''
    : String(str).replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));

export function fmtMoney(n) {
  const num = Number(n) || 0;
  return num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('en-IN');
}

export function fmtDateTime(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString('en-IN');
}

export function daysSinceDate(dateStr) {
  if (!dateStr) return Infinity;
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
}

export const initials = (name) =>
  (name || '').trim().split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase() || '--';

const COMPANY_NAME_STOPWORDS = new Set([
  'co', 'company', 'ltd', 'limited', 'pvt', 'private', 'inc', 'incorporated', 'corp', 'corporation', 'llp', 'the',
]);
export function normalizeCompanyNameBasic(name) {
  return (name || '').toLowerCase().replace(/&/g, ' and ').replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/).filter(Boolean).join(' ').trim();
}
export function normalizeCompanyNameLoose(name) {
  return normalizeCompanyNameBasic(name).split(' ')
    .filter((w) => w && !COMPANY_NAME_STOPWORDS.has(w) && w !== 'and').join(' ').trim();
}
function levenshteinDistance(a, b) {
  const m = a.length, n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    const cur = [i];
    for (let j = 1; j <= n; j++) cur[j] = a[i - 1] === b[j - 1] ? prev[j - 1] : 1 + Math.min(prev[j - 1], prev[j], cur[j - 1]);
    prev = cur;
  }
  return prev[n];
}
export function companyNameSimilarity(a, b) {
  if (!a || !b) return 0;
  const dist = levenshteinDistance(a, b);
  const maxLen = Math.max(a.length, b.length) || 1;
  return 1 - dist / maxLen;
}
/** Finds existing customers whose name is the same as, or looks close to,
 * `name` — `exact` blocks the save, `near` only warns. */
export function findDuplicateCustomers(name, customers, excludeId) {
  const basic = normalizeCompanyNameBasic(name);
  const loose = normalizeCompanyNameLoose(name);
  let exact = null;
  const near = [];
  for (const c of customers) {
    if (excludeId && c.id === excludeId) continue;
    const cb = normalizeCompanyNameBasic(c.name);
    if (cb === basic && basic) { exact = c; continue; }
    const cl = normalizeCompanyNameLoose(c.name);
    if (loose && cl && companyNameSimilarity(loose, cl) >= 0.82) near.push(c);
  }
  return { exact, near };
}

export function toast(message, type = 'info') {
  let stack = document.querySelector('.toast-stack');
  if (!stack) {
    stack = document.createElement('div');
    stack.className = 'toast-stack';
    document.body.appendChild(stack);
  }
  const node = document.createElement('div');
  node.className = `toast ${type}`;
  node.textContent = message;
  stack.appendChild(node);
  setTimeout(() => node.remove(), 4200);
}

export function apiErrorMessage(err) {
  if (err && err.body) {
    if (err.body.detail) return err.body.detail;
    if (err.body.error) return err.body.error;
  }
  return err && err.message ? err.message : 'Something went wrong.';
}

let modalRoot = null;
export function openModal(innerHtml, { onMount } = {}) {
  closeModal();
  modalRoot = document.createElement('div');
  modalRoot.className = 'modal-backdrop open';
  modalRoot.innerHTML = `<div class="modal">${innerHtml}</div>`;
  modalRoot.addEventListener('mousedown', (e) => { if (e.target === modalRoot) closeModal(); });
  document.body.appendChild(modalRoot);
  if (onMount) onMount(modalRoot.querySelector('.modal'));
  return modalRoot;
}
export function closeModal() {
  if (modalRoot) { modalRoot.remove(); modalRoot = null; }
}

export function confirmDialog(message) {
  return new Promise((resolve) => {
    openModal(`
      <p style="margin-bottom:18px;">${escapeHtml(message)}</p>
      <div class="modal-actions">
        <button class="btn" id="cfNo">Cancel</button>
        <button class="btn danger" id="cfYes">Confirm</button>
      </div>`, {
      onMount: (modal) => {
        modal.querySelector('#cfNo').onclick = () => { closeModal(); resolve(false); };
        modal.querySelector('#cfYes').onclick = () => { closeModal(); resolve(true); };
      },
    });
  });
}

export function qs(obj) {
  const parts = [];
  Object.entries(obj || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`); });
  return parts.join('&');
}

export function renderTable(cols, rows, { empty = 'Nothing to show.', rowAttrs } = {}) {
  const head = `<tr>${cols.map((c) => `<th>${escapeHtml(c)}</th>`).join('')}</tr>`;
  const body = rows.length
    ? rows.map((r) => `<tr ${rowAttrs ? rowAttrs(r) : ''}>${cols.map((c) => `<td>${r[c] === undefined || r[c] === null || r[c] === '' ? '—' : r[c]}</td>`).join('')}</tr>`).join('')
    : `<tr><td colspan="${cols.length}" class="empty-state">${escapeHtml(empty)}</td></tr>`;
  return `<div class="table-scroll"><table class="report">${head}${body}</table></div>`;
}

export function statusColor(status) {
  const map = {
    Pending: '#c98a0b', Win: '#2f9e52', Won: '#2f9e52', Lose: '#ba1a1a', Lost: '#ba1a1a',
    Completed: '#2f9e52', Regretted: '#ba1a1a', Hold: '#7b4fab', Done: '#2f9e52', Open: '#3a7bd5',
    Approved: '#2f9e52', Rejected: '#ba1a1a', Active: '#2f9e52', Inactive: '#8a8a92',
  };
  return map[status] || '#5f5e5e';
}
export function badge(status) {
  return `<span class="badge" style="background:${statusColor(status)}">${escapeHtml(status || '—')}</span>`;
}

const loadedScripts = {};
// Lazily injects a classic <script> tag (for vendored UMD libs that attach a
// global, e.g. Leaflet/XLSX) and caches the promise so it only loads once.
export function loadScript(src) {
  if (loadedScripts[src]) return loadedScripts[src];
  loadedScripts[src] = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error(`Could not load ${src}`));
    document.head.appendChild(s);
  });
  return loadedScripts[src];
}

// ---- Customer pick-lists (REQ-CUS-07/08) ---------------------------------
// Every customer drop-down shows "Customer name, Plant, Area" (the server's
// `label`, never the city) and searches by word: typing "su" lists labels that
// start with "su" first, then labels where a LATER word starts with "su", then
// anything containing it. Same order as the server's `rank_by_query`.
export function rankByQuery(items, query, labelOf) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return items.slice();
  const starts = [], words = [], contains = [];
  items.forEach((item) => {
    const text = labelOf(item).toLowerCase();
    if (text.startsWith(q)) starts.push(item);
    else if (text.split(/[\s,.\-()/&]+/).some((w) => w.startsWith(q))) words.push(item);
    else if (text.includes(q)) contains.push(item);
  });
  return starts.concat(words, contains);
}

export const customerLabel = (c) => c.label || c.name;

/** Adds a search box above an existing <select> of customers and keeps the
 * select's value/ids untouched, so callers keep reading `select.value`. */
export function enhanceCustomerSelect(select, customers, { blank = '— select —' } = {}) {
  const render = (query) => {
    const keep = select.value;
    let shown = rankByQuery(customers, query, customerLabel);
    const kept = customers.find((c) => String(c.id) === String(keep));
    if (kept && !shown.includes(kept)) shown = [kept].concat(shown);
    select.innerHTML = `<option value="">${blank}</option>` +
      shown.map((c) => `<option value="${c.id}">${escapeHtml(customerLabel(c))}</option>`).join('');
    select.value = keep;
  };
  const box = document.createElement('input');
  box.type = 'search';
  box.placeholder = 'Type to search customers…';
  box.setAttribute('aria-label', 'Search customers');
  box.style.marginBottom = '4px';
  box.addEventListener('input', () => render(box.value));
  select.parentNode.insertBefore(box, select);
  render('');
  return { refresh: render, search: box };
}
