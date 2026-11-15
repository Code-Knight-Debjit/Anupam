// "+ Create new customer" from inside another form (a sales document, a payment, a task…). The dialog is its own overlay on top of
// whatever is open — nothing is navigated away from or re-mounted — so everything already typed in the form is still there when
// it closes. It asks for the essentials; the rest is added later from the Customer tab.
import { api } from './api.js';
import { state } from './state.js';
import { escapeHtml, apiErrorMessage, normalizeCompanyNameBasic } from './ui.js';
import { titleCaseWords, normPlant } from './customer_common.js';
import { INDIA_STATES } from './india.js';

const field = (id, label, extra = '') => `<div class="field"><label for="${id}">${label}</label>${extra}</div>`;

/** Opens the dialog; resolves with the created customer (the API's record) or null when cancelled. */
export function createCustomerDialog(prefillName = '') {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'overlay open qc-overlay';
    overlay.innerHTML = `<div class="modal qc-modal" role="dialog" aria-modal="true" aria-labelledby="qcTitle">
      <h2 id="qcTitle" style="margin-top:0;">New customer</h2>
      <p class="modal-sub">Add the essentials now — you can fill in the rest later from the Customer tab. Your form stays exactly as it is.</p>
      <div class="form-grid">
        <div class="field span2"><label for="qc-name">Company name <span style="color:var(--danger)">*</span></label><input type="text" id="qc-name" autocomplete="off"></div>
        <div class="field span2" id="qc-msg" role="alert" style="display:none; margin:0; padding:9px 11px; border-radius:8px; font-size:12.5px; line-height:1.4;"></div>
        ${field('qc-plant', 'Plant / Unit', '<input type="text" id="qc-plant" autocomplete="off">')}
        ${field('qc-gst', 'GST number', '<input type="text" id="qc-gst" autocomplete="off" style="text-transform:uppercase;">')}
        <div class="field span2"><label for="qc-address">Address</label><input type="text" id="qc-address" autocomplete="off"></div>
        ${field('qc-area', 'Area', '<input type="text" id="qc-area" autocomplete="off">')}
        ${field('qc-city', 'City', '<input type="text" id="qc-city" autocomplete="off">')}
        ${field('qc-state', 'State', `<select id="qc-state"><option value="">Select state</option>${INDIA_STATES.map((s) => `<option>${escapeHtml(s)}</option>`).join('')}</select>`)}
        ${field('qc-pin', 'Pincode', '<input type="text" id="qc-pin" inputmode="numeric" autocomplete="off">')}
        ${field('qc-contact', 'Contact person', '<input type="text" id="qc-contact" autocomplete="off">')}
        ${field('qc-title', 'Job title', `<select id="qc-title"><option value="">Select</option>${(state.lookups.job_title || []).map((j) => `<option>${escapeHtml(j.name)}</option>`).join('')}</select>`)}
        ${field('qc-phone', 'Phone', '<input type="text" id="qc-phone" inputmode="tel" autocomplete="off">')}
        ${field('qc-email', 'Email', '<input type="email" id="qc-email" autocomplete="off">')}
      </div>
      <div class="modal-actions"><button type="button" class="btn" id="qc-cancel">Cancel</button><button type="button" class="btn btn-primary" id="qc-save">Create customer</button></div>
    </div>`;
    document.body.appendChild(overlay);
    const $ = (id) => overlay.querySelector('#' + id);
    const done = (v) => { overlay.remove(); document.removeEventListener('keydown', onKey, true); resolve(v); };
    const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); done(null); } };
    document.addEventListener('keydown', onKey, true);
    overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) done(null); });
    $('qc-cancel').onclick = () => done(null);
    $('qc-name').value = titleCaseWords(prefillName || '');
    setTimeout(() => $('qc-name').focus(), 30);
    // Every message stays inside this dialog (the app's own alert / confirm dialogs would open underneath it — or replace a task form).
    const say = (msg, kind = 'err') => {
      const m = $('qc-msg'); m.textContent = msg; m.style.display = 'block';
      m.style.background = kind === 'err' ? 'var(--danger-bg)' : '#fff6e5'; m.style.color = kind === 'err' ? 'var(--danger)' : '#8a5a00';
    };
    const clear = () => { $('qc-msg').style.display = 'none'; $('qc-name').classList.remove('field-err'); };
    const fail = (msg) => { say(msg); $('qc-name').classList.add('field-err'); $('qc-name').focus(); };
    let warnedFor = '';                                          // the "looks similar" warning is shown once; saving again confirms it

    let busy = false;
    $('qc-save').onclick = async () => {
      if (busy) return;
      const name = titleCaseWords($('qc-name').value.trim()), plant = $('qc-plant').value.trim();
      if (!name) { fail('Enter a company name.'); return; }
      clear();
      busy = true; $('qc-save').disabled = true;
      try {
        let matches = [];
        try { matches = (await api.get(`customers/duplicate-check/?name=${encodeURIComponent(name)}`)).matches; } catch (e) { /* the form's own check is the same; carry on */ }
        const basic = normalizeCompanyNameBasic(name);
        const exact = matches.find((m) => normalizeCompanyNameBasic(m.name) === basic && normPlant(m.plant) === normPlant(plant));
        if (exact) {
          fail(plant ? `"${exact.name}" with plant "${exact.plant}" already exists — pick it from the list.` : `A customer named "${exact.name}" already exists — pick it from the list, or fill in the Plant / Unit if this is another unit.`);
          return;
        }
        const near = matches.filter((m) => normalizeCompanyNameBasic(m.name) !== basic);
        const key = name.toLowerCase() + '|' + normPlant(plant);
        if (near.length && warnedFor !== key) {
          warnedFor = key;
          say(`This name looks very similar to existing customer(s): ${near.slice(0, 3).map((m) => `"${m.name}"`).join(', ')}. If "${name}" really is a different company, press “Create customer” again.`, 'warn');
          return;
        }
        const cname = titleCaseWords($('qc-contact').value.trim()), phone = $('qc-phone').value.trim(), email = $('qc-email').value.trim();
        const body = { name, plant, address: titleCaseWords($('qc-address').value.trim()), area: $('qc-area').value.trim(), city: $('qc-city').value.trim(), state: $('qc-state').value,
          pincode: $('qc-pin').value.trim(), gst_number: $('qc-gst').value.trim().toUpperCase(), contacts: [] };
        if (cname || phone || email) body.contacts.push({ name: cname, job_title: $('qc-title').value, phone, phone2: '', email });
        let created;
        try { created = await api.post('customers/', body); } catch (e) { say(apiErrorMessage(e)); return; }
        done(created);
      } finally { busy = false; if ($('qc-save')) $('qc-save').disabled = false; }
    };
  });
}
