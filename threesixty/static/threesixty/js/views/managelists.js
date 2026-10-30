// Manage lists — Admin-only CRUD over the generic `LookupItem` table
// (job titles, sources, industries, languages, brands, products,
// categories, units, tax rates, payment terms, transport/courier).
import { api } from '../api.js';
import { el, escapeHtml, toast, apiErrorMessage, openModal, closeModal, confirmDialog, renderTable } from '../ui.js';

const KINDS = [
  ['job_title', 'Job Title'], ['source', 'Source'], ['industry', 'Industry'], ['language', 'Language'],
  ['brand', 'Brand'], ['product', 'Product'], ['category', 'Category'], ['unit', 'Unit'],
  ['tax_rate', 'Tax Rate'], ['payment_term', 'Payment Term'], ['transport', 'Transport'], ['courier', 'Courier'],
  ['sales_person', 'Sales Person'],
];

function openItemModal(kind, item, onSaved) {
  const it = item || {};
  openModal(`
    <h2>${item ? 'Edit' : 'New'} ${escapeHtml((KINDS.find((k) => k[0] === kind) || [])[1] || kind)}</h2>
    <div class="field"><label>Name *</label><input id="li-name" value="${escapeHtml(it.name || '')}"></div>
    <div class="field"><label>Extra</label><input id="li-extra" value="${escapeHtml(it.extra || '')}" placeholder="e.g. tax % or notes"></div>
    <div class="field"><label><input type="checkbox" id="li-active" style="width:auto;display:inline;" ${it.is_active !== false ? 'checked' : ''}> Active</label></div>
    <div class="modal-actions"><button class="btn" id="li-cancel">Cancel</button><button class="btn primary" id="li-save">Save</button></div>`, {
    onMount: (modal) => {
      modal.querySelector('#li-cancel').onclick = closeModal;
      modal.querySelector('#li-save').onclick = async () => {
        const name = modal.querySelector('#li-name').value.trim();
        if (!name) { toast('Name is required.', 'error'); return; }
        const data = { name, extra: modal.querySelector('#li-extra').value.trim(), is_active: modal.querySelector('#li-active').checked };
        try {
          if (item) await api.patch(`lookups/${item.id}/`, data);
          else await api.post('lookups/', { ...data, kind });
          toast('Saved.', 'success');
          closeModal();
          onSaved();
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

// Sales persons are their own table (name + phone), not a LookupItem kind.
async function renderSalesPersons(root) {
  const items = await api.all('sales-persons/');
  root.innerHTML = `
    <div class="flex-between"><h3 style="margin:0;">Sales Person</h3><button class="btn primary sm" id="newItemBtn">+ Add</button></div>
    ${renderTable(['Name', 'Phone', ''], items.map((it) => ({
      Name: escapeHtml(it.name), Phone: escapeHtml(it.phone),
      '': `<button class="btn sm" data-edit="${it.id}">Edit</button> <button class="btn sm danger" data-del="${it.id}">Remove</button>`,
    })), { empty: 'Nothing here yet.' })}`;
  const edit = (item) => openModal(`
    <h2>${item ? 'Edit' : 'New'} sales person</h2>
    <div class="field"><label>Name *</label><input id="sp-name" value="${escapeHtml((item || {}).name || '')}"></div>
    <div class="field"><label>Phone</label><input id="sp-phone" value="${escapeHtml((item || {}).phone || '')}"></div>
    <div class="modal-actions"><button class="btn" id="sp-cancel">Cancel</button><button class="btn primary" id="sp-save">Save</button></div>`, {
    onMount: (modal) => {
      modal.querySelector('#sp-cancel').onclick = closeModal;
      modal.querySelector('#sp-save').onclick = async () => {
        const data = { name: modal.querySelector('#sp-name').value.trim(), phone: modal.querySelector('#sp-phone').value.trim() };
        if (!data.name) { toast('Name is required.', 'error'); return; }
        try {
          if (item) await api.patch(`sales-persons/${item.id}/`, data); else await api.post('sales-persons/', data);
          closeModal(); renderSalesPersons(root);
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
  root.querySelector('#newItemBtn').onclick = () => edit(null);
  root.querySelectorAll('[data-edit]').forEach((btn) => btn.onclick = () => edit(items.find((it) => String(it.id) === btn.dataset.edit)));
  root.querySelectorAll('[data-del]').forEach((btn) => btn.onclick = async () => {
    if (!await confirmDialog('Remove this sales person? Existing documents keep their name.')) return;
    try { await api.delete(`sales-persons/${btn.dataset.del}/`); renderSalesPersons(root); } catch (e) { toast(apiErrorMessage(e), 'error'); }
  });
}

async function renderKind(root, kind) {
  if (kind === 'sales_person') return renderSalesPersons(root);
  const items = await api.all('lookups/', { kind });
  items.sort((a, b) => (a.sort_order - b.sort_order) || a.name.localeCompare(b.name));
  root.innerHTML = `
    <div class="flex-between"><h3 style="margin:0;">${escapeHtml((KINDS.find((k) => k[0] === kind) || [])[1] || kind)}</h3><button class="btn primary sm" id="newItemBtn">+ Add</button></div>
    ${renderTable(['Name', 'Extra', 'Active', ''], items.map((it) => ({
      Name: escapeHtml(it.name), Extra: escapeHtml(it.extra), Active: it.is_active ? 'Yes' : 'No',
      '': `<button class="btn sm" data-edit="${it.id}">Edit</button> <button class="btn sm danger" data-del="${it.id}">Remove</button>`,
    })), { empty: 'Nothing here yet.' })}`;
  root.querySelector('#newItemBtn').onclick = () => openItemModal(kind, null, () => renderKind(root, kind));
  root.querySelectorAll('[data-edit]').forEach((btn) => btn.onclick = () => openItemModal(kind, items.find((it) => String(it.id) === btn.dataset.edit), () => renderKind(root, kind)));
  root.querySelectorAll('[data-del]').forEach((btn) => btn.onclick = async () => {
    if (!await confirmDialog('Remove this entry?')) return;
    try {
      const res = await api.delete(`lookups/${btn.dataset.del}/`);
      if (res && res.deactivated) toast('Still used by customers, so it was hidden from the lists instead of deleted.', 'info');
    } catch (e) { toast(apiErrorMessage(e), 'error'); }
    renderKind(root, kind);
  });
}

export async function mountManageLists(root) {
  root.innerHTML = `
    <div class="tabbar">${KINDS.map((k, i) => `<button data-k="${k[0]}" class="${i === 0 ? 'active' : ''}">${escapeHtml(k[1])}</button>`).join('')}</div>
    <div id="mlBody"></div>`;
  const body = root.querySelector('#mlBody');
  root.querySelectorAll('[data-k]').forEach((btn) => btn.addEventListener('click', () => {
    root.querySelectorAll('[data-k]').forEach((b) => b.classList.toggle('active', b === btn));
    renderKind(body, btn.dataset.k);
  }));
  await renderKind(body, KINDS[0][0]);
}
