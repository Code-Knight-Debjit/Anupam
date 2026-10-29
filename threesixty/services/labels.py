"""Shipping labels (REQ-LBL-01..09, REQ-AUT-10).

Labels keep their ACTUAL size: on an A4 sheet a smaller label is tiled (A5 = 2
per sheet on a landscape sheet, 4x4 = 4, 6x4 = 2), never stretched; paper
"label" makes the page the label itself. Top to bottom: DELIVER TO (name,
address, AREA in bold, city/state, PIN, optional Attn/phone), transport /
courier / vehicle, "BOX n OF m", and the FROM block (logo + company + address)
always last. No Ref or Date. Preview, Print and Download PDF are one PDF.
"""
import io

from django.db.models import Q
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas as rl_canvas

from ..models import Branch, Contact, Customer, SalesDocument
from ..permissions import RoleRules
from ..rules import anupam_rules as rules
from . import contacts as contact_service
from . import documents as doc_service
from .errors import ServiceError

DEFAULTS = rules.LABEL_DEFAULTS
SIZES = rules.LABEL_SIZES
FROM_SCALES = rules.FROM_SCALES
MAX_BOXES = 200
PAPERS = ('a4', 'label')


def options():
    return {
        'defaults': {**DEFAULTS, 'paper': DEFAULTS['paper']},
        'sizes': {k: {'width_mm': w, 'height_mm': h} for k, (w, h) in SIZES.items()},
        'from_scales': list(FROM_SCALES), 'papers': list(PAPERS), 'max_boxes': MAX_BOXES,
    }


def can_print_labels(user) -> bool:
    return not RoleRules.is_sales_manager(user)        # the Print Label menu is hidden for Sales Managers (REQ-ROLE-04)


def _company_dict(customer):
    return {'name': customer.name, 'address': customer.address, 'area': customer.area, 'city': customer.city,
            'state': customer.state, 'pincode': customer.pincode, 'transportPreference': customer.transport_preference,
            'courierPreference': customer.courier_preference}


def autofill(user, customer_id, contact_id=None):
    """Picking a customer fills name, address, area, city, state, PIN, transport and courier; the
    person and phone only when the user also picks a contact (REQ-AUT-10, REQ-LBL-07)."""
    try:
        customer = RoleRules.visible_customers(user, Customer.objects.all()).get(pk=customer_id)
    except (Customer.DoesNotExist, ValueError, TypeError):
        raise ServiceError(404, 'Customer not found.')
    contact = None
    if contact_id:
        try:
            contact = contact_service.visible_contacts(user, customer).get(pk=contact_id)
        except (Contact.DoesNotExist, ValueError, TypeError):
            raise ServiceError(404, 'Contact not found.')
    return rules.label_autofill_from_customer(_company_dict(customer), {'name': contact.name, 'phone': contact.phone} if contact else None)


def _flag(value, default):
    if value is None or value == '':
        return default
    return str(value).lower() in ('1', 'true', 'yes', 'on')


def build_request(user, data):
    """Validate the print request and return everything the renderer needs."""
    paper = data.get('paper') or DEFAULTS['paper']
    size = data.get('size') or DEFAULTS['size']
    if paper not in PAPERS:
        raise ServiceError(400, 'Paper must be a4 or label.')
    if size not in SIZES:
        raise ServiceError(400, 'Label size must be one of: ' + ', '.join(SIZES))
    try:
        boxes = DEFAULTS['boxes'] if data.get('boxes') in (None, '') else int(data['boxes'])
        from_scale = DEFAULTS['from_scale'] if data.get('from_scale') in (None, '') else float(data['from_scale'])
    except (TypeError, ValueError):
        raise ServiceError(400, 'Boxes and FROM size must be numbers.')
    if not 1 <= boxes <= MAX_BOXES:
        raise ServiceError(400, f'Number of boxes must be between 1 and {MAX_BOXES}.')
    if from_scale not in FROM_SCALES:
        raise ServiceError(400, 'FROM size must be 100, 125, 150 or 200 %.')

    document = customer = contact = None
    if data.get('document_id'):
        try:
            document = doc_service.visible_documents(user).select_related('customer', 'branch').get(pk=data['document_id'])
        except (SalesDocument.DoesNotExist, ValueError, TypeError):
            raise ServiceError(404, 'Document not found.')
        customer = document.customer
    elif data.get('customer_id'):
        try:
            customer = RoleRules.visible_customers(user, Customer.objects.all()).get(pk=data['customer_id'])
        except (Customer.DoesNotExist, ValueError, TypeError):
            raise ServiceError(404, 'Customer not found.')
    if data.get('contact_id'):
        if customer is None:
            raise ServiceError(400, 'Pick a customer before picking a person.')
        try:
            contact = contact_service.visible_contacts(user, customer).get(pk=data['contact_id'])
        except (Contact.DoesNotExist, ValueError, TypeError):
            raise ServiceError(404, 'Contact not found.')

    base = rules.label_autofill_from_customer(_company_dict(customer), {'name': contact.name, 'phone': contact.phone} if contact else None) \
        if customer else {}
    typed = lambda key: (data.get(key) or '').strip() if isinstance(data.get(key), (str, type(None))) else str(data.get(key))
    # What the user typed wins over what was auto-filled (REQ-LBL-05).
    merged = {k: typed(k) or base.get(k, '') for k in ('address', 'area', 'city', 'state', 'pin', 'transport', 'courier', 'attn', 'phone')}
    if document is not None:
        merged['transport'] = typed('transport') or document.transport or base.get('transport', '')
    merged['vehicle'] = typed('vehicle') or (document.vehicle if document is not None else '')
    try:
        name = rules.label_target_name(typed('deliver_to'), {'name': customer.name} if customer else None)
    except ValueError:
        raise ServiceError(400, 'Enter who the label is for.')
    party = {'customer': name, 'addrLines': [l.strip() for l in merged['address'].splitlines() if l.strip()], 'area': merged['area'],
             'cityLine': ', '.join(x for x in (merged['city'], merged['state']) if x), 'pin': merged['pin'], 'attn': merged['attn'],
             'phone': merged['phone'], 'transport': merged['transport'], 'courier': merged['courier'], 'vehicle': merged['vehicle']}

    branch = document.branch if document is not None else None
    if branch is None and data.get('branch_id'):
        branch = Branch.objects.filter(pk=data['branch_id'], is_active=True).first()
        if branch is None:
            raise ServiceError(400, 'branch_id must be an active branch.')
    if branch is None:
        profile = getattr(user, 'threesixty_profile', None)
        branch = (profile.branches.filter(is_active=True).order_by('id').first() if profile else None) or Branch.objects.filter(is_active=True).first()
    return {'paper': paper, 'size': size, 'boxes': boxes, 'from_scale': from_scale,
            'print_attn': _flag(data.get('print_attn'), DEFAULTS['print_attn']),
            'print_phone': _flag(data.get('print_phone'), DEFAULTS['print_phone']), 'party': party, 'branch': branch}


def plan(req):
    return rules.label_sheet_plan(req['size'], req['boxes'], on_sheet=req['paper'] == 'a4')


# --------------------------------------------------------------------------- drawing
def _lines(content, branch):
    """Ordered (text, style) rows for one label's DELIVER TO part."""
    rows = [('DELIVER TO', 'tag'), (content['deliver_to'], 'name')]
    rows += [(l, 'body') for l in content['address']]
    if content['area_bold']:
        rows.append((content['area_bold'], 'bold'))
    if content['city']:
        rows.append((content['city'], 'body'))
    if content['pin']:
        rows.append((f'PIN: {content["pin"]}', 'body'))
    if content['attn']:
        rows.append((f'Attn: {content["attn"]}', 'bold'))
    if content['phone']:
        rows.append((f'Phone: {content["phone"]}', 'body'))
    rows += [(f'{key}: {value}', 'body') for key, value in content['meta']]
    return rows


FONTS = {'tag': ('Helvetica', 0.55), 'name': ('Helvetica-Bold', 1.35), 'body': ('Helvetica', 1.0), 'bold': ('Helvetica-Bold', 1.1)}


def _draw_label(c, x, y, w, h, content, branch, number, total, from_scale, dry=False):
    """Draw one label in the box whose lower-left corner is (x, y), size w x h (points).
    Returns False if the text did not fit at the chosen scale (callers shrink and retry)."""
    pad = 5 * mm
    base = max(7.0, min(w, h) / mm * 0.075)                         # body font size scales with the label
    inner = w - 2 * pad
    # --- bottom: FROM block (logo + company + address), always last
    fs = base * 0.62 * from_scale
    from_rows = []
    if branch is not None:
        company = branch.letterhead_name or branch.name
        from_rows.append((company, 'Helvetica-Bold', fs))
        for part in (branch.letterhead_address or '').splitlines() + ([f'Ph: {branch.letterhead_phone}'] if branch.letterhead_phone else []):
            if part.strip():
                from_rows.append((part.strip(), 'Helvetica', fs * 0.9))
    logo_path = None
    if branch is not None and branch.logo:
        try:
            logo_path = branch.logo.path
            ImageReader(logo_path)
        except Exception:
            logo_path = None
    logo_h = 9 * mm * from_scale if logo_path else 0
    logo_w_max = inner * 0.35 if logo_path else 0
    text_x = x + pad + (logo_w_max + 2 * mm if logo_path else 0)
    wrapped_from = [(ln, f, s) for text, f, s in from_rows for ln in simpleSplit(text, f, s, w - pad - (text_x - x))]
    from_h = max(logo_h, sum(s * 1.2 for _, _, s in wrapped_from)) + 5 * mm
    # --- box bar
    bar_h = base * 2.0
    # --- top: delivery text
    cursor = y + h - pad
    needed_top = y + from_h + bar_h + 3 * mm
    for text, style in _lines(content, branch):
        font, factor = FONTS[style]
        size = base * factor
        for ln in simpleSplit(text, font, size, inner):
            cursor -= size * 1.25
            if cursor < needed_top:
                return False
            if not dry:
                c.setFillColor(colors.HexColor('#555555') if style == 'tag' else colors.black)
                c.setFont(font, size)
                c.drawString(x + pad, cursor, ln)
    if dry:
        return True
    # box bar
    bar_y = y + from_h + 1.5 * mm
    c.setFillColor(colors.black)
    c.rect(x + pad, bar_y, inner, bar_h, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', base * 1.1)
    c.drawCentredString(x + w / 2, bar_y + bar_h / 2 - base * 0.38, f'BOX {number} OF {total}')
    # FROM block
    c.setStrokeColor(colors.grey)
    c.setLineWidth(0.5)
    c.line(x + pad, y + from_h, x + w - pad, y + from_h)
    c.setFillColor(colors.black)
    top = y + from_h - 2.5 * mm
    if logo_path:
        try:
            iw, ih = ImageReader(logo_path).getSize()
            scale = min(logo_w_max / iw, logo_h / ih)
            c.drawImage(logo_path, x + pad, top - ih * scale, iw * scale, ih * scale, mask='auto')
        except Exception:
            pass
    cy = top
    for ln, font, size in wrapped_from:
        cy -= size * 1.2
        c.setFont(font, size)
        c.drawString(text_x, cy, ln)
    return True


def build_pdf(req, compress=True) -> bytes:
    p = plan(req)
    label_w, label_h = SIZES[req['size']]
    page_w, page_h = p['page']
    per_page = p['per_page']
    cols = p.get('cols', 1)
    rows = p.get('rows', 1)
    content = rules.label_content(req['party'], req['print_attn'], req['print_phone'])
    out = io.BytesIO()
    c = rl_canvas.Canvas(out, pagesize=(page_w * mm, page_h * mm), pageCompression=1 if compress else 0)
    c.setTitle('Shipping label')
    lw, lh = label_w * mm, label_h * mm
    # the largest FROM scale (<= requested) at which the text fits; shrink the whole label text if even 1.0 does not
    from_scale = req['from_scale']
    scale = 1.0
    while scale > 0.45 and not _draw_label(c, 0, 0, lw, lh, content, req['branch'], 1, req['boxes'], from_scale * scale, dry=True):
        scale -= 0.05
    from_scale = from_scale * scale
    x0 = (page_w * mm - cols * lw) / 2
    y_top = page_h * mm - (page_h * mm - rows * lh) / 2
    for index in range(req['boxes']):
        slot = index % per_page
        if index and slot == 0:
            c.showPage()
        col, row = slot % cols, slot // cols
        x, y = x0 + col * lw, y_top - (row + 1) * lh
        if per_page > 1 or req['paper'] == 'a4':
            c.setStrokeColor(colors.lightgrey)
            c.setDash(2, 2)
            c.rect(x, y, lw, lh, stroke=1, fill=0)
            c.setDash()
        _draw_label(c, x, y, lw, lh, content, req['branch'], index + 1, req['boxes'], from_scale)
    c.save()
    return out.getvalue()
