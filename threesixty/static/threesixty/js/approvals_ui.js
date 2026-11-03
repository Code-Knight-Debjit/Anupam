// The "Pending edit & delete approvals" list used on the Dashboard (admin and branch manager) — same markup and
// buttons as the reference: request line, requester + time, View changes / Approve / Reject. Nothing is applied
// until someone approves (the server applies it).
import { api } from './api.js';
import { escapeHtml, fmtDateTime, openModal, closeModal, customConfirm, customAlert, apiErrorMessage } from './ui.js';

const TYPE_TITLES = { edit: 'Edit request', delete: 'Delete request', 'customer-access': 'Access request' };
// The reference shows a customer request as just the company name ("Customer " is only in the stored label).
const label = (r) => (r.customer_id && !r.contact_id && !r.document_id ? String(r.target_label || '').replace(/^Customer /, '') : r.target_label) || '—';
const show = (v) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));

export function approvalsHtml(list) {
  return list.length ? list.map((r) => `
    <div class="activity-item">
      <div>
        <div class="a-name">${TYPE_TITLES[r.type] || 'Edit request'}: ${escapeHtml(label(r))}</div>
        <div class="a-meta">${r.note ? escapeHtml(r.note) + ' &middot; ' : ''}Requested by ${escapeHtml(r.requested_by ? r.requested_by.full_name : '—')} &middot; ${fmtDateTime(r.requested_at)}</div>
      </div>
      <div style="display:flex; gap:8px;">
        ${r.type !== 'customer-access' ? `<button class="btn" style="padding:6px 12px; font-size:12px;" data-apv-view="${r.id}">${r.type === 'delete' ? 'View details' : 'View changes'}</button>` : ''}
        <button class="btn btn-primary" style="padding:6px 12px; font-size:12px;" data-apv-approve="${r.id}">Approve</button>
        <button class="btn-danger-text" data-apv-reject="${r.id}">Reject</button>
      </div>
    </div>`).join('') : '<p class="sub">Nothing waiting on your approval.</p>';
}

async function viewChanges(r, decide) {
  const res = await api.get(`approvals/${r.id}/changes/`);
  const isDelete = r.type === 'delete';
  const rows = isDelete
    ? res.changes.map((c) => `<tr><td>${escapeHtml(c.field.replace(/_/g, ' '))}</td><td>${escapeHtml(show(c.before))}</td></tr>`).join('')
    : (res.changes.length ? res.changes.map((c) => `<tr><td><b>${escapeHtml(c.field.replace(/_/g, ' '))}</b></td>
        <td style="color:var(--text-dim);text-decoration:line-through;">${escapeHtml(show(c.before))}</td>
        <td style="background:rgba(47,158,82,.12);">${escapeHtml(show(c.after))}</td></tr>`).join('')
      : '<tr><td colspan="3">No visible differences from the current record.</td></tr>');
  const head = isDelete ? '<tr><th style="width:34%;">What will be deleted</th><th>Details</th></tr>'
    : '<tr><th style="width:26%;">Field</th><th style="width:37%;">Current</th><th>Proposed</th></tr>';
  openModal(`<h2>${isDelete ? 'Delete request' : 'Edit request'} — ${escapeHtml(label(r))}</h2>
    <p class="modal-sub">Requested by ${escapeHtml(r.requested_by ? r.requested_by.full_name : '—')} · ${fmtDateTime(r.requested_at)}${r.note ? ' · ' + escapeHtml(r.note) : ''}</p>
    <div class="table-scroll"><table class="report">${head}${rows}${isDelete ? '<tr><td colspan="2" style="color:var(--danger);">Approving removes this permanently.</td></tr>' : ''}</table></div>
    <div class="modal-actions"><button class="btn" id="apvClose">Close</button><button class="btn-danger-text" id="apvReject">Reject</button><button class="btn btn-primary" id="apvApprove">Approve</button></div>`, {
    size: 'wide',
    onMount: (m) => {
      m.querySelector('#apvClose').onclick = closeModal;
      m.querySelector('#apvApprove').onclick = () => { closeModal(); decide(r.id, 'approve'); };
      m.querySelector('#apvReject').onclick = () => { closeModal(); decide(r.id, 'reject'); };
    },
  });
}

/** Wires the buttons rendered by approvalsHtml inside `root`; `onDone` re-renders the caller. */
export function wireApprovals(root, list, onDone) {
  const find = (id) => list.find((a) => String(a.id) === String(id));
  const decide = async (id, action) => {
    if (action === 'reject' && !await customConfirm('Reject this request? No changes will be made.')) return;
    try { await api.post(`approvals/${id}/${action}/`, {}); onDone(); }
    catch (e) { await customAlert(apiErrorMessage(e)); }
  };
  root.querySelectorAll('[data-apv-view]').forEach((b) => b.onclick = () => viewChanges(find(b.dataset.apvView), decide).catch((e) => customAlert(apiErrorMessage(e))));
  root.querySelectorAll('[data-apv-approve]').forEach((b) => b.onclick = () => decide(b.dataset.apvApprove, 'approve'));
  root.querySelectorAll('[data-apv-reject]').forEach((b) => b.onclick = () => decide(b.dataset.apvReject, 'reject'));
}
