"""Sales documents: Enquiry -> Quotation -> Proforma / Pending PO -> Delivery
Challan (REQUIREMENTS §4, §17, §22, REQ-DOC-*, REQ-PO-*, REQ-DC-*, REQ-LOG-*).

Everything that changes a document goes through here so the same rules apply
to a direct save, an approved edit and a clone. Money is `Decimal`.
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from ..models import (
    Branch, Contact, Customer, DocumentCallLog, InvoiceLogEntry, SalesDocument, SalesDocumentItem, StockTransaction,
    SupplyLogEntry,
)
from ..permissions import RoleRules
from ..rules import anupam_rules as rules
from . import contacts as contact_service
from . import tasks as task_service
from .errors import ServiceError
from .notifications import notify
from .numbering import NOT_GENERATED, allocate_next_number, bump_counter_to
from .totals import TYPE_FLAGS, compute_document_totals, compute_item_fields

STATUSES = rules.STATUSES                       # {'enquiry': [...], 'quotation': [...], ...}
DEFAULT_STATUS = {'enquiry': 'Pending', 'quotation': 'Pending', 'proforma': 'Pending', 'po': 'Pending', 'dc': ''}
SALES_MANAGER_TYPES = ('enquiry', 'quotation')   # "Sales Manager can raise Enquiry and Quotation only"
CALL_LOG_TYPES = ('quotation', 'proforma', 'dc')

SCALAR_FIELDS = (
    'contact_id', 'date', 'remarks', 'source', 'vehicle', 'transport',
    'show_discount_in_pdf', 'packing_charges', 'packing_tax', 'freight_charges', 'freight_tax',
    'other_charges', 'other_charges_tax', 'round_off', 'quotation_value', 'sales_person_id',
    'valid_till', 'ref_no', 'ref_date', 'payment_terms', 'terms',
)
DATE_FIELDS = ('date', 'valid_till', 'ref_date')
DECIMAL_FIELDS = ('packing_charges', 'packing_tax', 'freight_charges', 'freight_tax', 'other_charges',
                  'other_charges_tax', 'round_off', 'quotation_value')
ITEM_FIELDS = ('item_name', 'make', 'qty', 'unit', 'rate', 'discount', 'tax')


def D(value, field='value'):
    if value in (None, ''):
        return Decimal('0')
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ServiceError(400, f'{field} must be a number.')


def _parse_date(value, field):
    from django.utils.dateparse import parse_date
    if value in (None, ''):
        return None
    if not isinstance(value, str):
        return value
    parsed = parse_date(value)
    if parsed is None:
        raise ServiceError(400, f'Invalid date for {field}: {value!r}')
    return parsed


# --------------------------------------------------------------------------- visibility & lookups
def visible_documents(user):
    return RoleRules.visible_sales_documents(user, SalesDocument.objects.all())


def get_visible(user, pk):
    try:
        return visible_documents(user).get(pk=pk)
    except SalesDocument.DoesNotExist:
        raise ServiceError(404, 'Document not found.')


def _visible_customer(user, customer_id):
    try:
        return RoleRules.visible_customers(user, Customer.objects.all()).get(pk=customer_id)
    except (Customer.DoesNotExist, ValueError, TypeError):
        raise ServiceError(400, 'customer_id is required and must be a customer you can access.')


def _contact_for(user, customer, contact_id):
    if not contact_id:
        return None
    try:
        return contact_service.visible_contacts(user, customer).get(pk=contact_id)
    except (Contact.DoesNotExist, ValueError, TypeError):
        raise ServiceError(400, 'That contact does not belong to this customer (or is not available to you).')


# --------------------------------------------------------------------------- items & totals
def clean_items(doc_type, items):
    """Blank rows are dropped; numbers are checked (REQ-DOC-06)."""
    cleaned = []
    for row in items or []:
        if not (row.get('item_name') or '').strip() and not D(row.get('qty'), 'qty'):
            continue
        item = {k: row.get(k, '') for k in ITEM_FIELDS}
        item['item_name'] = (item['item_name'] or '').strip()
        for field in ('qty', 'rate', 'discount', 'tax'):
            item[field] = D(row.get(field), field)
            if item[field] < 0:
                raise ServiceError(400, f'{field} cannot be negative.')
        if item['discount'] > 100 or item['tax'] > 100:
            raise ServiceError(400, 'Discount and tax are percentages between 0 and 100.')
        item['id'] = row.get('id')
        cleaned.append(item)
    return cleaned


@transaction.atomic
def replace_items(document, items):
    """Rewrite the document's lines. A line sent with its `id` is updated in
    place, so its supply and invoice history survives an edit (REQ-PO-05);
    lines not sent are removed; new lines are created."""
    existing = {i.pk: i for i in document.items.all()}
    keep = set()
    for position, row in enumerate(items):
        amount, value = compute_item_fields(document.type, row)
        values = {f: row[f] for f in ITEM_FIELDS}
        values.update(position=position, amount=amount, value=value)
        row_id = row.get('id')
        try:
            row_id = int(row_id) if row_id not in (None, '') else None
        except (TypeError, ValueError):
            row_id = None
        if row_id in existing:
            item = existing[row_id]
            for key, val in values.items():
                setattr(item, key, val)
            item.save()
            keep.add(row_id)
        else:
            keep.add(SalesDocumentItem.objects.create(document=document, **values).pk)
    document.items.exclude(pk__in=keep).delete()


def recompute_totals(document):
    """sub_total / total_amount from the saved items and charges; 0 for types
    without charges (enquiry, PO)."""
    rows = [{'qty': i.qty, 'rate': i.rate, 'discount': i.discount, 'tax': i.tax} for i in document.items.all()]
    document.sub_total, document.total_amount = compute_document_totals(
        document.type, rows, document.packing_charges, document.packing_tax, document.freight_charges,
        document.freight_tax, document.other_charges, document.other_charges_tax, document.round_off)
    document.save(update_fields=['sub_total', 'total_amount'])


def apply_scalars(document, data):
    for field in SCALAR_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if field in DATE_FIELDS:
            value = _parse_date(value, field)
        elif field in DECIMAL_FIELDS:
            value = None if (field == 'quotation_value' and value in (None, '')) else D(value, field)
        elif field == 'terms' and not isinstance(value, list):
            raise ServiceError(400, 'terms must be a list.')
        setattr(document, field, value)
    if document.contact_id and document.pk is None:
        pass


# --------------------------------------------------------------------------- creating
def _validate_input(data, doc_type):
    flags = TYPE_FLAGS[doc_type]
    problem = rules.validate_sales_doc(
        {'customerId': data.get('customer_id'), 'branch': data.get('branch_id'),
         'items': [{'itemName': i.get('item_name'), 'qty': i.get('qty')} for i in data.get('items') or []]},
        has_items_cfg=flags['has_items'])
    if problem:
        raise ServiceError(400, problem)


def _check_reference(doc_type, reference):
    if reference is None:
        return
    expected = SalesDocument.REF_TYPE_OF.get(doc_type)
    if expected is None:
        raise ServiceError(400, f'{doc_type} documents do not take a reference document.')
    if reference.type != expected:
        raise ServiceError(400, f'reference document must be a {expected}, not a {reference.type}.')


@transaction.atomic
def create_document(user, data):
    """Returns (document, info) where info may carry `enquiry_completed`."""
    doc_type = data.get('type')
    if doc_type not in dict(SalesDocument.TYPE_CHOICES):
        raise ServiceError(400, 'A valid type is required.')
    if RoleRules.is_sales_manager(user) and doc_type not in SALES_MANAGER_TYPES:
        raise ServiceError(403, 'A Sales Manager can only raise Enquiries and Quotations.')
    _validate_input(data, doc_type)
    customer = _visible_customer(user, data['customer_id'])
    try:
        branch = Branch.objects.get(pk=data['branch_id'], is_active=True)
    except (Branch.DoesNotExist, ValueError, TypeError):
        raise ServiceError(400, 'branch_id must be an active branch.')
    if not data.get('date'):
        raise ServiceError(400, 'date is required.')
    reference = None
    if data.get('reference_id'):
        try:
            reference = visible_documents(user).get(pk=data['reference_id'])
        except SalesDocument.DoesNotExist:
            raise ServiceError(400, 'reference_id does not exist.')
    _check_reference(doc_type, reference)
    contact = _contact_for(user, customer, data.get('contact_id'))
    items = clean_items(doc_type, data.get('items')) if TYPE_FLAGS[doc_type]['has_items'] else []

    doc_number = (data.get('doc_number') or '').strip()
    if doc_type in NOT_GENERATED:
        pass                                        # Pending PO: the customer's own PO number, as typed
    elif doc_number:
        bump_counter_to(branch, doc_type, doc_number)
    else:
        doc_number = allocate_next_number(branch, doc_type)

    document = SalesDocument(type=doc_type, doc_number=doc_number, branch=branch, customer=customer,
                             reference=reference, created_by=user, contact=contact,
                             order_status=DEFAULT_STATUS[doc_type])
    scalars = {k: v for k, v in data.items() if k != 'contact_id'}
    apply_scalars(document, scalars)
    document.save()
    if items:
        replace_items(document, items)
    recompute_totals(document)
    info = {}
    if doc_type == 'quotation':
        completed = complete_enquiry_for(document, user)
        if completed:
            info['enquiry_completed'] = completed
    if doc_type == 'dc':
        stock_out_for_new_challan(document, user)
    if doc_type == 'po':
        recompute_po_status(document)
    return document, info


def complete_enquiry_for(quotation, user):
    """REQ-AUT-11: a quotation saved from an enquiry completes that enquiry and the user is told."""
    enquiry = quotation.reference
    if quotation.type != 'quotation' or enquiry is None or enquiry.type != 'enquiry' or enquiry.order_status == 'Completed':
        return None
    enquiry.order_status = 'Completed'
    enquiry.save(update_fields=['order_status', 'updated_at'])
    notify(user, 'enquiry_completed',
           f'Enquiry {enquiry.doc_number} was marked Completed because quotation {quotation.doc_number} was created from it.',
           document=enquiry)
    return enquiry.doc_number


def stock_out_for_new_challan(document, user):
    """REQ-AUT-13: one stock OUT per item with a name and quantity, only for a NEW challan."""
    if document.type != 'dc' or not document.branch_id:
        return
    for item in document.items.all():
        if not item.item_name or not item.qty:
            continue
        StockTransaction.objects.create(
            branch=document.branch, item_name=item.item_name, make=item.make, unit=item.unit,
            type=StockTransaction.TYPE_OUT, qty=item.qty, date=document.date, source='Delivery Challan',
            ref_document=document, remarks=f'Auto-generated from {document.doc_number}', recorded_by=user,
        )


# --------------------------------------------------------------------------- editing
def apply_edit(document, data, user):
    """Apply an edit (direct or approved). `items` rows with an `id` keep their history."""
    data = dict(data)
    data.pop('version', None)
    if 'customer_id' in data and int(data['customer_id']) != document.customer_id:
        raise ServiceError(400, 'The customer of a document cannot be changed; raise a new document instead.')
    if 'contact_id' in data and data['contact_id']:
        _contact_for(user, document.customer, data['contact_id'])
    status = data.pop('order_status', None)
    apply_scalars(document, data)
    if status is not None:
        _set_manual_status(document, status)
    document.version += 1
    document.save()
    if 'items' in data and TYPE_FLAGS[document.type]['has_items']:
        items = clean_items(document.type, data['items'])
        if not items:
            raise ServiceError(400, 'Add at least one item.')
        replace_items(document, items)
    recompute_totals(document)
    if document.type == 'po':
        recompute_po_status(document)
    if document.type == 'quotation':
        complete_enquiry_for(document, user)
    return document


def _set_manual_status(document, status):
    allowed = STATUSES[document.type]
    if status not in allowed:
        raise ServiceError(400, f'Status for a {document.get_type_display()} must be one of: {", ".join(allowed) or "none"}.')
    if document.type in ('quotation', 'proforma'):
        if status in ('Win', 'Lose'):
            raise ServiceError(400, 'Use the Win / Lose action — it needs an order value or a reason.')
        document.order_value, document.lost_reason = None, ''
    document.order_status = status


# --------------------------------------------------------------------------- Win / Lose (REQ-AUT-12)
@transaction.atomic
def mark_outcome(document, status, order_value=None, lost_reason=''):
    if document.type not in ('quotation', 'proforma'):
        raise ServiceError(400, 'Only quotations and proformas can be marked Win or Lose.')
    if status == 'Win':
        if order_value in (None, ''):
            raise ServiceError(400, 'An order value is required to mark a Win.')
        value = D(order_value, 'order_value')
        if value < 0:
            raise ServiceError(400, 'Order value cannot be negative.')
        document.order_status, document.order_value, document.lost_reason = 'Win', value, ''
    elif status == 'Lose':
        document.order_status, document.lost_reason, document.order_value = 'Lose', (lost_reason or '').strip(), None
    else:
        raise ServiceError(400, 'Status must be Win or Lose.')
    document.version += 1
    document.save()
    return document


# --------------------------------------------------------------------------- Pending PO supply (REQ-PO-*)
def item_supplied(item) -> Decimal:
    return sum((e.qty_supplied for e in item.supply_log.all()), Decimal('0.00'))


def item_pending(item) -> Decimal:
    return max(Decimal('0.00'), item.qty - item_supplied(item))


def recompute_po_status(document):
    """Automatic PO status from the supply log; Hold is manual and never overwritten."""
    if document.type != 'po' or document.order_status == 'Hold':
        return document
    items = list(document.items.prefetch_related('supply_log'))
    ordered = sum((i.qty for i in items), Decimal('0'))
    pending = sum((item_pending(i) for i in items), Decimal('0'))
    if ordered > 0 and pending <= 0:
        status = 'Completed'
    elif pending == ordered:
        status = 'Pending'
    else:
        status = 'Part Pending'
    if document.order_status != status:
        document.order_status = status
        document.save(update_fields=['order_status', 'updated_at'])
    return document


def _require_back_office(user):
    if not RoleRules.can_direct_edit_delete_sales_doc(user):
        raise ServiceError(403, 'You cannot record this against a document.')


def _qty(value, what='Quantity'):
    qty = D(value, what.lower())
    if qty <= 0:
        raise ServiceError(400, f'{what} must be greater than zero.')
    return qty


def _needs_confirmation(limit, what):
    return ServiceError(409, f'{what} is more than the balance ({limit}). Confirm to continue.',
                        needs_confirmation=True, balance=str(limit))


@transaction.atomic
def add_supply(user, item, qty, date, remarks='', confirm_over=False):
    _require_back_office(user)
    if item.document.type != 'po':
        raise ServiceError(400, 'Supply is recorded against Pending PO items only.')
    qty = _qty(qty)
    pending = item_pending(item)
    if qty > pending and not confirm_over:
        raise _needs_confirmation(pending, 'Quantity')
    entry = SupplyLogEntry.objects.create(item=item, date=_parse_date(date, 'date') or timezone.localdate(),
                                          qty_supplied=qty, remarks=remarks or '', recorded_by=user)
    recompute_po_status(item.document)
    return entry


@transaction.atomic
def update_supply(user, entry, data, confirm_over=False):
    _require_back_office(user)
    others = item_supplied(entry.item) - entry.qty_supplied
    if 'qty_supplied' in data:
        qty = _qty(data['qty_supplied'])
        pending = max(Decimal('0.00'), entry.item.qty - others)
        if qty > pending and not confirm_over:
            raise _needs_confirmation(pending, 'Quantity')
        entry.qty_supplied = qty
    if 'date' in data:
        entry.date = _parse_date(data['date'], 'date')
    if 'remarks' in data:
        entry.remarks = data['remarks'] or ''
    entry.save()
    recompute_po_status(entry.item.document)
    return entry


@transaction.atomic
def delete_supply(user, entry):
    _require_back_office(user)
    document = entry.item.document
    entry.delete()
    recompute_po_status(document)             # Hold stays


# --------------------------------------------------------------------------- Delivery challan invoicing (REQ-DC-01)
def item_invoiced(item) -> Decimal:
    return sum((e.qty_invoiced for e in item.invoice_log.all()), Decimal('0.00'))


def item_balance(item) -> Decimal:
    return max(Decimal('0.00'), item.qty - item_invoiced(item))


def dc_is_pending(document) -> bool:
    return any(item_balance(i) > 0 for i in document.items.all())


@transaction.atomic
def add_invoice(user, item, bill_number, bill_date, qty, confirm_over=False):
    _require_back_office(user)
    if item.document.type != 'dc':
        raise ServiceError(400, 'Invoicing is recorded against Delivery Challan items only.')
    if not (bill_number or '').strip():
        raise ServiceError(400, 'Bill number is required.')
    qty = _qty(qty)
    balance = item_balance(item)
    if qty > balance and not confirm_over:
        raise _needs_confirmation(balance, 'Quantity')
    return InvoiceLogEntry.objects.create(
        item=item, bill_number=bill_number.strip(), bill_date=_parse_date(bill_date, 'bill_date') or timezone.localdate(),
        qty_invoiced=qty, recorded_by=user)


# --------------------------------------------------------------------------- contact log (REQ-LOG-01/02)
@transaction.atomic
def add_contact_log(user, document, message, call_later_date=None, outcome=''):
    if document.type not in CALL_LOG_TYPES:
        raise ServiceError(400, 'Only quotations, proformas and challans have a contact log.')
    message = (message or '').strip()
    if not message:
        raise ServiceError(400, 'message is required.')
    if outcome and outcome not in DocumentCallLog.OUTCOMES:
        raise ServiceError(400, f'Outcome must be one of: {", ".join(DocumentCallLog.OUTCOMES)}.')
    call_later = _parse_date(call_later_date, 'call_later_date')
    entry = DocumentCallLog.objects.create(document=document, message=message, user=user,
                                           call_later_date=call_later, outcome=outcome or '')
    if call_later:                                          # "call me later" -> a Call task for the logger
        task_service.call_task(user, user, document.contact.name if document.contact_id else '', document.customer.name,
                               call_later, related_customer=document.customer, related_contact=document.contact,
                               related_document=document)
    return entry


def last_contact_on(document):
    logs = list(document.call_log.all())
    return max((l.timestamp for l in logs), default=None)


def next_call_later_date(document):
    dated = [l for l in document.call_log.all() if l.call_later_date]
    return max(dated, key=lambda l: l.timestamp).call_later_date if dated else None


def call_later_bucket(document, today=None):
    cl = next_call_later_date(document)
    today = today or timezone.localdate()
    if not cl:
        return 'none'
    return 'overdue' if cl < today else 'today' if cl == today else 'upcoming'


# --------------------------------------------------------------------------- clone
def clone_document(user, source):
    """A new document with the same customer, items and settings, a fresh number,
    today's date, and none of the source's history (logs, supply, outcome)."""
    data = {
        'type': source.type, 'branch_id': source.branch_id, 'customer_id': source.customer_id,
        'contact_id': source.contact_id, 'date': timezone.localdate().isoformat(), 'remarks': source.remarks,
        'reference_id': source.reference_id, 'source': source.source, 'vehicle': source.vehicle, 'transport': source.transport,
        'show_discount_in_pdf': source.show_discount_in_pdf, 'packing_charges': source.packing_charges,
        'packing_tax': source.packing_tax, 'freight_charges': source.freight_charges, 'freight_tax': source.freight_tax,
        'other_charges': source.other_charges, 'other_charges_tax': source.other_charges_tax, 'round_off': source.round_off,
        'sales_person_id': source.sales_person_id, 'payment_terms': source.payment_terms, 'terms': source.terms,
        'valid_till': None, 'ref_no': source.ref_no, 'ref_date': source.ref_date,
        'doc_number': '' if source.type != 'po' else source.doc_number,
        'items': [{k: getattr(i, k) for k in ITEM_FIELDS} for i in source.items.all()],
    }
    return create_document(user, data)


# --------------------------------------------------------------------------- approvals support
def snapshot(document):
    data = {f: getattr(document, f) for f in ('remarks', 'source', 'vehicle', 'transport', 'show_discount_in_pdf',
                                              'packing_charges', 'packing_tax', 'freight_charges', 'freight_tax',
                                              'other_charges', 'other_charges_tax', 'round_off', 'payment_terms',
                                              'ref_no', 'terms', 'order_status', 'contact_id', 'sales_person_id')}
    data['date'] = document.date
    data['valid_till'] = document.valid_till
    data['items'] = [{k: getattr(i, k) for k in ITEM_FIELDS} for i in document.items.all()]
    return _jsonable(data)


def _jsonable(value):
    import datetime
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


# --------------------------------------------------------------------------- list filters
def filter_documents(queryset, params):
    """Customer, number, item, date range, status, branch, call-later bucket, last contact."""
    get = params.get
    for key, field in (('type', 'type'), ('branch_id', 'branch_id'), ('customer_id', 'customer_id')):
        if get(key):
            queryset = queryset.filter(**{field: get(key)})
    if get('number'):
        queryset = queryset.filter(doc_number__icontains=get('number'))
    if get('item'):
        queryset = queryset.filter(items__item_name__icontains=get('item'))
    if get('date_from'):
        queryset = queryset.filter(date__gte=_parse_date(get('date_from'), 'date_from'))
    if get('date_to'):
        queryset = queryset.filter(date__lte=_parse_date(get('date_to'), 'date_to'))
    if get('status'):
        queryset = queryset.filter(order_status=get('status'))
    return queryset.distinct()


def post_filter(documents, params):
    """Filters that depend on the contact log (computed in Python over prefetched logs)."""
    bucket = params.get('call_later')
    if bucket:
        documents = [d for d in documents if call_later_bucket(d) == bucket]
    if params.get('last_contact_days'):
        try:
            cutoff = timezone.now() - timedelta(days=int(params['last_contact_days']))
        except ValueError:
            raise ServiceError(400, 'last_contact_days must be a number.')
        documents = [d for d in documents if (last_contact_on(d) or cutoff) <= cutoff]
    if params.get('pending') in ('1', 'true'):
        documents = [d for d in documents if (d.type == 'dc' and dc_is_pending(d)) or (d.type == 'po' and d.order_status != 'Completed')]
    return documents
