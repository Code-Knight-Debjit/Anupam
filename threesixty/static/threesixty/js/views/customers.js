// Customers — list, create/edit, contacts, interactions. Ported from the
// original's company list/detail screens; duplicate-name detection reuses
// the verified `findDuplicateCustomers` (ui.js) ahead of create/rename.
import { api } from '../api.js';
import { state, lookup, isAdmin, isBranchManager, isSalesManager } from '../state.js';
import {
  el, escapeHtml, fmtDate, fmtDateTime, toast, apiErrorMessage, openModal, closeModal,
  confirmDialog, renderTable, findDuplicateCustomers,
} from '../ui.js';

let allCustomers = [];
let search = '';

// `industry`/`source`/`potential`/`transport_preference`/`courier_preference` on
// Customer are plain free-text CharFields (see models/customers.py) — the
// lookup lists for `industry`/`source` only supply *suggested* option text,
// so the <select> must carry the LookupItem's name, not its id.
function freeTextLookupOptions(kind, selectedText) {
  const options = lookup(kind);
  const extra = selectedText && !options.some((l) => l.name === selectedText) ? [{ id: `__free_${selectedText}`, name: selectedText }] : [];
  return [...extra, ...options].map((l) => `<option value="${escapeHtml(l.name)}" ${l.name === selectedText ? 'selected' : ''}>${escapeHtml(l.name)}</option>`).join('');
}

function multiCheckboxes(name, kind, selectedIds) {
  return lookup(kind).map((l) => `<label style="display:inline-block;margin:0 10px 4px 0;"><input type="checkbox" class="${name}-cb" value="${l.id}" ${(selectedIds || []).includes(l.id) ? 'checked' : ''}> ${escapeHtml(l.name)}</label>`).join('') || '<span class="sub">None configured.</span>';
}

let employeesCache = null;
async function getEmployees() {
  if (!employeesCache) employeesCache = await api.all('employees/');
  return employeesCache;
}

function employeeCheckboxes(employees, selectedIds) {
  return (employees || []).map((e) => `<label style="display:inline-block;margin:0 10px 4px 0;"><input type="checkbox" class="assigned-cb" value="${e.user_id}" ${(selectedIds || []).includes(e.user_id) ? 'checked' : ''}> ${escapeHtml(e.full_name)}</label>`).join('') || '<span class="sub">No employees configured.</span>';
}

function geoToText(lat, lng) { return (lat || lng) ? `${lat ?? ''}, ${lng ?? ''}` : ''; }
function geoFromText(txt) {
  const m = String(txt || '').trim().match(/(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/);
  return m ? { lat: Number(m[1]), lng: Number(m[2]) } : { lat: null, lng: null };
}

function customerForm(customer, employees) {
  const c = customer || {};
  return `
    <div class="field-row">
      <div class="field"><label>Company name *</label><input id="cf-name" value="${escapeHtml(c.name || '')}"></div>
      <div class="field"><label>Industry</label><select id="cf-industry"><option value="">—</option>${freeTextLookupOptions('industry', c.industry)}</select></div>
    </div>
    <div class="field"><label>Plant / works address</label><input id="cf-plant" value="${escapeHtml(c.plant || '')}"></div>
    <div class="field-row">
      <div class="field"><label>Address</label><input id="cf-address" value="${escapeHtml(c.address || '')}"></div>
      <div class="field"><label>Area</label><input id="cf-area" value="${escapeHtml(c.area || '')}"></div>
    </div>
    <div class="field-row">
      <div class="field"><label>City</label><input id="cf-city" value="${escapeHtml(c.city || '')}"></div>
      <div class="field"><label>State</label><input id="cf-state" value="${escapeHtml(c.state || '')}"></div>
      <div class="field"><label>Pincode</label><input id="cf-pincode" value="${escapeHtml(c.pincode || '')}"></div>
    </div>
    <div class="field"><label>Plant map pin (lat, lng)</label><input id="cf-plant-geo" value="${escapeHtml(geoToText(c.plant_geo_lat, c.plant_geo_lng))}" placeholder="13.0285, 77.5197"></div>
    <div class="field-row">
      <div class="field"><label>Website</label><input id="cf-website" value="${escapeHtml(c.website || '')}"></div>
      <div class="field"><label>GST number</label><input id="cf-gst" value="${escapeHtml(c.gst_number || '')}"></div>
    </div>
    <div class="field-row">
      <div class="field"><label>Source</label><select id="cf-source"><option value="">—</option>${freeTextLookupOptions('source', c.source)}</select></div>
      <div class="field"><label>Potential</label><select id="cf-potential"><option value="">—</option><option ${c.potential === 'High' ? 'selected' : ''}>High</option><option ${c.potential === 'Medium' ? 'selected' : ''}>Medium</option><option ${c.potential === 'Low' ? 'selected' : ''}>Low</option></select></div>
    </div>
    <div class="field-row">
      <div class="field"><label>Transport preference</label><input id="cf-transport" value="${escapeHtml(c.transport_preference || '')}"></div>
      <div class="field"><label>Courier preference</label><input id="cf-courier" value="${escapeHtml(c.courier_preference || '')}"></div>
    </div>
    <details style="margin:10px 0;">
      <summary style="cursor:pointer;font-weight:600;">Head office (if different from plant)</summary>
      <div class="field-row">
        <div class="field"><label>HO name</label><input id="cf-ho-name" value="${escapeHtml(c.ho_name || '')}"></div>
        <div class="field"><label>HO phone</label><input id="cf-ho-phone" value="${escapeHtml(c.ho_phone || '')}"></div>
      </div>
      <div class="field"><label>HO address</label><input id="cf-ho-address" value="${escapeHtml(c.ho_address || '')}"></div>
      <div class="field-row">
        <div class="field"><label>HO city</label><input id="cf-ho-city" value="${escapeHtml(c.ho_city || '')}"></div>
        <div class="field"><label>HO state</label><input id="cf-ho-state" value="${escapeHtml(c.ho_state || '')}"></div>
        <div class="field"><label>HO pincode</label><input id="cf-ho-pincode" value="${escapeHtml(c.ho_pincode || '')}"></div>
      </div>
      <div class="field"><label>HO map pin (lat, lng)</label><input id="cf-ho-geo" value="${escapeHtml(geoToText(c.ho_geo_lat, c.ho_geo_lng))}"></div>
    </details>
    <div class="field"><label>Preferred languages</label>${multiCheckboxes('lang', 'language', c.preferred_language_ids)}</div>
    <div class="field"><label>Interested brands</label>${multiCheckboxes('brand', 'brand', c.interested_brand_ids)}</div>
    <div class="field"><label>Interested products</label>${multiCheckboxes('product', 'product', c.interested_product_ids)}</div>
    <div class="field"><label>Assigned to</label>${employeeCheckboxes(employees, c.assigned_to_ids)}</div>
    <div id="cf-dup-hint" class="sub" style="color:var(--error);"></div>
    <div class="modal-actions">
      <button class="btn" id="cf-cancel">Cancel</button>
      <button class="btn primary" id="cf-save">${customer ? 'Save changes' : 'Create customer'}</button>
    </div>`;
}

function readCustomerForm(modal) {
  const plantGeo = geoFromText(modal.querySelector('#cf-plant-geo').value);
  const hoGeo = geoFromText(modal.querySelector('#cf-ho-geo').value);
  const ids = (cls) => Array.from(modal.querySelectorAll(`.${cls}`)).filter((c) => c.checked).map((c) => Number(c.value));
  return {
    name: modal.querySelector('#cf-name').value.trim(),
    industry: modal.querySelector('#cf-industry').value || '',
    plant: modal.querySelector('#cf-plant').value.trim(),
    address: modal.querySelector('#cf-address').value.trim(),
    area: modal.querySelector('#cf-area').value.trim(),
    city: modal.querySelector('#cf-city').value.trim(),
    state: modal.querySelector('#cf-state').value.trim(),
    pincode: modal.querySelector('#cf-pincode').value.trim(),
    plant_geo_lat: plantGeo.lat, plant_geo_lng: plantGeo.lng,
    website: modal.querySelector('#cf-website').value.trim(),
    gst_number: modal.querySelector('#cf-gst').value.trim(),
    source: modal.querySelector('#cf-source').value || '',
    potential: modal.querySelector('#cf-potential').value || '',
    transport_preference: modal.querySelector('#cf-transport').value.trim(),
    courier_preference: modal.querySelector('#cf-courier').value.trim(),
    ho_name: modal.querySelector('#cf-ho-name').value.trim(),
    ho_phone: modal.querySelector('#cf-ho-phone').value.trim(),
    ho_address: modal.querySelector('#cf-ho-address').value.trim(),
    ho_city: modal.querySelector('#cf-ho-city').value.trim(),
    ho_state: modal.querySelector('#cf-ho-state').value.trim(),
    ho_pincode: modal.querySelector('#cf-ho-pincode').value.trim(),
    ho_geo_lat: hoGeo.lat, ho_geo_lng: hoGeo.lng,
    preferred_language_ids: ids('lang-cb'),
    interested_brand_ids: ids('brand-cb'),
    interested_product_ids: ids('product-cb'),
    assigned_to_ids: ids('assigned-cb'),
  };
}

async function openCustomerForm(customer, onSaved) {
  const employees = await getEmployees();
  openModal(`<h2>${customer ? 'Edit customer' : 'New customer'}</h2>${customerForm(customer, employees)}`, {
    onMount: (modal) => {
      modal.querySelector('#cf-cancel').onclick = closeModal;
      const nameInput = modal.querySelector('#cf-name');
      const hint = modal.querySelector('#cf-dup-hint');
      const checkDup = () => {
        const { exact, near } = findDuplicateCustomers(nameInput.value, allCustomers, customer && customer.id);
        hint.textContent = exact ? `A customer named "${exact.name}" already exists.` : near.length ? `Looks similar to: ${near.map((n) => n.name).join(', ')}` : '';
      };
      nameInput.addEventListener('input', checkDup);
      checkDup();
      modal.querySelector('#cf-save').onclick = async () => {
        const data = readCustomerForm(modal);
        if (!data.name) { toast('Company name is required.', 'error'); return; }
        const { exact } = findDuplicateCustomers(data.name, allCustomers, customer && customer.id);
        if (exact) { toast(`A customer named "${exact.name}" already exists.`, 'error'); return; }
        try {
          if (customer) {
            const res = await api.patch(`customers/${customer.id}/`, { ...data, version: customer.version });
            if (res && res.approval_requested) toast('Edit sent for approval.', 'info');
            else toast('Customer updated.', 'success');
          } else {
            await api.post('customers/', data);
            toast('Customer created.', 'success');
          }
          closeModal();
          onSaved();
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

async function deleteCustomer(customer, onDone) {
  if (!await confirmDialog(`Remove "${customer.name}"? This cannot be undone.`)) return;
  try {
    const res = await api.delete(`customers/${customer.id}/`);
    if (res && res.approval_requested) toast('Delete sent for approval.', 'info');
    else toast('Customer removed.', 'success');
    onDone();
  } catch (e) { toast(apiErrorMessage(e), 'error'); }
}

function contactForm(contact) {
  const c = contact || {};
  return `
    <div class="field-row">
      <div class="field"><label>Name *</label><input id="kf-name" value="${escapeHtml(c.name || '')}"></div>
      <div class="field"><label>Job title</label><input id="kf-title" value="${escapeHtml(c.job_title || '')}"></div>
    </div>
    <div class="field-row">
      <div class="field"><label>Phone</label><input id="kf-phone" value="${escapeHtml(c.phone || '')}"></div>
      <div class="field"><label>Phone 2</label><input id="kf-phone2" value="${escapeHtml(c.phone2 || '')}"></div>
      <div class="field"><label>Email</label><input id="kf-email" value="${escapeHtml(c.email || '')}"></div>
    </div>
    <div class="field"><label><input type="checkbox" id="kf-dnd" style="width:auto;display:inline;" ${c.dnd ? 'checked' : ''}> Do not disturb</label></div>
    <div class="modal-actions"><button class="btn" id="kf-cancel">Cancel</button><button class="btn primary" id="kf-save">Save</button></div>`;
}

async function openContactModal(customerId, contact, onSaved) {
  openModal(`<h2>${contact ? 'Edit contact' : 'New contact'}</h2>${contactForm(contact)}`, {
    onMount: (modal) => {
      modal.querySelector('#kf-cancel').onclick = closeModal;
      modal.querySelector('#kf-save').onclick = async () => {
        const data = {
          name: modal.querySelector('#kf-name').value.trim(), job_title: modal.querySelector('#kf-title').value.trim(),
          phone: modal.querySelector('#kf-phone').value.trim(), phone2: modal.querySelector('#kf-phone2').value.trim(),
          email: modal.querySelector('#kf-email').value.trim(), dnd: modal.querySelector('#kf-dnd').checked,
        };
        if (!data.name) { toast('Name is required.', 'error'); return; }
        try {
          if (contact) await api.patch(`contacts/${contact.id}/`, data);
          else await api.post(`customers/${customerId}/contacts/`, data);
          closeModal();
          toast('Saved.', 'success');
          onSaved();
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

async function renderContactsTab(container, customer) {
  const contacts = await api.all(`customers/${customer.id}/contacts/`);
  container.innerHTML = `
    <div class="flex-between"><h3>Contacts</h3><button class="btn sm primary" id="addContactBtn">+ Add contact</button></div>
    ${renderTable(['Name', 'Title', 'Phone', 'Email', 'DND', ''], contacts.map((c) => ({
      Name: escapeHtml(c.name), Title: escapeHtml(c.job_title), Phone: escapeHtml(c.phone),
      Email: escapeHtml(c.email), DND: c.dnd ? 'Yes' : '',
      '': `<button class="btn sm" data-edit="${c.id}">Edit</button> <button class="btn sm danger" data-del="${c.id}">Remove</button>`,
    })))}`;
  container.querySelector('#addContactBtn').onclick = () => openContactModal(customer.id, null, () => renderContactsTab(container, customer));
  container.querySelectorAll('[data-edit]').forEach((btn) => btn.onclick = () => {
    const c = contacts.find((x) => String(x.id) === btn.dataset.edit);
    openContactModal(customer.id, c, () => renderContactsTab(container, customer));
  });
  container.querySelectorAll('[data-del]').forEach((btn) => btn.onclick = async () => {
    if (!await confirmDialog('Remove this contact?')) return;
    await api.delete(`contacts/${btn.dataset.del}/`);
    renderContactsTab(container, customer);
  });
}

async function renderInteractionsTab(container, customer) {
  const contacts = await api.all(`customers/${customer.id}/contacts/`);
  const lists = await Promise.all(contacts.map((c) => api.all(`contacts/${c.id}/interactions/`)));
  const interactions = lists.flat().sort((a, b) => new Date(b.date) - new Date(a.date));
  const contactName = (id) => { const c = contacts.find((x) => x.id === id); return c ? c.name : '—'; };

  container.innerHTML = `
    <div class="flex-between"><h3>Interactions</h3>
      <select id="newIntContact" style="width:auto;">${contacts.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('') || '<option value="">No contacts yet</option>'}</select>
    </div>
    <div class="card" style="margin-bottom:14px;">
      <div class="field-row">
        <div class="field"><label>Type</label><select id="int-type"><option>Call</option><option>Visit</option><option>Appointment</option></select></div>
        <div class="field"><label>Date</label><input type="date" id="int-date" value="${new Date().toISOString().slice(0, 10)}"></div>
        <div class="field"><label>Follow-up date</label><input type="date" id="int-followup"></div>
      </div>
      <div class="field"><label>Notes</label><textarea id="int-notes" rows="2"></textarea></div>
      <button class="btn primary sm" id="int-add">Log interaction</button>
    </div>
    ${interactions.length ? interactions.map((i) => `
      <div class="card" style="margin-bottom:8px;padding:12px 16px;">
        <div class="flex-between" style="margin-bottom:4px;">
          <strong>${escapeHtml(i.type)} · ${escapeHtml(contactName(i.contact_id))}</strong>
          <span class="sub">${fmtDate(i.date)}</span>
        </div>
        <div style="font-size:13px;">${escapeHtml(i.notes || '')}</div>
        ${i.followup_date ? `<div class="sub">Follow-up: ${fmtDate(i.followup_date)}</div>` : ''}
      </div>`).join('') : '<p class="sub">No interactions logged yet.</p>'}`;

  const addBtn = container.querySelector('#int-add');
  if (addBtn) addBtn.onclick = async () => {
    const contactId = container.querySelector('#newIntContact').value;
    if (!contactId) { toast('Add a contact first.', 'error'); return; }
    try {
      await api.post(`contacts/${contactId}/interactions/`, {
        type: container.querySelector('#int-type').value,
        date: container.querySelector('#int-date').value,
        followup_date: container.querySelector('#int-followup').value || null,
        notes: container.querySelector('#int-notes').value.trim(),
      });
      toast('Interaction logged.', 'success');
      renderInteractionsTab(container, customer);
    } catch (e) { toast(apiErrorMessage(e), 'error'); }
  };
}

function openCustomerDetail(customer, onChanged) {
  openModal(`
    <div class="flex-between"><h2>${escapeHtml(customer.name)}</h2>
      <div>
        <button class="btn sm" id="cd-edit">Edit</button>
        <button class="btn sm danger" id="cd-delete">Remove</button>
      </div>
    </div>
    <div class="tabbar">
      <button data-tab="profile" class="active">Profile</button>
      <button data-tab="contacts">Contacts</button>
      <button data-tab="interactions">Interactions</button>
    </div>
    <div id="cd-body"></div>
  `, {
    onMount: (modal) => {
      const body = modal.querySelector('#cd-body');
      const renderProfile = () => {
        body.innerHTML = `
          <table class="data" style="width:100%;">
            <tr><td>Plant</td><td>${escapeHtml(customer.plant || '—')}</td></tr>
            <tr><td>Address</td><td>${escapeHtml(customer.address || '—')}, ${escapeHtml(customer.city || '')} ${escapeHtml(customer.state || '')} ${escapeHtml(customer.pincode || '')}</td></tr>
            <tr><td>Website</td><td>${escapeHtml(customer.website || '—')}</td></tr>
            <tr><td>GST</td><td>${escapeHtml(customer.gst_number || '—')}</td></tr>
            <tr><td>Created</td><td>${fmtDateTime(customer.created_at)}${customer.created_by ? ' by ' + escapeHtml(customer.created_by.full_name) : ''}</td></tr>
          </table>`;
      };
      const tabs = { profile: renderProfile, contacts: () => renderContactsTab(body, customer), interactions: () => renderInteractionsTab(body, customer) };
      modal.querySelectorAll('.tabbar button').forEach((btn) => btn.addEventListener('click', () => {
        modal.querySelectorAll('.tabbar button').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        tabs[btn.dataset.tab]();
      }));
      renderProfile();
      modal.querySelector('#cd-edit').onclick = () => openCustomerForm(customer, onChanged);
      modal.querySelector('#cd-delete').onclick = () => deleteCustomer(customer, () => { closeModal(); onChanged(); });
    },
  });
}

async function renderList(root) {
  const canEdit = state.flags.can_edit_customer_direct || isSalesManager();
  allCustomers = await api.all('customers/', search ? { search } : {});
  root.innerHTML = `
    <div class="flex-between">
      <input id="custSearch" placeholder="Search customers…" style="max-width:320px;" value="${escapeHtml(search)}">
      <button class="btn primary" id="newCustBtn">+ New Customer</button>
    </div>
    ${renderTable(['Name', 'City', 'Industry', 'Potential', 'Assigned'], allCustomers.map((c) => ({
      Name: `<a data-open="${c.id}" style="cursor:pointer;color:var(--primary);font-weight:600;">${escapeHtml(c.name)}</a>`,
      City: escapeHtml(c.city), Industry: escapeHtml(c.industry || ''), Potential: escapeHtml(c.potential || ''),
      Assigned: (c.assigned_to_ids || []).length,
    })), { empty: 'No customers found.' })}`;

  root.querySelector('#newCustBtn').onclick = () => openCustomerForm(null, () => renderList(root));
  const searchBox = root.querySelector('#custSearch');
  let t;
  searchBox.oninput = () => { clearTimeout(t); t = setTimeout(() => { search = searchBox.value; renderList(root); }, 300); };
  root.querySelectorAll('[data-open]').forEach((a) => a.onclick = () => {
    const c = allCustomers.find((x) => String(x.id) === a.dataset.open);
    openCustomerDetail(c, () => renderList(root));
  });
}

export async function mountCustomers(root) {
  await renderList(root);
}
