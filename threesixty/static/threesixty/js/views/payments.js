// Payment Collection — tracks what a customer owes and receipts logged
// against it. Permission/scope is a documented conservative default
// (`views_payments.py`): Admin/Branch Manager/Branch Staff manage all,
// Sales Manager only their own-created records.
import { api } from '../api.js';
import { state } from '../state.js';
import { el, escapeHtml, fmtDate, fmtMoney, toast, apiErrorMessage, openModal, closeModal, confirmDialog, renderTable } from '../ui.js';

let customersCache = null;
async function getCustomers() {
  if (!customersCache) customersCache = await api.all('customers/');
  return customersCache;
}
function customerName(id, customers) { const c = customers.find((x) => x.id === id); return c ? c.name : `#${id}`; }

function openNewPaymentModal(customers, onSaved) {
  const myBranchId = (state.branches.find((b) => (state.me.branch_ids || []).includes(b.id)) || state.branches[0] || {}).id;
  openModal(`
    <h2>New payment collection</h2>
    <div class="field-row">
      <div class="field"><label>Branch</label><select id="pf-branch">${state.branches.map((b) => `<option value="${b.id}" ${b.id === myBranchId ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('')}</select></div>
      <div class="field"><label>Customer *</label><select id="pf-customer"><option value="">— select —</option>${customers.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('')}</select></div>
    </div>
    <div class="field"><label>Amount due *</label><input type="number" step="any" id="pf-amount"></div>
    <div class="modal-actions"><button class="btn" id="pf-cancel">Cancel</button><button class="btn primary" id="pf-save">Create</button></div>`, {
    onMount: (modal) => {
      modal.querySelector('#pf-cancel').onclick = closeModal;
      modal.querySelector('#pf-save').onclick = async () => {
        const customerId = modal.querySelector('#pf-customer').value;
        const amount = modal.querySelector('#pf-amount').value;
        if (!customerId || !amount) { toast('Customer and amount are required.', 'error'); return; }
        try {
          await api.post('payment-collections/', { branch_id: modal.querySelector('#pf-branch').value, customer_id: customerId, amount });
          toast('Created.', 'success');
          closeModal();
          onSaved();
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

async function openDetail(payment, customers, onChanged) {
  const render = async () => {
    const fresh = await api.get(`payment-collections/${payment.id}/`);
    return fresh;
  };
  const p = await render();
  openModal(`
    <h2>${escapeHtml(customerName(p.customer_id, customers))}</h2>
    <p class="sub">Amount due ₹${fmtMoney(p.amount)} · Collected ₹${fmtMoney(Number(p.amount) - Number(p.balance))} · Balance ₹${fmtMoney(p.balance)}</p>
    <h3 style="margin:16px 0 8px;">Receipts</h3>
    <div id="pd-receipts"></div>
    <div class="card" style="margin-top:12px;">
      <div class="field-row">
        <div class="field"><label>Amount *</label><input type="number" step="any" id="pd-amount"></div>
        <div class="field"><label>Date *</label><input type="date" id="pd-date" value="${new Date().toISOString().slice(0, 10)}"></div>
        <div class="field"><label>Mode</label><select id="pd-mode"><option>Cash</option><option>Cheque</option><option>Bank Transfer</option><option>UPI</option></select></div>
      </div>
      <div class="field"><label>Remarks</label><input id="pd-remarks"></div>
      <button class="btn primary sm" id="pd-add">Log receipt</button>
    </div>
    <div class="modal-actions"><button class="btn" id="pd-close">Close</button></div>`, {
    onMount: (modal) => {
      const renderReceipts = () => {
        modal.querySelector('#pd-receipts').innerHTML = renderTable(['Date', 'Amount', 'Mode', 'Remarks', 'By'], (p.receipts || []).map((r) => ({
          Date: fmtDate(r.date), Amount: `₹${fmtMoney(r.amount)}`, Mode: escapeHtml(r.mode), Remarks: escapeHtml(r.remarks),
          By: escapeHtml(r.recorded_by ? r.recorded_by.full_name : '—'),
        })), { empty: 'No receipts logged yet.' });
      };
      renderReceipts();
      modal.querySelector('#pd-close').onclick = closeModal;
      modal.querySelector('#pd-add').onclick = async () => {
        const amount = modal.querySelector('#pd-amount').value;
        const date = modal.querySelector('#pd-date').value;
        if (!amount || !date) { toast('Amount and date are required.', 'error'); return; }
        try {
          await api.post(`payment-collections/${p.id}/receipts/`, {
            amount, date, mode: modal.querySelector('#pd-mode').value, remarks: modal.querySelector('#pd-remarks').value.trim(),
          });
          toast('Receipt logged.', 'success');
          closeModal();
          const updated = await render();
          Object.assign(p, updated);
          onChanged();
          openDetail(updated, customers, onChanged);
        } catch (e) { toast(apiErrorMessage(e), 'error'); }
      };
    },
  });
}

async function deletePayment(payment, onDone) {
  if (!await confirmDialog('Remove this payment collection record?')) return;
  try { await api.delete(`payment-collections/${payment.id}/`); toast('Removed.', 'success'); onDone(); } catch (e) { toast(apiErrorMessage(e), 'error'); }
}

async function render(root) {
  const [payments, customers] = await Promise.all([api.all('payment-collections/'), getCustomers()]);
  payments.sort((a, b) => Number(b.balance) - Number(a.balance));
  const totalDue = payments.reduce((s, p) => s + Number(p.balance), 0);
  root.innerHTML = `
    <div class="flex-between"><h2 style="margin:0;">Payment Collection — outstanding ₹${fmtMoney(totalDue)}</h2><button class="btn primary" id="newPayBtn">+ New</button></div>
    ${renderTable(['Customer', 'Amount', 'Balance', 'Created by', ''], payments.map((p) => ({
      Customer: `<a data-open="${p.id}" style="cursor:pointer;color:var(--primary);font-weight:600;">${escapeHtml(customerName(p.customer_id, customers))}</a>`,
      Amount: `₹${fmtMoney(p.amount)}`, Balance: `₹${fmtMoney(p.balance)}`,
      'Created by': escapeHtml(p.created_by ? p.created_by.full_name : '—'),
      '': `<button class="btn sm danger" data-delete="${p.id}">Remove</button>`,
    })), { empty: 'No payment collections yet.' })}`;

  root.querySelector('#newPayBtn').onclick = () => openNewPaymentModal(customers, () => render(root));
  root.querySelectorAll('[data-open]').forEach((a) => a.onclick = () => openDetail(payments.find((p) => String(p.id) === a.dataset.open), customers, () => render(root)));
  root.querySelectorAll('[data-delete]').forEach((btn) => btn.onclick = () => deletePayment(payments.find((p) => String(p.id) === btn.dataset.delete), () => render(root)));
}

export async function mountPayments(root) {
  await render(root);
}
