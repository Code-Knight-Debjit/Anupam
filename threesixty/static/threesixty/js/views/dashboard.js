// Dashboard — full (Admin/Branch Manager) vs personal (Branch Staff/Sales
// Manager) view, ported from `renderDashboard`/`renderPersonalDashboard`
// (contact_management.html ~L6835-6960). Simplified: the mini task
// calendar is not ported (a convenience widget, not business logic).
import { api } from '../api.js';
import { state, isAdmin, isBranchManager } from '../state.js';
import { escapeHtml, fmtMoney, fmtDateTime } from '../ui.js';
import { navigate } from '../router.js';

function tile(n, label, cls, onClick) {
  return `<div class="dash-card ${cls}${n ? '' : ' zero'}" style="${onClick ? 'cursor:pointer' : ''}" data-go="${onClick || ''}">
    <div class="n">${n}</div><div class="l">${escapeHtml(label)}</div></div>`;
}

function wireTileClicks(root) {
  root.querySelectorAll('[data-go]').forEach((node) => {
    const go = node.dataset.go;
    if (!go) return;
    const [view, subtab] = go.split(':');
    node.addEventListener('click', () => navigate(view, subtab));
  });
}

async function renderApprovals() {
  const approvals = await api.all('approvals/', { status: 'Pending' });
  if (!approvals.length) return '<p class="sub">Nothing waiting on your approval.</p>';
  return approvals.map((r) => `
    <div class="flex-between" style="background:var(--surface-container-lowest);border-radius:var(--radius-md);padding:10px 14px;">
      <div>
        <div style="font-weight:600;font-size:13px;">${r.type === 'delete' ? 'Delete request' : r.type === 'customer-access' ? 'Access request' : 'Edit request'}</div>
        <div class="sub">${r.note ? escapeHtml(r.note) + ' · ' : ''}Requested by ${escapeHtml(r.requested_by ? r.requested_by.full_name : '—')} · ${fmtDateTime(r.requested_at)}</div>
      </div>
      <div style="display:flex;gap:8px;">
        <button class="btn sm primary" data-approve="${r.id}">Approve</button>
        <button class="btn sm danger" data-reject="${r.id}">Reject</button>
      </div>
    </div>`).join('');
}

function wireApprovalButtons(root, rerender) {
  root.querySelectorAll('[data-approve]').forEach((btn) => btn.addEventListener('click', async () => {
    await api.post(`approvals/${btn.dataset.approve}/approve/`, {});
    rerender();
  }));
  root.querySelectorAll('[data-reject]').forEach((btn) => btn.addEventListener('click', async () => {
    await api.post(`approvals/${btn.dataset.reject}/reject/`, {});
    rerender();
  }));
}

async function renderFullDashboard(root) {
  const [enquiries, quotations, proformas, pos, dcs, payments] = await Promise.all([
    api.all('sales-documents/', { type: 'enquiry' }), api.all('sales-documents/', { type: 'quotation' }),
    api.all('sales-documents/', { type: 'proforma' }), api.all('sales-documents/', { type: 'po' }),
    api.all('sales-documents/', { type: 'dc' }), api.all('payment-collections/'),
  ]);
  const openEnquiries = enquiries.filter((d) => (d.order_status || 'Pending') === 'Pending').length;
  const openQuotations = quotations.filter((d) => (d.order_status || 'Pending') === 'Pending').length;
  const openProformas = proformas.filter((d) => (d.order_status || 'Pending') === 'Pending').length;
  const pendingOrders = pos.filter((d) => d.order_status !== 'Completed').length;
  const pendingDCs = dcs.filter((d) => (d.items || []).some((it) => Number(it.qty) > 0)).length;
  const due = payments.filter((p) => Number(p.balance) > 0).sort((a, b) => Number(b.balance) - Number(a.balance));
  const totalDue = due.reduce((s, p) => s + Number(p.balance), 0);

  root.innerHTML = `
    <p class="sub" style="margin-bottom:16px;">Balance overview of everything — approvals, pipeline, and collections.</p>
    ${isBranchManager() ? `<div class="card" style="margin-bottom:20px;"><h3 style="margin-bottom:12px;">Pending your approval</h3><div id="dashApprovals"></div></div>` : ''}
    <div class="dash-grid" style="margin-bottom:20px;">
      ${tile(openEnquiries, 'Open enquiries', 'pipe-1', 'sales:enquiry')}
      ${tile(openQuotations, 'Open quotations', 'pipe-2', 'sales:quotation')}
      ${tile(openProformas, 'Open proforma invoices', 'pipe-3', 'sales:proforma')}
      ${tile(pendingOrders, 'Pending PO', 'pipe-4', 'sales:po')}
      ${tile(pendingDCs, 'Delivery challans pending', 'pipe-5', 'sales:dc')}
    </div>
    <div class="card">
      <h3 style="margin-bottom:12px;">Payment collection — outstanding ₹${fmtMoney(totalDue)}</h3>
      <div id="dashPayments"></div>
    </div>`;
  wireTileClicks(root);

  const payBox = root.querySelector('#dashPayments');
  payBox.innerHTML = due.length ? due.slice(0, 8).map((p) => `
    <div class="flex-between" style="margin-bottom:0;padding:6px 0;">
      <span>${escapeHtml(p.customer_id ? 'Customer #' + p.customer_id : '—')}</span>
      <strong>₹${fmtMoney(p.balance)}</strong>
    </div>`).join('') : '<p class="sub">No pending collections.</p>';

  if (isBranchManager()) {
    const approvalsBox = root.querySelector('#dashApprovals');
    const refresh = async () => { approvalsBox.innerHTML = await renderApprovals(); wireApprovalButtons(approvalsBox, refresh); };
    await refresh();
  }
}

async function renderPersonalDashboard(root) {
  const uid = state.me.user_id;
  const [tasks, calls, enquiries, quotations, proformas, pos, dcs, payments] = await Promise.all([
    api.all('tasks/', { status: 'Open' }),
    api.all('call-assignments/'),
    api.all('sales-documents/', { type: 'enquiry' }), api.all('sales-documents/', { type: 'quotation' }),
    api.all('sales-documents/', { type: 'proforma' }), api.all('sales-documents/', { type: 'po' }),
    api.all('sales-documents/', { type: 'dc' }), api.all('payment-collections/'),
  ]);
  const myTasks = tasks.filter((t) => t.assigned_to.id === uid || (t.joint_with_user_ids || []).includes(uid)).length;
  const myCalling = calls.filter((a) => a.assigned_to && a.assigned_to.id === uid && a.status !== 'Called').length;
  const myDue = payments.filter((p) => Number(p.balance) > 0).length;
  const mine = (d) => d.created_by && d.created_by.id === uid;

  root.innerHTML = `
    <p class="sub" style="margin-bottom:16px;">Your own pending work and activity at a glance.</p>
    ${isBranchManager() ? `<div class="card" style="margin-bottom:20px;"><h3 style="margin-bottom:12px;">Pending your approval</h3><div id="dashApprovals"></div></div>` : ''}
    <div style="margin-bottom:10px;font-weight:600;font-size:13px;color:var(--secondary);">NEEDS YOUR ATTENTION</div>
    <div class="dash-grid" style="margin-bottom:20px;">
      ${tile(myTasks, 'Tasks pending', 'pipe-1', 'tasks')}
      ${tile(myCalling, 'Outreach calls pending', 'pipe-4', 'callinglist')}
      ${tile(myDue, 'Payments to collect', 'alert', 'payments')}
    </div>
    <div style="margin-bottom:10px;font-weight:600;font-size:13px;color:var(--secondary);">MY SALES PIPELINE</div>
    <div class="dash-grid">
      ${tile(enquiries.filter((d) => mine(d) && (d.order_status || 'Pending') === 'Pending').length, 'Enquiries pending', 'pipe-1', 'sales:enquiry')}
      ${tile(quotations.filter((d) => mine(d) && (d.order_status || 'Pending') === 'Pending').length, 'Quotations pending', 'pipe-2', 'sales:quotation')}
      ${tile(proformas.filter((d) => mine(d) && (d.order_status || 'Pending') === 'Pending').length, 'Proforma invoices pending', 'pipe-3', 'sales:proforma')}
      ${tile(pos.filter((d) => mine(d) && d.order_status !== 'Completed').length, 'POs pending', 'pipe-4', 'sales:po')}
      ${tile(dcs.filter((d) => mine(d) && (d.items || []).some((it) => Number(it.qty) > 0)).length, 'Delivery challans pending', 'pipe-5', 'sales:dc')}
    </div>`;
  wireTileClicks(root);
  if (isBranchManager()) {
    const approvalsBox = root.querySelector('#dashApprovals');
    const refresh = async () => { approvalsBox.innerHTML = await renderApprovals(); wireApprovalButtons(approvalsBox, refresh); };
    await refresh();
  }
}

export async function mountDashboard(root) {
  if (!state.flags.can_see_dashboard) { navigate('customers'); return; }
  if (state.flags.uses_personal_dashboard) await renderPersonalDashboard(root);
  else await renderFullDashboard(root);
}
