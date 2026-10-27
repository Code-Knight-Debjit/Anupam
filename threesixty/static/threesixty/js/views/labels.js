// Print Label — ported from the original's shipping-label panel
// (`renderLabelsPage`/`lcGo`, ~L9792-9845): pick a customer (or type a
// one-off address), choose a paper size, print. Simplified: the original's
// multi-box PDF tiling (`labelPdfParts`/`labelPrintParts`, jsPDF-based) is
// not ported — this uses the browser's native print dialog against a
// single label laid out at the chosen paper size via `@media print`.
import { api } from '../api.js';
import { state } from '../state.js';
import { el, escapeHtml, toast } from '../ui.js';

const LABEL_SIZES = [
  { key: 'a4', label: 'A4 (210 × 297 mm)', w: 210, h: 297 },
  { key: 'a5', label: 'A5 (148 × 210 mm)', w: 148, h: 210 },
  { key: '4x4', label: '4 × 4 inch', w: 101.6, h: 101.6 },
  { key: '6x4', label: '6 × 4 inch (portrait)', w: 101.6, h: 152.4 },
];

let customersCache = null;
async function getCustomers() {
  if (!customersCache) customersCache = await api.all('customers/');
  return customersCache;
}

function printLabel(data, size) {
  const sizeDef = LABEL_SIZES.find((s) => s.key === size) || LABEL_SIZES[0];
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>Label</title><style>
    @page { size: ${sizeDef.w}mm ${sizeDef.h}mm; margin: 8mm; }
    body { font-family: Arial, sans-serif; font-size: 13pt; color: #111; }
    .label-from { font-size: 9pt; color: #555; margin-bottom: 10mm; }
    .label-to { font-size: 11pt; color: #555; letter-spacing: .05em; margin-bottom: 2mm; }
    .label-name { font-size: 16pt; font-weight: 700; margin-bottom: 2mm; }
    .label-line { margin-bottom: 1mm; }
    .label-attn { margin-top: 4mm; font-weight: 600; }
  </style></head><body>
    <div class="label-from">From: ${escapeHtml(data.branch || '')}</div>
    <div class="label-to">TO</div>
    <div class="label-name">${escapeHtml(data.customer || '')}</div>
    ${data.addrLines.map((l) => `<div class="label-line">${escapeHtml(l)}</div>`).join('')}
    ${data.area ? `<div class="label-line">${escapeHtml(data.area)}</div>` : ''}
    ${data.cityLine ? `<div class="label-line">${escapeHtml(data.cityLine)}</div>` : ''}
    ${data.pin ? `<div class="label-line">PIN: ${escapeHtml(data.pin)}</div>` : ''}
    ${data.attn ? `<div class="label-attn">Attn: ${escapeHtml(data.attn)}${data.phone ? ' · ' + escapeHtml(data.phone) : ''}</div>` : ''}
    ${data.transport ? `<div class="label-line">Via: ${escapeHtml(data.transport)}</div>` : ''}
  </body></html>`;
  let iframe = document.getElementById('labelPrintIframe');
  if (!iframe) {
    iframe = document.createElement('iframe');
    iframe.id = 'labelPrintIframe';
    iframe.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;';
    document.body.appendChild(iframe);
  }
  iframe.onload = () => { setTimeout(() => { try { iframe.contentWindow.focus(); iframe.contentWindow.print(); } catch (e) { toast('Print failed: ' + e.message, 'error'); } }, 150); };
  iframe.srcdoc = html;
}

export async function mountLabels(root) {
  const customers = await getCustomers();
  const myBranchId = (state.branches.find((b) => (state.me.branch_ids || []).includes(b.id)) || state.branches[0] || {}).id;

  root.innerHTML = `
    <h2 style="margin-top:0;">Print Label</h2>
    <div class="card" style="max-width:560px;">
      <div class="field-row">
        <div class="field"><label>From branch</label><select id="lc-branch">${state.branches.map((b) => `<option value="${b.id}" ${b.id === myBranchId ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('')}</select></div>
        <div class="field"><label>Paper size</label><select id="lc-size">${LABEL_SIZES.map((s) => `<option value="${s.key}">${escapeHtml(s.label)}</option>`).join('')}</select></div>
      </div>
      <div class="field-row">
        <div class="field"><label>Customer</label><select id="lc-cust"><option value="">— select, or type below —</option>${customers.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('')}</select></div>
        <div class="field"><label>Contact person</label><select id="lc-person"><option value="">—</option></select></div>
      </div>
      <div class="field"><label>Customer name</label><input id="lc-name"></div>
      <div class="field"><label>Address</label><textarea id="lc-addr" rows="2"></textarea></div>
      <div class="field-row">
        <div class="field"><label>Area</label><input id="lc-area"></div>
        <div class="field"><label>City, state</label><input id="lc-city"></div>
        <div class="field"><label>PIN</label><input id="lc-pin"></div>
      </div>
      <div class="field-row">
        <div class="field"><label>Attn</label><input id="lc-attn"></div>
        <div class="field"><label>Phone</label><input id="lc-phone"></div>
        <div class="field"><label>Transport</label><input id="lc-transport"></div>
      </div>
      <button class="btn primary" id="lcPrintBtn">Print label</button>
    </div>`;

  const fillPeople = () => {
    const c = customers.find((x) => String(x.id) === el('lc-cust').value);
    el('lc-person').innerHTML = '<option value="">—</option>';
    if (!c) return;
    api.all(`customers/${c.id}/contacts/`).then((contacts) => {
      el('lc-person').innerHTML = '<option value="">—</option>' + contacts.map((p) => `<option value="${p.id}" data-phone="${escapeHtml(p.phone || '')}" data-name="${escapeHtml(p.name || '')}">${escapeHtml(p.name || '—')}</option>`).join('');
    });
  };

  el('lc-cust').addEventListener('change', () => {
    const c = customers.find((x) => String(x.id) === el('lc-cust').value);
    fillPeople();
    if (!c) return;
    el('lc-name').value = c.name || '';
    el('lc-addr').value = (c.address || '').trim();
    el('lc-area').value = c.area || '';
    el('lc-city').value = [c.city, c.state].filter(Boolean).join(', ');
    el('lc-pin').value = c.pincode || '';
    el('lc-transport').value = c.transport_preference || c.courier_preference || '';
    el('lc-attn').value = ''; el('lc-phone').value = '';
  });
  el('lc-person').addEventListener('change', (e) => {
    const opt = e.target.selectedOptions[0];
    if (!opt || !opt.value) return;
    el('lc-attn').value = opt.dataset.name || '';
    el('lc-phone').value = opt.dataset.phone || '';
  });

  el('lcPrintBtn').addEventListener('click', () => {
    const name = el('lc-name').value.trim();
    if (!name) { toast('Enter who the label is for.', 'error'); return; }
    const branch = state.branches.find((b) => String(b.id) === el('lc-branch').value);
    printLabel({
      branch: branch ? branch.name : '', customer: name,
      addrLines: el('lc-addr').value.split('\n').map((v) => v.trim()).filter(Boolean),
      area: el('lc-area').value.trim(), cityLine: el('lc-city').value.trim(), pin: el('lc-pin').value.trim(),
      attn: el('lc-attn').value.trim(), phone: el('lc-phone').value.trim(), transport: el('lc-transport').value.trim(),
    }, el('lc-size').value);
  });
}
