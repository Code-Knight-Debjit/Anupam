// Branches — the reference's page: the App logo and Sidebar logo panel, the list of branches (Edit Details / Edit Numbering /
// Rename / Remove) with an "Add a new branch…" row, the branch-details dialog (letterhead, logos, watermark, accent colour,
// bank details) and the document-numbering dialog. Only an Admin may change anything here (the server enforces it).
import { api } from '../api.js';
import { state, loadBootstrap, applyLogos } from '../state.js';
import { el, escapeHtml, customAlert, customConfirm, customPrompt, apiErrorMessage } from '../ui.js';
import { mountRefView, useOverlays, openOverlay, closeOverlay } from '../customer_common.js';

const DEFAULT_ACCENT = '#d97b2f';
// What Print / PDF number: Pending PO carries the customer's own PO number, and the stock bills of the reference's Sales / Purchase
// numbering are not part of Anupam 360's screens.
const NUMBERING_TYPES = [['enquiry', 'Enquiry', 'ENQ'], ['quotation', 'Quotation', 'QUO'], ['dc', 'Delivery Challan', 'DC'], ['proforma', 'Proforma Invoice', 'PI']];
const SIZE = { small: 30, medium: 50, large: 75 };
const sizeKey = (n) => (n <= 40 ? 'small' : n >= 65 ? 'large' : 'medium');
const IMAGE_SLOTS = [['logo', 'bd-logo', 'logo_url'], ['dealer_logo', 'bd-dealer-logo', 'dealer_logo_url'], ['footer_image', 'bd-footer-image', 'footer_image_url'], ['payment_qr', 'bd-qr', 'payment_qr_url']];

let branches = [];
const appLogo = () => (state.siteSettings || {}).appLogo;
const sidebarLogo = () => (state.siteSettings || {}).sidebarLogo;
const defaultOf = (selector) => { const i = document.querySelector(selector); return i ? (i.dataset.default || i.getAttribute('src')) : ''; };

// ---- App logo & sidebar logo --------------------------------------------------------------------------------------------------------
function paintLogos() {
  el('appLogoPreview').src = (appLogo() && appLogo().url) || defaultOf('#logoRowMobile img');
  el('sidebarLogoPreview').src = (sidebarLogo() && sidebarLogo().url) || (appLogo() && appLogo().url) || defaultOf('#logoRowApp img');
}
/** Shrinks a big image (keeping transparency) so the stored logo stays small, as the reference does. */
function shrink(file, maxW) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = (e) => {
      const img = new Image();
      img.onerror = reject;
      img.onload = () => {
        const scale = img.naturalWidth > maxW ? maxW / img.naturalWidth : 1;
        const c = document.createElement('canvas');
        c.width = Math.round(img.naturalWidth * scale); c.height = Math.round(img.naturalHeight * scale);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        c.toBlob((blob) => resolve({ blob, aspect: c.width / c.height }), 'image/png');
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  });
}
function wireLogo({ input, reset, hint, kind, key, maxW, done, resetText }) {
  el(input).onchange = async () => {
    const file = el(input).files[0]; if (!file) return;
    if (!file.type.startsWith('image/')) { el(hint).textContent = 'Please choose an image file.'; return; }
    try {
      const { blob, aspect } = await shrink(file, maxW);
      const fd = new FormData(); fd.append('file', blob, 'logo.png'); fd.append('aspect', aspect);
      state.siteSettings[key] = await api.post(`branding/${kind}/`, fd);
      applyLogos(); paintLogos(); renderBranchList();
      el(hint).textContent = done; el(input).value = '';
    } catch (e) { el(hint).textContent = e && e.status ? apiErrorMessage(e) : "Couldn't read that image. Try a PNG or JPG."; }
  };
  el(reset).onclick = async () => {
    try { await api.delete(`branding/${kind}/`); } catch (e) { el(hint).textContent = apiErrorMessage(e); return; }
    delete state.siteSettings[key];
    applyLogos(); paintLogos(); renderBranchList();
    el(hint).textContent = resetText; el(input).value = '';
  };
}

// ---- list --------------------------------------------------------------------------------------------------------------------------------
function renderBranchList() {
  const listEl = el('branchesList');
  if (!branches.length) { listEl.innerHTML = '<p class="sub">No branches yet.</p>'; return; }
  const fallback = (appLogo() && appLogo().url) || defaultOf('#logoRowMobile img');
  listEl.innerHTML = branches.map((b) => `
    <div class="manage-item">
      <span class="mi-name" style="display:flex; align-items:center; gap:8px;">
        <img src="${escapeHtml(b.logo_url || fallback)}" alt="" style="width:22px; height:22px; object-fit:contain; border-radius:4px; background:#fff; border:1px solid var(--line);">
        <span title="Accent colour" style="width:12px; height:12px; border-radius:50%; background:${escapeHtml(b.accent_color || DEFAULT_ACCENT)}; border:1px solid var(--line); display:inline-block;"></span>
        ${escapeHtml(b.name)}
        ${b.letterhead_name ? `<span style="color:var(--text-faint); font-weight:400; font-size:12px;">&middot; ${escapeHtml(b.letterhead_name)}</span>` : ''}
      </span>
      <span class="mi-actions">
        <button data-act="details" data-id="${b.id}">Edit Details</button>
        <button data-act="numbering" data-id="${b.id}">Edit Numbering</button>
        <button data-act="rename" data-id="${b.id}">Rename</button>
        <button class="danger" data-act="remove" data-id="${b.id}">Remove</button>
      </span>
    </div>`).join('');
  listEl.querySelectorAll('[data-act]').forEach((btn) => {
    btn.onclick = () => {
      const b = branches.find((x) => String(x.id) === btn.dataset.id); if (!b) return;
      if (btn.dataset.act === 'details') openDetails(b); else if (btn.dataset.act === 'numbering') openNumbering(b); else if (btn.dataset.act === 'rename') rename(b); else remove(b);
    };
  });
}
async function reload() {
  branches = await api.all('branches/');
  await loadBootstrap();
  renderBranchList();
}
async function rename(b) {
  const val = await customPrompt('Rename branch to:', b.name); if (val === null || !val.trim()) return;
  try { await api.patch(`branches/${b.id}/`, { name: val.trim() }); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
  await reload();
}
async function remove(b) {
  if (!await customConfirm('Remove this branch? Users already assigned to it will keep the old name as text.')) return;
  try { await api.delete(`branches/${b.id}/`); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
  await reload();
}

// ---- branch details ----------------------------------------------------------------------------------------------------------------------
function openDetails(b) {
  useOverlays('branchDetailOverlay');
  const pending = {};              // slot -> { file } to upload, or { remove: true }
  el('branchDetailTitle').textContent = `Branch Details — ${b.name}`;
  [['bd-companyname', 'letterhead_name'], ['bd-address', 'letterhead_address'], ['bd-phone', 'letterhead_phone'], ['bd-mobile', 'letterhead_mobile'], ['bd-email', 'letterhead_email'], ['bd-website', 'letterhead_website'],
    ['bd-gst', 'letterhead_gstin'], ['bd-udyam', 'udyam_number'], ['bd-bank-acno', 'bank_account_no'], ['bd-bank-ifsc', 'bank_ifsc'], ['bd-bank-name', 'bank_name'], ['bd-bank-branch', 'bank_branch']]
    .forEach(([id, field]) => { el(id).value = b[field] || ''; });
  el('bd-docfmt').value = b.doc_format === 2 ? '2' : '1';
  el('bd-wm-enabled').checked = !!b.watermark_enabled;
  el('bd-wm-type').value = b.watermark_type === 'text' ? 'text' : 'logo';
  el('bd-wm-text').value = b.watermark_text || ''; el('bd-wm-size').value = sizeKey(b.watermark_size || 50);
  el('bd-wm-text-wrap').style.display = b.watermark_type === 'text' ? '' : 'none';
  el('bd-wm-type').onchange = (e) => { el('bd-wm-text-wrap').style.display = e.target.value === 'text' ? '' : 'none'; };
  el('bd-accent').value = b.accent_color || DEFAULT_ACCENT;
  el('bd-accent-reset').onclick = () => { el('bd-accent').value = DEFAULT_ACCENT; };

  const paint = (slot, prefix, urlField) => {
    const img = el(prefix + '-preview'), p = pending[slot];
    const src = p ? (p.file ? URL.createObjectURL(p.file) : '') : (b[urlField] || '');
    if (src) { img.src = src; img.style.display = 'block'; } else { img.src = ''; img.style.display = 'none'; }
  };
  IMAGE_SLOTS.forEach(([slot, prefix, urlField]) => {
    el(prefix + '-input').value = '';
    el(prefix + '-input').onchange = async () => {
      const file = el(prefix + '-input').files[0]; if (!file) return;
      if (!file.type.startsWith('image/')) { await customAlert('Please choose an image file.'); el(prefix + '-input').value = ''; return; }
      pending[slot] = { file }; paint(slot, prefix, urlField);
    };
    el(prefix + '-remove').onclick = () => { pending[slot] = { remove: true }; el(prefix + '-input').value = ''; paint(slot, prefix, urlField); };
    paint(slot, prefix, urlField);
  });
  el('branchDetailCancelBtn').onclick = () => closeOverlay('branchDetailOverlay');
  el('branchDetailSaveBtn').onclick = async () => {
    const text = el('bd-wm-text').value.trim();
    if (el('bd-wm-enabled').checked && el('bd-wm-type').value === 'text' && !text) { await customAlert('Enter the watermark text, or switch the watermark off.'); return; }
    const data = {
      letterhead_name: el('bd-companyname').value.trim(), letterhead_address: el('bd-address').value.trim(), letterhead_phone: el('bd-phone').value.trim(), letterhead_mobile: el('bd-mobile').value.trim(),
      letterhead_email: el('bd-email').value.trim(), letterhead_website: el('bd-website').value.trim(), letterhead_gstin: el('bd-gst').value.trim(), udyam_number: el('bd-udyam').value.trim(),
      doc_format: el('bd-docfmt').value === '2' ? 2 : 1, watermark_enabled: el('bd-wm-enabled').checked, watermark_type: el('bd-wm-type').value, watermark_text: text || b.watermark_text || '',
      watermark_size: SIZE[el('bd-wm-size').value], bank_account_no: el('bd-bank-acno').value.trim(), bank_ifsc: el('bd-bank-ifsc').value.trim(), bank_name: el('bd-bank-name').value.trim(),
      bank_branch: el('bd-bank-branch').value.trim(), accent_color: el('bd-accent').value === DEFAULT_ACCENT ? '' : el('bd-accent').value,
    };
    try {
      await api.patch(`branches/${b.id}/`, data);
      for (const [slot, p] of Object.entries(pending)) {
        if (p.file) { const fd = new FormData(); fd.append('file', p.file); await api.post(`branches/${b.id}/images/${slot}/`, fd); }
        else if (p.remove && b[IMAGE_SLOTS.find((s) => s[0] === slot)[2]]) await api.delete(`branches/${b.id}/images/${slot}/`);
      }
    } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    closeOverlay('branchDetailOverlay');
    await reload();
    await customAlert("Branch details saved. They will now show on this branch's Quotation letterhead.");
  };
  openOverlay('branchDetailOverlay');
}

// ---- document numbering --------------------------------------------------------------------------------------------------------------
async function openNumbering(b) {
  useOverlays('branchNumberingOverlay');
  let configs;
  try { configs = await Promise.all(NUMBERING_TYPES.map(([key]) => api.get(`branches/${b.id}/numbering/${key}/`))); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
  el('branchNumberingTitle').textContent = `Document Numbering — ${b.name}`;
  el('branchNumberingBody').innerHTML = NUMBERING_TYPES.map(([key, label, def], i) => `
    <div style="border:1px solid var(--line); border-radius:8px; padding:12px;">
      <div style="font-weight:600; margin-bottom:8px;">${escapeHtml(label)} <span style="font-weight:400; color:var(--text-faint); font-size:12px;">&middot; next number ${escapeHtml(configs[i].next_number || '—')}</span></div>
      <div class="form-grid">
        <div class="field"><label for="bn-${key}-prefix">Prefix</label><input type="text" id="bn-${key}-prefix" placeholder="${escapeHtml(configs[i].effective_prefix || def)}" value="${escapeHtml(configs[i].prefix || '')}"></div>
        <div class="field"><label for="bn-${key}-suffix">Suffix</label><input type="text" id="bn-${key}-suffix" placeholder="none" value="${escapeHtml(configs[i].suffix || '')}"></div>
        <div class="field"><label for="bn-${key}-start">Serial Number Start From</label><input type="number" id="bn-${key}-start" min="1" placeholder="1" value="${configs[i].start_at && configs[i].start_at !== 1 ? configs[i].start_at : ''}"></div>
      </div>
    </div>`).join('');
  el('branchNumberingCancelBtn').onclick = () => closeOverlay('branchNumberingOverlay');
  el('branchNumberingSaveBtn').onclick = async () => {
    try {
      await Promise.all(NUMBERING_TYPES.map(([key]) => {
        const startRaw = el(`bn-${key}-start`).value;
        return api.patch(`branches/${b.id}/numbering/${key}/`, {
          prefix: el(`bn-${key}-prefix`).value.trim(), suffix: el(`bn-${key}-suffix`).value.trim(), start_at: startRaw !== '' ? Math.max(1, Number(startRaw) || 1) : 1,
        });
      }));
    } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    closeOverlay('branchNumberingOverlay');
    await customAlert('Numbering settings saved for this branch. New documents for this branch will use them.');
  };
  openOverlay('branchNumberingOverlay');
}

export async function mountBranches(root) {
  mountRefView(root, 'view-branches');
  branches = await api.all('branches/');
  paintLogos(); renderBranchList();
  wireLogo({ input: 'appLogoInput', reset: 'appLogoResetBtn', hint: 'appLogoHint', kind: 'app', key: 'appLogo', maxW: 900, done: 'Logo updated.', resetText: 'Back to the default logo.' });
  wireLogo({ input: 'sidebarLogoInput', reset: 'sidebarLogoResetBtn', hint: 'sidebarLogoHint', kind: 'sidebar', key: 'sidebarLogo', maxW: 600, done: 'Sidebar logo updated.', resetText: 'The sidebar now uses the app logo.' });
  el('addBranchBtn').onclick = async () => {
    const val = el('newBranchInput').value.trim(); if (!val) return;
    try { await api.post('branches/', { name: val }); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    el('newBranchInput').value = ''; await reload();
  };
  el('newBranchInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') el('addBranchBtn').click(); });
}
