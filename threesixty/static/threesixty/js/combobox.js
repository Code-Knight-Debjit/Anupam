// A searchable picker that sits on top of an ordinary <select>. The select stays in the page (hidden) and stays the source of
// truth — `select.value`, its "change" event, `disabled` and re-filling its <option>s all keep working — so a screen only has to
// say `makeCombobox(select, {...})` (or tag the select with data-combo and let the observer below do it).
//
//   • type in the box and the matching entries are listed right below it;
//   • matching is on the TEXT: what you type must appear as-is, in that order ("Lin" finds "Linde", "Franklin", "Alinea" —
//     never a name that merely has an l, an i and an n somewhere);
//   • entries that start with the text come first, then ones with a word that starts with it, then the rest;
//   • optional "+ Create new …" entry (`onCreate`) for when the person isn't in the list.
import { escapeHtml } from './ui.js';

const WORD_SPLIT = /[\s,.\-()/&]+/;

/** Contiguous, case-insensitive match, best matches first. `items` are {value, label}. */
export function rankMatches(items, query) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return items.slice();
  const starts = [], words = [], inside = [];
  items.forEach((it) => {
    const text = String(it.label).toLowerCase();
    if (text.startsWith(q)) starts.push(it);
    else if (text.split(WORD_SPLIT).some((w) => w.startsWith(q))) words.push(it);
    else if (text.includes(q)) inside.push(it);
  });
  return starts.concat(words, inside);
}

function highlight(label, query) {
  const q = (query || '').trim();
  if (!q) return escapeHtml(label);
  const i = String(label).toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return escapeHtml(label);
  return `${escapeHtml(label.slice(0, i))}<mark>${escapeHtml(label.slice(i, i + q.length))}</mark>${escapeHtml(label.slice(i + q.length))}`;
}

const nativeValue = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
const nativeDisabled = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'disabled');
let uid = 0;

/**
 * @param select  the <select> to upgrade (its first <option value=""> is the "nothing chosen" entry)
 * @param opts    { placeholder, noun = 'customer', onCreate?: async (typedText) => ({ value, label } | null) }
 */
export function makeCombobox(select, opts = {}) {
  if (!select || select._combo) return select && select._combo;
  const noun = opts.noun || 'customer';
  const wrap = document.createElement('div');
  wrap.className = 'cbx';
  const input = document.createElement('input');
  input.type = 'text'; input.className = 'cbx-input'; input.autocomplete = 'off'; input.spellcheck = false;
  input.setAttribute('role', 'combobox'); input.setAttribute('aria-expanded', 'false'); input.setAttribute('aria-autocomplete', 'list');
  input.placeholder = opts.placeholder || `Search ${noun}…`;
  const caret = document.createElement('span'); caret.className = 'cbx-caret'; caret.innerHTML = '&#9662;'; caret.setAttribute('aria-hidden', 'true');
  const list = document.createElement('div');
  list.className = 'cbx-list'; list.id = 'cbx-list-' + (++uid); list.setAttribute('role', 'listbox'); list.hidden = true;
  input.setAttribute('aria-controls', list.id);
  wrap.append(input, caret, list);
  select.parentNode.insertBefore(wrap, select);
  select.style.display = 'none';
  select.setAttribute('aria-hidden', 'true'); select.tabIndex = -1;
  if (select.id) { const lab = document.querySelector(`label[for="${select.id}"]`); if (lab) lab.htmlFor = ''; }

  let shown = [], active = -1, open = false, typed = false;
  const options = () => [...select.options].filter((o) => o.value !== '').map((o) => ({ value: o.value, label: o.textContent.trim() }));
  const chosenLabel = () => { const o = select.selectedOptions[0]; return o && o.value !== '' ? o.textContent.trim() : ''; };
  const syncText = () => { if (!typed) input.value = chosenLabel(); wrap.classList.toggle('has-value', !!chosenLabel()); };

  function render() {
    const q = typed ? input.value : '';
    shown = rankMatches(options(), q);
    const create = opts.onCreate ? `<button type="button" class="cbx-item cbx-create" data-create="1" role="option">＋ Create new ${escapeHtml(noun)}${q.trim() ? ` “${escapeHtml(q.trim())}”` : ''}</button>` : '';
    const rows = shown.map((it, i) => `<button type="button" class="cbx-item${String(it.value) === select.value ? ' sel' : ''}${i === active ? ' act' : ''}" role="option" data-i="${i}">${highlight(it.label, q)}</button>`).join('');
    list.innerHTML = (rows || `<div class="cbx-empty">No ${escapeHtml(noun)} matches “${escapeHtml(q.trim())}”.</div>`) + create;
    const a = list.querySelector('.act'); if (a) a.scrollIntoView({ block: 'nearest' });
  }
  function openList() {
    if (select.disabled || open) return;
    open = true; wrap.classList.add('open'); input.setAttribute('aria-expanded', 'true'); list.hidden = false;
    const r = input.getBoundingClientRect();
    wrap.classList.toggle('up', window.innerHeight - r.bottom < 300 && r.top > window.innerHeight - r.bottom);   // not enough room below: open upwards
    render();
  }
  function closeList(revert = true) {
    if (!open) return;
    open = false; wrap.classList.remove('open'); input.setAttribute('aria-expanded', 'false'); list.hidden = true; active = -1;
    if (revert) { typed = false; syncText(); }
  }
  function choose(value) {
    nativeValue.set.call(select, value);
    typed = false; closeList(false); syncText();
    select.dispatchEvent(new Event('change', { bubbles: true }));
  }
  async function create() {
    const text = input.value.trim();
    closeList(false);
    let made = null;
    try { made = await opts.onCreate(typed ? text : ''); } catch (e) { console.error(e); }
    typed = false;
    if (made && made.value !== undefined) {
      if (![...select.options].some((o) => o.value === String(made.value))) select.add(new Option(made.label, String(made.value)));
      choose(String(made.value));
    } else syncText();
  }

  input.addEventListener('focus', () => { input.select(); openList(); });
  input.addEventListener('click', () => { if (!open) openList(); });
  input.addEventListener('input', () => { typed = true; active = 0; if (!open) openList(); else render(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault(); if (!open) { openList(); return; }
      active = Math.max(0, Math.min(shown.length - 1, active + (e.key === 'ArrowDown' ? 1 : -1))); render();
    } else if (e.key === 'Enter') {
      if (!open) return;
      e.preventDefault();
      if (active >= 0 && shown[active]) choose(shown[active].value);
      else if (!shown.length && opts.onCreate) create();
      else if (shown.length === 1) choose(shown[0].value);
    } else if (e.key === 'Escape') { if (open) { e.stopPropagation(); closeList(); } }
    else if (e.key === 'Tab') closeList();
  });
  list.addEventListener('mousedown', (e) => e.preventDefault());            // keep the focus in the box while clicking an entry
  list.addEventListener('click', (e) => {
    const b = e.target.closest('.cbx-item'); if (!b) return;
    if (b.dataset.create) create(); else choose(shown[Number(b.dataset.i)].value);
  });
  input.addEventListener('blur', () => setTimeout(() => closeList(), 120));
  document.addEventListener('mousedown', (e) => { if (open && !wrap.contains(e.target)) closeList(); });

  // The select is still the source of truth: code that sets `select.value`, `select.disabled` or rewrites its <option>s is mirrored.
  Object.defineProperty(select, 'value', { configurable: true, get() { return nativeValue.get.call(this); }, set(v) { nativeValue.set.call(this, v); typed = false; syncText(); } });
  Object.defineProperty(select, 'disabled', { configurable: true, get() { return nativeDisabled.get.call(this); }, set(v) { nativeDisabled.set.call(this, v); input.disabled = !!v; wrap.classList.toggle('disabled', !!v); } });
  new MutationObserver(() => { if (!select.isConnected) { wrap.remove(); return; } syncText(); if (open) render(); }).observe(select, { childList: true, subtree: true, characterData: true });
  select.addEventListener('change', () => { typed = false; syncText(); });
  input.disabled = select.disabled; wrap.classList.toggle('disabled', select.disabled);
  syncText();
  const api = { refresh: () => { typed = false; syncText(); if (open) render(); }, focus: () => input.focus(), input, wrap };
  select._combo = api;
  return api;
}

// Tag a <select> with data-combo="customer" (and data-combo-create for the "+ Create new" entry) and it is upgraded wherever it appears.
// The default "+ Create new customer": the shared dialog (customer_quick.js), then the new customer is selected.
let createHook = async (select, text) => {
  const { createCustomerDialog } = await import('./customer_quick.js');
  const c = await createCustomerDialog(text);
  return c ? { value: String(c.id), label: c.label || c.select_label || [c.name, c.plant, c.area].filter(Boolean).join(', ') } : null;
};
export const setComboCreateHook = (fn) => { createHook = fn; };
/** A customer picker: search box + list, and (unless create:false) the "+ Create new customer" entry. `onCreate(text)` may replace the default dialog. */
export function makeCustomerCombobox(select, { create = true, onCreate, placeholder } = {}) {
  return makeCombobox(select, { noun: 'customer', placeholder, onCreate: create ? (onCreate || ((text) => createHook(select, text))) : null });
}
function upgrade(root) {
  (root.matches && root.matches('select[data-combo]') ? [root] : []).concat([...(root.querySelectorAll ? root.querySelectorAll('select[data-combo]') : [])]).forEach((s) => {
    if (s._combo) return;
    const noun = s.dataset.combo || 'customer';
    makeCombobox(s, { noun, placeholder: s.dataset.comboPlaceholder, onCreate: s.hasAttribute('data-combo-create') && createHook ? (text) => createHook(s, text) : null });
  });
}
new MutationObserver((muts) => { muts.forEach((m) => m.addedNodes.forEach((n) => { if (n.nodeType === 1) upgrade(n); })); }).observe(document.documentElement, { childList: true, subtree: true });
upgrade(document);
