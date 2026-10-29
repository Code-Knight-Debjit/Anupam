// Approvals — Admin / Branch Manager decide; everyone else follows their own requests.
// "View" shows exactly what changes (before → after). Nothing is applied until approved.
import { api } from '../api.js';
import { state } from '../state.js';
import { escapeHtml, fmtDateTime, toast, apiErrorMessage, openModal, closeModal, confirmDialog, renderTable, badge } from '../ui.js';

const TYPE_LABELS = { edit: 'Edit', delete: 'Delete', 'customer-access': 'Access request' };
const show = (v) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));

async function viewChanges(approval) {
  const res = await api.get(`approvals/${approval.id}/changes/`);
  const rows = res.changes.map((c) => ({ Field: escapeHtml(c.field.replace(/_/g, ' ')), Before: escapeHtml(show(c.before)), After: escapeHtml(show(c.after)) }));
  openModal(`<h2>${escapeHtml(TYPE_LABELS[approval.type] || approval.type)} — ${escapeHtml(approval.target_label)}</h2>
    <p class="sub">Requested by ${escapeHtml(approval.requested_by ? approval.requested_by.full_name : '—')} · ${fmtDateTime(approval.requested_at)}</p>
    ${approval.type === 'customer-access' ? '<p>Approving adds this person to the customer’s assigned people.</p>'
      : renderTable(['Field', approval.type === 'delete' ? 'Will be removed' : 'Before', approval.type === 'delete' ? '' : 'After'], rows, { empty: 'No field differs from the current record.' })}
    <div class="modal-actions"><button class="btn" id="ap-close">Close</button></div>`, { onMount: (m) => { m.querySelector('#ap-close').onclick = closeModal; } });
}

async function decide(approval, action, onDone) {
  const text = action === 'approve' ? 'Approve this request? The change is applied immediately.' : 'Reject this request? Nothing will change.';
  if (!await confirmDialog(text)) return;
  try { await api.post(`approvals/${approval.id}/${action}/`, {}); toast(action === 'approve' ? 'Approved and applied.' : 'Rejected.', 'success'); onDone(); }
  catch (e) { toast(apiErrorMessage(e), 'error'); }
}

let tab = 'pending';
export async function mountApprovals(root) {
  const canDecide = !!state.flags.is_approver;
  const list = await api.all('approvals/', tab === 'pending' ? { status: 'pending' } : {});
  const rows = (tab === 'pending' ? list : list.filter((a) => a.status !== 'pending')).map((a) => ({
    Request: escapeHtml(TYPE_LABELS[a.type] || a.type), Record: escapeHtml(a.target_label || '—'),
    'Requested by': escapeHtml(a.requested_by ? a.requested_by.full_name : '—'), When: fmtDateTime(a.requested_at), Status: badge(a.status),
    '': `<button class="btn sm" data-view="${a.id}">View</button>` + (canDecide && a.status === 'pending'
      ? ` <button class="btn sm primary" data-approve="${a.id}">Approve</button> <button class="btn sm danger" data-reject="${a.id}">Reject</button>` : ''),
  }));
  root.innerHTML = `<h2 style="margin-top:0;">${canDecide ? 'Approvals' : 'My requests'}</h2>
    <div class="tabbar"><button data-tab="pending" class="${tab === 'pending' ? 'active' : ''}">Pending</button><button data-tab="done" class="${tab === 'done' ? 'active' : ''}">Decided</button></div>
    ${renderTable(['Request', 'Record', 'Requested by', 'When', 'Status', ''], rows, { empty: tab === 'pending' ? 'Nothing waiting.' : 'No decided requests yet.' })}`;
  const find = (id) => list.find((a) => String(a.id) === String(id));
  root.querySelectorAll('[data-tab]').forEach((b) => b.onclick = () => { tab = b.dataset.tab; mountApprovals(root); });
  root.querySelectorAll('[data-view]').forEach((b) => b.onclick = () => viewChanges(find(b.dataset.view)).catch((e) => toast(apiErrorMessage(e), 'error')));
  root.querySelectorAll('[data-approve]').forEach((b) => b.onclick = () => decide(find(b.dataset.approve), 'approve', () => mountApprovals(root)));
  root.querySelectorAll('[data-reject]').forEach((b) => b.onclick = () => decide(find(b.dataset.reject), 'reject', () => mountApprovals(root)));
}
