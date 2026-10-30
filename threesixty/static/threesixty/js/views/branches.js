// Branches — Admin-only Branch CRUD + per-branch document numbering
// (prefix/start-at per doc type, `branch_numbering_detail`).
import { api } from '../api.js';
import { el, escapeHtml, toast, apiErrorMessage, openModal, closeModal, confirmDialog, renderTable } from '../ui.js';

// Pending PO is not listed: it carries the customer's own PO number (REQ-DOC-02).
const DOC_TYPES = [['enquiry', 'Enquiry'], ['quotation', 'Quotation'], ['proforma', 'Proforma Invoice'], ['dc', 'Delivery Challan']];
const IMAGE_KINDS = [['logo', 'Company logo'], ['dealer_logo', 'Dealer logo'], ['footer_image', 'Footer image'], ['payment_qr', 'Payment QR']];

function branchForm(branch) {
  const b = branch || {};
  const v = (k) => escapeHtml(b[k] == null ? '' : b[k]);
  const imageBlock = branch ? `
    <h3>Images</h3>
    <div class="field-row">${IMAGE_KINDS.map(([k, label]) => `
      <div class="field"><label>${label}</label>
        ${b[k + '_url'] ? `<img src="${escapeHtml(b[k + '_url'])}" alt="" style="max-height:48px;max-width:100%;display:block;margin-bottom:4px;">` : '<div class="sub">None</div>'}
        <input type="file" accept="image/png,image/jpeg,image/webp" data-image="${k}">
        ${b[k + '_url'] ? `<button type="button" class="link-btn" data-image-remove="${k}">Remove</button>` : ''}
      </div>`).join('')}</div>` : '<p class="sub">Save the branch first, then add its logo and QR images.</p>';
  return `
    <div class="field"><label>Name *</label><input id="bf-name" value="${v('name')}"></div>
    <h3>Letterhead</h3>
    <div class="field"><label>Company name</label><input id="bf-letterhead_name" value="${v('letterhead_name')}"></div>
    <div class="field"><label>Address</label><textarea id="bf-letterhead_address" rows="2">${v('letterhead_address')}</textarea></div>
    <div class="field-row">
      <div class="field"><label>Phone</label><input id="bf-letterhead_phone" value="${v('letterhead_phone')}"></div>
      <div class="field"><label>Mobile</label><input id="bf-letterhead_mobile" value="${v('letterhead_mobile')}"></div>
      <div class="field"><label>Email</label><input id="bf-letterhead_email" value="${v('letterhead_email')}"></div>
    </div>
    <div class="field-row">
      <div class="field"><label>Website</label><input id="bf-letterhead_website" value="${v('letterhead_website')}"></div>
      <div class="field"><label>GSTIN</label><input id="bf-letterhead_gstin" value="${v('letterhead_gstin')}"></div>
      <div class="field"><label>Udyam</label><input id="bf-udyam_number" value="${v('udyam_number')}"></div>
    </div>
    <h3>Bank details</h3>
    <div class="field-row">
      <div class="field"><label>Bank</label><input id="bf-bank_name" value="${v('bank_name')}"></div>
      <div class="field"><label>Branch</label><input id="bf-bank_branch" value="${v('bank_branch')}"></div>
      <div class="field"><label>A/C no.</label><input id="bf-bank_account_no" value="${v('bank_account_no')}"></div>
      <div class="field"><label>IFSC</label><input id="bf-bank_ifsc" value="${v('bank_ifsc')}"></div>
    </div>
    ${imageBlock}
    <h3>Print layout</h3>
    <div class="field-row">
      <div class="field"><label>Document format</label><select id="bf-doc_format"><option value="1" ${b.doc_format !== 2 ? 'selected' : ''}>Format 1</option><option value="2" ${b.doc_format === 2 ? 'selected' : ''}>Format 2</option></select></div>
      <div class="field"><label>Accent colour</label><input id="bf-accent_color" placeholder="#a14000" value="${v('accent_color')}"></div>
    </div>
    <div class="field-row">
      <div class="field"><label><input type="checkbox" id="bf-watermark_enabled" style="width:auto;display:inline;" ${b.watermark_enabled ? 'checked' : ''}> Watermark on all prints</label></div>
      <div class="field"><label>Type</label><select id="bf-watermark_type"><option value="logo" ${b.watermark_type !== 'text' ? 'selected' : ''}>Logo</option><option value="text" ${b.watermark_type === 'text' ? 'selected' : ''}>Text</option></select></div>
      <div class="field"><label>Text</label><input id="bf-watermark_text" value="${v('watermark_text')}"></div>
      <div class="field"><label>Size %</label><input type="number" min="10" max="100" id="bf-watermark_size" value="${b.watermark_size || 50}"></div>
    </div>
    <div class="field"><label>Default terms &amp; conditions</label><textarea id="bf-terms" rows="4">${v('terms')}</textarea></div>
    <div class="field"><label><input type="checkbox" id="bf-active" style="width:auto;display:inline;" ${b.is_active !== false ? 'checked' : ''}> Active</label></div>
    <div class="modal-actions"><button class="btn" id="bf-cancel">Cancel</button><button class="btn primary" id="bf-save">${branch ? 'Save changes' : 'Create branch'}</button></div>`;
}

const TEXT_FIELDS = ['name', 'letterhead_name', 'letterhead_address', 'letterhead_phone', 'letterhead_mobile', 'letterhead_email',
  'letterhead_website', 'letterhead_gstin', 'udyam_number', 'bank_name', 'bank_branch', 'bank_account_no', 'bank_ifsc',
  'accent_color', 'watermark_text', 'terms'];

function openBranchForm(branch, onSaved) {
  openModal(`<h2>${branch ? 'Edit branch' : 'New branch'}</h2>${branchForm(branch)}`, {
    onMount: (modal) => {
      modal.querySelector('#bf-cancel').onclick = closeModal;
      modal.querySelectorAll('[data-image]').forEach((input) => input.addEventListener('change', async () => {
        if (!input.files[0]) return;
        try { await api.upload(`branches/${branch.id}/images/${input.dataset.image}/`, input.files[0]); toast('Image uploaded.', 'success'); closeModal(); onSaved(); }
        catch (e) { toast(apiErrorMessage(e), 'error'); }
      }));
      modal.querySelectorAll('[data-image-remove]').forEach((btn) => btn.addEventListener('click', async () => {
        try { await api.delete(`branches/${branch.id}/images/${btn.dataset.imageRemove}/`); closeModal(); onSaved(); }
        catch (e) { toast(apiErrorMessage(e), 'error'); }
      }));
      modal.querySelector('#bf-save').onclick = async () => {
        const data = {};
        TEXT_FIELDS.forEach((k) => { data[k] = modal.querySelector(`#bf-${k}`).value.trim(); });
        if (!data.name) { toast('Name is required.', 'error'); return; }
        data.doc_format = Number(modal.querySelector('#bf-doc_format').value);
        data.watermark_type = modal.querySelector('#bf-watermark_type').value;
        data.watermark_enabled = modal.querySelector('#bf-watermark_enabled').checked;
        data.watermark_size = Number(modal.querySelector('#bf-watermark_size').value) || 50;
        data.is_active = modal.querySelector('#bf-active').checked;
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
      <tr><th>Document</th><th>Prefix</th><th>Suffix</th><th>Start at</th><th>Next number</th></tr>
      ${DOC_TYPES.map(([dt, label], i) => `<tr data-dt="${dt}">
        <td>${escapeHtml(label)}</td>
        <td><input class="num-prefix" value="${escapeHtml(configs[i].prefix || '')}" placeholder="${escapeHtml(configs[i].effective_prefix || '')}" style="width:90px;"></td>
        <td><input class="num-suffix" value="${escapeHtml(configs[i].suffix || '')}" style="width:80px;"></td>
        <td><input class="num-start" type="number" value="${configs[i].start_at}" style="width:80px;"></td>
        <td class="sub">${escapeHtml(configs[i].next_number || '—')}</td>
      </tr>`).join('')}
    </table></div>
    <p class="sub">Blank prefix uses the default shown in grey. Pending PO has no generated number — it uses the customer's own PO number.</p>
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
  if (!await confirmDialog(`Remove branch "${branch.name}"? If documents or people use it, it is hidden instead and they keep it.`)) return;
  try {
    const res = await api.delete(`branches/${branch.id}/`);
    toast(res && res.deactivated ? 'Branch is in use, so it was deactivated instead of deleted.' : 'Removed.', 'success');
    onDone();
  } catch (e) { toast(apiErrorMessage(e), 'error'); }
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
