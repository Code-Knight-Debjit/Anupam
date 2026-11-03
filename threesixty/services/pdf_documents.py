"""PDF for quotations, proformas and delivery challans (REQUIREMENTS §4.1, §18).

One renderer serves Preview, Print and Download PDF, so they are identical
(the browser prints the same PDF). Square corners everywhere. Format 2 joins the
customer details, the number/date panel and the item table into ONE bordered
block and gives the totals box the same border; Format 1 keeps them as separate
boxes. Header (letterhead + logo), footer image and watermark are shared by both.
Challans carry no bank / QR block.
"""
import io
from datetime import date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from django.conf import settings
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from .errors import ServiceError
from .printing import amount_in_words, money, print_totals

PRINTABLE = {'quotation': 'QUOTATION', 'proforma': 'PROFORMA INVOICE', 'dc': 'DELIVERY CHALLAN'}
PAGE_W, PAGE_H = A4
MARGIN = 9 * mm
TOP, BOTTOM = 52 * mm, 22 * mm
DEFAULT_ACCENT = '#d97b2f'          # the reference's document accent

_base = ParagraphStyle('base', fontName='Helvetica', fontSize=8.5, leading=11)
SMALL = ParagraphStyle('small', parent=_base, fontSize=7.5, leading=9.5)
BOLD = ParagraphStyle('bold', parent=_base, fontName='Helvetica-Bold')
RIGHT = ParagraphStyle('right', parent=_base, alignment=2)
HEAD = ParagraphStyle('head', parent=_base, fontName='Helvetica-Bold', textColor=colors.white, alignment=1)


def _p(text, style=_base):
    return Paragraph(escape(str(text if text is not None else '')).replace('\n', '<br/>'), style)


def _num(value, places=2):
    return f'{value:,.{places}f}'


def _image_path(field):
    try:
        return field.path if field else None
    except (ValueError, NotImplementedError):
        return None


def _image(path, max_w, max_h):
    try:
        w, h = ImageReader(path).getSize()
    except Exception:
        return None
    scale = min(max_w / w, max_h / h, 1e6)
    return Image(path, width=w * scale, height=h * scale)


# --------------------------------------------------------------------------- page furniture
GREY, LINE, DARK = colors.HexColor('#999999'), colors.HexColor('#dddddd'), colors.HexColor('#1e1e1e')
DOC_LABEL = {'quotation': 'Quotation', 'proforma': 'Proforma Invoice', 'dc': 'Delivery Challan'}
DEFAULT_LOGO = 'threesixty/img/logo-on-light.png'
LABEL = ParagraphStyle('label', parent=_base, fontSize=6.5, leading=8, textColor=GREY)
CELL_VALUE = ParagraphStyle('cellvalue', parent=_base, fontName='Helvetica-Bold', fontSize=8.5, leading=10)
NUM = ParagraphStyle('num', parent=_base, alignment=2)
TH = ParagraphStyle('th', parent=_base, fontName='Helvetica-Bold', textColor=colors.white)
THR = ParagraphStyle('thr', parent=TH, alignment=2)
TOTAL_LABEL = ParagraphStyle('tl', parent=_base, textColor=colors.HexColor('#666666'))
GRAND = ParagraphStyle('grand', parent=_base, fontName='Helvetica-Bold', fontSize=10.5, leading=13)


def _accent(branch):
    try:
        return colors.HexColor(branch.accent_color or DEFAULT_ACCENT)
    except ValueError:
        return colors.HexColor(DEFAULT_ACCENT)


def _default_logo_path():
    """The app logo the Admin chose on the Branches page, else the built-in one."""
    from django.contrib.staticfiles import finders
    from . import branding
    chosen = branding.info('app')
    return chosen['path'] if chosen else finders.find(DEFAULT_LOGO)


def _fmt_date(d):
    return f'{d.day}/{d.month}/{d.year}' if d else '—'


def _rs(value):
    return 'Rs. ' + _num(money(value))


def _watermark(canvas, branch):
    if not branch.watermark_enabled:
        return
    canvas.saveState()
    canvas.setFillAlpha(0.08)
    size = max(10, min(100, branch.watermark_size or 50)) / 100
    if branch.watermark_type == 'text' and branch.watermark_text.strip():
        canvas.translate(PAGE_W / 2, PAGE_H / 2)
        canvas.rotate(35)
        canvas.setFillColor(colors.black)
        canvas.setFont('Helvetica-Bold', 90 * size)
        canvas.drawCentredString(0, 0, branch.watermark_text.strip()[:40])
    else:
        path = _image_path(branch.logo) or _default_logo_path()
        if path:
            try:
                w, h = ImageReader(path).getSize()
                width = PAGE_W * size
                height = width * h / w
                canvas.drawImage(path, (PAGE_W - width) / 2, (PAGE_H - height) / 2, width, height, mask='auto')
            except Exception:
                pass
    canvas.restoreState()


def _letterhead_lines(branch):
    """The company block: address split over two lines, phone / mobile, e-mail / website, registration numbers."""
    parts = [p.strip() for p in (branch.letterhead_address or '').replace('\n', ',').split(',') if p.strip()]
    if len(parts) > 1:                                              # the reference's splitAddressTwoLines: the most even split
        best, diff = 1, 10 ** 9
        for i in range(1, len(parts)):
            d = abs(len(', '.join(parts[:i])) - len(', '.join(parts[i:])))
            if d < diff:
                best, diff = i, d
        lines = [', '.join(parts[:best]), ', '.join(parts[best:])]
    else:
        lines = parts
    if branch.letterhead_phone:
        lines.append(f'Ph: {branch.letterhead_phone}')
    if branch.letterhead_mobile:
        lines.append(f'Mob: {branch.letterhead_mobile}')
    contact = '   '.join(x for x in (branch.letterhead_email, branch.letterhead_website) if x)
    if contact:
        lines.append(contact)
    reg = '   |   '.join(x for x in (f'GSTIN: {branch.letterhead_gstin}' if branch.letterhead_gstin else '',
                                     f'Udyam: {branch.udyam_number}' if branch.udyam_number else '') if x)
    if reg:
        lines.append(reg)
    return lines


def _page_furniture(branch, title):
    def draw(canvas, doc):
        canvas.saveState()
        _watermark(canvas, branch)
        top = PAGE_H - MARGIN
        # logo (left), company block (middle), dealership logo (right) — the reference's three-column head
        text_x = MARGIN
        logo = _image_path(branch.logo) or _default_logo_path()
        if logo:
            try:
                w, h = ImageReader(logo).getSize()
                box = 32 * mm
                scale = min(box / w, box / h)
                canvas.drawImage(logo, MARGIN, top - h * scale - 2 * mm, w * scale, h * scale, mask='auto')
                text_x = MARGIN + box + 5 * mm
            except Exception:
                pass
        canvas.setFillColor(DARK)
        canvas.setFont('Helvetica-Bold', 13)
        canvas.drawString(text_x, top - 5 * mm, branch.letterhead_name or branch.name)
        canvas.setFillColor(colors.HexColor('#666666'))
        canvas.setFont('Helvetica', 8)
        y = top - 10 * mm
        for line in _letterhead_lines(branch)[:8]:
            canvas.drawString(text_x, y, line[:110])
            y -= 3.9 * mm
        dealer = _image_path(branch.dealer_logo)
        if dealer:
            try:
                w, h = ImageReader(dealer).getSize()
                box = 38 * mm
                scale = min(box / w, box / h)
                canvas.drawImage(dealer, PAGE_W - MARGIN - w * scale, top - h * scale - 2 * mm, w * scale, h * scale, mask='auto')
            except Exception:
                pass
        rule_y = PAGE_H - TOP + 9 * mm
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN, rule_y, PAGE_W - MARGIN, rule_y)
        canvas.setFillColor(DARK)
        canvas.setFont('Helvetica-Bold', 11)
        canvas.drawCentredString(PAGE_W / 2, rule_y - 6 * mm, title)
        footer = _image_path(branch.footer_image)
        if footer:
            try:
                w, h = ImageReader(footer).getSize()
                width = PAGE_W - 2 * MARGIN
                height = min(width * h / w, 22 * mm)
                canvas.drawImage(footer, MARGIN, MARGIN - 4 * mm, width, height, mask='auto', preserveAspectRatio=True)
            except Exception:
                pass
        canvas.restoreState()
    return draw


# --------------------------------------------------------------------------- content
def _customer_box(document, square):
    customer, contact = document.customer, document.contact
    addr = ', '.join(x for x in (customer.address, customer.area, customer.city, customer.state, customer.pincode) if x)
    rows = [_p('CUSTOMER DETAILS', LABEL), _p(customer.name + (f' — {customer.plant}' if customer.plant else ''), ParagraphStyle('cn', parent=BOLD, fontSize=9.5, leading=12))]
    if addr:
        rows.append(_p(addr))
    if customer.gst_number:
        rows.append(_p(f'GSTIN: {customer.gst_number}'))
    if contact:
        rows.append(_p(f'Attn: {contact.name}'))
        if contact.phone:
            rows.append(_p(contact.phone))
    return rows


def _meta_rows(document):
    """[(label, value), ...] per row — the reference's quote-meta stack, per document type."""
    t = document.type
    number_label = {'quotation': 'Quotation Number', 'proforma': 'Proforma Invoice Number', 'dc': 'Delivery Challan Number'}[t]
    rows = [[(number_label, document.doc_number or '—'), ('Date', _fmt_date(document.date))],
            [('Reference Number', document.ref_no or '—'), ('Reference Date', _fmt_date(document.ref_date))]]
    if t == 'quotation':
        rows.append([('Quotation Valid Till', _fmt_date(document.valid_till))])
    if t in ('quotation', 'proforma'):
        rows.append([('Payment Terms', document.payment_terms or '—')])
    if t == 'dc':
        rows.append([('Vehicle Number', document.vehicle or '—'), ('Transport Name', document.transport or '—')])
    return rows


def _meta_box(document, width, square):
    rows = _meta_rows(document)
    data, styles = [], [('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]
    for r, pair in enumerate(rows):
        cells = [[_p(label.upper(), LABEL), _p(value, CELL_VALUE)] for label, value in pair]
        if len(cells) == 1:
            cells.append('')
            styles.append(('SPAN', (0, r), (1, r)))
        data.append(cells)
        if r:
            styles.append(('LINEABOVE', (0, r), (-1, r), 0.5, LINE))
    if any(len(p) == 2 for p in rows):
        styles.append(('LINEAFTER', (0, 0), (0, -1), 0.5, LINE))
    for r, pair in enumerate(rows):
        if len(pair) == 1:
            styles.append(('LINEAFTER', (0, r), (0, r), 0, colors.white))
    if not square:
        styles.append(('ROUNDEDCORNERS', [6, 6, 6, 6]))
    styles.append(('BOX', (0, 0), (-1, -1), 0.5, LINE))
    return Table(data, colWidths=[width / 2, width / 2], style=TableStyle(styles))


def _items_table(document, totals, accent, width):
    show_disc = document.show_discount_in_pdf
    head, widths, right = ['#', 'Item & Description', 'Qty', 'Unit', 'Rate'], [8 * mm, None, 14 * mm, 14 * mm, 24 * mm], [2, 3, 4]
    if show_disc:
        head.append('Discount %'); widths.append(20 * mm); right.append(len(head) - 1)
    head += ['Tax %', 'Amount']; widths += [14 * mm, 28 * mm]; right += [len(head) - 2, len(head) - 1]
    widths[1] = width - sum(w for w in widths if w)
    rows = [[_p(h, THR if i in right else TH) for i, h in enumerate(head)]]
    for line in totals['lines']:
        qty = line['qty']
        row = [_p(line['sr']), _p(line['name']), _p(_num(qty, 0) if qty == qty.to_integral() else _num(qty), NUM), _p(line['unit'] or '—', NUM), _p(_rs(line['rate']), NUM)]
        if show_disc:
            row.append(_p(f"{line['discount'].normalize():f}%", NUM))
        tax_pct = line['tax_pct']
        row += [_p(f"{tax_pct.normalize():f}%", NUM), _p(_rs(line['amount']), NUM)]
        rows.append(row)
    return Table(rows, colWidths=widths, repeatRows=1, style=TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), accent), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, LINE), ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))


def _totals_box(document, totals, square):
    def charge_label(name, pct):
        return f'{name} Charges' + (f' (+{Decimal(pct).normalize():f}% tax)' if pct else '')
    rows = [('Sub Total', totals['sub_total'])]
    if totals['tax_total']:
        rows.append(('Tax Amount', totals['tax_total']))
    for name, key, amount, pct in (('Packing', 'packing', document.packing_charges, document.packing_tax), ('Freight', 'freight', document.freight_charges, document.freight_tax),
                                   ('Other', 'other', document.other_charges, document.other_charges_tax)):
        if totals[key]:
            rows.append((charge_label(name, pct), totals[key]))
    if totals['round_off']:
        rows.append(('Round Off', totals['round_off']))
    data = [[_p(k, TOTAL_LABEL), _p(('+' if k == 'Round Off' and v > 0 else '') + _rs(v), ParagraphStyle('tv', parent=NUM, fontName='Helvetica-Bold'))] for k, v in rows]
    data.append([_p('Total Amount', GRAND), _p(_rs(totals['total']), ParagraphStyle('gv', parent=GRAND, alignment=2))])
    last = len(data) - 1
    styles = [('BOX', (0, 0), (-1, -1), 0.5, LINE), ('LINEBELOW', (0, 0), (-1, last - 1), 0.5, colors.HexColor('#eeeeee')),
              ('BACKGROUND', (0, last), (-1, last), colors.HexColor('#faf8f4')), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
              ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]
    if not square:
        styles.append(('ROUNDEDCORNERS', [6, 6, 6, 6]))
    return Table(data, colWidths=[46 * mm, 38 * mm], style=TableStyle(styles))


def _terms(document, branch):
    terms = [t for t in (document.terms or []) if str(t).strip()]
    if not terms and branch.terms.strip():
        terms = [t for t in branch.terms.splitlines() if t.strip()]
    return terms


def _bank_and_qr(branch, width):
    bank = [(label, value) for label, value in (('Bank Name', branch.bank_name), ('A/c No.', branch.bank_account_no), ('IFSC Code', branch.bank_ifsc), ('Branch Name', branch.bank_branch)) if value]
    left = ([_p('BANK DETAILS', LABEL)] + [_p(f'<font color="#888888">{escape(l)}:</font> {escape(v)}', SMALL) for l, v in bank]) if bank else ''
    qr_path = _image_path(branch.payment_qr)
    qr = _image(qr_path, 26 * mm, 26 * mm) if qr_path else None
    if not bank and not qr:
        return None
    return Table([[left, [_p('SCAN TO PAY', LABEL), qr] if qr else '']], colWidths=[width - 34 * mm, 34 * mm], style=TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))


def build_pdf(document, compress=True) -> bytes:
    """Render `document` (quotation / proforma / challan) to PDF bytes, laid out like the reference's printed document."""
    if document.type not in PRINTABLE:
        raise ServiceError(400, 'Only quotations, proformas and delivery challans can be printed.')
    branch = document.branch
    title = PRINTABLE[document.type]
    accent = _accent(branch)
    square = branch.doc_format == 2
    items = list(document.items.all())
    totals = print_totals(document, items)
    width = PAGE_W - 2 * MARGIN
    story = []

    half = (width - 4 * mm) / 2
    top = Table([[_customer_box(document, square), _meta_box(document, half, square)]], colWidths=[half + 2 * mm, half + 2 * mm], style=TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    customer_cell = Table([[_customer_box(document, square)]], colWidths=[half], style=TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, LINE), ('LEFTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]
        + ([] if square else [('ROUNDEDCORNERS', [6, 6, 6, 6])])))
    top = Table([[customer_cell, _meta_box(document, half, square)]], colWidths=[half + 4 * mm, half], style=TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (0, 0), 4 * mm), ('RIGHTPADDING', (1, 0), (1, 0), 0)]))
    story += [top, Spacer(1, 4 * mm), _items_table(document, totals, accent, width), Spacer(1, 4 * mm)]
    words = [_p('TOTAL AMOUNT (IN WORDS)', LABEL), Spacer(1, 1 * mm), _p(amount_in_words(totals['total']), BOLD)]
    story.append(Table([[words, _totals_box(document, totals, square)]], colWidths=[width - 86 * mm, 86 * mm],
                       style=TableStyle([('VALIGN', (0, 0), (-1, -1), 'BOTTOM'), ('LEFTPADDING', (0, 0), (0, 0), 0), ('RIGHTPADDING', (1, 0), (1, 0), 0)])))
    story.append(Spacer(1, 5 * mm))
    if document.type != 'dc':                                  # challans carry no bank / QR block
        bank = _bank_and_qr(branch, width)
        if bank:
            story += [bank, Spacer(1, 5 * mm)]
    terms = _terms(document, branch)
    terms_cell = ([_p('TERMS &amp; CONDITIONS'.replace('&amp;', '&'), LABEL), Spacer(1, 1.5 * mm)] + [_p(f'{n}. {t}', SMALL) for n, t in enumerate(terms, 1)]) if terms else ''
    if document.remarks.strip():
        terms_cell = (terms_cell or []) + [Spacer(1, 2 * mm), _p('REMARKS', LABEL), _p(document.remarks, SMALL)]
    sign = [_p(f'For {branch.letterhead_name or branch.name}', ParagraphStyle('sg', parent=BOLD, alignment=2)), Spacer(1, 11 * mm),
            _p('Authorized Signatory', ParagraphStyle('sig', parent=SMALL, alignment=2, textColor=GREY))]
    story.append(KeepTogether(Table([[terms_cell, sign]], colWidths=[width - 62 * mm, 62 * mm], style=TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (0, 0), 0), ('RIGHTPADDING', (1, 0), (1, 0), 0)]))))

    out = io.BytesIO()
    pdf = SimpleDocTemplate(out, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=TOP, bottomMargin=BOTTOM,
                            title=f'{title} {document.doc_number}', author=branch.letterhead_name or branch.name,
                            pageCompression=1 if compress else 0)
    furniture = _page_furniture(branch, title)
    pdf.build(story, onFirstPage=furniture, onLaterPages=furniture)
    return out.getvalue()
