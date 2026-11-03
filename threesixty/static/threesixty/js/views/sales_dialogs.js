// Invoice Done (challan items), Pricing and Supply Qty (sales-order items) — the reference's three small dialogs. The
// quantities, the "more than pending? confirm" rule and the order-status recalculation are applied by the server.
import { api } from '../api.js';
import { el, fmtMoney, customAlert, customConfirm, apiErrorMessage } from '../ui.js';
import { useOverlays, openOverlay, closeOverlay } from '../customer_common.js';
import { navigate } from '../router.js';

const num = (v) => Number(v) || 0;
const today = () => new Date().toISOString().slice(0, 10);
const customerName = (d) => d.customer_name || d.customer_label || '';

export async function openInvoiceDone(docId, itemIndex, onSaved) {
  useOverlays('invoiceDoneOverlay');
  const doc = await api.get(`sales-documents/${docId}/`);
  const item = doc.items[itemIndex]; if (!item) return;
  el('invoiceDoneSub').textContent = `${doc.doc_number} — ${customerName(doc)}`;
  el('inv-itemname').value = item.item_name || '';
  el('inv-dcqty').value = num(item.qty); el('inv-already').value = num(item.invoiced); el('inv-balance').value = num(item.balance);
  el('inv-billno').value = ''; el('inv-billdate').value = today(); el('inv-qty').value = ''; el('inv-qty').max = num(item.balance);
  el('invoiceDoneCancelBtn').onclick = () => closeOverlay('invoiceDoneOverlay');
  el('invoiceDoneSaveBtn').onclick = async () => {
    const billNumber = el('inv-billno').value.trim(), qty = Number(el('inv-qty').value);
    if (!billNumber) { await customAlert('Enter the bill number.'); return; }
    if (!qty || qty <= 0) { await customAlert('Enter a quantity greater than zero.'); return; }
    const balance = num(item.balance);
    const confirm_over = qty > balance;
    if (confirm_over && !await customConfirm(`Only ${balance} is pending for this item, but you're invoicing ${qty}. Save anyway?`)) return;
    try { await api.post(`sales-document-items/${item.id}/invoice-log/`, { bill_number: billNumber, bill_date: el('inv-billdate').value || null, qty_invoiced: qty, confirm_over }); }
    catch (e) { await customAlert('Could not save the invoice: ' + apiErrorMessage(e)); return; }
    closeOverlay('invoiceDoneOverlay');
    if (onSaved) await onSaved();
  };
  openOverlay('invoiceDoneOverlay');
}

export async function openPricing(docId, itemIndex) {
  useOverlays('pricingOverlay');
  const doc = await api.get(`sales-documents/${docId}/`);
  const item = doc.items[itemIndex]; if (!item) return;
  const rate = num(item.rate), discount = num(item.discount), unit = rate * (1 - discount / 100);
  el('pricingModalSub').textContent = doc.doc_number;
  el('pricingItemName').textContent = item.item_name || 'Item';
  el('pricingRate').value = `₹${fmtMoney(rate)}`; el('pricingDiscount').value = `${discount}%`;
  el('pricingAmount').value = `₹${fmtMoney(unit)}`; el('pricingValue').value = `₹${fmtMoney(num(item.qty) * unit)}`;
  el('pricingEditBtn').onclick = () => { closeOverlay('pricingOverlay'); navigate('salesform', 'po', doc.id); };
  el('pricingCloseBtn').onclick = () => closeOverlay('pricingOverlay');
  openOverlay('pricingOverlay');
}

/** Record a supply against a sales-order item; with `logId`, edit that entry instead. */
export async function openSupply(docId, itemIndex, logId, onSaved) {
  useOverlays('supplyOverlay');
  const doc = await api.get(`sales-documents/${docId}/`);
  const item = doc.items[itemIndex]; if (!item) return;
  const entry = logId ? item.supply_log.find((l) => String(l.id) === String(logId)) : null;
  const supplied = num(item.supplied), pending = num(item.pending), mine = entry ? num(entry.qty_supplied) : 0;
  document.querySelector('#supplyOverlay h2').textContent = entry ? 'Edit supply' : 'Record supply';
  el('supplyModalSub').textContent = `${doc.doc_number} — ${customerName(doc)}`;
  el('sup-itemname').value = item.item_name || '';
  el('sup-ordered').value = num(item.qty); el('sup-already').value = supplied - mine; el('sup-pending').value = pending + mine;
  el('sup-date').value = entry ? entry.date : today(); el('sup-qty').value = entry ? num(entry.qty_supplied) : '';
  el('sup-qty').max = pending + mine; el('sup-remarks').value = entry ? entry.remarks || '' : '';
  el('supplySaveBtn').textContent = entry ? 'Save changes' : 'Save supply';
  el('supplyCancelBtn').onclick = () => closeOverlay('supplyOverlay');
  el('supplySaveBtn').onclick = async () => {
    const qty = Number(el('sup-qty').value);
    if (!qty || qty <= 0) { await customAlert('Enter a quantity greater than zero.'); return; }
    const maxAllowed = Number(el('sup-qty').max) || Infinity;
    const confirm_over = qty > maxAllowed;
    if (confirm_over && !await customConfirm(`Only ${maxAllowed} is pending for this item, but you're recording ${qty}. Save anyway?`)) return;
    const body = { qty_supplied: qty, date: el('sup-date').value, remarks: el('sup-remarks').value.trim(), confirm_over };
    try { if (entry) await api.patch(`supply-log/${entry.id}/`, body); else await api.post(`sales-document-items/${item.id}/supply-log/`, body); }
    catch (e) { await customAlert('Could not save the supply record: ' + apiErrorMessage(e)); return; }
    closeOverlay('supplyOverlay');
    if (onSaved) await onSaved();
  };
  openOverlay('supplyOverlay');
}
