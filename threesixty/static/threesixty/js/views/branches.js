// Branches — Admin-only Branch CRUD + per-branch document numbering
// (prefix/start-at per doc type, `branch_numbering_detail`).
import { api } from '../api.js';
import { el, escapeHtml, toast, apiErrorMessage, openModal, closeModal, confirmDialog, renderTable } from '../ui.js';

const DOC_TYPES = [['enquiry', 'Enquiry'], ['quotation', 'Quotation'], ['po', 'Purchase Order'], ['dc', 'Delivery Challan'], ['proforma', 'Proforma Invoice']];

function branchForm(branch) {
  const b = branch || {};
  return `
    <div class="field"><label>Name *</label><input id="bf-name" value="${escapeHtml(b.name || '')}"></div>
    <div class="field"><label>Letterhead name</label><input id="bf-lh-name" value="${escapeHtml(b.letterhead_name || '')}"></div>
    <div class="field"><label>Letterhead address</label><textarea id="bf-lh-address" rows="2">${escapeHtml(b.letterhead_address || '')}</textarea></div>
    <div class="field-row">
      <div class="field"><label>GSTIN</label><input id="bf-lh-gstin" value="${escapeHtml(b.letterhead_gstin || '')}"></div>
      <div class="field"><label>Phone</label><input id="bf-lh-phone" value="${escapeHtml(b.letterhead_phone || '')}"></div>
      <div class="field"><label>Email</label><input id="bf-lh-email" value="${escapeHtml(b.letterhead_email || '')}"></div>
    </div>
    <div class="field"><label><input type="checkbox" id="bf-active" style="width:auto;display:inline;" ${b.is_active !== false ? 'checked' : ''}> Active</label></div>
    <div class="modal-actions"><button class="btn" id="bf-cancel">Cancel</button><button class="btn primary" id="bf-save">${branch ? 'Save changes' : 'Create branch'}</button></div>`;
}

function openBranchForm(branch, onSaved) {
  openModal(`<h2>${branch ? 'Edit branch' : 'New branch'}</h2>${branchForm(branch)}`, {
    onMount: (modal) => {
      modal.querySelector('#bf-cancel').onclick = closeModal;
      modal.querySelector('#bf-save').onclick = async () => {
        const name = modal.querySelector('#bf-name').value.trim();
        if (!name) { toast('Name is required.', 'error'); return; }
        const data = {
          name, letterhead_name: modal.querySelector('#bf-lh-name').value.trim(),
          letterhead_address: modal.querySelector('#bf-lh-address').value.trim(),
          letterhead_gstin: modal.querySelector('#bf-lh-gstin').value.trim(),
          letterhead_phone: modal.querySelector('#bf-lh-phone').value.trim(),
          letterhead_email: modal.querySelector('#bf-lh-email').value.trim(),
          is_active: modal.querySelector('#bf-active').checked,
        };
        try {
          if (branch) await api.patch(`branches/${branch.id}/`, data);
          else await api.post('branches/', data);
          toast('Saved.', 'success');
          closeModal();
          onSaved();
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

async function openNumberingModal(branch) {
  const configs = await Promise.all(DOC_TYPES.map(([dt]) => api.get(`branches/${branch.id}/numbering/${dt}/`)));
  openModal(`
    <h2>Document numbering — ${escapeHtml(branch.name)}</h2>
    <div class="table-scroll"><table class="report">
      <tr><th>Document</th><th>Prefix</th><th>Suffix</th><th>Start at</th><th>Last issued</th></tr>
      ${DOC_TYPES.map(([dt, label], i) => `<tr data-dt="${dt}">
        <td>${escapeHtml(label)}</td>
        <td><input class="num-prefix" value="${escapeHtml(configs[i].prefix || '')}" style="width:80px;"></td>
        <td><input class="num-suffix" value="${escapeHtml(configs[i].suffix || '')}" style="width:80px;"></td>
        <td><input class="num-start" type="number" value="${configs[i].start_at}" style="width:80px;"></td>
        <td class="sub">${configs[i].last_issued || '—'}</td>
      </tr>`).join('')}
    </table></div>
    <div class="modal-actions"><button class="btn" id="num-close">Close</button><button class="btn primary" id="num-save">Save all</button></div>`, {
    onMount: (modal) => {
      modal.querySelector('#num-close').onclick = closeModal;
      modal.querySelector('#num-save').onclick = async () => {
        try {
          await Promise.all(Array.from(modal.querySelectorAll('tr[data-dt]')).map((tr) => api.patch(`branches/${branch.id}/numbering/${tr.dataset.dt}/`, {
            prefix: tr.querySelector('.num-prefix').value.trim(),
            suffix: tr.querySelector('.num-suffix').value.trim(),
            start_at: Number(tr.querySelector('.num-start').value) || 1,
          })));
          toast('Numbering saved.', 'success');
          closeModal();
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

async function deleteBranch(branch, onDone) {
  if (!await confirmDialog(`Remove branch "${branch.name}"? This cannot be undone.`)) return;
  try { await api.delete(`branches/${branch.id}/`); toast('Removed.', 'success'); onDone(); } catch (e) { toast(apiErrorMessage(e), 'error'); }
}

async function render(root) {
  const branches = await api.all('branches/');
  root.innerHTML = `
    <div class="flex-between"><h2 style="margin:0;">Branches</h2><button class="btn primary" id="newBranchBtn">+ New branch</button></div>
    ${renderTable(['Name', 'GSTIN', 'Phone', 'Active', ''], branches.map((b) => ({
      Name: escapeHtml(b.name), GSTIN: escapeHtml(b.letterhead_gstin), Phone: escapeHtml(b.letterhead_phone),
      Active: b.is_active ? 'Yes' : 'No',
      '': `<button class="btn sm" data-numbering="${b.id}">Numbering</button> <button class="btn sm" data-edit="${b.id}">Edit</button> <button class="btn sm danger" data-del="${b.id}">Remove</button>`,
    })), { empty: 'No branches yet.' })}`;
  root.querySelector('#newBranchBtn').onclick = () => openBranchForm(null, () => render(root));
  root.querySelectorAll('[data-numbering]').forEach((btn) => btn.onclick = () => openNumberingModal(branches.find((b) => String(b.id) === btn.dataset.numbering)));
  root.querySelectorAll('[data-edit]').forEach((btn) => btn.onclick = () => openBranchForm(branches.find((b) => String(b.id) === btn.dataset.edit), () => render(root)));
  root.querySelectorAll('[data-del]').forEach((btn) => btn.onclick = () => deleteBranch(branches.find((b) => String(b.id) === btn.dataset.del), () => render(root)));
}

export async function mountBranches(root) {
  await render(root);
}
