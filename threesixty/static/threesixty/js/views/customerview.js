// Customer view — the reference's read-only profile of one customer: hero (logo, name, address, Check Transactions /
// Edit), the details grid, location pins, head office, preferences & assignment, and the contact persons.
import { api } from '../api.js';
import { state } from '../state.js';
import { navigate } from '../router.js';
import { el, escapeHtml, fmtMoney, customAlert, customConfirm, apiErrorMessage } from '../ui.js';
import {
  mountRefView, useOverlays, openOverlay, closeOverlay, waLink, webUrl, dotColorForTitle, initialsOf, geoLink, geoDirLink, pinOf, fmtD,
  CALL_ICON_SVG, EMAIL_ICON_SVG, WHATSAPP_ICON_SVG,
} from '../customer_common.js';
import { getLocation } from '../attendance_actions.js';
import { openContactEdit } from './customers.js';

const GEO_LABEL = { plant: 'Plant', ho: 'Head office' };

function geoGrid(c, reload) {
  const box = el('cvGeoGrid');
  box.innerHTML = ['plant', 'ho'].map((k) => {
    const g = pinOf(c, k);
    if (!g) return `<div class="cv-mini"><label>📍 ${GEO_LABEL[k]}</label><p style="color:var(--text-dim);">Not pinned</p><div class="cv-geo-links"><button type="button" data-pin="${k}">Pin my current location</button></div></div>`;
    return `<div class="cv-mini"><label>📍 ${GEO_LABEL[k]}</label><p>${g.lat}, ${g.lng}</p>
      <div class="cv-geo-links"><a href="${geoLink(g)}" target="_blank" rel="noopener">Open map</a><a href="${geoDirLink(g)}" target="_blank" rel="noopener">Directions</a><button type="button" data-pin="${k}">Update to my location</button><button type="button" data-clearpin="${k}">Remove</button></div>
      <div style="font-size:11.5px; color:var(--text-dim); margin-top:2px;">${g.by ? 'Set by ' + escapeHtml(g.by) : ''}${g.at ? ' · ' + fmtD(g.at) : ''}</div></div>`;
  }).join('');
  box.querySelectorAll('[data-pin]').forEach((b) => b.onclick = async () => {
    const k = b.dataset.pin;
    if (pinOf(c, k) && !await customConfirm(`Replace the saved ${GEO_LABEL[k].toLowerCase()} pin with your current location?`)) return;
    let p; try { p = await getLocation(); } catch (e) { await customAlert(e.message); return; }
    try { await api.patch(`customers/${c.id}/`, { [`${k}_geo`]: `${p.lat}, ${p.lng}`, version: c.version }); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    reload();
  });
  box.querySelectorAll('[data-clearpin]').forEach((b) => b.onclick = async () => {
    const k = b.dataset.clearpin;
    if (!await customConfirm(`Remove the ${GEO_LABEL[k].toLowerCase()} pin?`)) return;
    try { await api.patch(`customers/${c.id}/`, { [`${k}_geo`]: '', version: c.version }); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    reload();
  });
}

function contactRows(c) {
  return c.contacts.length ? c.contacts.map((ct) => {
    const wa = waLink(ct.phone);
    return `
      <div class="contact-row" data-cid="${c.id}" data-ctid="${ct.id}"${ct.dnd ? ' style="background:var(--danger-bg); border-radius:8px;"' : ''}>
        <div class="contact-left" style="text-align:left; cursor:pointer;" data-person="${ct.id}" title="View profile">
          <span class="desig-dot" style="background:${dotColorForTitle(ct.job_title)}"></span>
          <div style="text-align:left;">
            <div class="c-name" style="text-decoration:underline;${ct.dnd ? ' color:var(--danger);' : ''}">${escapeHtml(ct.name || 'Unnamed')}${ct.dnd ? ' <span title="Do Not Disturb" style="font-size:10px; font-weight:700;">(DND)</span>' : ''}</div>
            <div class="c-desig">${escapeHtml(ct.job_title || 'Other')}</div>
          </div>
        </div>
        <div class="c-meta">
          ${ct.phone ? `<button type="button" class="btn btn-call c-meta-icon-btn" data-phone="${escapeHtml(ct.phone)}" title="Call ${escapeHtml(ct.phone)}">${CALL_ICON_SVG}</button>` : ''}
          ${ct.phone2 ? `<button type="button" class="btn btn-call c-meta-icon-btn" data-phone="${escapeHtml(ct.phone2)}" title="Call ${escapeHtml(ct.phone2)}">${CALL_ICON_SVG}</button>` : ''}
          ${ct.email ? `<button type="button" class="btn btn-email c-meta-icon-btn copy-email" data-email="${escapeHtml(ct.email)}" title="Copy email: ${escapeHtml(ct.email)}">${EMAIL_ICON_SVG}</button>` : `<button type="button" class="btn btn-email-missing c-meta-icon-btn" title="No email on file">${EMAIL_ICON_SVG}</button>`}
          ${wa ? `<a class="btn btn-wa c-meta-icon-btn" href="${wa}" target="_blank" rel="noopener" title="WhatsApp">${WHATSAPP_ICON_SVG}</a>` : ''}
          <button class="btn btn-icon c-meta-btn" data-person="${ct.id}">View Profile</button>
          <button class="btn btn-icon c-meta-btn" data-contactedit="${ct.id}" title="Edit this contact">Edit</button>
        </div>
      </div>`;
  }).join('') : '<div class="no-contacts">No contact persons added.</div>';
}

const money = (v) => '₹' + fmtMoney(v);
const docRows = (rows) => (rows.length ? `<tr><th>Doc No.</th><th>Date</th><th>Contact</th><th>Status</th><th>Value</th></tr>${rows.map((d) => `<tr><td>${escapeHtml(d.number || '—')}</td><td>${d.date ? fmtD(d.date) : '—'}</td><td>${escapeHtml(d.contact || '—')}</td><td>${escapeHtml(d.status || '—')}</td><td>${money(d.value)}</td></tr>`).join('')}` : '<tr><td>None yet.</td></tr>');

async function openTransactions(c) {
  useOverlays('companyTransactionsOverlay');
  let t;
  try { t = await api.get(`customers/${c.id}/transactions/`); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
  el('ctName').textContent = `Transactions — ${c.name || '—'}`;
  el('ctSub').textContent = 'Every enquiry, quotation, proforma invoice, and payment recorded for this company.';
  el('ctEnquiryTable').innerHTML = docRows(t.enquiry);
  el('ctQuotationTable').innerHTML = docRows(t.quotation);
  el('ctProformaTable').innerHTML = docRows(t.proforma);
  el('ctPaymentsTable').innerHTML = t.payments.length ? `<tr><th>Date</th><th>Contact</th><th>Amount</th><th>Received</th><th>Balance</th></tr>${t.payments.map((p) => `<tr><td>${p.date ? fmtD(p.date) : '—'}</td><td>${escapeHtml(p.contact || '—')}</td><td>${money(p.amount)}</td><td>${money(p.received)}</td><td>${money(p.balance)}</td></tr>`).join('')}` : '<tr><td>No payments recorded yet.</td></tr>';
  el('companyTransactionsCloseBtn').onclick = () => closeOverlay('companyTransactionsOverlay');
  openOverlay('companyTransactionsOverlay');
}

export async function mountCustomerView(root, id) {
  const view = mountRefView(root, 'view-customerview');
  const render = async () => {
    const c = (await api.get('customers/cards/')).results.find((x) => String(x.id) === String(id));
    if (!c) { root.innerHTML = '<div class="empty">That customer is not available.</div>'; return; }
    window.__cardCustomer = c;
    el('cvName').textContent = c.name || '—';
    el('cvAv').innerHTML = c.logo_url ? `<img alt="" src="${c.logo_url}">` : escapeHtml(initialsOf(c.name || '?'));
    el('cvAv').classList.toggle('has-logo', !!c.logo_url);
    el('cvAddress').textContent = c.address || '';
    el('cvWebsite').innerHTML = c.website ? `<a href="${escapeHtml(webUrl(c.website))}" target="_blank" rel="noopener" style="color:var(--blue);">${escapeHtml(c.website)}</a>` : '—';
    el('cvGst').textContent = c.gst_number || '—';
    geoGrid(c, render);
    const hasHo = c.ho_address || c.ho_city || c.ho_state || c.ho_pincode || c.ho_name || c.ho_phone;
    el('cvHoWrap').style.display = hasHo ? 'block' : 'none';
    el('cvHoGrid').innerHTML = hasHo ? [['Name', c.ho_name], ['Address', c.ho_address], ['City', c.ho_city], ['State', c.ho_state], ['Pincode', c.ho_pincode], ['Phone', c.ho_phone]].filter((x) => x[1])
      .map(([l, v]) => `<div class="cv-mini" ${l === 'Address' ? 'style="grid-column:span 2;"' : ''}><label>${l}</label><p>${escapeHtml(v)}</p></div>`).join('') : '';
    const set = (k, v) => { el(k).textContent = v || '—'; };
    set('cvArea', c.area); set('cvCity', c.city); set('cvState', c.state); set('cvPincode', c.pincode); set('cvIndustry', c.industry); set('cvSource', c.source);
    set('cvTransport', c.transport_preference); set('cvCourier', c.courier_preference);
    set('cvLanguage', c.preferred_languages.join(', ')); set('cvAssigned', c.assigned_to.map((a) => a.full_name).join(', ')); set('cvAddedBy', c.created_by_name);
    el('cvBrands').innerHTML = c.interested_brands.length ? c.interested_brands.map((b) => `<span class="tag tag-brand">${escapeHtml(b)}</span>`).join('') : '—';
    el('cvProducts').innerHTML = c.interested_products.length ? c.interested_products.map((p) => `<span class="tag tag-product">${escapeHtml(p)}</span>`).join('') : '—';
    const box = el('cvContacts');
    box.innerHTML = contactRows(c);
    box.querySelectorAll('[data-person]').forEach((b) => b.onclick = () => navigate('person', c.id, b.dataset.person));
    box.querySelectorAll('[data-phone]').forEach((b) => b.onclick = () => window.showPhoneOptions(b.dataset.phone));
    box.querySelectorAll('.copy-email').forEach((b) => b.onclick = () => window.copyEmailToClipboard(b));
    box.querySelectorAll('[data-contactedit]').forEach((b) => b.onclick = () => openContactEdit(c.id, Number(b.dataset.contactedit), render));
    box.querySelectorAll('.contact-row[data-ctid]').forEach((row) => row.addEventListener('click', (e) => {
      if (e.target.closest('button,a,input,select,textarea,.contact-left')) return;
      navigate('person', row.dataset.cid, row.dataset.ctid);
    }));
    el('cvEditBtn').onclick = () => navigate('customerform', c.id);
    el('cvTransactionsBtn').onclick = () => openTransactions(c);
  };
  el('customerViewBackBtn').onclick = () => { if (window.history.length > 1) window.history.back(); else navigate('customers'); };
  await render();
}
