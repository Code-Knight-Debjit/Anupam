// The Sales sub-pages of the reference: the Contact Log (chat-style, per document), the document overview dialog, and the
// history pages (Completed & Regretted enquiries, Win / Lose quotations and proformas, DC history, Sales Order history).
import { api } from '../api.js';
import { state, isSalesManager } from '../state.js';
import { navigate } from '../router.js';
import { el, escapeHtml, fmtMoney, customAlert, customConfirm, apiErrorMessage, exportRowsToExcel, exportRowsToPdf, printRowsTable } from '../ui.js';
import { mountRefView, useOverlays, openOverlay, closeOverlay, fmtD } from '../customer_common.js';
import { docPdf, docPrint, docPreview } from './sales_legacy.js';

const num = (v) => Number(v) || 0;
const docValue = (d) => num(d.total_amount) || (d.items || []).reduce((s, i) => s + num(i.value), 0) || num(d.quotation_value);
const customerName = (d) => d.customer_name || d.customer_label || '—';
const LABEL = { enquiry: 'Enquiry', quotation: 'Quotation', proforma: 'Proforma Invoice', dc: 'Delivery Challan', po: 'Sales Order' };
const back = (fallback) => () => { if (window.history.length > 1) window.history.back(); else navigate(...fallback); };

// ---- Contact Log -------------------------------------------------------------------------------------------------------------------
export async function mountContactLog(root, docId) {
  await mountLogPage(root, {
    title: 'Contact Log',
    load: () => api.get(`sales-documents/${docId}/`),
    sub: (doc) => `${doc.doc_number} — ${customerName(doc)}${doc.contact_name ? ' — ' + doc.contact_name : ''}`,
    messages: (doc) => doc.call_log || [],
    post: (text, callLater) => api.post(`sales-documents/${docId}/calls/`, { message: text, call_later_date: callLater || null }),
    back: (doc) => back(['sales', doc.type === 'dc' ? 'dc' : doc.type]),
  });
}

// The chat-style log page the reference shares between a document's Contact Log and a payment's Payment Log.
export async function mountLogPage(root, cfg) {
  mountRefView(root, 'view-contactlog');
  let doc = await cfg.load();
  const draw = () => {
    el('contactLogTitle').textContent = cfg.title;
    el('contactLogSub').textContent = cfg.sub(doc);
    const msgs = cfg.messages(doc);
    const wrap = el('contactLogMessages');
    wrap.innerHTML = msgs.length ? msgs.map((m) => `
      <div class="cl-message">
        <div class="cl-meta"><span class="cl-user">${escapeHtml((m.user && m.user.full_name) || 'Unknown')}</span><span>${m.timestamp ? new Date(m.timestamp).toLocaleString('en-IN') : ''}</span></div>
        <div class="cl-text">${escapeHtml(m.message || '')}</div>
        ${m.call_later_date ? `<div class="cl-followup">&#128337; Call back on ${fmtD(m.call_later_date)}</div>` : ''}
      </div>`).join('') : '<p class="sub" style="align-self:center;">No messages yet. Log an update after your next call.</p>';
    wrap.scrollTop = wrap.scrollHeight;
  };
  const send = async (text, callLater) => {
    if (!text) return;
    try { await cfg.post(text, callLater); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
    doc = await cfg.load(); draw();
  };
  el('contactLogInput').value = ''; el('clCallLaterPanel').style.display = 'none';
  draw();
  el('contactLogSendBtn').onclick = async () => { const t = el('contactLogInput').value.trim(); if (!t) return; await send(t); el('contactLogInput').value = ''; };
  el('contactLogInput').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); el('contactLogSendBtn').click(); } });
  document.querySelectorAll('.cl-suggestion-chip[data-suggestion]').forEach((b) => { b.onclick = () => send(b.dataset.suggestion); });
  el('clSuggestCallLater').onclick = () => { el('clCallLaterPanel').style.display = 'flex'; el('clCallLaterDate').value = new Date().toISOString().slice(0, 10); };
  el('clCallLaterCancelBtn').onclick = () => { el('clCallLaterPanel').style.display = 'none'; };
  el('clCallLaterSendBtn').onclick = async () => {
    const d = el('clCallLaterDate').value; if (!d) { await customAlert('Pick a date first.'); return; }
    await send('Call me later', d); el('clCallLaterPanel').style.display = 'none';
  };
  el('contactLogBackBtn').onclick = cfg.back(doc);
}

// ---- document overview dialog ----------------------------------------------------------------------------------------------------------
export async function openDocView(docId, onChange) {
  useOverlays('salesDocViewOverlay');
  let doc;
  try { doc = await api.get(`sales-documents/${docId}/`); } catch (e) { await customAlert(apiErrorMessage(e)); return; }
  const t = doc.type, label = LABEL[t] || 'Document';
  const show = (id, on) => { el(id).style.display = on ? 'block' : 'none'; };
  el('salesDocViewTitle').textContent = `${label} Overview`;
  el('salesDocViewSub').textContent = `${doc.doc_number} — ${doc.date ? fmtD(doc.date) : ''}`;
  el('sdvCustomer').textContent = customerName(doc); el('sdvContact').textContent = doc.contact_name || '—'; el('sdvBranch').textContent = doc.branch_name || '—';
  const hideAddedBy = t === 'quotation';
  show('sdvAddedByWrap', !hideAddedBy); if (!hideAddedBy) el('sdvAddedBy').textContent = (doc.created_by && doc.created_by.full_name) || '—';
  show('sdvSourceWrap', t === 'enquiry'); if (t === 'enquiry') { el('sdvSourceLabel').textContent = 'Source of Enquiry'; el('sdvSource').textContent = doc.source || '—'; }
  const hasStatus = t !== 'dc';
  show('sdvStatusWrap', hasStatus); if (hasStatus) el('sdvStatus').textContent = doc.order_status || 'Pending';
  show('sdvVehicleWrap', t === 'dc'); show('sdvTransportWrap', t === 'dc');
  if (t === 'dc') { el('sdvVehicle').textContent = doc.vehicle || '—'; el('sdvTransport').textContent = doc.transport || '—'; }
  const meta = t === 'quotation' || t === 'proforma';
  show('sdvSalesPersonWrap', meta); show('sdvValidTillWrap', t === 'quotation'); show('sdvRefWrap', meta); show('sdvPaymentTermsWrap', meta);
  if (meta) {
    el('sdvSalesPerson').textContent = doc.sales_person_name || '—'; el('sdvValidTill').textContent = doc.valid_till ? fmtD(doc.valid_till) : '—';
    el('sdvRef').textContent = [doc.ref_no || '', doc.ref_date ? fmtD(doc.ref_date) : ''].filter(Boolean).join(' · ') || '—'; el('sdvPaymentTerms').textContent = doc.payment_terms || '—';
  }
  el('sdvRemarks').textContent = doc.remarks || '—'; el('sdvRemarks').style.whiteSpace = 'pre-wrap';
  const hasItems = t !== 'enquiry';
  show('sdvItemsWrap', hasItems);
  if (hasItems) {
    const m = (v) => '₹' + fmtMoney(v);
    if (t === 'dc') {
      el('sdvItemsHead').innerHTML = '<th>Item Name</th><th>DC Qty</th><th>Inv Qty</th><th>Balance Qty</th><th>Rate</th><th>Amount</th>';
      el('sdvItems').innerHTML = doc.items.map((i) => `<tr><td>${escapeHtml(i.item_name || '—')}</td><td>${i.qty}</td><td>${i.invoiced}</td><td>${i.balance}</td><td>${m(i.rate)}</td><td>${m(i.value)}</td></tr>`).join('') + `<tr><td colspan="5" style="text-align:right; font-weight:600;">Total</td><td style="font-weight:600;">${m(docValue(doc))}</td></tr>`;
    } else if (t === 'po') {
      el('sdvItemsHead').innerHTML = '<th>Item Name</th><th>Make</th><th>Ordered Qty</th><th>Supplied</th><th>Pending</th><th>Rate</th><th>Value</th>';
      el('sdvItems').innerHTML = doc.items.map((i) => `<tr><td>${escapeHtml(i.item_name || '—')}</td><td>${escapeHtml(i.make || '—')}</td><td>${i.qty}</td><td>${i.supplied}</td><td>${i.pending}</td><td>${m(i.rate)}</td><td>${m(i.value)}</td></tr>`).join('') + `<tr><td colspan="6" style="text-align:right; font-weight:600;">Total</td><td style="font-weight:600;">${m(docValue(doc))}</td></tr>`;
    } else {
      el('sdvItemsHead').innerHTML = '<th>Item Name</th><th>Qty</th><th>Unit</th><th>Rate</th><th>Discount %</th><th>Tax %</th><th>Amount</th>';
      el('sdvItems').innerHTML = doc.items.map((i) => `<tr><td style="white-space:pre-wrap;">${escapeHtml(i.item_name || '—')}</td><td>${i.qty}</td><td>${escapeHtml(i.unit || '—')}</td><td>${m(i.rate)}</td><td>${i.discount || 0}%</td><td>${i.tax || 0}%</td><td>${m(i.value)}</td></tr>`).join('')
        + (meta ? `<tr><td colspan="6" style="text-align:right;">Sub Total</td><td>${m(doc.sub_total)}</td></tr><tr><td colspan="6" style="text-align:right;">Packing Charges</td><td>${m(doc.packing_charges)}</td></tr><tr><td colspan="6" style="text-align:right;">Freight Charges</td><td>${m(doc.freight_charges)}</td></tr><tr><td colspan="6" style="text-align:right;">Other Charges</td><td>${m(doc.other_charges)}</td></tr><tr><td colspan="6" style="text-align:right; font-weight:600;">Total Amount</td><td style="font-weight:600;">${m(docValue(doc))}</td></tr>`
          : `<tr><td colspan="6" style="text-align:right; font-weight:600;">Total</td><td style="font-weight:600;">${m(docValue(doc))}</td></tr>`);
    }
  }
  const printable = ['quotation', 'dc', 'proforma'].includes(t);
  ['sdvPdfBtn', 'sdvPrintBtn', 'sdvPreviewBtn'].forEach((id) => { el(id).style.display = printable ? 'inline-flex' : 'none'; });
  el('sdvPdfBtn').onclick = () => docPdf(doc);
  el('sdvPrintBtn').onclick = () => docPrint(doc);
  el('sdvPreviewBtn').onclick = () => docPreview(doc);
  const canClone = ['quotation', 'proforma', 'dc'].includes(t) && !(isSalesManager() && t === 'quotation');
  el('sdvCloneBtn').style.display = canClone ? 'inline-flex' : 'none';
  el('sdvCloneBtn').onclick = () => { closeOverlay('salesDocViewOverlay'); navigate('salesform', t, 'new', doc.id); };
  // Call details
  const log = [...(doc.call_log || [])].sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));
  const nextCb = doc.call_later_date; const today = new Date(); today.setHours(0, 0, 0, 0);
  const cbLate = nextCb && new Date(nextCb) < today;
  const fmtDT = (d) => (d ? new Date(d).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—');
  const fmtDS = (d) => (d ? new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—');
  el('sdvCallStats').innerHTML = `<div class="sdv-cs"><div class="n">${log.length}</div><div class="l">Call log entries</div></div>
    <div class="sdv-cs"><div class="n sm">${log.length ? fmtDS(log[0].timestamp) : '—'}</div><div class="l">Last contact</div></div>
    <div class="sdv-cs ${cbLate ? 'late' : (nextCb ? 'next' : '')}"><div class="n sm">${nextCb ? fmtDS(nextCb) : '—'}</div><div class="l">${cbLate ? 'Call-back overdue' : 'Next call-back'}</div></div>`;
  el('sdvCallList').innerHTML = log.length ? log.map((m) => `<div class="sdv-call"><div class="sdv-call-top"><span class="who">${escapeHtml((m.user && m.user.full_name) || 'Unknown')}</span><span class="when">${fmtDT(m.timestamp)}</span></div><div class="sdv-call-text">${escapeHtml(m.message || '')}</div>${m.call_later_date ? `<span class="sdv-cb">🕑 Call back on ${fmtDS(m.call_later_date)}</span>` : ''}</div>`).join('') : '<p class="sub" style="margin:4px 0 8px;">No calls logged for this document yet. Use “Call Log” to add one.</p>';
  el('sdvContactCalls').innerHTML = '';
  show('sdvCallWrap', true);
  el('sdvCallLogBtn').onclick = () => { closeOverlay('salesDocViewOverlay'); navigate('contactlog', doc.id); };
  const st = el('sdvHeroStatus'); const stText = hasStatus ? (doc.order_status || 'Pending') : '';
  st.textContent = stText; st.style.display = stText ? '' : 'none'; st.dataset.s = stText; el('sdvCallWrap').dataset.type = t;
  // Schedule a follow-up as a task
  el('sdvSchDate').value = new Date().toISOString().slice(0, 10);
  el('sdvSchWho').innerHTML = state.employees.map((e) => `<option value="${e.user_id}"${e.user_id === state.me.user_id ? ' selected' : ''}>${escapeHtml(e.full_name)}</option>`).join('');
  el('sdvSchNote').value = '';
  el('sdvSchBtn').onclick = async () => {
    try { await api.post(`sales-documents/${doc.id}/schedule/`, { kind: el('sdvSchKind') ? el('sdvSchKind').value : 'Visit', due_date: el('sdvSchDate').value, assigned_to_id: Number(el('sdvSchWho').value) }); }
    catch (e) { await customAlert(apiErrorMessage(e)); return; }
    await customAlert('Scheduled — it is in the Task panel.');
  };
  const vaWrap = el('sdvVAWrap'); if (vaWrap) vaWrap.style.display = 'none';
  const closeBtn = document.querySelector('#salesDocViewOverlay [id$="CloseBtn"], #salesDocViewOverlay #sdvCloseBtn');
  if (closeBtn) closeBtn.onclick = () => closeOverlay('salesDocViewOverlay');
  openOverlay('salesDocViewOverlay');
}

// ---- history pages ---------------------------------------------------------------------------------------------------------------------------
const COLS = {
  enquiry: ['Enquiry No. / Date / Branch / Added by', 'Customer Name', 'Contact Person', 'Status'],
  quotation: ['Quotation No. / Date / Branch / Added by', 'Company', 'Contact', 'Quotation Value', 'Order Status', 'Order Value / Reason'],
  proforma: ['PI No. / Date / Branch / Added by', 'Company', 'Contact', 'Invoice Value', 'Order Status', 'Order Value / Reason'],
};
const stacked = (d) => `<div>${escapeHtml(d.doc_number || '—')}</div><div style="font-size:11px; color:var(--text-faint); margin-top:2px;">${d.date ? fmtD(d.date) : '—'}</div><div style="font-size:11px; color:var(--text-faint); margin-top:1px;">${escapeHtml(d.branch_name || '—')}</div><div style="font-size:11px; color:var(--text-faint); margin-top:1px;">Added by: ${escapeHtml((d.created_by && d.created_by.full_name) || '—')}</div>`;
function table(cols, rows, emptyText) {
  return rows.length ? `<div class="table-scroll"><table class="report"><tr>${cols.map((c) => `<th>${c}</th>`).join('')}<th></th></tr>${rows.join('')}</table></div>` : `<div class="empty">${emptyText}</div>`;
}

function historyPage(kind) {
  const cfg = {
    enqhistory: { view: 'view-enqhistory', type: 'enquiry', backTo: ['sales', 'enquiry'], back: 'enqHistBackBtn', filter: 'enqHistFilterRow', wrap: ['enqHistoryWrap'], ex: 'enqHist', title: 'Completed & Regretted Enquiries' },
    quotationhistory: { view: 'view-quotationhistory', type: 'quotation', backTo: ['sales', 'quotation'], back: 'quotHistBackBtn', filter: 'quotHistFilterRow', wrap: ['quotHistoryWinWrap', 'quotHistoryLoseWrap'], ex: 'quotHist', title: 'Win and Lose Quotations' },
    proformahistory: { view: 'view-proformahistory', type: 'proforma', backTo: ['sales', 'proforma'], back: 'pfHistBackBtn', filter: 'pfHistFilterRow', wrap: ['pfHistoryWinWrap', 'pfHistoryLoseWrap'], ex: 'pfHist', title: 'Win and Lose Proforma Invoices' },
  }[kind];
  return async function mount(root) {
    mountRefView(root, cfg.view);
    const docs = (await api.all('sales-documents/', { type: cfg.type })).filter((d) => (d.order_status || 'Pending') !== 'Pending');
    let f = { customer: '', branch: '' };
    const rowHtml = (d) => {
      if (cfg.type === 'enquiry') return `<tr><td style="white-space:nowrap;">${stacked(d)}</td><td>${escapeHtml(customerName(d))}</td><td>${escapeHtml(d.contact_name || '—')}</td><td>${escapeHtml(d.order_status)}</td><td style="white-space:nowrap;"><button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-view="${d.id}">View</button></td></tr>`;
      const outcome = d.order_status === 'Win' ? '₹' + fmtMoney(d.order_value !== null && d.order_value !== undefined ? d.order_value : docValue(d)) : escapeHtml(d.lost_reason || '—');
      return `<tr><td style="white-space:nowrap;">${stacked(d)}</td><td>${escapeHtml(customerName(d))}</td><td>${escapeHtml(d.contact_name || '—')}</td><td>₹${fmtMoney(docValue(d))}</td><td>${escapeHtml(d.order_status)}</td><td>${outcome}</td><td style="white-space:nowrap;"><button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-view="${d.id}">View</button></td></tr>`;
    };
    const filtered = () => docs.filter((d) => (!f.customer || customerName(d) === f.customer) && (!f.branch || d.branch_name === f.branch));
    const draw = () => {
      const list = filtered();
      if (cfg.type === 'enquiry') el(cfg.wrap[0]).innerHTML = table(COLS.enquiry, list.map(rowHtml), 'No completed or regretted enquiries yet.');
      else {
        el(cfg.wrap[0]).innerHTML = table(COLS[cfg.type], list.filter((d) => d.order_status === 'Win').map(rowHtml), `No ${cfg.type === 'quotation' ? 'won quotations' : 'won proforma invoices'} yet.`);
        el(cfg.wrap[1]).innerHTML = table(COLS[cfg.type], list.filter((d) => d.order_status === 'Lose').map(rowHtml), `No ${cfg.type === 'quotation' ? 'lost quotations' : 'lost proforma invoices'} yet.`);
      }
      cfg.wrap.forEach((w) => el(w).querySelectorAll('[data-view]').forEach((b) => b.onclick = () => openDocView(b.dataset.view, draw)));
    };
    const customers = [...new Set(docs.map(customerName))].sort();
    el(cfg.filter).innerHTML = `<select id="hfCustomer"><option value="">All customers</option>${customers.map((c) => `<option>${escapeHtml(c)}</option>`).join('')}</select><select id="hfBranch"><option value="">All branches</option>${state.branches.map((b) => `<option>${escapeHtml(b.name)}</option>`).join('')}</select><button class="btn" id="hfClear">Clear filters</button>`;
    el('hfCustomer').onchange = (e) => { f.customer = e.target.value; draw(); }; el('hfBranch').onchange = (e) => { f.branch = e.target.value; draw(); };
    el('hfClear').onclick = () => { f = { customer: '', branch: '' }; el('hfCustomer').value = ''; el('hfBranch').value = ''; draw(); };
    // The columns, sheet names and file names of the reference's exports.
    const money = (v) => fmtMoney(num(v));
    const lastOn = (d) => (d.last_contact_on ? new Date(d.last_contact_on).toLocaleString('en-IN') : '');
    const laterOn = (d) => (d.call_later_date ? new Date(d.call_later_date).toLocaleDateString('en-IN') : '');
    const rows = () => filtered().map((d) => (cfg.type === 'enquiry'
      ? { 'Enquiry No.': d.doc_number || '', Date: d.date || '', 'Customer Name': customerName(d), 'Contact Person': d.contact_name || '', 'Added by': (d.created_by && d.created_by.full_name) || '', Status: d.order_status || '' }
      : { [cfg.type === 'quotation' ? 'Quotation No' : 'Proforma Invoice No']: d.doc_number, Date: d.date || '', Company: customerName(d), Contact: d.contact_name || '',
        [cfg.type === 'quotation' ? 'Quotation Value' : 'Invoice Value']: money(docValue(d)), 'Order Status': d.order_status || '',
        'Order Value': d.order_status === 'Win' ? money(d.order_value || 0) : '', 'Lost Reason': d.order_status === 'Lose' ? (d.lost_reason || '') : '', 'Last Contact On': lastOn(d), 'Call Me Later': laterOn(d) }));
    const sheet = { enquiry: 'Enquiry History', quotation: 'Quotation History', proforma: 'Proforma Invoice History' }[cfg.type];
    el(cfg.ex + 'ExcelBtn').onclick = () => exportRowsToExcel(rows(), 'anupam360-' + cfg.type + '-history', sheet);
    el(cfg.ex + 'PdfBtn').onclick = () => exportRowsToPdf(rows(), 'Anupam 360 — ' + cfg.title, 'anupam360-' + cfg.type + '-history');
    el(cfg.ex + 'PrintBtn').onclick = () => printRowsTable(rows(), 'Anupam 360 — ' + cfg.title);
    el(cfg.back).onclick = () => navigate(...cfg.backTo);
    draw();
  };
}
export const mountEnqHistory = historyPage('enqhistory');
export const mountQuotationHistory = historyPage('quotationhistory');
export const mountProformaHistory = historyPage('proformahistory');

// ---- Delivery Challan history -----------------------------------------------------------------------------------------------------------------------------
export async function mountDcHistory(root) {
  mountRefView(root, 'view-dchistory');
  const { openInvoiceDone } = await import('./sales_dialogs.js');
  const docs = await api.all('sales-documents/', { type: 'dc' });
  let f = { customer: '', itemName: '' };
  const fmtCell = (d) => `<div><span>${escapeHtml(d.contact_name || '—')}</span></div>`;
  const draw = () => {
    const q = f.itemName.toLowerCase();
    const matchDoc = (d, it) => (!f.customer || customerName(d) === f.customer) && (!q || (it.item_name || '').toLowerCase().includes(q) || (d.doc_number || '').toLowerCase().includes(q));
    const done = [], tx = [];
    docs.forEach((d) => d.items.forEach((it) => {
      if (!matchDoc(d, it)) return;
      if (num(it.balance) === 0 && num(it.qty) > 0) done.push({ d, it });
      (it.invoice_log || []).forEach((l) => tx.push({ d, it, l }));
    }));
    done.sort((a, b) => new Date(b.d.date || 0) - new Date(a.d.date || 0));
    tx.sort((a, b) => new Date(b.l.bill_date || 0) - new Date(a.l.bill_date || 0));
    el('dcHistoryCompletedWrap').innerHTML = done.length ? `<div class="table-scroll"><table class="report"><tr><th>DC No.</th><th>Date</th><th>Customer</th><th>Contact</th><th>Item Name</th><th>DC Qty</th><th>Inv Qty</th><th></th></tr>${done.map(({ d, it }) => `<tr><td>${escapeHtml(d.doc_number)}</td><td>${d.date ? fmtD(d.date) : '—'}</td><td>${escapeHtml(customerName(d))}</td><td>${fmtCell(d)}</td><td>${escapeHtml(it.item_name || '—')}</td><td>${num(it.qty)}</td><td>${num(it.invoiced)}</td><td style="white-space:nowrap;">
      <button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-act="view" data-id="${d.id}">View</button><button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-act="print" data-id="${d.id}">Print</button><button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-act="pdf" data-id="${d.id}">PDF</button><button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-act="calllog" data-id="${d.id}">Call Log</button><button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-act="edit" data-id="${d.id}">Edit</button></td></tr>`).join('')}</table></div>` : '<div class="empty">No fully invoiced items yet.</div>';
    el('dcHistoryTxWrap').innerHTML = tx.length ? `<div class="table-scroll"><table class="report"><tr><th>Bill Date</th><th>Bill Number</th><th>DC No.</th><th>Customer</th><th>Item Name</th><th>Qty Invoiced</th><th>Recorded By</th></tr>${tx.map(({ d, it, l }) => `<tr><td>${l.bill_date ? fmtD(l.bill_date) : '—'}</td><td>${escapeHtml(l.bill_number || '—')}</td><td>${escapeHtml(d.doc_number || '—')}</td><td>${escapeHtml(customerName(d))}</td><td>${escapeHtml(it.item_name || '—')}</td><td>${num(l.qty_invoiced)}</td><td>${escapeHtml((l.recorded_by && l.recorded_by.full_name) || '—')}</td></tr>`).join('')}</table></div>` : '<div class="empty">No invoice transactions recorded yet.</div>';
    document.querySelectorAll('#dcHistoryCompletedWrap [data-act]').forEach((b) => b.onclick = () => {
      const d = docs.find((x) => String(x.id) === b.dataset.id), a = b.dataset.act;
      if (a === 'view') openDocView(d.id, draw); else if (a === 'print') docPrint(d); else if (a === 'pdf') docPdf(d);
      else if (a === 'calllog') navigate('contactlog', d.id); else if (a === 'edit') navigate('salesform', 'dc', d.id);
    });
  };
  const customers = [...new Set(docs.map(customerName))].sort();
  el('dcHistFilterRow').innerHTML = `<select id="dchCustomer"><option value="">All customers</option>${customers.map((c) => `<option>${escapeHtml(c)}</option>`).join('')}</select><input type="text" id="dchItem" placeholder="Item name or DC No." style="max-width:200px;"><button class="btn" id="dchClear">Clear filters</button>`;
  el('dchCustomer').onchange = (e) => { f.customer = e.target.value; draw(); }; el('dchItem').oninput = (e) => { f.itemName = e.target.value; draw(); };
  el('dchClear').onclick = () => { f = { customer: '', itemName: '' }; el('dchCustomer').value = ''; el('dchItem').value = ''; draw(); };
  el('dcHistBackBtn').onclick = () => navigate('sales', 'dc');
  draw();
}

// ---- Sales Order history ------------------------------------------------------------------------------------------------------------------------------------
export async function mountPoHistory(root) {
  mountRefView(root, 'view-pohistory');
  const { openSupply } = await import('./sales_dialogs.js');
  const { deleteDoc } = await import('./sales_legacy.js');
  const docs = await api.all('sales-documents/', { type: 'po' });
  const fc = { customer: '', ponumber: '', date: '', itemName: '', make: '' }, ft = { customer: '', ponumber: '', itemName: '', date: '' };
  const has = (v, q) => (v || '').toLowerCase().includes((q || '').toLowerCase());
  const draw = async () => {
    const completed = [];
    docs.filter((d) => d.order_status === 'Completed').forEach((d) => d.items.forEach((it) => completed.push({ d, it })));
    const rows = completed.filter(({ d, it }) => (!fc.customer || customerName(d) === fc.customer) && (!fc.ponumber || has(d.doc_number, fc.ponumber)) && (!fc.date || d.date === fc.date) && (!fc.itemName || has(it.item_name, fc.itemName)) && (!fc.make || has(it.make, fc.make)))
      .sort((a, b) => new Date(b.d.date || 0) - new Date(a.d.date || 0));
    el('poHistoryCompletedWrap').innerHTML = rows.length ? `<div class="table-scroll"><table class="report"><tr><th>S.No.</th><th>Customer Name</th><th>PO No.</th><th>Date</th><th>Item Name</th><th>Make</th><th>Ordered Qty</th><th>Supplied Qty</th><th>Rate</th><th>Discount %</th><th>Amount</th><th>Value</th><th></th></tr>${rows.map(({ d, it }, i) => { const unit = num(it.rate) * (1 - num(it.discount) / 100); return `<tr><td>${i + 1}</td><td>${escapeHtml(customerName(d))}</td><td>${escapeHtml(d.doc_number)}</td><td>${d.date ? fmtD(d.date) : '—'}</td><td>${escapeHtml(it.item_name || '—')}</td><td>${escapeHtml(it.make || '—')}</td><td>${num(it.qty)}</td><td>${num(it.supplied)}</td><td>₹${fmtMoney(it.rate)}</td><td>${num(it.discount)}%</td><td>₹${fmtMoney(unit)}</td><td>₹${fmtMoney(num(it.qty) * unit)}</td><td style="white-space:nowrap;"><button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-edit="${d.id}">Edit</button><button class="btn-danger-text" data-del="${d.id}">Delete</button></td></tr>`; }).join('')}</table></div>` : '<div class="empty">No completed purchase orders match.</div>';
    const tx = [];
    docs.forEach((d) => d.items.forEach((it, idx) => (it.supply_log || []).forEach((l) => tx.push({ d, it, idx, l }))));
    const txRows = tx.filter(({ d, it, l }) => (!ft.customer || customerName(d) === ft.customer) && (!ft.ponumber || has(d.doc_number, ft.ponumber)) && (!ft.itemName || has(it.item_name, ft.itemName)) && (!ft.date || l.date === ft.date))
      .sort((a, b) => new Date(b.l.date || 0) - new Date(a.l.date || 0));
    el('poHistoryTransactionsWrap').innerHTML = txRows.length ? `<div class="table-scroll"><table class="report"><tr><th>Date</th><th>PO No.</th><th>Customer</th><th>Item Name</th><th>Qty Supplied</th><th>Bill Number &amp; Date</th><th>Recorded By</th><th></th></tr>${txRows.map(({ d, it, idx, l }) => `<tr><td>${l.date ? fmtD(l.date) : '—'}</td><td>${escapeHtml(d.doc_number)}</td><td>${escapeHtml(customerName(d))}</td><td>${escapeHtml(it.item_name || '—')}</td><td>${num(l.qty_supplied)}</td><td>${escapeHtml(l.remarks || '—')}</td><td>${escapeHtml((l.recorded_by && l.recorded_by.full_name) || '—')}</td><td style="white-space:nowrap;"><button class="btn btn-icon" style="padding:5px 9px; font-size:12px;" data-supedit="${d.id}:${idx}:${l.id}">Edit</button><button class="btn-danger-text" data-supdel="${l.id}">Delete</button></td></tr>`).join('')}</table></div>` : '<div class="empty">No supply transactions match.</div>';
    const reload = async () => { const fresh = await api.all('sales-documents/', { type: 'po' }); docs.splice(0, docs.length, ...fresh); draw(); };
    root.querySelectorAll('[data-edit]').forEach((b) => b.onclick = () => navigate('salesform', 'po', b.dataset.edit));
    root.querySelectorAll('[data-del]').forEach((b) => b.onclick = () => deleteDoc(docs.find((x) => String(x.id) === b.dataset.del), reload));
    root.querySelectorAll('[data-supedit]').forEach((b) => b.onclick = () => { const [d, i, l] = b.dataset.supedit.split(':'); openSupply(d, Number(i), l, reload); });
    root.querySelectorAll('[data-supdel]').forEach((b) => b.onclick = async () => {
      if (!await customConfirm('Delete this supply transaction? The order status will be recalculated.')) return;
      try { await api.delete(`supply-log/${b.dataset.supdel}/`); } catch (e) { await customAlert(apiErrorMessage(e)); }
      await reload();
    });
  };
  const filterRows = () => {
    const custs = (pred) => [...new Set(docs.filter(pred).map(customerName))].sort();
    el('poHistCompletedFilterRow').innerHTML = `<select id="phcCustomer"><option value="">All customers</option>${custs((d) => d.order_status === 'Completed').map((c) => `<option>${escapeHtml(c)}</option>`).join('')}</select><input type="text" id="phcPoNo" placeholder="PO No." style="max-width:120px;"><input type="date" id="phcDate"><input type="text" id="phcItemName" placeholder="Item name" style="max-width:130px;"><input type="text" id="phcMake" placeholder="Make" style="max-width:110px;"><button class="btn" id="phcClear">Clear filters</button>`;
    el('poHistTxFilterRow').innerHTML = `<select id="phtCustomer"><option value="">All customers</option>${custs(() => true).map((c) => `<option>${escapeHtml(c)}</option>`).join('')}</select><input type="text" id="phtPoNo" placeholder="PO No." style="max-width:120px;"><input type="text" id="phtItemName" placeholder="Item name" style="max-width:130px;"><input type="date" id="phtDate"><button class="btn" id="phtClear">Clear filters</button>`;
    [['phcCustomer', fc, 'customer'], ['phcPoNo', fc, 'ponumber'], ['phcDate', fc, 'date'], ['phcItemName', fc, 'itemName'], ['phcMake', fc, 'make'], ['phtCustomer', ft, 'customer'], ['phtPoNo', ft, 'ponumber'], ['phtItemName', ft, 'itemName'], ['phtDate', ft, 'date']]
      .forEach(([id, obj, key]) => el(id).addEventListener(id.endsWith('Customer') || id.endsWith('Date') ? 'change' : 'input', (e) => { obj[key] = e.target.value; draw(); }));
    el('phcClear').onclick = () => { Object.keys(fc).forEach((k) => { fc[k] = ''; }); filterRows(); draw(); };
    el('phtClear').onclick = () => { Object.keys(ft).forEach((k) => { ft[k] = ''; }); filterRows(); draw(); };
  };
  filterRows();
  // Same rows, columns, sheet names and files as the reference (they follow the filters, not the screen's table).
  const m2 = (v) => fmtMoney(num(v));
  const exportCompleted = () => {
    const out = [];
    docs.filter((d) => d.order_status === 'Completed').forEach((d) => d.items.forEach((it) => out.push({ d, it })));
    return out.filter(({ d, it }) => (!fc.customer || customerName(d) === fc.customer) && (!fc.ponumber || has(d.doc_number, fc.ponumber)) && (!fc.date || d.date === fc.date) && (!fc.itemName || has(it.item_name, fc.itemName)) && (!fc.make || has(it.make, fc.make)))
      .sort((a, b) => new Date(b.d.date || 0) - new Date(a.d.date || 0))
      .map(({ d, it }, i) => { const unit = num(it.rate) * (1 - num(it.discount) / 100);
        return { 'S.No': i + 1, 'Customer Name': customerName(d), 'PO No': d.doc_number, Date: d.date || '', 'Item Name': it.item_name || '', Make: it.make || '', 'Ordered Qty': num(it.qty), 'Supplied Qty': num(it.supplied),
          Rate: num(it.rate), 'Discount %': num(it.discount), Amount: m2(unit), Value: m2(num(it.qty) * unit) }; });
  };
  const exportTx = () => {
    const out = [];
    docs.forEach((d) => d.items.forEach((it) => (it.supply_log || []).forEach((l) => out.push({ d, it, l }))));
    return out.filter(({ d, it, l }) => (!ft.customer || customerName(d) === ft.customer) && (!ft.ponumber || has(d.doc_number, ft.ponumber)) && (!ft.itemName || has(it.item_name, ft.itemName)) && (!ft.date || l.date === ft.date))
      .sort((a, b) => new Date(b.l.date || 0) - new Date(a.l.date || 0))
      .map(({ d, it, l }) => ({ Date: l.date || '', 'PO No': d.doc_number, Customer: customerName(d), 'Item Name': it.item_name || '', 'Qty Supplied': num(l.qty_supplied), 'Bill Number & Date': l.remarks || '', 'Recorded By': (l.recorded_by && l.recorded_by.full_name) || '' }));
  };
  [['poHistCompleted', exportCompleted, 'Completed Sales Orders', 'Completed POs', 'anupam360-po-history-completed'], ['poHistTx', exportTx, 'Supply Transactions', 'Supply Transactions', 'anupam360-po-history-transactions']].forEach(([p, get, title, sheetName, prefix]) => {
    el(p + 'ExcelBtn').onclick = () => exportRowsToExcel(get(), prefix, sheetName);
    el(p + 'PdfBtn').onclick = () => exportRowsToPdf(get(), 'Anupam 360 — ' + title, prefix);
    el(p + 'PrintBtn').onclick = () => printRowsTable(get(), 'Anupam 360 — ' + title);
  });
  el('poHistBackBtn').onclick = () => navigate('sales', 'po');
  await draw();
}
