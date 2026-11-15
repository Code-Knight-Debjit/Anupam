// Gmail-style paging for every long list: "1–25 of 342  ‹ ›" with a rows-per-page choice, above and below the list.
//
// The screens build their tables / card lists exactly as before (and export / print from their own full data, never from what is on
// screen). This module watches the page: when a table (`table.report`) or one of the listed card containers has more rows than fit,
// it shows one page at a time and adds the pager bars (a list that fits on one page gets none). A screen that re-renders (filter, search, status change, reload) is paged again
// automatically and keeps its page; typing in a search box or changing a filter goes back to page 1.
//
// Opt out with data-nopage on the table / container. Tables inside dialogs are never paged.

const SIZES = [10, 25, 50, 100];
let defaultSize = 25;
try { const v = Number(localStorage.getItem('threesixty.pageSize')); if (SIZES.includes(v)) defaultSize = v; } catch (e) { /* storage may be blocked */ }

// What to page: a container selector and how to find its items. `groups` (tasks): section headings are hidden when all of their cards are.
const TARGETS = [
  { sel: 'table.report', items: (c) => [...c.querySelectorAll(':scope > tbody > tr, :scope > tr')].filter((r) => r.querySelector(':scope > td') && !r.hasAttribute('data-nopage')) },
  { sel: '.card-list', items: (c) => [...c.children] },
  { sel: '.ol-grid', items: (c) => [...c.children] },
  { sel: '#usersList', items: (c) => [...c.children] },
  { sel: '#branchesList', items: (c) => [...c.children] },
  // Tasks: one card list, or side-by-side columns by kind — each page then shows an even slice of every column.
  { sel: '#taskListWrap', items: (c) => [...c.querySelectorAll('.tcard')], groups: '.tsec',
    columns: (c) => { const cols = [...c.querySelectorAll(':scope > .tcol')]; return cols.length > 1 ? cols.map((col) => [...col.querySelectorAll('.tcard')]) : null; } },
  { sel: '[data-paginate]', items: (c) => [...c.children] },
];

const pages = new Map();                       // key -> { page, size }
const bars = new WeakMap();                    // container -> [bar elements]

function keyOf(container, index) {
  const view = container.closest('.view');
  return `${view ? view.id : 'page'}|${container.id || container.tagName + index}`;
}
const excluded = (c) => !!c.closest('.modal, .overlay, [data-nopage]');

function barHtml(st, info) {
  return `<label>Rows per page <select class="pager-size" aria-label="Rows per page">${SIZES.map((n) => `<option value="${n}"${n === st.size ? ' selected' : ''}>${n}</option>`).join('')}</select></label>
    <span class="pager-range" aria-live="polite">${info.start}–${info.end} of ${info.total}</span>
    <button type="button" class="pager-btn" data-go="prev" aria-label="Newer / previous page" title="Previous page"${st.page <= 1 ? ' disabled' : ''}>&#8249;</button>
    <button type="button" class="pager-btn" data-go="next" aria-label="Older / next page" title="Next page"${st.page >= info.last ? ' disabled' : ''}>&#8250;</button>`;
}

function makeBar(container, where) {
  const bar = document.createElement('div');
  bar.className = 'pager-bar ' + where;
  bar.addEventListener('click', (e) => {
    const b = e.target.closest('[data-go]'); if (!b || b.disabled) return;
    const st = pages.get(bar._key); if (!st) return;
    st.page += b.dataset.go === 'next' ? 1 : -1;
    schedule();
    const r = container.getBoundingClientRect();
    if (r.top < 0) container.scrollIntoView({ block: 'start' });
  });
  bar.addEventListener('change', (e) => {
    if (!e.target.classList.contains('pager-size')) return;
    const st = pages.get(bar._key); if (!st) return;
    const first = (st.page - 1) * st.size;                    // keep the first row that is on screen
    st.size = Number(e.target.value); st.page = Math.floor(first / st.size) + 1;
    defaultSize = st.size;
    try { localStorage.setItem('threesixty.pageSize', String(st.size)); } catch (err) { /* ignore */ }
    pages.forEach((s) => { if (s !== st) s.size = st.size; });
    schedule();
  });
  return bar;
}

function anchorOf(container) { return container.closest('.table-scroll') || container; }

function ensureBars(container) {
  let pair = bars.get(container);
  const anchor = anchorOf(container);
  if (!pair || !pair[0].isConnected || !pair[1].isConnected || pair[0].nextElementSibling !== anchor) {
    if (pair) pair.forEach((b) => b.remove());
    pair = [makeBar(container, 'top'), makeBar(container, 'bottom')];
    anchor.insertAdjacentElement('beforebegin', pair[0]);
    anchor.insertAdjacentElement('afterend', pair[1]);
    bars.set(container, pair);
  }
  return pair;
}
function dropBars(container) {
  const pair = bars.get(container);
  if (pair) { pair.forEach((b) => b.remove()); bars.delete(container); }
}

function apply(container, target, index) {
  const items = target.items(container);
  const total = items.length;
  if (total <= defaultSize) {                      // everything fits on one page: no pager (it appears as soon as there is a second page)
    items.forEach((r) => r.classList.remove('pg-hide'));
    if (target.groups) container.querySelectorAll(target.groups).forEach((g) => g.classList.remove('pg-hide'));
    dropBars(container); return;
  }
  const key = keyOf(container, index);
  let st = pages.get(key);
  if (!st) { st = { page: 1, size: defaultSize }; pages.set(key, st); }
  // Side-by-side columns page together: every column shows its next slice, so no column runs dry while another has more.
  const cols = (target.columns && target.columns(container)) || [items];
  const perCol = cols.length > 1 ? Math.max(1, Math.floor(st.size / cols.length)) : st.size;
  const last = Math.max(1, Math.max(...cols.map((c) => Math.ceil(c.length / perCol))));
  st.page = Math.min(Math.max(1, st.page), last);
  const from = (st.page - 1) * perCol, to = from + perCol;
  let before = 0, now = 0;
  cols.forEach((col) => {
    col.forEach((r, i) => r.classList.toggle('pg-hide', i < from || i >= to));
    before += Math.min(col.length, from); now += Math.max(0, Math.min(col.length, to) - from);
  });
  if (target.groups) {                                       // a heading with no card left on this page is hidden too
    container.querySelectorAll(target.groups).forEach((g) => {
      let n = g.nextElementSibling, any = false;
      while (n && !n.matches(target.groups)) { if (!n.classList.contains('pg-hide') && (n.matches('.tcard') || n.querySelector('.tcard:not(.pg-hide)'))) any = true; n = n.nextElementSibling; }
      g.classList.toggle('pg-hide', !any);
    });
  }
  const info = { start: before + 1, end: before + now, total, last };
  const pair = ensureBars(container);
  pair.forEach((b) => {
    b._key = key;
    const html = barHtml(st, info);
    if (b._html !== html) { b.innerHTML = html; b._html = html; }
  });
}

let queued = false;
function run() {
  queued = false;
  const seen = new Set();
  TARGETS.forEach((t) => {
    document.querySelectorAll(t.sel).forEach((c, i) => {
      if (seen.has(c) || excluded(c)) return;
      seen.add(c); apply(c, t, i);
    });
  });
}
function schedule() { if (!queued) { queued = true; requestAnimationFrame(run); } }
export const refreshPager = schedule;

// Only real content changes matter — not our own bars being added or updated.
const isBar = (n) => n.nodeType === 1 && n.classList.contains('pager-bar');
new MutationObserver((records) => {
  for (const r of records) {
    if (r.target.nodeType === 1 && r.target.closest && r.target.closest('.pager-bar')) continue;
    const real = [...r.addedNodes, ...r.removedNodes].some((n) => !isBar(n));
    if (real) { schedule(); return; }
  }
}).observe(document.documentElement, { childList: true, subtree: true });

// Searching or changing a filter starts again from page 1 (a status change inside the table itself does not).
function resetPages(e) {
  const t = e.target;
  if (!t || !t.closest || t.closest('.pager-bar, table, .card-list, .tcard, .modal, .overlay')) return;
  if (!t.matches('input, select, textarea')) return;
  pages.forEach((s) => { s.page = 1; });
  schedule();
}
document.addEventListener('input', resetPages);
document.addEventListener('change', resetPages);
schedule();
window.addEventListener('hashchange', () => { pages.clear(); schedule(); });
