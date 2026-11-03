// Printed documents and shipping labels, built the way the reference builds them. The layout code is the reference's own
// (doc_print_ref.js, generated from contact_management.html); this file only gathers the data it needs from 360: the document,
// its customer and contact, the branch letterhead with its images, and the watermark. Everything runs in the browser.
import { api } from './api.js';
import { state } from './state.js';
import { getJsPdf, customAlert } from './ui.js';
import { dataUrl, imageSize, watermark, pdfWatermark, wmHtml as watermarkHtml } from './report_export.js';
import * as ref from './doc_print_ref.js';
import { useOverlays, closeOverlay } from './customer_common.js';

const { ctx, sync, DEFAULT_DOC_THEME, DEFAULT_LOGO_ASPECT } = ref;
const PRINTABLE = ['quotation', 'proforma', 'dc'];
export const isPrintable = (type) => PRINTABLE.includes(type);

// ---- branch letterhead, in the reference's shape (images already loaded as data URLs) ---------------------------------------------
const imageCache = new Map();
async function loaded(url) {
  if (!url) return { src: '', aspect: 0 };
  if (!imageCache.has(url)) {
    const src = await dataUrl(url);
    imageCache.set(url, src ? { src, aspect: await imageSize(src) } : { src: '', aspect: 0 });
  }
  return imageCache.get(url);
}
let prepared = {};     // branch name -> letterhead
let watermarks = {};   // branch name ('' = the user's own) -> { wm, logo }

async function prepareBranch(name) {
  const b = state.branches.find((x) => x.name === name) || null;
  const [logo, dealer, footer, qr, appLogo] = await Promise.all([
    loaded(b && b.logo_url), loaded(b && b.dealer_logo_url), loaded(b && b.footer_image_url), loaded(b && b.payment_qr_url), loaded(window.THREESIXTY_LOGO)]);
  prepared[name || ''] = {
    logo: logo.src || appLogo.src, logoAspect: logo.src ? logo.aspect : (appLogo.aspect || DEFAULT_LOGO_ASPECT),
    companyName: (b && b.letterhead_name) || 'Anupam Bearings', address: (b && b.letterhead_address) || '', phone: (b && b.letterhead_phone) || '', mobile: (b && b.letterhead_mobile) || '',
    email: (b && b.letterhead_email) || '', website: (b && b.letterhead_website) || '', gstNumber: (b && b.letterhead_gstin) || '', udyamNumber: (b && b.udyam_number) || '',
    bankAcNo: (b && b.bank_account_no) || '', bankIfsc: (b && b.bank_ifsc) || '', bankName: (b && b.bank_name) || '', bankBranch: (b && b.bank_branch) || '',
    accentColor: (b && b.accent_color) || DEFAULT_DOC_THEME.accentColor,
    dealershipLogo: dealer.src, dealershipLogoAspect: dealer.aspect || 1, footerImage: footer.src, footerImageAspect: footer.aspect || 1,
    paymentQr: qr.src, paymentQrAspect: qr.aspect || 1, docFormat: b && b.doc_format === 2 ? 2 : 1,
  };
  const wm = watermark(name || '');
  watermarks[name || ''] = { wm, logo: wm && wm.type === 'logo' ? await (async () => { const l = await loaded(wm.lh.logo); return l.src ? { data: l.src, aspect: l.aspect } : null; })() : null };
  if (wm && wm.lh) wm.lh = { ...wm.lh, logo: wm.type === 'logo' && watermarks[name || ''].logo ? watermarks[name || ''].logo.data : wm.lh.logo };
}

ctx.docTheme = { ...DEFAULT_DOC_THEME, terms: [...DEFAULT_DOC_THEME.terms] };
ctx.branchLetterhead = (name) => prepared[name || ''] || prepared[''];
ctx.branchByName = (name) => {
  const b = state.branches.find((x) => x.name === name);
  return b ? { terms: b.terms ? String(b.terms).split('\n').map((t) => t.trim()).filter(Boolean) : [] } : null;
};
ctx.applyPdfWatermark = (doc, name) => { const w = watermarks[name || ''] || watermarks['']; if (w && w.wm) pdfWatermark(doc, w.wm, w.logo); };
ctx.wmHtml = (name) => { const w = watermarks[name || ''] || watermarks['']; return w && w.wm ? watermarkHtml(w.wm) : ''; };

async function ready(branchNames) {
  await getJsPdf();
  prepared = {}; watermarks = {};
  await Promise.all([...new Set(['', ...branchNames])].map(prepareBranch));
  sync();
}

// ---- a 360 document -> the reference's salesDoc ---------------------------------------------------------------------------------------------
const num = (v) => (v === null || v === undefined || v === '' ? 0 : Number(v) || 0);
async function toRefDoc(d) {
  const full = d.items && d.customer_id !== undefined && d.date ? d : await api.get(`sales-documents/${d.id}/`);
  const [customer, contacts] = await Promise.all([api.get(`customers/${full.customer_id}/`), api.all(`customers/${full.customer_id}/contacts/`)]);
  const branch = full.branch_name || (state.branches.find((b) => b.id === full.branch_id) || {}).name || '';
  const person = state.salesPersons.find((p) => p.id === full.sales_person_id || (full.sales_person_name && p.name === full.sales_person_name));
  ctx.companies = [{
    id: customer.id, name: customer.name, address: customer.address, area: customer.area, city: customer.city, state: customer.state, pincode: customer.pincode, gstNumber: customer.gst_number,
    contacts: contacts.map((c) => ({ id: c.id, name: c.name, phone: c.phone || c.phone2 || '' })),
  }];
  sync();
  return {
    id: full.id, type: full.type, docNumber: full.doc_number, date: full.date, branch, customerId: customer.id,
    customerName: (customer.plant || '').trim() ? `${customer.name} — ${customer.plant.trim()}` : customer.name,
    contactId: full.contact_id, contactName: full.contact_name || '', refNo: full.ref_no || '', refDate: full.ref_date || '', validTill: full.valid_till || '',
    salesPersonName: full.sales_person_name || '', salesPersonPhone: person ? person.phone || '' : '', paymentTerms: full.payment_terms || '', vehicle: full.vehicle || '', transport: full.transport || '',
    showDiscountInPdf: !!full.show_discount_in_pdf, packingCharges: num(full.packing_charges), packingTax: num(full.packing_tax), freightCharges: num(full.freight_charges), freightTax: num(full.freight_tax),
    otherCharges: num(full.other_charges), otherChargesTax: num(full.other_charges_tax), roundOff: num(full.round_off),
    terms: Array.isArray(full.terms) ? full.terms : [],
    items: (full.items || []).map((i) => ({ itemName: i.item_name, make: i.make, qty: num(i.qty), unit: i.unit, rate: num(i.rate), discount: num(i.discount), tax: num(i.tax) })),
  };
}

async function withDoc(d, fn) {
  try {
    const sd = await toRefDoc(d);
    await ready([sd.branch]);
    fn(sd);
  } catch (e) { console.error(e); await customAlert('Could not prepare the document: ' + (e.message || e)); }
}

/** PDF download, browser print dialog, and the on-page Preview of a Quotation / Proforma Invoice / Delivery Challan. */
export const docPdf = (d) => withDoc(d, (sd) => ref.printQuotationPdf(sd));
export const docPrint = (d) => withDoc(d, (sd) => ref.printQuotationPrint(sd));
export const docPreview = (d) => {
  useOverlays('quotPreviewOverlay');
  return withDoc(d, (sd) => {
    ref.previewQuotationDoc(sd);
    document.getElementById('quotPreviewCloseBtn').onclick = () => closeOverlay('quotPreviewOverlay');
  });
};

// ---- shipping labels ---------------------------------------------------------------------------------------------------------------------------
export const LABEL_SIZES = ref.LABEL_SIZES;
/** `parts` is the reference's label data (branch name, customer, addrLines, area, cityLine, pin, attn, phone, transport, ...). */
export async function labelOut(parts, mode, n, size, fileBase, onSheet) {
  try {
    await ready([parts.branch]);
    if (mode === 'pdf') ref.labelPdfParts(parts, n, size, fileBase, onSheet); else ref.labelPrintParts(parts, n, size, onSheet);
  } catch (e) { console.error(e); await customAlert('Could not create the label: ' + (e.message || e)); }
}
