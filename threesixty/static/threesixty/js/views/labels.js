// Print Label — builds the label on the SERVER (`/360/api/labels/pdf/`), so Preview,
// Print and Download PDF are one and the same PDF (REQ-LBL-08). Labels keep their
// actual size and are tiled on an A4 sheet; the FROM block is always at the bottom.
// Picking a customer fills the form, but the person (Attn) and phone only when
// you pick a contact yourself (REQ-LBL-07).
import { api } from '../api.js';
import { state } from '../state.js';
import { el, escapeHtml, toast, apiErrorMessage, enhanceCustomerSelect } from '../ui.js';

const SIZE_LABELS = { a4: 'A4 (210 × 297 mm)', a5: 'A5 (148 × 210 mm)', '4x4': '4 × 4 inch', '6x4': '6 × 4 inch (portrait)' };

function collect() {
  return {
    customer_id: el('lc-cust').value || null, contact_id: el('lc-person').value || null,
    branch_id: el('lc-branch').value, deliver_to: el('lc-name').value.trim(),
    address: el('lc-addr').value.trim(), area: el('lc-area').value.trim(), city: el('lc-city').value.trim(),
    state: el('lc-state').value.trim(), pin: el('lc-pin').value.trim(), transport: el('lc-transport').value.trim(),
    courier: el('lc-courier').value.trim(), vehicle: el('lc-vehicle').value.trim(),
    attn: el('lc-attn').value.trim(), phone: el('lc-phone').value.trim(),
    paper: el('lc-paper').value, size: el('lc-size').value, boxes: el('lc-boxes').value,
    from_scale: el('lc-from').value, print_attn: el('lc-print-attn').checked, print_phone: el('lc-print-phone').checked,
  };
}

function url(download) {
  const params = new URLSearchParams();
  Object.entries(collect()).forEach(([k, v]) => { if (v !== null && v !== '' && v !== false) params.set(k, v === true ? '1' : v); });
  if (download) params.set('download', '1');
  return `/360/api/labels/pdf/?${params.toString()}`;
}

async function check() {
  // Ask the server first so a missing name etc. is a readable message, not a blank PDF tab.
  const resp = await fetch(url(false), { credentials: 'same-origin' });
  if (!resp.ok) { const body = await resp.json().catch(() => ({})); throw new Error(body.error || 'Could not make the label.'); }
}

export async function mountLabels(root) {
  const [customers, options] = await Promise.all([api.all('customers/'), api.get('labels/options/')]);
  const d = options.defaults;
  const myBranchId = (state.branches.find((b) => (state.me.branch_ids || []).includes(b.id)) || state.branches[0] || {}).id;
  root.innerHTML = `
    <h2 style="margin-top:0;">Print Label</h2>
    <div class="card glass" style="max-width:640px;">
      <div class="field-row">
        <div class="field"><label>From branch</label><select id="lc-branch">${state.branches.map((b) => `<option value="${b.id}" ${b.id === myBranchId ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('')}</select></div>
        <div class="field"><label>Paper</label><select id="lc-paper"><option value="a4" ${d.paper === 'a4' ? 'selected' : ''}>A4 sheet</option><option value="label">Label size</option></select></div>
        <div class="field"><label>Label size</label><select id="lc-size">${Object.keys(options.sizes).map((k) => `<option value="${k}" ${k === d.size ? 'selected' : ''}>${SIZE_LABELS[k] || k}</option>`).join('')}</select></div>
        <div class="field"><label>Boxes</label><input type="number" id="lc-boxes" min="1" max="${options.max_boxes}" value="${d.boxes}"></div>
      </div>
      <div class="field-row">
        <div class="field"><label>Customer</label><select id="lc-cust"></select></div>
        <div class="field"><label>Contact person (optional)</label><select id="lc-person"><option value="">—</option></select></div>
      </div>
      <div class="field"><label>Deliver to *</label><input id="lc-name" placeholder="Customer name, or type another"></div>
      <div class="field"><label>Address</label><textarea id="lc-addr" rows="2"></textarea></div>
      <div class="field-row">
        <div class="field"><label>Area</label><input id="lc-area"></div>
        <div class="field"><label>City</label><input id="lc-city"></div>
        <div class="field"><label>State</label><input id="lc-state"></div>
        <div class="field"><label>PIN</label><input id="lc-pin"></div>
      </div>
      <div class="field-row">
        <div class="field"><label>Transport</label><input id="lc-transport"></div>
        <div class="field"><label>Courier</label><input id="lc-courier"></div>
        <div class="field"><label>Vehicle</label><input id="lc-vehicle"></div>
      </div>
      <div class="field-row">
        <div class="field"><label>Attn</label><input id="lc-attn"></div>
        <div class="field"><label>Phone</label><input id="lc-phone"></div>
        <div class="field"><label>FROM size</label><select id="lc-from">${options.from_scales.map((s) => `<option value="${s}" ${s === d.from_scale ? 'selected' : ''}>${Math.round(s * 100)} %</option>`).join('')}</select></div>
      </div>
      <div class="field-row">
        <label><input type="checkbox" id="lc-print-attn" style="width:auto;display:inline;" ${d.print_attn ? 'checked' : ''}> Print person (Attn)</label>
        <label><input type="checkbox" id="lc-print-phone" style="width:auto;display:inline;" ${d.print_phone ? 'checked' : ''}> Print phone</label>
      </div>
      <div class="modal-actions" style="justify-content:flex-start;">
        <button class="btn" id="lcPreview">Preview</button>
        <button class="btn" id="lcPrint">Print</button>
        <button class="btn primary" id="lcPdf">Download PDF</button>
      </div>
    </div>`;
  enhanceCustomerSelect(el('lc-cust'), customers, { blank: '— select, or type below —' });

  el('lc-cust').addEventListener('change', async () => {
    el('lc-person').innerHTML = '<option value="">—</option>';
    el('lc-attn').value = ''; el('lc-phone').value = '';
    if (!el('lc-cust').value) return;
    try {
      const [fill, contacts] = await Promise.all([api.get(`labels/autofill/?customer_id=${el('lc-cust').value}`), api.all(`customers/${el('lc-cust').value}/contacts/`)]);
      el('lc-name').value = fill.customer; el('lc-addr').value = fill.address; el('lc-area').value = fill.area; el('lc-city').value = fill.city;
      el('lc-state').value = fill.state; el('lc-pin').value = fill.pin; el('lc-transport').value = fill.transport; el('lc-courier').value = fill.courier;
      el('lc-person').innerHTML = '<option value="">—</option>' + contacts.map((p) => `<option value="${p.id}">${escapeHtml(p.name || '—')}</option>`).join('');
    } catch (e) { toast(apiErrorMessage(e), 'error'); }
  });
  el('lc-person').addEventListener('change', async () => {
    if (!el('lc-person').value) { el('lc-attn').value = ''; el('lc-phone').value = ''; return; }
    try {
      const fill = await api.get(`labels/autofill/?customer_id=${el('lc-cust').value}&contact_id=${el('lc-person').value}`);
      el('lc-attn').value = fill.attn; el('lc-phone').value = fill.phone;
    } catch (e) { toast(apiErrorMessage(e), 'error'); }
  });

  const run = async (action) => {
    try {
      await check();
      if (action === 'preview') window.open(url(false), '_blank');
      else if (action === 'pdf') window.location.href = url(true);
      else {
        const frame = document.createElement('iframe');
        frame.style.cssText = 'position:fixed;width:0;height:0;border:0;';
        frame.src = url(false);
        frame.onload = () => { try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch (e) { window.open(url(false), '_blank'); } };
        document.body.appendChild(frame);
        setTimeout(() => frame.remove(), 60000);
      }
    } catch (e) { toast(e.message, 'error'); }
  };
  el('lcPreview').onclick = () => run('preview');
  el('lcPrint').onclick = () => run('print');
  el('lcPdf').onclick = () => run('pdf');
}
