"""Regenerates static/threesixty/js/doc_print_ref.js and rupee_font.js from the reference app's script: python gen_docprint.py <ref_app.js>."""
import sys
src = open(sys.argv[1]).read().split('\n')
L = lambda a, b: '\n'.join(src[a-1:b])
def block(start):                                   # a top-level construct up to its closing line
    for i in range(start, len(src)):
        if src[i] in ('}', '};'): return L(start, i + 1)
J = '/home/debjit/Desktop/Anupam/threesixty/static/threesixty/js/'
fonts = L(5527, 5528).replace('const RUPEE', 'export const RUPEE')
open(J + 'rupee_font.js', 'w').write('// The embedded DejaVu Sans subset (space + the rupee glyph) the reference uses so jsPDF can print the rupee sign.\n' + fonts + '\n')

header = '''// GENERATED from contact_management.html (tests/parity/gen_docprint.py): the reference's own code for the printed documents
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
'''
theme_end = next(i for i in range(92, 140) if src[i] == '};') + 1
body = [
 L(73, theme_end),                                  # DEFAULT_LOGO_ASPECT, fitBox, splitAddressTwoLines, DEFAULT_DOC_THEME
 L(106, 167),                                       # SALES_DOC_CONFIG
 block(476),                                        # hexToRgb
 block(4438).replace('(docTheme.terms && docTheme.terms.length) ? docTheme.terms : DEFAULT_DOC_THEME.terms', '(docTheme.terms && docTheme.terms.length) ? docTheme.terms : DEFAULT_DOC_THEME.terms'),
 L(5218, 5235),                                     # savePdfBlob
 L(5236, 5526),                                     # numberToWords ... drawQuotationHeader
 L(5529, 6090),                                     # rupee helpers, printQuotationPdf, buildQuotationPrintHtml
 L(6092, 6262),                                     # shipping label engine
 L(6317, 6337),                                     # printQuotationPrint
]
tail = '''
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
'''
open(J + 'doc_print_ref.js', 'w').write(header + '\n'.join(body) + '\n' + tail)
print('ok', theme_end)
