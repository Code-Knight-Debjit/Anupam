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

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from .errors import ServiceError
from .printing import amount_in_words, money, print_totals

PRINTABLE = {'quotation': 'QUOTATION', 'proforma': 'PROFORMA INVOICE', 'dc': 'DELIVERY CHALLAN'}
PAGE_W, PAGE_H = A4
MARGIN = 12 * mm
TOP, BOTTOM = 46 * mm, 30 * mm
DEFAULT_ACCENT = '#a14000'

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
def _accent(branch):
    try:
        return colors.HexColor(branch.accent_color or DEFAULT_ACCENT)
    except ValueError:
        return colors.HexColor(DEFAULT_ACCENT)


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
        path = _image_path(branch.logo)
        if path:
            try:
                w, h = ImageReader(path).getSize()
                width = PAGE_W * size
                height = width * h / w
                canvas.drawImage(path, (PAGE_W - width) / 2, (PAGE_H - height) / 2, width, height, mask='auto')
            except Exception:
                pass
    canvas.restoreState()


def _page_furniture(branch, title):
    accent = _accent(branch)

    def draw(canvas, doc):
        canvas.saveState()
        _watermark(canvas, branch)
        top = PAGE_H - MARGIN
        text_x = MARGIN
        logo = _image_path(branch.logo)
        if logo:
            try:
                w, h = ImageReader(logo).getSize()
                height = 20 * mm
                width = min(height * w / h, 42 * mm)
                canvas.drawImage(logo, MARGIN, top - height, width, height, mask='auto', preserveAspectRatio=True)
                text_x = MARGIN + width + 4 * mm
            except Exception:
                pass
        canvas.setFillColor(accent)
        canvas.setFont('Helvetica-Bold', 15)
        canvas.drawString(text_x, top - 6 * mm, branch.letterhead_name or branch.name)
        canvas.setFillColor(colors.black)
        canvas.setFont('Helvetica', 8)
        y = top - 11 * mm
        for line in (branch.letterhead_address,
                     ' | '.join(x for x in (f'Ph: {branch.letterhead_phone}' if branch.letterhead_phone else '',
                                            f'Mob: {branch.letterhead_mobile}' if branch.letterhead_mobile else '',
                                            branch.letterhead_email, branch.letterhead_website) if x),
                     ' | '.join(x for x in (f'GSTIN: {branch.letterhead_gstin}' if branch.letterhead_gstin else '',
                                            f'Udyam: {branch.udyam_number}' if branch.udyam_number else '') if x)):
            for part in (line or '').splitlines():
                if part.strip():
                    canvas.drawString(text_x, y, part.strip()[:120])
                    y -= 3.6 * mm
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(1.2)
        canvas.line(MARGIN, PAGE_H - TOP + 6 * mm, PAGE_W - MARGIN, PAGE_H - TOP + 6 * mm)
        canvas.setFont('Helvetica-Bold', 11)
        canvas.setFillColor(accent)
        canvas.drawRightString(PAGE_W - MARGIN, top - 6 * mm, title)
        # footer: image (shared by both formats) and page number
        footer = _image_path(branch.footer_image)
        if footer:
            try:
                w, h = ImageReader(footer).getSize()
                width = PAGE_W - 2 * MARGIN
                height = min(width * h / w, 16 * mm)
                canvas.drawImage(footer, MARGIN, MARGIN - 4 * mm, width, height, mask='auto', preserveAspectRatio=True)
            except Exception:
                pass
        canvas.setFillColor(colors.grey)
        canvas.setFont('Helvetica', 7)
        canvas.drawRightString(PAGE_W - MARGIN, 6 * mm, f'Page {doc.page}')
        canvas.restoreState()
    return draw


# --------------------------------------------------------------------------- content
def _customer_block(document):
    customer, contact = document.customer, document.contact
    addr = ', '.join(x for x in (customer.address, customer.area, customer.city, customer.state, customer.pincode) if x)
    rows = [_p('Bill to', SMALL), _p(customer.name + (f' — {customer.plant}' if customer.plant else ''), BOLD)]
    if addr:
        rows.append(_p(addr))
    if customer.gst_number:
        rows.append(_p(f'GSTIN: {customer.gst_number}'))
    if contact:
        rows.append(_p(f'Attn: {contact.name}' + (f' ({contact.phone})' if contact.phone else '')))
    return rows


def _meta_block(document, title):
    label = {'quotation': 'Quotation No.', 'proforma': 'Proforma No.', 'dc': 'Challan No.'}[document.type]
    pairs = [(label, document.doc_number), ('Date', document.date.strftime('%d-%m-%Y'))]
    if document.type == 'quotation' and document.valid_till:
        pairs.append(('Valid till', document.valid_till.strftime('%d-%m-%Y')))
    if document.ref_no:
        pairs.append(('Your ref.', document.ref_no))
    if document.sales_person_name:
        pairs.append(('Sales person', document.sales_person_name))
    if document.type == 'dc':
        pairs += [(l, v) for l, v in (('Vehicle', document.vehicle), ('Transport', document.transport)) if v]
    if document.payment_terms and document.type != 'dc':
        pairs.append(('Payment terms', document.payment_terms))
    return Table([[_p(k, SMALL), _p(v, BOLD)] for k, v in pairs], colWidths=[24 * mm, 36 * mm],
                 style=TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 1),
                                   ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))


def _items_table(document, totals, accent, show_unit):
    show_disc = document.show_discount_in_pdf
    head = ['Sr', 'Description']
    widths = [9 * mm, None]
    head.append('Qty'); widths.append(16 * mm)
    if show_unit:
        head.append('Unit'); widths.append(13 * mm)
    head.append('Rate'); widths.append(21 * mm)
    if show_disc:
        head.append('Disc %'); widths.append(15 * mm)
    head.append('Amount'); widths.append(26 * mm)
    fixed = sum(w for w in widths if w)
    widths[1] = PAGE_W - 2 * MARGIN - fixed
    rows = [[_p(h, HEAD) for h in head]]
    for line in totals['lines']:
        row = [_p(line['sr']), _p(line['name']), _p(_num(line['qty'], 0) if line['qty'] == line['qty'].to_integral() else _num(line['qty'])), ]
        if show_unit:
            row.append(_p(line['unit']))
        row.append(_p(_num(line['rate']), RIGHT))
        if show_disc:
            row.append(_p(_num(line['discount'])))
        row.append(_p(_num(money(line['amount'])), RIGHT))
        rows.append(row)
    table = Table(rows, colWidths=widths, repeatRows=1, style=TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), accent), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black), ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    return table


def _totals_table(document, totals):
    rows = [('Sub Total', totals['sub_total'])]
    rows.append(('Tax Amount', totals['tax_total']))
    for label, key, raw in (('Packing', 'packing', document.packing_charges), ('Freight', 'freight', document.freight_charges),
                            ('Other charges', 'other', document.other_charges)):
        if raw:
            rows.append((label, totals[key]))
    if totals['round_off']:
        rows.append(('Round off', totals['round_off']))
    rows.append(('TOTAL', totals['total']))
    data = [[_p(k, BOLD if k == 'TOTAL' else _base), _p(_num(money(v)), RIGHT)] for k, v in rows]
    return Table(data, colWidths=[40 * mm, 30 * mm], hAlign='RIGHT', style=TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black), ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f2f2f2')),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))


def _terms(document, branch):
    terms = [t for t in (document.terms or []) if str(t).strip()]
    if not terms and branch.terms.strip():
        terms = [t for t in branch.terms.splitlines() if t.strip()]
    return terms


def _bank_and_qr(branch):
    cells = []
    bank = [x for x in (f'Bank: {branch.bank_name}' if branch.bank_name else '',
                        f'Branch: {branch.bank_branch}' if branch.bank_branch else '',
                        f'A/C No.: {branch.bank_account_no}' if branch.bank_account_no else '',
                        f'IFSC: {branch.bank_ifsc}' if branch.bank_ifsc else '') if x]
    cells.append([_p('Bank details', BOLD)] + [_p(b, SMALL) for b in bank] if bank else '')
    qr_path = _image_path(branch.payment_qr)
    qr = _image(qr_path, 28 * mm, 28 * mm) if qr_path else None
    if not bank and not qr:
        return None
    cells.append([_p('Scan to pay', SMALL), qr] if qr else '')
    return Table([cells], colWidths=[(PAGE_W - 2 * MARGIN) / 2] * 2, style=TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOX', (0, 0), (-1, -1), 0.5, colors.black)]))


def build_pdf(document, compress=True) -> bytes:
    """Render `document` (quotation / proforma / challan) to PDF bytes."""
    if document.type not in PRINTABLE:
        raise ServiceError(400, 'Only quotations, proformas and delivery challans can be printed.')
    branch = document.branch
    title = PRINTABLE[document.type]
    accent = _accent(branch)
    items = list(document.items.all())
    totals = print_totals(document, items)
    width = PAGE_W - 2 * MARGIN
    story = []

    customer = _customer_block(document)
    meta = _meta_block(document, title)
    show_unit = any(i.unit for i in items)
    items_table = _items_table(document, totals, accent, show_unit)
    if branch.doc_format == 2:
        top = Table([[customer, meta]], colWidths=[width - 62 * mm, 62 * mm], style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEAFTER', (0, 0), (0, 0), 0.5, colors.black)]))
        story.append(Table([[top], [items_table]], colWidths=[width], style=TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black), ('LINEBELOW', (0, 0), (0, 0), 0.5, colors.black),
            ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)])))
    else:
        top = Table([[customer, meta]], colWidths=[width - 66 * mm, 66 * mm], style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOX', (0, 0), (0, 0), 0.5, colors.black), ('BOX', (1, 0), (1, 0), 0.5, colors.black),
            ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4)]))
        story += [top, Spacer(1, 3 * mm), items_table]
    story.append(Spacer(1, 3 * mm))
    words = Table([[_p('Amount in words', SMALL)], [_p(amount_in_words(totals['total']), BOLD)]], colWidths=[width - 74 * mm])
    story.append(Table([[words, _totals_table(document, totals)]], colWidths=[width - 72 * mm, 72 * mm],
                       style=TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')])))
    story.append(Spacer(1, 4 * mm))
    block = []
    terms = _terms(document, branch)
    if terms:
        block += [_p('Terms & conditions', BOLD)] + [_p(f'{n}. {t}', SMALL) for n, t in enumerate(terms, 1)]
    if document.remarks.strip():
        block += [Spacer(1, 2 * mm), _p('Remarks', BOLD), _p(document.remarks, SMALL)]
    if document.type != 'dc':                                  # challans carry no bank / QR block
        bank = _bank_and_qr(branch)
        if bank:
            block += [Spacer(1, 3 * mm), bank]
    block += [Spacer(1, 10 * mm), Table([[_p(''), _p(f'For {branch.letterhead_name or branch.name}', BOLD)],
                                         [_p(''), _p('Authorised signatory', SMALL)]], colWidths=[width - 70 * mm, 70 * mm])]
    story.append(KeepTogether(block))

    out = io.BytesIO()
    pdf = SimpleDocTemplate(out, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=TOP, bottomMargin=BOTTOM,
                            title=f'{title} {document.doc_number}', author=branch.letterhead_name or branch.name,
                            pageCompression=1 if compress else 0)
    furniture = _page_furniture(branch, title)
    pdf.build(story, onFirstPage=furniture, onLaterPages=furniture)
    return out.getvalue()
