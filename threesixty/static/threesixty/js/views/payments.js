// Payment Collection — the reference's list (grouped per branch, with the three stat tiles), the New / Edit page, the
// Payment Overview and Received Payment dialogs, Payment History, and the Payment Log (the chat-style log page shared with
// the sales documents). The server decides who sees which payments; the screens follow the reference markup.
import { api } from '../api.js';
import { state, isAdmin, isBranchManager, isBranchStaff } from '../state.js';
import { navigate } from '../router.js';
import { el, escapeHtml, fmtMoney, customAlert, customConfirm, apiErrorMessage } from '../ui.js';
import { mountRefView, useOverlays, openOverlay, closeOverlay, waLink, fmtD, WHATSAPP_ICON_SVG } from '../customer_common.js';
import { mountLogPage } from './sales_pages.js';

const CALL_LOG_ICON_SVG = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';
const num = (v) => Number(v) || 0;
const today = () => new Date().toISOString().slice(0, 10);
const when = (d) => (d ? new Date(d).toLocaleDateString('en-IN') : '—');

let payments = [];
let filters = { customer: '', search: '', branch: '' };
let filtersBeforeViewAll = null;
let filtersSeeded = false;

const loadPayments = async () => { payments = await api.all('payment-collections/'); };
const balance = (p) => num(p.balance);
const received = (p) => num(p.received);
const branchOf = (p) => p.branch_name || '';

// Admin, Branch Manager and Branch Staff land on their own branch (the Filters panel widens it); the rest see only their own payments.
function seedFilters() {
  if (filtersSeeded) return;
  filtersSeeded = true;
  if (isAdmin() || !(isBranchManager() || isBranchStaff())) return;
  const own = state.branches.find((b) => (state.me.branch_ids || []).includes(b.id));
  if (own) filters.branch = own.name;
}

function applyFilters(list) {
  if (filters.customer) list = list.filter((p) => p.customer_name === filters.customer);
  if (filters.branch) list = list.filter((p) => branchOf(p) === filters.branch);
  if (filters.search) {
    const q = filters.search.toLowerCase();
    list = list.filter((p) => (p.customer_name || '').toLowerCase().includes(q) || (p.remarks || '').toLowerCase().includes(q));
  }
  return list;
}
const byDateDesc = (a, b) => new Date(b.date || b.created_at) - new Date(a.date || a.created_at);

// ---- contact cell ------------------------------------------------------------------------------------------------------------------
function contactCell(p) {
  const wa = p.contact_name ? waLink(p.contact_phone) : null;
  return `<div>
    <span style="display:inline-flex; align-items:center; gap:4px; white-space:nowrap;">
      <span>${escapeHtml(p.contact_name || '—')}</span>
      ${wa ? `<a class="btn btn-wa" style="display:inline-flex; align-items:center; justify-content:center; padding:3px 4px; line-height:1;" href="${wa}" target="_blank" rel="noopener" title="WhatsApp">${WHATSAPP_ICON_SVG}</a>` : ''}
      <button type="button" class="btn btn-icon" data-paylog="${p.id}" style="display:inline-flex; align-items:center; justify-content:center; padding:3px 4px; line-height:1;" title="Payment Log">${CALL_LOG_ICON_SVG}</button>
    </span>
    <div style="font-size:11px; color:var(--text-faint); margin-top:3px; white-space:nowrap;">Last contact: ${p.last_contact_on ? new Date(p.last_contact_on).toLocaleString('en-IN') : '—'}</div>
    <div style="font-size:11px; margin-top:1px; white-space:nowrap; color:${p.call_later_date ? 'var(--accent)' : 'var(--text-faint)'}; font-weight:${p.call_later_date ? '600' : '400'};">Call later: ${p.call_later_date ? fmtD(p.call_later_date) : '—'}</div>
  </div>`;
}
const rowButtons = (p, withReceive) => `
  <button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-pay-act="view" data-id="${p.id}">View</button>
  ${withReceive ? `<button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-pay-act="receive" data-id="${p.id}">Received Payment</button>` : ''}
  <button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-pay-act="edit" data-id="${p.id}">Edit</button>
  <button class="btn-danger-text" data-pay-act="delete" data-id="${p.id}">Delete</button>`;

function wireRows(root, redraw) {
  root.querySelectorAll('[data-paylog]').forEach((b) => { b.onclick = () => navigate('paymentlog', b.dataset.paylog); });
  root.querySelectorAll('[data-pay-act]').forEach((b) => {
    b.onclick = () => {
      const p = payments.find((x) => String(x.id) === b.dataset.id);
      if (!p) return;
      if (b.dataset.payAct === 'view') openPaymentView(p);
      else if (b.dataset.payAct === 'receive') openReceived(p, redraw);
      else if (b.dataset.payAct === 'edit') navigate('paymentform', p.id);
      else deletePayment(p, redraw);
    };
  });
}

async function deletePayment(p, redraw) {
  if (!await customConfirm('Delete this payment record? This cannot be undone.')) return;
  try { await api.delete(`payment-collections/${p.id}/`); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
  await loadPayments(); redraw();
}

// ---- dialogs -------------------------------------------------------------------------------------------------------------------------
function openPaymentView(p) {
  useOverlays('paymentViewOverlay');
  el('pvSub').textContent = `${p.date ? new Date(p.date).toLocaleDateString('en-IN') : ''} ${p.remarks ? '— ' + p.remarks : ''}`;
  el('pvCustomer').textContent = p.customer_name || '—';
  el('pvContact').textContent = p.contact_name || '—';
  el('pvTotal').textContent = `₹${fmtMoney(num(p.amount))}`;
  el('pvReceived').textContent = `₹${fmtMoney(received(p))}`;
  el('pvBalance').textContent = `₹${fmtMoney(balance(p))}`;
  el('pvRemarks').textContent = p.remarks || '—';
  const log = [...(p.receipts || [])].sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));
  el('pvReceipts').innerHTML = log.length ? log.map((r) => `
    <tr>
      <td>${when(r.date)}</td>
      <td>₹${fmtMoney(num(r.amount))}</td>
      <td>${escapeHtml(r.mode || '—')}</td>
      <td>${escapeHtml(r.remarks || '—')}</td>
      <td>${escapeHtml((r.recorded_by && r.recorded_by.full_name) || '—')}</td>
    </tr>`).join('') : '<tr><td colspan="5" style="text-align:center; color:var(--text-faint);">No receipts recorded yet.</td></tr>';
  el('paymentViewCloseBtn').onclick = () => closeOverlay('paymentViewOverlay');
  openOverlay('paymentViewOverlay');
}

function openReceived(p, redraw) {
  useOverlays('receivedPaymentOverlay');
  el('rpSub').textContent = `${p.customer_name} — ${p.remarks || ''}`;
  el('rp-total').value = `₹${fmtMoney(num(p.amount))}`;
  el('rp-balance').value = `₹${fmtMoney(balance(p))}`;
  el('rp-amount').value = '';
  el('rp-amount').max = balance(p);
  el('rp-date').value = today();
  el('rp-mode').value = 'Cash';
  el('rp-remarks').value = '';
  el('receivedPaymentCancelBtn').onclick = () => closeOverlay('receivedPaymentOverlay');
  el('receivedPaymentSaveBtn').onclick = async () => {
    const amount = Number(el('rp-amount').value);
    if (!amount || amount <= 0) { await customAlert('Enter an amount greater than zero.'); return; }
    const due = balance(p);
    const over = amount > due;
    if (over && !await customConfirm(`Only ₹${fmtMoney(due)} is due, but you're recording ₹${fmtMoney(amount)}. Save anyway?`)) return;
    try {
      await api.post(`payment-collections/${p.id}/receipts/`, {
        amount, date: el('rp-date').value, mode: el('rp-mode').value, remarks: el('rp-remarks').value.trim(), confirm_over: over,
      });
    } catch (e) { await customAlert('Could not save: ' + apiErrorMessage(e)); return; }
    closeOverlay('receivedPaymentOverlay');
    await loadPayments(); redraw();
  };
  openOverlay('receivedPaymentOverlay');
}

// ---- filters (shared by the list and the history page) ----------------------------------------------------------------------
function customerOptions() {
  const seen = new Map();
  payments.forEach((p) => { if (p.customer_name) seen.set(p.customer_name, p.customer_label || p.customer_name); });
  return [...seen.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}
function filterRowHtml(ids) {
  return `
    <select id="${ids.customer}"><option value="">All customers</option>${customerOptions().map(([v, t]) => `<option value="${escapeHtml(v)}" ${filters.customer === v ? 'selected' : ''}>${escapeHtml(t)}</option>`).join('')}</select>
    <select id="${ids.branch}"><option value="">All branches</option>${state.branches.map((b) => `<option value="${escapeHtml(b.name)}" ${filters.branch === b.name ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('')}</select>
    <input type="text" id="${ids.search}" placeholder="Search customer or remarks" value="${escapeHtml(filters.search)}" style="max-width:220px;">
    <button class="btn" id="${ids.clear}">Clear filters</button>`;
}
function wireFilters(ids, redrawTables, redrawFilters) {
  el(ids.customer).addEventListener('change', (e) => { filters.customer = e.target.value; redrawTables(); });
  el(ids.branch).addEventListener('change', (e) => { filters.branch = e.target.value; redrawTables(); });
  el(ids.search).addEventListener('input', (e) => { filters.search = e.target.value; redrawTables(); });
  el(ids.clear).addEventListener('click', () => { filters = { customer: '', search: '', branch: '' }; redrawFilters(); redrawTables(); });
}

// ---- Payment Collection list -----------------------------------------------------------------------------------------------
export async function mountPayments(root) {
  seedFilters();
  mountRefView(root, 'view-payments');
  await loadPayments();
  filtersBeforeViewAll = null;
  const ids = { customer: 'fltPayCustomer', branch: 'fltPayBranch', search: 'fltPaySearch', clear: 'fltPayClear' };

  const stats = () => {
    const total = payments.reduce((s, p) => s + num(p.amount), 0);
    const pending = payments.reduce((s, p) => s + balance(p), 0);
    const collected = payments.reduce((s, p) => s + received(p), 0);
    el('paymentStatsRow').innerHTML = `
      <div class="dash-card"><div class="n">₹${fmtMoney(total)}</div><div class="l">Total Payment</div></div>
      <div class="dash-card"><div class="n">₹${fmtMoney(pending)}</div><div class="l">Pending Collection</div></div>
      <div class="dash-card"><div class="n">₹${fmtMoney(collected)}</div><div class="l">Collection Done</div></div>`;
  };
  const badge = () => {
    const n = [...el('paymentFilterRow').querySelectorAll('select, input')].filter((x) => x.value).length;
    const b = el('paymentFilterBadge'); b.textContent = n; b.style.display = n ? '' : 'none';
  };
  const table = () => {
    badge();
    const wrap = el('paymentsTableWrap');
    const list = applyFilters(payments.filter((p) => balance(p) > 0)).sort(byDateDesc);
    if (!list.length) { wrap.innerHTML = '<div class="empty"><div class="big">No payments due</div>Click "+ New Payment" to record an amount owed, or check Payment History.</div>'; return; }
    const order = state.branches.map((b) => b.name);
    const groups = new Map();
    list.forEach((p) => { const b = branchOf(p) || 'No branch'; if (!groups.has(b)) groups.set(b, []); groups.get(b).push(p); });
    const names = [...groups.keys()].sort((a, b) => { const ia = order.indexOf(a), ib = order.indexOf(b); return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib) || a.localeCompare(b); });
    wrap.innerHTML = names.map((n) => {
      const items = groups.get(n);
      const pend = items.reduce((s, p) => s + balance(p), 0);
      return `
    <div class="pay-branch-head"><span>🏢 ${escapeHtml(n)}</span><span class="pb-meta">${items.length} payment${items.length === 1 ? '' : 's'} &middot; Pending ₹${fmtMoney(pend)}</span></div>
    <div class="table-scroll" style="margin-bottom:14px;"><table class="report">
      <tr><th>Customer Name</th><th>Contact Person</th><th>Amount</th><th></th></tr>
      ${items.map((p) => `
        <tr>
          <td>${escapeHtml(p.customer_name || '—')}</td>
          <td>${contactCell(p)}</td>
          <td>₹${fmtMoney(balance(p))}</td>
          <td style="white-space:nowrap;">${rowButtons(p, true)}</td>
        </tr>`).join('')}
    </table></div>`;
    }).join('');
    wireRows(wrap, redraw);
  };
  const drawFilters = () => {
    el('paymentFilterRow').innerHTML = filterRowHtml(ids);
    wireFilters(ids, table, drawFilters);
  };
  const redraw = () => { stats(); table(); };

  stats(); drawFilters(); table();
  el('paymentNewBtn').onclick = () => navigate('paymentform', 'new');
  el('paymentHistoryBtn').onclick = () => navigate('paymenthistory');
  el('paymentFilterToggleBtn').onclick = () => { const panel = el('paymentFilterRow'); panel.style.display = panel.style.display === 'none' ? 'flex' : 'none'; };
  // One click shows every branch's payments; click again to restore the filters that were active before.
  el('paymentViewAllBtn').onclick = () => {
    if (filtersBeforeViewAll) {
      filters = filtersBeforeViewAll; filtersBeforeViewAll = null; el('paymentViewAllBtn').textContent = 'View All';
    } else {
      filtersBeforeViewAll = { ...filters }; filters = { customer: '', search: '', branch: '' }; el('paymentViewAllBtn').textContent = 'Undo View All';
    }
    el('paymentFilterRow').style.display = 'none';
    drawFilters(); table();
  };
}

// ---- New / Edit page ------------------------------------------------------------------------------------------------------------
export async function mountPaymentForm(root, sub) {
  mountRefView(root, 'view-paymentform');
  const editing = sub && sub !== 'new' ? sub : null;
  const [customers, existing] = await Promise.all([api.all('customers/'), editing ? api.get(`payment-collections/${editing}/`) : null]);
  const p = existing;
  const leave = () => { if (window.history.length > 1) window.history.back(); else navigate('payments'); };
  el('paymentFormTitle').textContent = editing ? 'Edit Payment' : 'New Payment';
  el('pay-customer').innerHTML = '<option value="">Select customer</option>' + customers.map((c) => `<option value="${c.id}">${escapeHtml(c.label || c.name)}</option>`).join('');
  el('pay-customer').value = p ? String(p.customer_id) : '';
  const fillContacts = async (customerId, selected) => {
    const contacts = customerId ? await api.all(`customers/${customerId}/contacts/`) : [];
    el('pay-contact').innerHTML = '<option value="">Select contact</option>' + contacts.map((c) => `<option value="${c.id}" ${c.id === selected ? 'selected' : ''}>${escapeHtml(c.name || 'Unnamed')} — ${escapeHtml(c.job_title || '')}</option>`).join('');
  };
  await fillContacts(p ? p.customer_id : '', p ? p.contact_id : null);
  el('pay-customer').addEventListener('change', () => fillContacts(el('pay-customer').value, null));
  el('pay-amount').value = p ? num(p.amount) : '';
  el('pay-date').value = p ? (p.date || '') : today();
  el('pay-remarks').value = p ? (p.remarks || '') : '';
  el('pay-branch').innerHTML = '<option value="">Select branch</option>' + state.branches.map((b) => `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join('');
  const own = (state.me.branch_ids || [])[0];
  el('pay-branch').value = p ? String(p.branch_id) : (own ? String(own) : '');
  el('paymentFormHint').textContent = '';
  el('paymentFormCancelBtn').onclick = leave;
  el('paymentFormBackBtn').onclick = leave;
  el('paymentFormSaveBtn').onclick = async () => {
    const hint = (t) => { el('paymentFormHint').textContent = t; };
    const customerId = el('pay-customer').value;
    if (!customerId) { hint('Select a customer.'); return; }
    const amount = el('pay-amount').value;
    if (amount === '' || Number(amount) <= 0) { hint('Enter an amount greater than zero.'); return; }
    if (!el('pay-branch').value) { hint('Select the branch this amount belongs to.'); return; }
    const body = {
      branch_id: Number(el('pay-branch').value), customer_id: Number(customerId), contact_id: el('pay-contact').value ? Number(el('pay-contact').value) : null,
      amount, date: el('pay-date').value, remarks: el('pay-remarks').value.trim(),
    };
    try {
      if (editing) await api.patch(`payment-collections/${editing}/`, { ...body, version: p.version });
      else await api.post('payment-collections/', body);
    } catch (e) { hint(apiErrorMessage(e)); return; }
    leave();
  };
}

// ---- Payment History -------------------------------------------------------------------------------------------------------------
export async function mountPaymentHistory(root) {
  seedFilters();
  mountRefView(root, 'view-paymenthistory');
  await loadPayments();
  const ids = { customer: 'phCustomer', branch: 'phBranch', search: 'phSearch', clear: 'phClear' };
  const tables = () => {
    const done = applyFilters(payments.filter((p) => balance(p) === 0 && num(p.amount) > 0)).sort(byDateDesc);
    el('paymentHistCompletedWrap').innerHTML = done.length ? `
    <div class="table-scroll"><table class="report">
      <tr><th>Customer Name</th><th>Contact Person</th><th>Amount</th><th></th></tr>
      ${done.map((p) => `
        <tr>
          <td>${escapeHtml(p.customer_name || '—')}</td>
          <td>${contactCell(p)}</td>
          <td>₹${fmtMoney(num(p.amount))}</td>
          <td style="white-space:nowrap;">${rowButtons(p, false)}</td>
        </tr>`).join('')}
    </table></div>` : '<div class="empty">No fully collected payments yet.</div>';
    wireRows(el('paymentHistCompletedWrap'), redraw);

    let rows = [];
    payments.forEach((p) => (p.receipts || []).forEach((r) => rows.push({ ...r, customer_name: p.customer_name, branch: branchOf(p) })));
    if (filters.customer) rows = rows.filter((r) => r.customer_name === filters.customer);
    if (filters.branch) rows = rows.filter((r) => r.branch === filters.branch);
    if (filters.search) { const q = filters.search.toLowerCase(); rows = rows.filter((r) => (r.customer_name || '').toLowerCase().includes(q) || (r.remarks || '').toLowerCase().includes(q)); }
    rows.sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));
    el('paymentHistTxWrap').innerHTML = rows.length ? `
    <div class="table-scroll"><table class="report">
      <tr><th>Date</th><th>Customer</th><th>Amount</th><th>Mode</th><th>Remarks</th><th>Recorded By</th></tr>
      ${rows.map((r) => `
        <tr>
          <td>${when(r.date)}</td>
          <td>${escapeHtml(r.customer_name || '—')}</td>
          <td>₹${fmtMoney(num(r.amount))}</td>
          <td>${escapeHtml(r.mode || '—')}</td>
          <td>${escapeHtml(r.remarks || '—')}</td>
          <td>${escapeHtml((r.recorded_by && r.recorded_by.full_name) || '—')}</td>
        </tr>`).join('')}
    </table></div>` : '<div class="empty">No receipts recorded yet.</div>';
  };
  const drawFilters = () => { el('paymentHistFilterRow').innerHTML = filterRowHtml(ids); wireFilters(ids, tables, drawFilters); };
  const redraw = () => tables();
  drawFilters(); tables();
  el('paymentHistBackBtn').onclick = () => navigate('payments');
}

// ---- Payment Log -----------------------------------------------------------------------------------------------------------------
export async function mountPaymentLog(root, paymentId) {
  await mountLogPage(root, {
    title: 'Payment Log',
    load: () => api.get(`payment-collections/${paymentId}/`),
    sub: (p) => `${p.customer_name || ''}${p.contact_name ? ' — ' + p.contact_name : ''} — ₹${fmtMoney(num(p.amount))}`,
    messages: (p) => p.contact_log || [],
    post: (text, callLater) => api.post(`payment-collections/${paymentId}/contact-log/`, { message: text, call_later_date: callLater || null }),
    back: () => () => { if (window.history.length > 1) window.history.back(); else navigate('payments'); },
  });
}
