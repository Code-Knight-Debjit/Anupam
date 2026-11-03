// GENERATED from contact_management.html (tests/parity/gen_docprint.py): the reference's own code for the printed documents
// (Quotation / Proforma Invoice / Delivery Challan PDF, Print and Preview) and for shipping labels, unchanged, so what is printed
// is the same. Only the data comes from 360 (see doc_print.js, which fills the variables below before each call).
import { RUPEE_FONT_REGULAR_B64, RUPEE_FONT_BOLD_B64 } from './rupee_font.js';
import { escapeHtml, fmtMoney, customAlert } from './ui.js';

export const ctx = { branchByName: null, companies: [], docTheme: null, branchLetterhead: null, branchTermsOf: null, applyPdfWatermark: null, wmHtml: null, savePdf: null };
const el = (id) => document.getElementById(id);
const setPersonal = () => {};
const branchByName = (n) => ctx.branchByName(n);
let docTheme = null, companies = [];
const branchLetterhead = (n) => ctx.branchLetterhead(n);
const applyPdfWatermark = (d, n) => ctx.applyPdfWatermark(d, n);
const wmHtml = (n) => ctx.wmHtml(n);
export const sync = () => { docTheme = ctx.docTheme; companies = ctx.companies; };
function runAutoTable(doc, opts) { doc.autoTable(opts); return true; }
const DEFAULT_LOGO_ASPECT = 3384/1007; // width/height of the default Anupam Bearings logo asset
function fitBox(aspect, maxW, maxH){
  const a = aspect || 1;
  let w = maxW, h = w / a;
  if(h > maxH){ h = maxH; w = h * a; }
  return { w, h };
}
function splitAddressTwoLines(address){
  if(!address) return [];
  const parts = address.split(',').map(s => s.trim()).filter(Boolean);
  if(parts.length <= 1) return [address];
  let bestI = 1, bestDiff = Infinity;
  for(let i = 1; i < parts.length; i++){
    const line1 = parts.slice(0, i).join(', ');
    const line2 = parts.slice(i).join(', ');
    const diff = Math.abs(line1.length - line2.length);
    if(diff < bestDiff){ bestDiff = diff; bestI = i; }
  }
  return [parts.slice(0, bestI).join(', '), parts.slice(bestI).join(', ')];
}
const DEFAULT_DOC_THEME = {
  accentColor: '#d97b2f',
  footerLabel: 'For Anupam Bearings',
  signatoryLabel: 'Authorized Signatory',
  showLogo: true,
  terms: [
    'Prices are exclusive of GST unless otherwise stated.',
    'Delivery timeline is subject to stock availability at the time of order confirmation.',
    'Payment terms as mutually agreed upon order confirmation.',
    'This quotation is valid for 15 days from the date of issue.'
  ]
};
const SALES_DOC_CONFIG = {
  enquiry: {
    label: 'Enquiry', plural: 'Enquiries', prefix: 'ENQ',
    hasSource: true, hasContact: true, showDocNumberField: true, docNumberLabel: 'Enquiry Number', docNumberEditable: true, docNumberBesideDate: true, hasBranch: true,
    itemCols: [], hasValue: false,
    refType: null, extra: [], hasOrderStatus: true, showStatusInForm: false,
    orderStatusOptions: [
      { value: 'Pending', color: '#e0a30c' },
      { value: 'Completed', color: '#2f9e52' },
      { value: 'Regretted', color: '#d9534f' }
    ],
    hasCallLog: false, hideAddedBy: false
  },
  quotation: {
    label: 'Quotation', plural: 'Quotations', prefix: 'QUO',
    hasSource: false, hasContact: true, showDocNumberField: true, docNumberLabel: 'Quotation Number', docNumberEditable: true, hasBranch: true,
    itemCols: ['itemName','qty','unit','rate','discount','tax'], hasValue: true, hasDiscount: true, hasTax: true,
    itemNameMultiline: true, hasCharges: true, hasSdToggle: true, hasQuoteMeta: true, hasTerms: true, hideSalesPersonInPrint: true,
    refType: 'enquiry', extra: [], hasOrderStatus: true, showStatusInForm: false,
    orderStatusOptions: [
      { value: 'Pending', color: '#e0a30c' },
      { value: 'Win', color: '#2f9e52' },
      { value: 'Lose', color: '#d9534f' }
    ],
    hasCallLog: true, hideAddedBy: true
  },
  po: {
    label: 'Sales Order', plural: 'Pending PO', prefix: 'PO',
    hasSource: false, hasContact: false, showDocNumberField: true, docNumberLabel: 'Customer PO No.', docNumberEditable: true, docNumberBesideDate: true, hasBranch: true,
    itemCols: ['itemName','qty','rate','discount'], hasValue: true, hasDiscount: true,
    itemColLabels: { qty: 'Ordered Qty' },
    refType: null, extra: [], hasOrderStatus: true,
    orderStatusOptions: [
      { value: 'Pending', color: '#e0a30c' },
      { value: 'Part Pending', color: '#e07a2c' },
      { value: 'Hold', color: '#8b97a6' },
      { value: 'Completed', color: '#2f9e52' }
    ],
    hasCallLog: false, hideAddedBy: false
  },
  dc: {
    label: 'Delivery Challan', plural: 'Delivery Challans', prefix: 'DC',
    hasSource: false, hasContact: true, showDocNumberField: true, docNumberLabel: 'Delivery Challan Number', docNumberEditable: true, docNumberBesideDate: true, hasBranch: true,
    itemCols: ['itemName','qty','unit','rate','discount','tax'], hasValue: true, hasDiscount: true, hasTax: true,
    itemNameMultiline: true, hasCharges: true, hasSdToggle: true, hasQuoteMeta: true, hasTerms: true,
    hasSalesPerson: false, hasValidTill: false, hasPaymentTerms: false,
    refType: 'po', extra: ['vehicle','transport'], hasOrderStatus: false, hasCallLog: true, hideAddedBy: false, hideBankQr: true
  },
  proforma: {
    label: 'Proforma Invoice', plural: 'Proforma Invoices', prefix: 'PI',
    hasSource: false, hasContact: true, showDocNumberField: true, docNumberLabel: 'Proforma Invoice Number', docNumberEditable: true, docNumberBesideDate: true, hasBranch: true,
    itemCols: ['itemName','qty','unit','rate','discount','tax'], hasValue: true, hasDiscount: true, hasTax: true,
    itemNameMultiline: true, hasCharges: true, hasSdToggle: true, hasQuoteMeta: true, hasTerms: true, hasValidTill: false, hideSalesPersonInPrint: true,
    refType: 'quotation', extra: [], hasOrderStatus: true, showStatusInForm: false,
    orderStatusOptions: [
      { value: 'Pending', color: '#e0a30c' },
      { value: 'Win', color: '#2f9e52' },
      { value: 'Lose', color: '#d9534f' }
    ],
    hasCallLog: true, hideAddedBy: true
  }
};
function hexToRgb(hex){
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex||'');
  if(!m) return [217,123,47];
  return [parseInt(m[1],16), parseInt(m[2],16), parseInt(m[3],16)];
}
function branchTerms(branchName){
  const b = branchByName(branchName);
  if(b && Array.isArray(b.terms) && b.terms.length) return b.terms;
  return (docTheme.terms && docTheme.terms.length) ? docTheme.terms : DEFAULT_DOC_THEME.terms;
}
function savePdfBlob(doc, filename, noWatermark, branchName){
  if(!noWatermark) applyPdfWatermark(doc, branchName);
  try{
    const blob = doc.output('blob');
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }catch(e){
    console.error('PDF save fallback failed, trying doc.save()', e);
    doc.save(filename);
  }
}
function numberToWordsIndian(num){
  const ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten',
    'Eleven','Twelve','Thirteen','Fourteen','Fifteen','Sixteen','Seventeen','Eighteen','Nineteen'];
  const tens = ['', '', 'Twenty','Thirty','Forty','Fifty','Sixty','Seventy','Eighty','Ninety'];
  function twoDigits(n){
    if(n < 20) return ones[n];
    return tens[Math.floor(n/10)] + (n%10 ? ' ' + ones[n%10] : '');
  }
  function threeDigits(n){
    if(n < 100) return twoDigits(n);
    return ones[Math.floor(n/100)] + ' Hundred' + (n%100 ? ' ' + twoDigits(n%100) : '');
  }
  num = Math.floor(num);
  if(num === 0) return 'Zero';
  let str = '';
  const crore = Math.floor(num / 10000000); num %= 10000000;
  const lakh = Math.floor(num / 100000); num %= 100000;
  const thousand = Math.floor(num / 1000); num %= 1000;
  const hundred = num;
  if(crore) str += threeDigits(crore) + ' Crore ';
  if(lakh) str += twoDigits(lakh) + ' Lakh ';
  if(thousand) str += twoDigits(thousand) + ' Thousand ';
  if(hundred) str += threeDigits(hundred) + ' ';
  return str.trim();
}
function amountInWords(amount){
  amount = Math.round((Number(amount)||0) * 100) / 100;
  const rupees = Math.floor(Math.abs(amount));
  const paise = Math.round((Math.abs(amount) - rupees) * 100);
  let words = 'Rupees ' + numberToWordsIndian(rupees);
  if(paise > 0) words += ' and ' + numberToWordsIndian(paise) + ' Paise';
  words += ' Only';
  if(amount < 0) words = 'Minus ' + words;
  return words;
}
function companyFullAddress(company){
  if(!company) return '';
  const bits = [company.address, company.area, company.city, company.state, company.pincode].map(b=>(b||'').trim()).filter(Boolean);
  return bits.join(', ');
}
function computeQuotationDocData(salesDoc){
  const showDiscount = !!salesDoc.showDiscountInPdf;
  let computedSubTotal = 0;
  let computedTaxTotal = 0;
  const items = (salesDoc.items||[]).map((it, idx) => {
    const qty = Number(it.qty)||0;
    const rate = Number(it.rate)||0;
    const discount = Number(it.discount)||0;
    const tax = Number(it.tax)||0;
    let displayRate, amount;
    if(showDiscount){
      displayRate = rate;
      amount = qty * rate * (1 - discount/100);
    } else {
      // Fold the discount into the rate and round it to the nearest whole rupee,
      // so the customer only ever sees a clean, discount-free-looking price.
      displayRate = Math.round(rate * (1 - discount/100));
      amount = qty * displayRate;
    }
    // The Amount column shown per line excludes tax; every item's tax is instead totalled
    // into a single consolidated "Tax Amount" line in the totals box, right after Sub Total.
    const taxAmount = amount * (tax/100);
    computedSubTotal += amount;
    computedTaxTotal += taxAmount;
    // Doc types that also track a Make/brand per item (e.g. Delivery Challan) don't get their
    // own printed column for it — Quotation's item table layout is reused as-is — so it's folded
    // into the description here instead of being dropped from the printed document.
    const printedItemName = it.make ? `${it.itemName||'—'} (${it.make})` : (it.itemName||'—');
    return { srNo: idx+1, itemName: printedItemName, qty, unit: it.unit||'', displayRate, discount, tax, amount, taxAmount };
  });
  const packing = Number(salesDoc.packingCharges)||0;
  const packingTax = Number(salesDoc.packingTax)||0;
  const freight = Number(salesDoc.freightCharges)||0;
  const freightTax = Number(salesDoc.freightTax)||0;
  const other = Number(salesDoc.otherCharges)||0;
  const otherTax = Number(salesDoc.otherChargesTax)||0;
  const roundOff = Number(salesDoc.roundOff)||0;
  const packingFinal = packing * (1 + packingTax/100);
  const freightFinal = freight * (1 + freightTax/100);
  const otherFinal = other * (1 + otherTax/100);
  // Sub Total / Tax Amount are always recomputed from the individual item rows (qty × rate,
  // discount-folded) so the figures shown on the printed document add up cleanly.
  const subTotal = computedSubTotal;
  const taxTotal = computedTaxTotal;
  const total = subTotal + taxTotal + packingFinal + freightFinal + otherFinal + roundOff;
  return { showDiscount, items, subTotal, taxTotal, packing, packingTax, packingFinal, freight, freightTax, freightFinal, other, otherTax, otherFinal, roundOff, total };
}
let docSharp = false;
function docRR(doc, x, y, w, h, rx, ry){ if(docSharp) doc.rect(x, y, w, h); else doc.roundedRect(x, y, w, h, rx, ry); }
function drawMetaSectionBox(doc, sections, x, y, width){
  const colW = width / sections.length;
  let maxRowH = 14;
  const colValueLines = sections.map(sec => doc.splitTextToSize(sec.value, colW - 10));
  colValueLines.forEach(lines => { maxRowH = Math.max(maxRowH, 8 + lines.length * 4.5); });
  doc.setDrawColor(210,210,210);
  docRR(doc, x, y, width, maxRowH, 1.5, 1.5);
  sections.forEach((sec, i) => {
    const colX = x + i * colW;
    if(i > 0){ doc.line(colX, y, colX, y + maxRowH); }
    doc.setFont('helvetica','normal'); doc.setFontSize(7.5); doc.setTextColor(140,140,140);
    doc.text(sec.label.toUpperCase(), colX + 6, y + 6);
    doc.setFont('helvetica','bold'); doc.setFontSize(9.5); doc.setTextColor(30,30,30);
    doc.text(colValueLines[i], colX + 6, y + 11);
  });
  return y + maxRowH + 8;
}
function drawStackedMetaBox(doc, rowsInput, x, y, width){
  // rowsInput: array of rows, each row an array of 1 or 2 {label, value} cells drawn side by side
  const innerPad = 4;
  const topPad = 1.6, labelLineH = 2.7, labelValueGap = 1.2, valueLineH = 3.2, bottomPad = 0.9;
  const rows = rowsInput.map(row => {
    const colW = width / row.length;
    const cells = row.map(it => {
      doc.setFont('helvetica','normal'); doc.setFontSize(7);
      const labelLines = doc.splitTextToSize(it.label.toUpperCase(), colW - innerPad * 2);
      // Measure the value's wrap width at the same font/size it's actually drawn in further down
      // (bold, 9pt) — measuring it at the label's smaller 7pt font understated its width and let
      // long values (e.g. a sales person's name + phone) spill past the box's border when drawn.
      doc.setFont('helvetica','bold'); doc.setFontSize(9);
      const valueLines = doc.splitTextToSize(it.value, colW - innerPad * 2);
      return { ...it, labelLines, valueLines };
    });
    const h = Math.max(...cells.map(c => topPad + c.labelLines.length * labelLineH + labelValueGap + c.valueLines.length * valueLineH + bottomPad));
    return { cells, colW, h };
  });
  const totalH = rows.reduce((s, r) => s + r.h, 0);
  doc.setDrawColor(210,210,210);
  docRR(doc, x, y, width, totalH, 1.5, 1.5);
  let curY = y;
  rows.forEach((row, i) => {
    if(i > 0){ doc.line(x, curY, x + width, curY); }
    row.cells.forEach((c, j) => {
      const cellX = x + j * row.colW;
      if(j > 0){ doc.line(cellX, curY, cellX, curY + row.h); }
      // When a neighboring cell in this row wraps to more lines (e.g. a long Sales Person Details
      // value), row.h grows to fit it — vertically center this cell's own, shorter label+value
      // block within that taller row instead of leaving it stuck against the top edge.
      const blockH = topPad + c.labelLines.length * labelLineH + labelValueGap + c.valueLines.length * valueLineH + bottomPad;
      const vOffset = Math.max(0, (row.h - blockH) / 2);
      doc.setFont('helvetica','normal'); doc.setFontSize(7); doc.setTextColor(140,140,140);
      doc.text(c.labelLines, cellX + innerPad, curY + vOffset + topPad + 1.3);
      const valueY = curY + vOffset + topPad + c.labelLines.length * labelLineH + labelValueGap;
      doc.setFont('helvetica','bold'); doc.setFontSize(9); doc.setTextColor(30,30,30);
      doc.text(c.valueLines, cellX + innerPad, valueY);
    });
    curY += row.h;
  });
  return y + totalH;
}
function drawTotalsBox(doc, rows, x, y, width){
  const normalH = 7.5;
  const grandH = 10;
  const totalH = rows.reduce((s,r)=> s + (r.grand ? grandH : normalH), 0);
  doc.setDrawColor(210,210,210);
  docRR(doc, x, y, width, totalH, 1.5, 1.5);
  let curY = y;
  rows.forEach((r, i) => {
    const h = r.grand ? grandH : normalH;
    if(r.grand){
      doc.setFillColor(250,248,244);
      doc.rect(x + 0.4, curY + 0.4, width - 0.8, h - 0.8, 'F');
    }
    if(i > 0){
      doc.setDrawColor(230,230,230);
      doc.line(x, curY, x + width, curY);
    }
    const textY = curY + h/2 + 1.6;
    doc.setFont('helvetica', r.grand ? 'bold' : 'normal');
    doc.setFontSize(r.grand ? 11 : 9.5);
    doc.setTextColor(r.grand?30:90, r.grand?30:90, r.grand?30:90);
    doc.text(r.label, x + 6, textY);
    drawCurrencyText(doc, r.value, x + width - 6, textY, { align: 'right' });
    curY += h;
  });
  return curY;
}
// Small vector-drawn contact icons for the PDF. jsPDF's standard 14 fonts (Helvetica etc.) only
// support the WinAnsi/Latin-1 character set — Unicode emoji/pictographs (pin, phone, mail, globe...)
// silently render as the wrong glyph or nothing at all. Drawing simple shapes avoids that entirely.
const CONTACT_ICON_W = 4.6; // mm reserved for icon + gap before the text that follows it
function drawContactIcon(doc, type, x, textBaselineY, size){
  const s = size || 3.2;
  const cx = x + s / 2;
  const cy = textBaselineY - s * 0.36; // roughly the vertical center of the text this icon sits beside
  doc.setDrawColor(130,130,130);
  doc.setFillColor(130,130,130);
  if(type === 'pin'){
    const r = s * 0.26;
    doc.setLineWidth(0.28);
    doc.circle(cx, cy - r * 0.2, r, 'S');
    doc.triangle(cx - r * 0.55, cy + r * 0.35, cx + r * 0.55, cy + r * 0.35, cx, cy + r * 1.7, 'F');
  } else if(type === 'phone'){
    const r = s * 0.14;
    doc.setLineWidth(s * 0.16);
    doc.line(cx - s * 0.22, cy - s * 0.2, cx + s * 0.22, cy + s * 0.2);
    doc.circle(cx - s * 0.22, cy - s * 0.2, r, 'F');
    doc.circle(cx + s * 0.22, cy + s * 0.2, r, 'F');
  } else if(type === 'mobile'){
    const w = s * 0.42, h = s * 0.74;
    doc.setLineWidth(0.28);
    doc.roundedRect(cx - w / 2, cy - h / 2, w, h, 0.5, 0.5, 'S');
    doc.setLineWidth(0.45);
    doc.line(cx - w * 0.16, cy + h / 2 - 0.55, cx + w * 0.16, cy + h / 2 - 0.55);
  } else if(type === 'email'){
    const w = s * 0.78, h = s * 0.52;
    doc.setLineWidth(0.28);
    doc.rect(cx - w / 2, cy - h / 2, w, h, 'S');
    doc.line(cx - w / 2, cy - h / 2, cx, cy + h * 0.06);
    doc.line(cx + w / 2, cy - h / 2, cx, cy + h * 0.06);
  } else if(type === 'web'){
    const r = s * 0.32;
    doc.setLineWidth(0.26);
    doc.circle(cx, cy, r, 'S');
    doc.line(cx - r, cy, cx + r, cy);
    doc.ellipse(cx, cy, r * 0.42, r, 'S');
  }
  doc.setDrawColor(0,0,0);
  doc.setFillColor(0,0,0);
}
// Draws the letterhead header (logo | company details | dealership logo, then the QUOTATION
// title box and divider) on whichever page is currently active in `doc`. Called once for page 1
// and again on every subsequent page so the header repeats throughout the document.
function drawQuotationHeader(doc, lh, pageWidth, marginX, docTitleText){
  const mainLogoBoxW = 32;  // mm — reserved width for our logo (fits a square ~591x591px logo, or a wider one at full height)
  const mainLogoBoxH = 32;  // mm — target height, matching width so a square logo prints at full size
  const dealerLogoBox = 40; // mm — fits a ~300x300px logo
  const headerGap = 6;
  const col1X = marginX;
  const compBlockX = marginX + mainLogoBoxW + headerGap;
  const dealerBoxRight = pageWidth - marginX;
  const topY = 5;

  let logoBottomY = topY;
  if(docTheme.showLogo !== false){
    try{
      const fmt = /^data:image\/jpe?g/i.test(lh.logo) ? 'JPEG' : 'PNG';
      const aspect = lh.logoAspect || DEFAULT_LOGO_ASPECT;
      const { w: logoW, h: logoH } = fitBox(aspect, mainLogoBoxW, mainLogoBoxH);
      doc.addImage(lh.logo, fmt, col1X, topY, logoW, logoH);
      logoBottomY = topY + logoH;
    }catch(e){ logoBottomY = topY; }
  }

  let compY = topY + 4;
  doc.setFont('helvetica','bold'); doc.setFontSize(13); doc.setTextColor(30,30,30);
  doc.text(lh.companyName, compBlockX, compY);
  compY += 5;
  doc.setFont('helvetica','normal'); doc.setFontSize(8); doc.setTextColor(100,100,100);
  splitAddressTwoLines(lh.address).forEach((line, i) => {
    if(i === 0) drawContactIcon(doc, 'pin', compBlockX, compY);
    doc.text(line, compBlockX + CONTACT_ICON_W, compY); compY += 3.8;
  });
  if(lh.phone){ drawContactIcon(doc, 'phone', compBlockX, compY); doc.text(lh.phone, compBlockX + CONTACT_ICON_W, compY); compY += 3.8; }
  if(lh.mobile){ drawContactIcon(doc, 'mobile', compBlockX, compY); doc.text(lh.mobile, compBlockX + CONTACT_ICON_W, compY); compY += 3.8; }
  if(lh.email || lh.website){
    let ex = compBlockX;
    if(lh.email){ drawContactIcon(doc, 'email', ex, compY); doc.text(lh.email, ex + CONTACT_ICON_W, compY); ex += CONTACT_ICON_W + doc.getTextWidth(lh.email) + 5; }
    if(lh.website){ drawContactIcon(doc, 'web', ex, compY); doc.text(lh.website, ex + CONTACT_ICON_W, compY); }
    compY += 3.8;
  }
  const lhRegBits = [lh.gstNumber ? `GSTIN: ${lh.gstNumber}` : '', lh.udyamNumber ? `Udyam: ${lh.udyamNumber}` : ''].filter(Boolean).join('  |  ');
  if(lhRegBits){ doc.text(lhRegBits, compBlockX, compY); compY += 3.8; }

  let dealerBottomY = topY;
  if(lh.dealershipLogo){
    try{
      const fmt = /^data:image\/jpe?g/i.test(lh.dealershipLogo) ? 'JPEG' : 'PNG';
      const aspect = lh.dealershipLogoAspect || 1;
      const { w: dealerW, h: dealerH } = fitBox(aspect, dealerLogoBox, dealerLogoBox);
      doc.addImage(lh.dealershipLogo, fmt, dealerBoxRight - dealerW, topY, dealerW, dealerH);
      dealerBottomY = topY + dealerH;
    }catch(e){ dealerBottomY = topY; }
  }

  let y = Math.max(logoBottomY, compY, dealerBottomY) + 8;
  doc.setFont('helvetica','bold'); doc.setFontSize(11); doc.setTextColor(30,30,30);
  const titleText = docTitleText || 'QUOTATION';
  const titleBoxH = 7.5;
  const titleBoxY = y - titleBoxH + 2.2;
  doc.text(titleText, pageWidth / 2, y, { align: 'center' });
  y = titleBoxY + titleBoxH + 3;
  doc.setDrawColor(220,220,220);
  doc.line(marginX, y, pageWidth - marginX, y);
  y += 3;
  return y;
}
// Rupee (₹) glyph support for jsPDF. jsPDF's standard 14 fonts (Helvetica etc.) only support the
// WinAnsi/Latin-1 character set, which does NOT include U+20B9 (₹) — it silently renders as
// nothing. A minimal DejaVu Sans subset (space + ₹ glyph only, in regular and bold) is embedded so
// the symbol can be drawn, then text is switched back to Helvetica immediately after for the rest
// of the string, since only the ₹ glyph itself needs the embedded font.
function ensureRupeeFont(doc){
  try{
    doc.addFileToVFS('DejaVuSans-Rupee-Regular.ttf', RUPEE_FONT_REGULAR_B64);
    doc.addFont('DejaVuSans-Rupee-Regular.ttf', 'RupeeFont', 'normal');
    doc.addFileToVFS('DejaVuSans-Rupee-Bold.ttf', RUPEE_FONT_BOLD_B64);
    doc.addFont('DejaVuSans-Rupee-Bold.ttf', 'RupeeFont', 'bold');
  }catch(e){ /* if embedding fails, ₹ characters will just fall back to blank — non-fatal */ }
}
// Draws text that may contain a single ₹ character, switching to the embedded RupeeFont just for
// that glyph and back to Helvetica for everything else, so the whole string still lines up and
// aligns (left/center/right) as if it had been drawn normally in one font.
function drawCurrencyText(doc, text, x, y, opts){
  opts = opts || {};
  const align = opts.align || 'left';
  const idx = text.indexOf('\u20B9');
  if(idx === -1){ doc.text(text, x, y, opts); return; }
  const before = text.slice(0, idx);
  const after = text.slice(idx + 1);
  const curFont = doc.getFont();
  const fontStyle = curFont.fontStyle === 'bold' ? 'bold' : 'normal';
  doc.setFont('helvetica', fontStyle);
  const beforeW = before ? doc.getTextWidth(before) : 0;
  const afterW = after ? doc.getTextWidth(after) : 0;
  doc.setFont('RupeeFont', fontStyle);
  const glyphW = doc.getTextWidth('\u20B9');
  doc.setFont('helvetica', fontStyle);
  const totalW = beforeW + glyphW + afterW;
  let startX = x;
  if(align === 'right') startX = x - totalW;
  else if(align === 'center') startX = x - totalW / 2;
  if(before){ doc.setFont('helvetica', fontStyle); doc.text(before, startX, y); }
  doc.setFont('RupeeFont', fontStyle);
  doc.text('\u20B9', startX + beforeW, y);
  if(after){ doc.setFont('helvetica', fontStyle); doc.text(after, startX + beforeW + glyphW, y); }
  doc.setFont('helvetica', fontStyle);
}
function printQuotationPdf(salesDoc){
  try{
    if(!window.jspdf || !window.jspdf.jsPDF){ customAlert("PDF library didn't load — check your internet connection and try again."); return; }
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
    ensureRupeeFont(doc);
    const pageWidth = doc.internal.pageSize.getWidth();
    const marginX = 5;
    const lh = branchLetterhead(salesDoc.branch);
    docSharp = lh.docFormat === 2;
    const accentRgb = hexToRgb(lh.accentColor);
    // This layout is shared by every priced sales document (Quotation, Delivery Challan,
    // Proforma Invoice) — only the page title and a couple of field labels change per type.
    const docCfg = SALES_DOC_CONFIG[salesDoc.type] || SALES_DOC_CONFIG.quotation;
    const docLabel = docCfg.label || 'Quotation';
    const docTitleText = docLabel.toUpperCase();
    const docNumberLabel = docCfg.docNumberLabel || 'Quotation Number';

    // Header (logo, company details, dealership logo, document title) repeats on every page.
    let y = drawQuotationHeader(doc, lh, pageWidth, marginX, docTitleText);
    const headerContentStartY = y; // where page content starts on continuation pages too

    // Footer image (promotional banner) repeats at a fixed position at the bottom of every page.
    let footerImgW = 0, footerImgH = 0;
    if(lh.footerImage){
      const aspect = lh.footerImageAspect || (1200/100);
      footerImgW = pageWidth - 2 * marginX;
      footerImgH = footerImgW / aspect;
      const maxFooterImgH = 22;
      if(footerImgH > maxFooterImgH){ footerImgH = maxFooterImgH; footerImgW = footerImgH * aspect; }
    }
    const pageHeight = doc.internal.pageSize.getHeight();
    const bottomMargin = 5;
    const footerBandH = lh.footerImage ? (footerImgH + 4) : 0;
    const effectiveBottomMargin = bottomMargin + footerBandH;

    const company = companies.find(c => c.id === salesDoc.customerId);
    const contact = company ? (company.contacts||[]).find(ct => ct.id === salesDoc.contactId) : null;

    // --- 2-section layout: Customer Details (left, bordered) | Quotation meta (right, bordered) ---
    const twoColGap = docSharp ? 0 : 8;   // Format 2: customer details and document details touch
    const leftColX = marginX;
    const leftColWidth = (pageWidth - 2 * marginX - twoColGap) / 2;
    const rightColX = leftColX + leftColWidth + twoColGap;
    const rightColWidth = leftColWidth;
    const sectionTopY = y;
    const leftPad = 6;
    const leftContentX = leftColX + leftPad;
    const leftContentWidth = leftColWidth - leftPad * 2;

    let leftY = sectionTopY + leftPad + 3;
    doc.setFont('helvetica','bold'); doc.setFontSize(8); doc.setTextColor(140,140,140);
    doc.text('CUSTOMER DETAILS', leftContentX, leftY);
    leftY += 4.5;
    doc.setFont('helvetica','bold'); doc.setFontSize(10); doc.setTextColor(30,30,30);
    doc.text(salesDoc.customerName || '—', leftContentX, leftY);
    leftY += 5;
    doc.setFont('helvetica','normal'); doc.setFontSize(9); doc.setTextColor(80,80,80);
    const fullAddr = companyFullAddress(company);
    if(fullAddr){
      const addrLines = doc.splitTextToSize(fullAddr, leftContentWidth - CONTACT_ICON_W);
      addrLines.forEach((line, i) => {
        if(i === 0) drawContactIcon(doc, 'pin', leftContentX, leftY);
        doc.text(line, leftContentX + CONTACT_ICON_W, leftY); leftY += 4.5;
      });
    }
    if(company && company.gstNumber){ doc.text(`GSTIN: ${company.gstNumber}`, leftContentX, leftY); leftY += 4.5; }
    if(salesDoc.contactName){ doc.text(`Attn: ${salesDoc.contactName}`, leftContentX, leftY); leftY += 4.5; }
    if(contact && contact.phone){ drawContactIcon(doc, 'phone', leftContentX, leftY); doc.text(contact.phone, leftContentX + CONTACT_ICON_W, leftY); leftY += 4.5; }
    const leftBoxHeight = (leftY - sectionTopY) + leftPad - 2;

    const validTillDisplay = salesDoc.validTill ? new Date(salesDoc.validTill).toLocaleDateString('en-IN') : '—';
    const refDateDisplay = salesDoc.refDate ? new Date(salesDoc.refDate).toLocaleDateString('en-IN') : '—';
    const salesPersonBits = [salesDoc.salesPersonName||'', salesDoc.salesPersonPhone||''].filter(Boolean).join(' / ') || '—';
    const showValidTillRow = docCfg.hasValidTill !== false;
    const showSalesPersonRow = docCfg.hasSalesPerson !== false && !docCfg.hideSalesPersonInPrint;
    const showPaymentTermsRow = docCfg.hasPaymentTerms !== false;
    const quoteMetaRows = [
      [ { label: docNumberLabel, value: salesDoc.docNumber || '—' }, { label: 'Date', value: salesDoc.date ? new Date(salesDoc.date).toLocaleDateString('en-IN') : '—' } ],
      [ { label: 'Reference Number', value: salesDoc.refNo || '—' }, { label: 'Reference Date', value: refDateDisplay } ]
    ];
    if(showValidTillRow || showSalesPersonRow){
      const row = [];
      if(showValidTillRow) row.push({ label: `${docLabel} Valid Till`, value: validTillDisplay });
      if(showSalesPersonRow) row.push({ label: 'Sales Person Details', value: salesPersonBits });
      quoteMetaRows.push(row);
    }
    if(showPaymentTermsRow) quoteMetaRows.push([ { label: 'Payment Terms', value: salesDoc.paymentTerms || '—' } ]);
    // Delivery Challan (and any future type) that also tracks vehicle/transport info gets an
    // extra row for it here, right in the same meta box — Quotation itself has no such fields
    // (docCfg.extra is empty), so this is a no-op for it.
    if((docCfg.extra||[]).includes('vehicle') || (docCfg.extra||[]).includes('transport')){
      quoteMetaRows.push([
        { label: 'Vehicle Number', value: salesDoc.vehicle || '—' },
        { label: 'Transport Name', value: salesDoc.transport || '—' }
      ]);
    }
    const rightBottomY = drawStackedMetaBox(doc, quoteMetaRows, rightColX, sectionTopY, rightColWidth);
    const rightBoxHeight = rightBottomY - sectionTopY;

    // Match both panels to the same height, then draw the Customer Details border last (on top)
    const matchedBoxHeight = Math.max(leftBoxHeight, rightBoxHeight);
    if(matchedBoxHeight > rightBoxHeight){
      doc.setDrawColor(210,210,210);
      docRR(doc, rightColX, sectionTopY, rightColWidth, matchedBoxHeight, 1.5, 1.5);
    }
    doc.setDrawColor(210,210,210);
    docRR(doc, leftColX, sectionTopY, leftColWidth, matchedBoxHeight, 1.5, 1.5);

    y = sectionTopY + matchedBoxHeight + (docSharp ? 0 : 8);   // Format 2: the item table sits directly under the joined panels

    const data = computeQuotationDocData(salesDoc);
    const showDiscount = data.showDiscount;
    // Rate/Amount headers omit a "(Rs.)"/"(₹)" suffix here because header cells are drawn by
    // autoTable in plain Helvetica, which can't render the ₹ glyph — the currency symbol still
    // appears on every value in these columns via the RupeeFont cell-drawing hooks below.
    const cols = showDiscount
      ? ['#','Item & Description','Qty','Unit','Rate','Discount %','Tax %','Amount']
      : ['#','Item & Description','Qty','Unit','Rate','Tax %','Amount'];
    const rateColIdx = 4;
    const amountColIdx = showDiscount ? 7 : 6;
    const currencyCols = [rateColIdx, amountColIdx];
    const body = data.items.map(it => {
      const row = [ String(it.srNo), it.itemName, String(it.qty), it.unit||'—', `₹ ${fmtMoney(it.displayRate)}` ];
      if(showDiscount) row.push(`${it.discount}%`);
      row.push(`${it.tax}%`);
      row.push(`₹ ${fmtMoney(it.amount)}`);
      return row;
    });
    // Qty / Unit / Rate / Discount % / Tax % / Amount are all numeric-ish columns, right-aligned
    // (like a standard invoice) so the figures line up; # and Item & Description stay left.
    // "#" gets a little extra width + center alignment + no-wrap so double-digit (and higher)
    // serial numbers stay on one line instead of wrapping digit-by-digit ("1" / "0").
    const columnStyles = showDiscount
      ? { 0: { cellWidth: 11, halign: 'center', overflow: 'hidden' }, 1: { cellWidth: 'auto' }, 2: { cellWidth: 14, halign: 'right' }, 3: { cellWidth: 16, halign: 'right' }, 4: { cellWidth: 20, halign: 'right' }, 5: { cellWidth: 18, halign: 'right' }, 6: { cellWidth: 14, halign: 'right' }, 7: { cellWidth: 24, halign: 'right' } }
      : { 0: { cellWidth: 11, halign: 'center', overflow: 'hidden' }, 1: { cellWidth: 'auto' }, 2: { cellWidth: 16, halign: 'right' }, 3: { cellWidth: 18, halign: 'right' }, 4: { cellWidth: 24, halign: 'right' }, 5: { cellWidth: 16, halign: 'right' }, 6: { cellWidth: 26, halign: 'right' } };
    runAutoTable(doc, {
      startY: y, head: [cols], body,
      margin: { left: marginX, right: marginX, top: headerContentStartY, bottom: effectiveBottomMargin },
      styles: Object.assign({ fontSize: 9, cellPadding: 3, overflow: 'linebreak', valign: 'middle' }, docSharp ? { lineColor: [210,210,210], lineWidth: 0.2 } : {}),
      headStyles: { fillColor: accentRgb },
      columnStyles,
      theme: 'grid',
      willDrawCell: (dataArg) => {
        // Suppress autoTable's own (Helvetica) draw of the Rate/Amount cell text — we redraw it
        // manually just below so the ₹ glyph can be swapped in via the embedded RupeeFont.
        if(dataArg.section === 'body' && currencyCols.includes(dataArg.column.index)){
          dataArg.cell.text = [];
        }
      },
      didDrawCell: (dataArg) => {
        if(dataArg.section === 'body' && currencyCols.includes(dataArg.column.index)){
          const raw = Array.isArray(dataArg.cell.raw) ? dataArg.cell.raw.join(' ') : String(dataArg.cell.raw);
          const st = dataArg.cell.styles;
          doc.setFont('helvetica', st.fontStyle === 'bold' ? 'bold' : 'normal');
          doc.setFontSize(st.fontSize);
          const tc = st.textColor;
          if(Array.isArray(tc)) doc.setTextColor(tc[0], tc[1], tc[2]); else doc.setTextColor(tc);
          const pos = dataArg.cell.getTextPos();
          drawCurrencyText(doc, raw, pos.x, pos.y, { align: st.halign || 'left' });
        }
      },
      didDrawPage: (dataArg) => {
        // Continuation pages created by the table itself also get the repeating header.
        if(dataArg.pageNumber > 1){ drawQuotationHeader(doc, lh, pageWidth, marginX, docTitleText); }
      }
    });

    const finalY = (doc.lastAutoTable && doc.lastAutoTable.finalY) ? doc.lastAutoTable.finalY : y + 20;

    const totalsRows = [
      { label: 'Sub Total', value: `₹ ${fmtMoney(data.subTotal)}` }
    ];
    if(data.taxTotal) totalsRows.push({ label: 'Tax Amount', value: `₹ ${fmtMoney(data.taxTotal)}` });
    if(data.packingFinal) totalsRows.push({ label: `Packing Charges${data.packingTax?` (+${data.packingTax}% tax)`:''}`, value: `₹ ${fmtMoney(data.packingFinal)}` });
    if(data.freightFinal) totalsRows.push({ label: `Freight Charges${data.freightTax?` (+${data.freightTax}% tax)`:''}`, value: `₹ ${fmtMoney(data.freightFinal)}` });
    if(data.otherFinal) totalsRows.push({ label: `Other Charges${data.otherTax?` (+${data.otherTax}% tax)`:''}`, value: `₹ ${fmtMoney(data.otherFinal)}` });
    if(data.roundOff) totalsRows.push({ label: 'Round Off', value: `${data.roundOff>0?'+':''}₹ ${fmtMoney(data.roundOff)}` });
    totalsRows.push({ label: 'Total Amount', value: `₹ ${fmtMoney(data.total)}`, grand: true });

    const totalsBoxWidth = 90;
    const totalsBoxX = pageWidth - marginX - totalsBoxWidth;
    const wordsWidth = Math.max(60, totalsBoxX - marginX - 10);
    doc.setFont('helvetica','normal'); doc.setFontSize(9);
    const wordsLines = doc.splitTextToSize(amountInWords(data.total), wordsWidth);
    const hideBankQr = (SALES_DOC_CONFIG[salesDoc.type] || {}).hideBankQr;
    const bankRows = hideBankQr ? [] : [
      lh.bankName ? ['Bank Name', lh.bankName] : null,
      lh.bankAcNo ? ['A/c No.', lh.bankAcNo] : null,
      lh.bankIfsc ? ['IFSC Code', lh.bankIfsc] : null,
      lh.bankBranch ? ['Branch Name', lh.bankBranch] : null
    ].filter(Boolean);
    // Estimate the height this whole block (totals box / amount-in-words / bank details) needs, and
    // start a fresh page — with the repeating header — if it wouldn't fit above the footer band.
    const totalsBoxHeightEst = totalsRows.reduce((s,r)=> s + (r.grand ? 10 : 7.5), 0);
    const wordsBlockHeightEst = 10.5 + wordsLines.length * 4.2 + (bankRows.length ? (8 + 5 + bankRows.length * 5) : 0);
    const totalsBlockNeeded = 8 + Math.max(totalsBoxHeightEst, wordsBlockHeightEst);
    let totalsBoxY;
    if(finalY + totalsBlockNeeded > pageHeight - effectiveBottomMargin){
      doc.addPage();
      totalsBoxY = drawQuotationHeader(doc, lh, pageWidth, marginX, docTitleText) + 4;
    } else {
      totalsBoxY = finalY + (docSharp ? 0 : 8);   // Format 2: the amount section joins the item table
    }
    const totalsBottomY = drawTotalsBox(doc, totalsRows, totalsBoxX, totalsBoxY, totalsBoxWidth);

    // Format 2: "Total amount in words" gets its own bordered box, same top, bottom and border as the totals box beside it.
    const wordsPadX = docSharp ? 4 : 0;
    if(docSharp){
      doc.setDrawColor(210,210,210); doc.setLineWidth(0.2);
      doc.rect(marginX, totalsBoxY, totalsBoxX - marginX, Math.max(totalsBottomY - totalsBoxY, 10.5 + wordsLines.length * 4.2 + 2));
    }
    doc.setFont('helvetica','bold'); doc.setFontSize(7.5); doc.setTextColor(140,140,140);
    doc.text('TOTAL AMOUNT (IN WORDS)', marginX + wordsPadX, totalsBoxY + 4 + (docSharp ? 2 : 0));
    // A touch more room between this label and the words below it than a plain 5mm baseline
    // step gives — at these font sizes that left them looking almost joined together.
    doc.setFont('helvetica','normal'); doc.setFontSize(9); doc.setTextColor(50,50,50);
    doc.text(wordsLines, marginX + wordsPadX, totalsBoxY + 10.5 + (docSharp ? 2 : 0));

    // Bank Details (left) and the payment QR code (right) sit side by side on the same row,
    // below whichever of the totals box / amount-in-words block ends lower.
    const wordsBottomY = totalsBoxY + 10.5 + wordsLines.length * 4.2;
    const sectionY = Math.max(wordsBottomY + (docSharp ? 3 : 0), totalsBottomY) + 8;
    const qrSize = 28;

    let bankBottomY = sectionY;
    if(bankRows.length){
      let by = sectionY;
      doc.setFont('helvetica','bold'); doc.setFontSize(7.5); doc.setTextColor(140,140,140);
      doc.text('BANK DETAILS', marginX, by);
      by += 6.5;
      doc.setFont('helvetica','normal'); doc.setFontSize(9); doc.setTextColor(50,50,50);
      bankRows.forEach(([label, value]) => {
        doc.setTextColor(120,120,120);
        doc.text(`${label}:`, marginX, by);
        doc.setTextColor(50,50,50);
        doc.text(String(value), marginX + 32, by);
        by += 5;
      });
      bankBottomY = by;
    }

    let qrBottomY = sectionY;
    if(lh.paymentQr && !hideBankQr){
      try{
        const fmt = /^data:image\/jpe?g/i.test(lh.paymentQr) ? 'JPEG' : 'PNG';
        const qrAspect = lh.paymentQrAspect || 1;
        const { w: qrW, h: qrH } = fitBox(qrAspect, qrSize, qrSize);
        const qrX = pageWidth - marginX - qrSize;
        doc.setFont('helvetica','bold'); doc.setFontSize(7.5); doc.setTextColor(140,140,140);
        doc.text('SCAN TO PAY', qrX, sectionY);
        doc.addImage(lh.paymentQr, fmt, qrX, sectionY + 3, qrW, qrH);
        qrBottomY = sectionY + 3 + qrH;
      }catch(e){ /* ignore malformed QR image */ }
    }

    let sy = Math.max(bankBottomY, qrBottomY);

    const quotationTerms = (salesDoc.terms && salesDoc.terms.length) ? salesDoc.terms : branchTerms(salesDoc.branch);
    const termsHeightEst = 5 + quotationTerms.length * 5;
    const signatureHeightEst = 16 + 10;
    const termsBlockNeeded = Math.max(termsHeightEst, signatureHeightEst) + 14;
    let ty = sy + 8;
    if(ty + termsBlockNeeded > pageHeight - effectiveBottomMargin){
      doc.addPage();
      ty = drawQuotationHeader(doc, lh, pageWidth, marginX, docTitleText);
    }

    // Terms & Conditions (left) and the Authorized Signatory block (right) also share the same row.
    const termsStartY = ty;
    doc.setFont('helvetica','bold'); doc.setFontSize(9); doc.setTextColor(140,140,140);
    doc.text('TERMS & CONDITIONS', marginX, termsStartY);
    let termsY = termsStartY + 5;
    doc.setFont('helvetica','normal'); doc.setFontSize(8.5); doc.setTextColor(90,90,90);
    quotationTerms.forEach((t,i) => { doc.text(`${i+1}. ${t}`, marginX, termsY); termsY += 5; });

    doc.setFont('helvetica','bold'); doc.setFontSize(10); doc.setTextColor(30,30,30);
    const footerText = (docTheme.footerLabel && docTheme.footerLabel !== DEFAULT_DOC_THEME.footerLabel) ? docTheme.footerLabel : `For ${lh.companyName}`;
    doc.text(footerText, pageWidth - marginX, termsStartY, { align: 'right' });
    doc.setFont('helvetica','normal'); doc.setFontSize(8.5); doc.setTextColor(140,140,140);
    doc.text(docTheme.signatoryLabel || DEFAULT_DOC_THEME.signatoryLabel, pageWidth - marginX, termsStartY + 16, { align: 'right' });

    // Draw the footer (promotional banner) image at a fixed position on the bottom of every page.
    if(lh.footerImage){
      try{
        const fmt = /^data:image\/jpe?g/i.test(lh.footerImage) ? 'JPEG' : 'PNG';
        const footerImgY = pageHeight - bottomMargin - footerImgH;
        const totalPages = doc.internal.getNumberOfPages();
        for(let p = 1; p <= totalPages; p++){
          doc.setPage(p);
          doc.addImage(lh.footerImage, fmt, marginX, footerImgY, footerImgW, footerImgH);
        }
      }catch(e){ /* ignore malformed footer image */ }
    }

    const pdfFileSlug = (s) => (s||'').trim().replace(/[^a-z0-9]+/gi,'-').replace(/^-+|-+$/g,'');
    const pdfFileName = [pdfFileSlug(salesDoc.docNumber) || 'draft', pdfFileSlug(salesDoc.customerName)].filter(Boolean).join('-');
    savePdfBlob(doc, `${pdfFileName}.pdf`, false, salesDoc.branch);
  }catch(err){
    console.error(err);
    customAlert('PDF export failed: ' + err.message);
  }
}
function buildQuotationPrintHtml(salesDoc){
    const data = computeQuotationDocData(salesDoc);
    const company = companies.find(c => c.id === salesDoc.customerId);
    const contact = company ? (company.contacts||[]).find(ct => ct.id === salesDoc.contactId) : null;
    const lh = branchLetterhead(salesDoc.branch);
    const accent = lh.accentColor || docTheme.accentColor || DEFAULT_DOC_THEME.accentColor;
    // Same shared layout as the PDF (printQuotationPdf) — only the title and a couple of field
    // labels change per document type.
    const docCfg = SALES_DOC_CONFIG[salesDoc.type] || SALES_DOC_CONFIG.quotation;
    const docLabel = docCfg.label || 'Quotation';
    const docNumberLabel = docCfg.docNumberLabel || 'Quotation Number';
    const rows = data.items.map(it => `
      <tr>
        <td>${it.srNo}</td>
        <td style="white-space:pre-wrap;">${escapeHtml(it.itemName)}</td>
        <td class="num">${it.qty}</td>
        <td class="num">${escapeHtml(it.unit||'—')}</td>
        <td class="num">₹ ${fmtMoney(it.displayRate)}</td>
        ${data.showDiscount ? `<td class="num">${it.discount}%</td>` : ''}
        <td class="num">${it.tax}%</td>
        <td class="num">₹ ${fmtMoney(it.amount)}</td>
      </tr>
    `).join('');
    const quotationTerms = (salesDoc.terms && salesDoc.terms.length) ? salesDoc.terms : branchTerms(salesDoc.branch);
    const termsHtml = quotationTerms.map((t,i)=>`<li>${escapeHtml(t)}</li>`).join('');
    const logoHtml = docTheme.showLogo !== false ? `<img src="${lh.logo}" style="max-width:100%; max-height:100%; object-fit:contain;">` : '';
    const dealerLogoHtml = lh.dealershipLogo ? `<img src="${lh.dealershipLogo}" style="max-width:100%; max-height:100%; object-fit:contain;">` : '';
    const lhAddressLines = splitAddressTwoLines(lh.address).map(l => escapeHtml(l));
    const lhRegBits = [lh.gstNumber ? `GSTIN: ${escapeHtml(lh.gstNumber)}` : '', lh.udyamNumber ? `Udyam: ${escapeHtml(lh.udyamNumber)}` : ''].filter(Boolean).join(' &nbsp;|&nbsp; ');
    const hideBankQr = docCfg.hideBankQr;
    const bankRowsArr = hideBankQr ? [] : [
      lh.bankName ? ['Bank Name', lh.bankName] : null,
      lh.bankAcNo ? ['A/c No.', lh.bankAcNo] : null,
      lh.bankIfsc ? ['IFSC Code', lh.bankIfsc] : null,
      lh.bankBranch ? ['Branch Name', lh.bankBranch] : null
    ].filter(Boolean);
    const bankDetailsHtml = bankRowsArr.length ? `
      <div class="bank-details">
        <div class="bd-label">Bank Details</div>
        ${bankRowsArr.map(([label,value]) => `<div class="bd-row"><span>${escapeHtml(label)}:</span> ${escapeHtml(value)}</div>`).join('')}
      </div>
    ` : '<div></div>';
    const companyBlockHtml = `
      <div class="company-block">
        <div class="company-name">${escapeHtml(lh.companyName)}</div>
        ${lhAddressLines.map(l => `<div class="company-line"><span class="ico">📍</span>${l}</div>`).join('')}
        ${lh.phone ? `<div class="company-line"><span class="ico">☎</span>${escapeHtml(lh.phone)}</div>` : ''}
        ${lh.mobile ? `<div class="company-line"><span class="ico">📱</span>${escapeHtml(lh.mobile)}</div>` : ''}
        ${(lh.email || lh.website) ? `<div class="company-line">${lh.email ? `<span class="ico">✉</span>${escapeHtml(lh.email)}` : ''}${(lh.email && lh.website) ? '&nbsp;&nbsp;' : ''}${lh.website ? `<span class="ico">🌐</span>${escapeHtml(lh.website)}` : ''}</div>` : ''}
        ${lhRegBits ? `<div class="company-line">${lhRegBits}</div>` : ''}
      </div>
    `;
    const validTillDisplay = salesDoc.validTill ? new Date(salesDoc.validTill).toLocaleDateString('en-IN') : '—';
    const refDateDisplay = salesDoc.refDate ? new Date(salesDoc.refDate).toLocaleDateString('en-IN') : '—';
    const salesPersonBits = [salesDoc.salesPersonName||'', salesDoc.salesPersonPhone||''].filter(Boolean).join(' / ') || '—';
    const showValidTillRow = docCfg.hasValidTill !== false;
    const showSalesPersonRow = docCfg.hasSalesPerson !== false && !docCfg.hideSalesPersonInPrint;
    const showPaymentTermsRow = docCfg.hasPaymentTerms !== false;
    const quoteMetaRows = [
      [ { label: docNumberLabel, value: escapeHtml(salesDoc.docNumber || '—') }, { label: 'Date', value: salesDoc.date ? new Date(salesDoc.date).toLocaleDateString('en-IN') : '—' } ],
      [ { label: 'Reference Number', value: escapeHtml(salesDoc.refNo || '—') }, { label: 'Reference Date', value: refDateDisplay } ]
    ];
    if(showValidTillRow || showSalesPersonRow){
      const row = [];
      if(showValidTillRow) row.push({ label: `${docLabel} Valid Till`, value: validTillDisplay });
      if(showSalesPersonRow) row.push({ label: 'Sales Person Details', value: escapeHtml(salesPersonBits) });
      quoteMetaRows.push(row);
    }
    if(showPaymentTermsRow) quoteMetaRows.push([ { label: 'Payment Terms', value: escapeHtml(salesDoc.paymentTerms || '—') } ]);
    if((docCfg.extra||[]).includes('vehicle') || (docCfg.extra||[]).includes('transport')){
      quoteMetaRows.push([
        { label: 'Vehicle Number', value: escapeHtml(salesDoc.vehicle || '—') },
        { label: 'Transport Name', value: escapeHtml(salesDoc.transport || '—') }
      ]);
    }
    const quoteMetaHtml = `
      <div class="quote-meta-stack">
        ${quoteMetaRows.map(row => `<div class="qms-row-pair">${row.map(c => `<div class="qms-cell"><span>${c.label}</span><strong>${c.value}</strong></div>`).join('')}</div>`).join('')}
      </div>
    `;
    const customerDetailsHtml = `
      <div class="to-label">Customer Details</div>
      <div class="customer">${escapeHtml(salesDoc.customerName||'—')}</div>
      ${companyFullAddress(company) ? `<div><span class="ico">📍</span>${escapeHtml(companyFullAddress(company))}</div>` : ''}
      ${company && company.gstNumber ? `<div>GSTIN: ${escapeHtml(company.gstNumber)}</div>` : ''}
      ${salesDoc.contactName ? `<div>Attn: ${escapeHtml(salesDoc.contactName)}</div>` : ''}
      ${contact && contact.phone ? `<div><span class="ico">☎</span>${escapeHtml(contact.phone)}</div>` : ''}
    `;
    const html = `
      <!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(docLabel)} ${escapeHtml(salesDoc.docNumber||'')}</title>
      <style>
        body{ font-family: Arial, Helvetica, sans-serif; color:#1e1e1e; margin:24px; }
        .head-3col{ display:flex; align-items:flex-start; justify-content:space-between; border-bottom:1px solid #ddd; padding-bottom:14px; margin-bottom:10px; gap:14px; }
        .head-logo{ flex:0 0 auto; width:120px; height:120px; display:flex; align-items:center; justify-content:flex-start; }
        .head-dealer{ flex:0 0 auto; width:145px; height:145px; display:flex; align-items:center; justify-content:flex-end; }
        .head-company{ flex:1; min-width:0; display:flex; align-items:flex-start; }
        .doc-title-wrap{ text-align:center; margin:0 0 6px 0; }
        .doc-title{ display:inline-block; font-size:13px; letter-spacing:.04em; margin:0; padding:5px 18px; }
        .company-block{ font-size:10.5px; color:#666; line-height:1.5; text-align:left; }
        .company-block .company-name{ font-size:15px; font-weight:700; color:#1e1e1e; margin-bottom:2px; }
        .company-block .company-line{ max-width:420px; margin:0; }
        .ico{ display:inline-block; margin-right:5px; }
        .to-label{ font-size:10px; letter-spacing:.05em; color:#999; text-transform:uppercase; }
        .customer{ font-size:12px; font-weight:700; margin:4px 0; }
        table{ width:100%; border-collapse:collapse; margin-top:16px; font-size:12px; }
        th{ background:${accent}; color:#fff; text-align:left; padding:8px; }
        td{ border:1px solid #ddd; padding:8px; vertical-align:top; }
        th.num, td.num{ text-align:right; }
        .totals-wrap{ display:flex; justify-content:space-between; align-items:flex-end; margin-top:14px; gap:24px; }
        .amount-words{ flex:1; min-width:0; padding-bottom:2px; }
        .amount-words .aw-label{ font-size:9.5px; letter-spacing:.04em; color:#999; text-transform:uppercase; margin-bottom:3px; }
        .amount-words .aw-value{ font-size:11.5px; font-weight:600; color:#333; line-height:1.5; }
        .bank-qr-row{ display:flex; justify-content:space-between; align-items:flex-start; margin-top:12px; gap:24px; }
        .bank-qr-left{ flex:1; min-width:0; }
        .bank-details{ margin-top:0; }
        .bank-details .bd-label{ font-size:9.5px; letter-spacing:.04em; color:#999; text-transform:uppercase; margin-bottom:3px; }
        .bank-details .bd-row{ font-size:10.5px; color:#444; line-height:1.6; }
        .bank-details .bd-row span{ color:#888; }
        .totals{ width:300px; flex-shrink:0; font-size:12.5px; border:1px solid #ddd; border-radius:6px; overflow:hidden; }
        .totals-row{ display:flex; justify-content:space-between; gap:14px; padding:8px 14px; border-bottom:1px solid #eee; }
        .totals-row span:first-child{ color:#666; }
        .totals-row span:last-child{ font-weight:600; white-space:nowrap; }
        .totals-row.grand{ font-weight:700; font-size:14px; background:#faf8f4; border-bottom:none; padding-top:10px; padding-bottom:10px; }
        .totals-row.grand span{ font-weight:700 !important; color:#1e1e1e !important; }
        .two-col-section{ display:flex; gap:20px; margin-top:0; align-items:stretch; }
        .two-col-left{ flex:1; min-width:0; border:1px solid #ddd; border-radius:6px; padding:9px 14px; }
        .two-col-right{ flex:1; min-width:0; display:flex; flex-direction:column; }
        .quote-meta-stack{ border:1px solid #ddd; border-radius:6px; overflow:hidden; flex:1; display:flex; flex-direction:column; }
        .qms-row-pair:last-child{ flex:1; }
        .qms-row-pair{ display:flex; border-top:1px solid #ddd; }
        .qms-row-pair:first-child{ border-top:none; }
        .qms-cell{ flex:1; min-width:0; display:flex; flex-direction:column; gap:0px; padding:3px 12px; justify-content:center; }
        .qms-cell:not(:first-child){ border-left:1px solid #ddd; }
        .qms-cell span{ color:#999; font-size:7.5px; text-transform:uppercase; letter-spacing:.04em; line-height:1.2; }
        .qms-cell strong{ font-size:10px; font-weight:600; line-height:1.25; }
        .payment-qr{ margin-top:0; flex-shrink:0; }
        .payment-qr .pq-label{ font-size:9.5px; letter-spacing:.04em; color:#999; text-transform:uppercase; margin-bottom:5px; }
        .payment-qr img{ width:100px; height:100px; object-fit:contain; border:1px solid #ddd; border-radius:6px; padding:4px; }
        .terms-footer-row{ display:flex; justify-content:space-between; align-items:flex-start; margin-top:26px; gap:24px; }
        .terms{ margin-top:0; font-size:10.5px; color:#555; flex:1; min-width:0; }
        .terms h4{ font-size:10px; letter-spacing:.05em; color:#999; text-transform:uppercase; margin-bottom:6px; }
        .footer{ margin-top:0; text-align:right; font-size:12px; flex-shrink:0; }
        .footer .sig{ margin-top:40px; color:#999; font-size:10.5px; }
        .footer-image-wrap{ margin-top:22px; text-align:left; clear:both; }
        .footer-image-wrap img{ max-width:100%; max-height:90px; object-fit:contain; }
        .page-table{ width:100%; border-collapse:collapse; margin-top:0; }
        .page-table > thead > tr > td, .page-table > tfoot > tr > td, .page-table > tbody > tr > td{ padding:0; border:none; }
        .page-table > thead .doc-title-wrap{ margin-bottom:6px; }
        ${lh.docFormat === 2 ? `
        .two-col-section{ gap:0 !important; }
        .two-col-left, .quote-meta-stack, .totals, .payment-qr img{ border-radius:0 !important; }
        .quote-meta-stack{ border-left:none !important; }
        .two-col-section + table{ margin-top:0 !important; }
        .totals-wrap{ margin-top:0 !important; gap:0 !important; align-items:stretch !important; }
        .amount-words{ border:1px solid #ddd; border-top:none; border-right:none; padding:10px 14px !important; display:flex; flex-direction:column; justify-content:center; }
        .totals{ border-top:none !important; }` : ''}
        @media print{ body{ margin:5mm 5mm 5mm 5mm; } }
      </style></head>
      <body>
        <table class="page-table">
          <thead><tr><td>
            <div class="head-3col">
              <div class="head-col head-logo">${logoHtml}</div>
              <div class="head-col head-company">${companyBlockHtml}</div>
              ${lh.dealershipLogo ? `<div class="head-col head-dealer">${dealerLogoHtml}</div>` : ''}
            </div>
            <div class="doc-title-wrap"><h1 class="doc-title">${escapeHtml(docLabel.toUpperCase())}</h1></div>
          </td></tr></thead>
          ${lh.footerImage ? `<tfoot><tr><td><div class="footer-image-wrap"><img src="${lh.footerImage}" alt="Footer image"></div></td></tr></tfoot>` : ''}
          <tbody><tr><td>
            <div class="two-col-section">
              <div class="two-col-left">${customerDetailsHtml}</div>
              <div class="two-col-right">${quoteMetaHtml}</div>
            </div>
            <table>
              <thead><tr>
                <th>#</th><th>Item &amp; Description</th><th class="num">Qty</th><th class="num">Unit</th><th class="num">Rate</th>
                ${data.showDiscount ? '<th class="num">Discount %</th>' : ''}
                <th class="num">Tax %</th><th class="num">Amount</th>
              </tr></thead>
              <tbody>${rows}</tbody>
            </table>
            <div class="totals-wrap">
              <div class="amount-words">
                <div class="aw-label">Total Amount (in words)</div>
                <div class="aw-value">${escapeHtml(amountInWords(data.total))}</div>
              </div>
              <div class="totals">
                <div class="totals-row"><span>Sub Total</span><span>₹ ${fmtMoney(data.subTotal)}</span></div>
                ${data.taxTotal ? `<div class="totals-row"><span>Tax Amount</span><span>₹ ${fmtMoney(data.taxTotal)}</span></div>` : ''}
                ${data.packingFinal ? `<div class="totals-row"><span>Packing Charges${data.packingTax?` (+${data.packingTax}% tax)`:''}</span><span>₹ ${fmtMoney(data.packingFinal)}</span></div>` : ''}
                ${data.freightFinal ? `<div class="totals-row"><span>Freight Charges${data.freightTax?` (+${data.freightTax}% tax)`:''}</span><span>₹ ${fmtMoney(data.freightFinal)}</span></div>` : ''}
                ${data.otherFinal ? `<div class="totals-row"><span>Other Charges${data.otherTax?` (+${data.otherTax}% tax)`:''}</span><span>₹ ${fmtMoney(data.otherFinal)}</span></div>` : ''}
                ${data.roundOff ? `<div class="totals-row"><span>Round Off</span><span>${data.roundOff>0?'+':''}₹ ${fmtMoney(data.roundOff)}</span></div>` : ''}
                <div class="totals-row grand"><span>Total Amount</span><span>₹ ${fmtMoney(data.total)}</span></div>
              </div>
            </div>
            ${hideBankQr ? '' : `
            <div class="bank-qr-row">
              <div class="bank-qr-left">${bankDetailsHtml}</div>
              ${lh.paymentQr ? `
              <div class="payment-qr">
                <div class="pq-label">Scan to Pay</div>
                <img src="${lh.paymentQr}" alt="Payment QR code">
              </div>` : ''}
            </div>`}
            <div class="terms-footer-row">
              <div class="terms">
                <h4>Terms &amp; Conditions</h4>
                <ol>${termsHtml}</ol>
              </div>
              <div class="footer">
                <div><strong>${escapeHtml((docTheme.footerLabel && docTheme.footerLabel !== DEFAULT_DOC_THEME.footerLabel) ? docTheme.footerLabel : `For ${lh.companyName}`)}</strong></div>
                <div class="sig">${escapeHtml(docTheme.signatoryLabel || DEFAULT_DOC_THEME.signatoryLabel)}</div>
              </div>
            </div>
          </td></tr></tbody>
        </table>
      ${wmHtml(salesDoc.branch)}
      </body></html>
    `;
    return html;
}
const LABEL_TYPES = ['quotation','dc','proforma','po'];
const LABEL_SIZES = [
  { key:'a4',  label:'A4 (210 × 297 mm)',      w:210,   h:297   },
  { key:'a5',  label:'A5 (148 × 210 mm)',      w:148,   h:210   },
  { key:'4x4', label:'4 × 4 inch',             w:101.6, h:101.6 },
  { key:'6x4', label:'6 × 4 inch (portrait)',  w:101.6, h:152.4 }
];
let labelSizeKey = 'a4';
function labelPartsFromDoc(salesDoc){
  const company = companies.find(c => c.id === salesDoc.customerId) || {};
  const contact = (company.contacts||[]).find(ct => ct.id === salesDoc.contactId) || {};
  return {
    branch: salesDoc.branch,
    customer: salesDoc.customerName || company.name || '—',
    addrLines: [company.address].map(v => (v||'').trim()).filter(Boolean),
    area: (company.area||'').trim(),
    cityLine: [company.city, company.state].map(v => (v||'').trim()).filter(Boolean).join(', '),
    pin: (company.pincode||'').trim(),
    attn: salesDoc.contactName || contact.name || '',
    phone: (contact.phone || contact.phone2 || '').trim(),
    transport: salesDoc.transport || company.transportPreference || '',
    courier: company.courierPreference || '',
    vehicle: salesDoc.vehicle || '',
    ref: ((SALES_DOC_CONFIG[salesDoc.type]||{}).label || 'Document') + (salesDoc.docNumber ? ' ' + salesDoc.docNumber : ''),
    date: salesDoc.date ? new Date(salesDoc.date).toLocaleDateString('en-IN') : ''
  };
}
// One layout engine feeds BOTH the print page and the PDF, so they always look the same. It positions every line in millimetres
// and shrinks the text until everything fits the chosen paper.
function labelLayout(P, i, n, size, md){
  const W = size.w, H = size.h, PT = 0.3528;
  const lh = branchLetterhead(P.branch);
  const f = Math.max(0.8, Math.min(2.5, Number(P.fromScale) || 1));   // user-chosen size of the FROM logo + address
  const fromBits = [lh.address, [lh.phone, lh.mobile].filter(Boolean).join(' / ')].filter(Boolean).join(' · ');
  const meta = [['TRANSPORT', P.transport], ['COURIER', P.courier], ['VEHICLE', P.vehicle]].filter(x => x[1]);   // no REF / DATE on labels
  const wrap = (t, sz, bold, w) => { md.setFont('helvetica', bold ? 'bold' : 'normal'); md.setFontSize(sz); return md.splitTextToSize(String(t), w); };
  const build = (k, wide) => {
    const els = []; const m = 6 * k;
    const put = (x, y, t, sz, bold, col, align) => els.push({ t:'text', x, y, text:t, sz, bold, col: col || '#111', align: align || 'left' });
    const para = (st, x, w, text, sz, bold, col, adv) => { const ls = wrap(text, sz, bold, w); ls.forEach((l, j) => put(x, st.y + sz * PT * 0.95 + j * sz * PT * (adv || 1.22), l, sz, bold, col)); st.y += ls.length * sz * PT * (adv || 1.22); };
    const dash = (x1, y1, x2, y2) => els.push({ t:'line', x1, y1, x2, y2, dash:true });
    els.push({ t:'rect', x:2, y:2, w:W-4, h:H-4, lw:0.4 });
    const colX = m, colW = wide ? W * 0.58 - m * 1.5 : W - 2 * m;
    const st = { y: m + 1 * k };
    // DELIVER TO is at the top; the sender (FROM: logo + company + address) is always at the bottom.
    put(colX, st.y + 7 * k * PT * 0.95, 'DELIVER TO', 7 * k, false, '#6e6e6e'); st.y += 4.5 * k;
    para(st, colX, colW, P.customer || '—', 16 * k, true, '#111', 1.15); st.y += 1 * k;
    (P.addrLines || []).forEach(l => para(st, colX, colW, l, 12 * k, false, '#111', 1.3));
    if(P.area) para(st, colX, colW, P.area, 14 * k, true, '#111', 1.3);   // area name in bold
    if(P.cityLine) para(st, colX, colW, P.cityLine, 12 * k, false, '#111', 1.3);
    if(P.pin){ st.y += 1.5 * k; para(st, colX, colW, 'PIN ' + P.pin, 14 * k, true); }
    if(P.attn){ st.y += 1.5 * k; para(st, colX, colW, 'Attn: ' + P.attn, 11 * k, false); }
    if(P.phone){ st.y += 0.5 * k; para(st, colX, colW, 'Ph: ' + P.phone, 13 * k, true); }
    // FROM block: drawn from y=0, then moved down to the bottom of the label.
    const i0 = els.length, fs = { y: 0 }; let tx = colX, tw = colW;
    if(lh.logo){
      const asp = lh.logoAspect || 1, lgH = 11 * k * f, lgW = Math.min(asp * lgH, colW * (f > 1 ? 0.55 : 0.42));
      els.push({ t:'img', src: lh.logo, x: colX, y: 0, w: lgW, h: lgW / asp > lgH ? lgH : lgW / asp });
      tx = colX + lgW + 3 * k; tw = colW - lgW - 3 * k;
    }
    put(tx, 7 * k * f * PT * 0.95, 'FROM', 7 * k * f, false, '#6e6e6e'); fs.y += 4 * k * f;
    para(fs, tx, tw, lh.companyName || '', 9 * k * f, true);
    para(fs, tx, tw, fromBits, 8 * k * f, false, '#333');
    if(lh.logo) fs.y = Math.max(fs.y, 11 * k * f);
    const fromTop = H - m - fs.y;
    for(let q = i0; q < els.length; q++){ const x = els[q]; if(x.t === 'line'){ x.y1 += fromTop; x.y2 += fromTop; } else x.y += fromTop; }
    dash(colX, fromTop - 2.5 * k, colX + colW, fromTop - 2.5 * k);
    let fits;
    if(!wide){
      const boxH = 10 * k, boxY = fromTop - 5 * k - boxH, rows = Math.ceil(meta.length / 2), rowH = 8 * k;
      const metaTop = boxY - 3 * k - rows * rowH;
      dash(m, metaTop - 2 * k, W - m, metaTop - 2 * k);
      meta.forEach((x, q) => { const cx = m + (q % 2) * (colW / 2), cy = metaTop + Math.floor(q / 2) * rowH;
        put(cx, cy + 6 * k * PT * 0.95, x[0], 6 * k, false, '#787878');
        put(cx, cy + 3.2 * k + 9 * k * PT * 0.95, wrap(x[1], 9 * k, true, colW / 2 - 2 * k)[0], 9 * k, true); });
      els.push({ t:'rect', x:m, y:boxY, w:colW, h:boxH, lw:0.5 });
      put(W / 2, boxY + boxH / 2 + 14 * k * PT * 0.35, `BOX ${i} OF ${n}`, 14 * k, true, '#111', 'center');
      fits = st.y <= metaTop - 4 * k;
    } else {
      const X = W * 0.58 + m * 0.5, RW = W - X - m;
      dash(W * 0.58, m, W * 0.58, H - m);
      const rs = { y: m + 1 * k };
      meta.forEach(x => { put(X, rs.y + 6 * k * PT * 0.95, x[0], 6 * k, false, '#787878'); rs.y += 3 * k; para(rs, X, RW, x[1], 10 * k, true); rs.y += 2 * k; });
      const boxH = 14 * k, boxY = H - m - boxH;
      els.push({ t:'rect', x:X, y:boxY, w:RW, h:boxH, lw:0.5 });
      put(X + RW / 2, boxY + boxH / 2 + 13 * k * PT * 0.35, `BOX ${i} OF ${n}`, 13 * k, true, '#111', 'center');
      fits = st.y <= fromTop - 4 * k && rs.y <= boxY - 2 * k;
    }
    return { els, fits };
  };
  const wide = W > H * 1.2;
  let k = wide ? H / 100 : W / 105, out = build(k, wide);
  for(let t = 0; t < 40 && !out.fits && k > 0.3; t++){ k *= 0.94; out = build(k, wide); }
  return out.els;
}
const LABEL_SHEET = { w:210, h:297 };
// Pages for print/PDF. On an A4 sheet each label keeps its ORIGINAL size (smaller labels are tiled); otherwise the page is the label size.
function labelPages(P, n, size, md, onSheet){
  const shift = (x, ox, oy) => x.t === 'line' ? Object.assign({}, x, { x1:x.x1+ox, x2:x.x2+ox, y1:x.y1+oy, y2:x.y2+oy }) : Object.assign({}, x, { x:x.x+ox, y:x.y+oy });
  const tile = onSheet && size.w < LABEL_SHEET.w && size.h < LABEL_SHEET.h;
  if(!tile){ const sheet = onSheet; const pw = sheet ? LABEL_SHEET.w : size.w, ph = sheet ? LABEL_SHEET.h : size.h;
    return { pw, ph, pages: Array.from({ length:n }, (_, q) => labelLayout(P, q+1, n, size, md).map(x => (onSheet && size.w === pw) ? x : x)) }; }
  // choose portrait or landscape A4 (and a 5 mm or 0 mm margin) so the most labels fit at their original size
  let best = null;
  [[LABEL_SHEET.w, LABEL_SHEET.h], [LABEL_SHEET.h, LABEL_SHEET.w]].forEach(([sw, sh]) => [5, 0].forEach(m => {
    const cols = Math.floor((sw - 2*m) / size.w), rows = Math.floor((sh - 2*m) / size.h);
    if(cols >= 1 && rows >= 1 && (!best || cols*rows > best.per)) best = { sw, sh, m, cols, rows, per: cols*rows };
  }));
  if(!best) return { pw: LABEL_SHEET.w, ph: LABEL_SHEET.h, pages: Array.from({ length:n }, (_, q) => labelLayout(P, q+1, n, size, md)) };
  const { sw, sh, m, cols, per } = best;
  const ox0 = (sw - cols*size.w) / 2, oy0 = m;
  const pages = [];
  for(let q = 0; q < n; q++){
    const pg = Math.floor(q / per), pos = q % per; if(!pages[pg]) pages[pg] = [];
    const ox = ox0 + (pos % cols) * size.w, oy = oy0 + Math.floor(pos / cols) * size.h;
    labelLayout(P, q+1, n, size, md).forEach(x => pages[pg].push(shift(x, ox, oy)));
  }
  return { pw: sw, ph: sh, pages };
}
function labelHtml(P, n, size, onSheet){
  const { jsPDF } = window.jspdf; const md = new jsPDF({ unit:'mm', format:[size.w, size.h] });
  const PT = 0.3528, e = escapeHtml;
  const LP = labelPages(P, n, size, md, onSheet);
  const sections = LP.pages.map((pageEls) => {
    const els = pageEls.map(x => {
      if(x.t === 'rect') return `<div style="position:absolute;left:${x.x}mm;top:${x.y}mm;width:${x.w}mm;height:${x.h}mm;border:${x.lw}mm solid #111;"></div>`;
      if(x.t === 'img') return `<img src="${x.src}" style="position:absolute;left:${x.x}mm;top:${x.y}mm;width:${x.w}mm;height:${x.h}mm;object-fit:contain;">`;
      if(x.t === 'line') return x.x1 === x.x2 ? `<div style="position:absolute;left:${x.x1}mm;top:${x.y1}mm;height:${x.y2 - x.y1}mm;border-left:0.25mm dashed #888;"></div>` : `<div style="position:absolute;left:${x.x1}mm;top:${x.y1}mm;width:${x.x2 - x.x1}mm;border-top:0.25mm dashed #888;"></div>`;
      const top = x.y - 0.8465 * x.sz * PT;
      const pos = x.align === 'center' ? `left:${x.x - 100}mm;width:200mm;text-align:center;` : `left:${x.x}mm;`;
      return `<div style="position:absolute;${pos}top:${top}mm;font-size:${x.sz}pt;line-height:1;white-space:nowrap;font-weight:${x.bold ? 700 : 400};color:${x.col};">${e(x.text)}</div>`;
    }).join('');
    return `<section class="label" style="width:${LP.pw}mm;height:${LP.ph}mm;">${els}</section>`;
  }).join('');
  return `<!doctype html><html><head><meta charset="utf-8"><title>Shipping label</title><style>
    @page{ size:${LP.pw}mm ${LP.ph}mm; margin:0; } *{ box-sizing:border-box; }
    html,body{ margin:0; padding:0; width:${LP.pw}mm; zoom:1; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
    body{ font-family:Helvetica,Arial,sans-serif; }
    .label{ position:relative; overflow:hidden; flex:none; page-break-after:always; } .label:last-child{ page-break-after:auto; }
  </style></head><body>${sections}</body></html>`;
}
function labelPrintParts(P, n, size, onSheet){
  try{
    if(!window.jspdf || !window.jspdf.jsPDF){ customAlert("The PDF library didn't load — check your internet connection and try again."); return; }
    const html = labelHtml(P, n, size, onSheet);
    let iframe = document.getElementById('labelPrintIframe');
    if(!iframe){ iframe = document.createElement('iframe'); iframe.id = 'labelPrintIframe'; iframe.style.cssText = 'position:fixed; right:0; bottom:0; width:0; height:0; border:0;'; document.body.appendChild(iframe); }
    iframe.onload = () => { setTimeout(() => { try{ iframe.contentWindow.focus(); iframe.contentWindow.print(); }catch(err){ customAlert('Print failed: ' + err.message); } }, 150); };
    iframe.srcdoc = html;
  }catch(err){ console.error(err); customAlert('Could not create the label: ' + err.message); }
}
function labelPdfParts(P, n, size, fileBase, onSheet){
  try{
    if(!window.jspdf || !window.jspdf.jsPDF){ customAlert("PDF library didn't load — check your internet connection and try again."); return; }
    const { jsPDF } = window.jspdf;
    const LP = labelPages(P, n, size, new jsPDF({ unit:'mm', format:[size.w, size.h] }), onSheet);
    const ori = LP.pw > LP.ph ? 'landscape' : 'portrait';
    const doc = new jsPDF({ orientation: ori, unit:'mm', format:[LP.pw, LP.ph] });
    const rgb = h => { const v = parseInt(String(h).replace('#','').padEnd(6, String(h).replace('#','')[0] || '0'), 16); return [(v>>16)&255, (v>>8)&255, v&255]; };
    LP.pages.forEach((pageEls, pi) => {
      if(pi > 0) doc.addPage([LP.pw, LP.ph], ori);
      pageEls.forEach(x => {
        if(x.t === 'rect'){ doc.setDrawColor(17,17,17); doc.setLineWidth(x.lw); doc.rect(x.x, x.y, x.w, x.h); }
        else if(x.t === 'img'){ try{ doc.addImage(x.src, /^data:image\/jpe?g/i.test(x.src) ? 'JPEG' : 'PNG', x.x, x.y, x.w, x.h); }catch(err){ /* logo couldn't be drawn; label still prints */ } }
        else if(x.t === 'line'){ doc.setDrawColor(150,150,150); doc.setLineWidth(0.25); doc.setLineDashPattern([1,1], 0); doc.line(x.x1, x.y1, x.x2, x.y2); doc.setLineDashPattern([], 0); }
        else { doc.setFont('helvetica', x.bold ? 'bold' : 'normal'); doc.setFontSize(x.sz); const c = rgb(x.col); doc.setTextColor(c[0], c[1], c[2]); doc.text(x.text, x.x, x.y, x.align === 'center' ? { align:'center' } : undefined); }
      });
    });
    savePdfBlob(doc, (fileBase || 'shipping-label') + '.pdf', true);   // same download method as the other PDFs
  }catch(err){ console.error(err); customAlert('Could not create the label PDF: ' + err.message); }
}
function printQuotationPrint(salesDoc){
  try{
    const html = buildQuotationPrintHtml(salesDoc);
    let iframe = document.getElementById('quotPrintIframe');
    if(!iframe){
      iframe = document.createElement('iframe');
      iframe.id = 'quotPrintIframe';
      iframe.style.cssText = 'position:fixed; right:0; bottom:0; width:0; height:0; border:0;';
      document.body.appendChild(iframe);
    }
    iframe.onload = () => {
      setTimeout(() => {
        try{ iframe.contentWindow.focus(); iframe.contentWindow.print(); }catch(e){ console.error(e); customAlert('Print failed: ' + e.message); }
      }, 150);
    };
    iframe.srcdoc = html;
  }catch(err){
    console.error(err);
    customAlert('Print failed: ' + err.message);
  }
}

export function previewQuotationDoc(salesDoc) {
  try {
    const html = buildQuotationPrintHtml(salesDoc);
    el('quotPreviewFrame').srcdoc = html;
    el('quotPreviewPrintBtn').onclick = () => { try { el('quotPreviewFrame').contentWindow.focus(); el('quotPreviewFrame').contentWindow.print(); } catch (e) { console.error(e); customAlert('Print failed: ' + e.message); } };
    el('quotPreviewPdfBtn').onclick = () => printQuotationPdf(salesDoc);
    el('quotPreviewOverlay').classList.add('open');
  } catch (err) { console.error(err); customAlert('Preview failed: ' + err.message); }
}
export { printQuotationPdf, printQuotationPrint, buildQuotationPrintHtml, labelPdfParts, labelPrintParts, LABEL_SIZES, SALES_DOC_CONFIG, DEFAULT_DOC_THEME, DEFAULT_LOGO_ASPECT, amountInWords };
