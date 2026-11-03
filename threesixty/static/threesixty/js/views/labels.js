// Print Label — the reference's page (the "Custom label" panel) and its options dialog (paper, FROM size, label size,
// number of boxes, Attn, phone). The label is built on the SERVER (`/360/api/labels/pdf/`), so Print and Download PDF
// are one and the same PDF (REQ-LBL-08). Picking a customer fills the form; the person (Attn) and phone are filled
// only when a person is picked (REQ-LBL-07). What is in the form is exactly what is printed.
import { api } from '../api.js';
import { state } from '../state.js';
import { el, escapeHtml, customAlert, apiErrorMessage } from '../ui.js';
import { mountRefView, useOverlays, openOverlay, closeOverlay } from '../customer_common.js';

const LABEL_SIZES = [
  ['a4', 'A4 (210 × 297 mm)'], ['a5', 'A5 (148 × 210 mm)'], ['4x4', '4 × 4 inch'], ['6x4', '6 × 4 inch (portrait)'],
];

function labelUrl(fields, download) {
  const params = new URLSearchParams();
  Object.entries(fields).forEach(([k, v]) => { if (v !== null && v !== undefined && v !== '') params.set(k, v === true ? '1' : v === false ? '0' : v); });
  if (download) params.set('download', '1');
  return `/360/api/labels/pdf/?${params.toString()}`;
}

async function run(fields, mode) {
  // Ask the server first so a problem is a readable message, not a blank PDF tab.
  const resp = await fetch(labelUrl(fields, false), { credentials: 'same-origin' });
  if (!resp.ok) { const body = await resp.json().catch(() => ({})); await customAlert(body.error || 'Could not make the label.'); return; }
  if (mode === 'pdf') { window.location.href = labelUrl(fields, true); return; }
  const frame = document.createElement('iframe');
  frame.style.cssText = 'position:fixed;width:0;height:0;border:0;';
  frame.src = labelUrl(fields, false);
  frame.onload = () => { try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch (e) { window.open(labelUrl(fields, false), '_blank'); } };
  document.body.appendChild(frame);
  setTimeout(() => frame.remove(), 60000);
}

/** The options dialog: nothing about paper is asked on the page, only when Print or PDF is pressed. */
function labelAction(party, mode) {
  useOverlays('lblOptOverlay');
  if (!el('lblSizeSel').options.length) el('lblSizeSel').innerHTML = LABEL_SIZES.map(([k, t]) => `<option value="${k}">${t}</option>`).join('');
  el('lblSizeSel').value = 'a5'; el('lblPaper').value = 'a4'; el('lblFrom').value = '1.5';
  el('lblOptTitle').textContent = mode === 'pdf' ? 'Download label PDF' : 'Print label';
  el('lblOptGo').textContent = mode === 'pdf' ? 'Download PDF' : 'Print';
  openOverlay('lblOptOverlay');
  el('lblOptCancel').onclick = () => closeOverlay('lblOptOverlay');
  el('lblOptGo').onclick = () => {
    closeOverlay('lblOptOverlay');
    const boxes = Math.max(1, Math.min(99, parseInt(el('lblBoxes').value, 10) || 1));
    run({
      ...party, paper: el('lblPaper').value, size: el('lblSizeSel').value, boxes, from_scale: el('lblFrom').value,
      print_attn: el('lblShowAttn').checked, print_phone: el('lblShowPhone').checked,
      ...(el('lblShowAttn').checked ? {} : { attn: '' }), ...(el('lblShowPhone').checked ? {} : { phone: '' }),
    }, mode);
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
    labelAction({
      branch_id: el('lc-branch').value, deliver_to: name, address: el('lc-addr').value.trim(), area: el('lc-area').value.trim(),
      city: el('lc-city').value.trim(), pin: el('lc-pin').value.trim(), attn: el('lc-attn').value.trim(), phone: el('lc-phone').value.trim(),
      transport: el('lc-transport').value.trim(),
    }, mode);
  };
  el('lcPrintBtn').onclick = () => go('print');
  el('lcPdfBtn').onclick = () => go('pdf');
}
