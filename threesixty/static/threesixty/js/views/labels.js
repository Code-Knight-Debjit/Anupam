// Print Label — the reference's page (the "Custom label" panel) and its options dialog (paper, FROM size, label size,
// number of boxes, Attn, phone). The label is laid out by the reference's own code in the browser (doc_print.js), so Print and
// Download PDF are one and the same label. Picking a customer fills the form; the person (Attn) and phone are filled
// only when a person is picked (REQ-LBL-07). What is in the form is exactly what is printed.
import { api } from '../api.js';
import { state } from '../state.js';
import { el, escapeHtml, customAlert, apiErrorMessage } from '../ui.js';
import { mountRefView, useOverlays, openOverlay, closeOverlay } from '../customer_common.js';
import { labelOut, LABEL_SIZES } from '../doc_print.js';

/** The options dialog: nothing about paper is asked on the page, only when Print or PDF is pressed (reference: labelAction). */
function labelAction(parts, fileBase, mode) {
  useOverlays('lblOptOverlay');
  if (!el('lblSizeSel').options.length) el('lblSizeSel').innerHTML = LABEL_SIZES.map((s) => `<option value="${s.key}">${s.label}</option>`).join('');
  el('lblSizeSel').value = 'a5'; el('lblPaper').value = 'a4'; el('lblFrom').value = '1.5';
  el('lblOptTitle').textContent = mode === 'pdf' ? 'Download label PDF' : 'Print label';
  el('lblOptGo').textContent = mode === 'pdf' ? 'Download PDF' : 'Print';
  openOverlay('lblOptOverlay');
  el('lblOptCancel').onclick = () => closeOverlay('lblOptOverlay');
  el('lblOptGo').onclick = () => {
    closeOverlay('lblOptOverlay');
    const size = LABEL_SIZES.find((x) => x.key === el('lblSizeSel').value) || LABEL_SIZES[0];
    const n = Math.max(1, Math.min(99, parseInt(el('lblBoxes').value, 10) || 1));
    const q = { ...parts, fromScale: parseFloat(el('lblFrom').value) || 1 };
    if (!el('lblShowAttn').checked) q.attn = '';
    if (!el('lblShowPhone').checked) q.phone = '';
    labelOut(q, mode, n, size, fileBase, el('lblPaper').value === 'a4');
  };
}

export async function mountLabels(root) {
  mountRefView(root, 'view-labels');
  const customers = (await api.all('customers/')).sort((a, b) => (a.name || '').localeCompare(b.name || ''));
  const set = (id, v) => { el(id).value = v || ''; };

  el('lc-branch').innerHTML = state.branches.map((b) => `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join('');
  const own = (state.me.branch_ids || [])[0];
  if (own) el('lc-branch').value = String(own);
  el('lc-cust').innerHTML = '<option value="">— Select customer —</option>' + customers.map((c) => `<option value="${c.id}">${escapeHtml(c.label || c.name || '—')}</option>`).join('');
  el('lc-person').innerHTML = '<option value="">— Select person —</option>';

  let people = [];
  el('lc-cust').addEventListener('change', async () => {
    people = []; set('lc-attn', ''); set('lc-phone', '');
    el('lc-person').innerHTML = '<option value="">— Select person —</option>';
    const id = el('lc-cust').value;
    if (!id) return;
    try {
      const [fill, contacts] = await Promise.all([api.get(`labels/autofill/?customer_id=${id}`), api.all(`customers/${id}/contacts/`)]);
      people = contacts;
      set('lc-name', fill.customer); set('lc-addr', (fill.address || '').trim()); set('lc-area', fill.area);
      set('lc-city', [fill.city, fill.state].map((v) => (v || '').trim()).filter(Boolean).join(', ')); set('lc-pin', fill.pin);
      set('lc-transport', fill.transport || fill.courier);
      el('lc-person').innerHTML = '<option value="">— Select person —</option>' + contacts.map((p) => `<option value="${p.id}">${escapeHtml(p.name || '—')}</option>`).join('');
    } catch (e) { await customAlert(apiErrorMessage(e)); }
  });
  el('lc-person').addEventListener('change', () => {
    const p = people.find((x) => String(x.id) === el('lc-person').value);
    if (p) { set('lc-attn', p.name); set('lc-phone', p.phone || p.phone2); }
  });

  const go = async (mode) => {
    const customer = customers.find((c) => String(c.id) === el('lc-cust').value);
    const name = el('lc-name').value.trim() || (customer ? (customer.name || '').trim() : '');
    if (!name) { await customAlert('Enter who the label is for.'); return; }
    const branch = (state.branches.find((b) => String(b.id) === el('lc-branch').value) || {}).name || '';
    labelAction({
      branch, customer: name, addrLines: el('lc-addr').value.split('\n').map((v) => v.trim()).filter(Boolean), area: el('lc-area').value.trim(), cityLine: el('lc-city').value.trim(),
      pin: el('lc-pin').value.trim(), attn: el('lc-attn').value.trim(), phone: el('lc-phone').value.trim(), transport: el('lc-transport').value.trim(), courier: '', vehicle: '', ref: '',
      date: new Date().toLocaleDateString('en-IN'),
    }, 'label-' + name.replace(/[^\w-]+/g, '_'), mode);
  };
  el('lcPrintBtn').onclick = () => go('print');
  el('lcPdfBtn').onclick = () => go('pdf');
}
