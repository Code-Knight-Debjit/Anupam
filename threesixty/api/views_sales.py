"""Sales document (enquiry/quotation/po/dc/proforma) resource.

Edit/delete permission resolution follows AUDIT.md §3 + §5.2 exactly:
`can_edit_delete_sales_document()` is checked first (the Sales-Manager/
Quotation hard block — a 403, never an approval request, see
`RoleRules.can_edit_delete_sales_document`), then Admin/Branch Manager/
Branch Staff act directly while a Sales Manager's edit/delete on any other
document type is routed to the approval queue.

Totals math is now recomputed server-side (Phase 3), exactly matching the
save-time handler at original ~L11370-11436 — see
`threesixty/services/totals.py` for the verified formula (distinct from
the separate print-time `computeQuotationDocData`, ~L8805-8850, which is
PDF-rendering-only and ported separately with the PDF export). Per-item
`amount`/`value` and the document's `sub_total`/`total_amount` are always
derived from `qty`/`rate`/`discount`/`tax` and the charge fields — a
client can no longer set them directly.

The reference-chain link (quotation->enquiry, dc->po, proforma->quotation)
is validated for *type compatibility* when a `reference_id` is supplied,
but is not required — whether the original always requires a reference on
these types was flagged "not yet deep-read" in AUDIT.md §1, so this stays
permissive rather than guessing a hard requirement.
"""
from django.http import JsonResponse

from ..models import (
    ApprovalRequest, Branch, Customer, DocumentCallLog, SalesDocument, SalesDocumentItem, StockTransaction,
    SupplyLogEntry,
)
from ..permissions import RoleRules
from ..services.numbering import allocate_next_number, bump_counter_to
from ..services.totals import TYPE_FLAGS, compute_document_totals, compute_item_fields
from .concurrency import check_version
from .fields import parse_date_input
from .http import ApiError, parse_body
from .resources import JsonResource
from .serializers import (
    serialize_approval_request, serialize_document_call_log_entry, serialize_sales_document,
    serialize_supply_log_entry,
)

DOCUMENT_SCALAR_FIELDS = (
    'contact_id', 'date', 'remarks', 'source', 'order_status', 'vehicle', 'transport',
    'show_discount_in_pdf', 'packing_charges', 'packing_tax', 'freight_charges', 'freight_tax',
    'other_charges', 'other_charges_tax', 'round_off',
    'quotation_value', 'sales_person_id', 'valid_till', 'ref_no', 'ref_date', 'payment_terms', 'terms',
)


DOCUMENT_DATE_FIELDS = ('date', 'valid_till', 'ref_date')


def _apply_scalars(instance, data):
    for field in DOCUMENT_SCALAR_FIELDS:
        if field in data:
            value = data[field]
            if field in DOCUMENT_DATE_FIELDS:
                value = parse_date_input(value, field)
            setattr(instance, field, value)


def _validate_reference(doc_type, reference):
    expected_ref_type = SalesDocument.REF_TYPE_OF.get(doc_type)
    if reference is None:
        return
    if expected_ref_type is None:
        raise ApiError(400, f'{doc_type} documents do not take a reference document.')
    if reference.type != expected_ref_type:
        raise ApiError(400, f'reference document must be a {expected_ref_type}, not a {reference.type}.')


def _replace_items(document, items_data):
    document.items.all().delete()
    for position, item_data in enumerate(items_data):
        amount, value = compute_item_fields(document.type, item_data)
        SalesDocumentItem.objects.create(
            document=document, position=position,
            item_name=item_data.get('item_name', ''), make=item_data.get('make', ''),
            qty=item_data.get('qty', 0), unit=item_data.get('unit', ''),
            rate=item_data.get('rate', 0), discount=item_data.get('discount', 0),
            tax=item_data.get('tax', 0), amount=amount, value=value,
        )


def _recompute_totals(document):
    """Sets `sub_total`/`total_amount` from the document's *saved* items +
    charges (verified save-time formula, see `services/totals.py`) — call
    after items have been written, whenever items or any charge field may
    have changed. Pins both to 0.00 for types without charges (enquiry/po),
    matching the original form never showing/setting them."""
    items_data = [
        {'qty': it.qty, 'rate': it.rate, 'discount': it.discount, 'tax': it.tax}
        for it in document.items.all()
    ]
    sub_total, total_amount = compute_document_totals(
        document.type, items_data, document.packing_charges, document.packing_tax,
        document.freight_charges, document.freight_tax, document.other_charges,
        document.other_charges_tax, document.round_off,
    )
    document.sub_total = sub_total
    document.total_amount = total_amount
    document.save(update_fields=['sub_total', 'total_amount'])


def _auto_stock_out_from_dc(document, user):
    """Exact port of `autoStockOutFromDC` (original ~L12844-12856) — fires
    only once, right after a *new* Delivery Challan is created (never on
    update), logging an OUT stock transaction per item that has both a
    name and a non-zero qty."""
    for item in document.items.all():
        if not item.item_name or not item.qty:
            continue
        StockTransaction.objects.create(
            branch=document.branch, item_name=item.item_name, make=item.make, unit=item.unit,
            type=StockTransaction.TYPE_OUT, qty=item.qty, date=document.date,
            source='Delivery Challan', ref_document=document,
            remarks=f'Auto-generated from {document.doc_number}', recorded_by=user,
        )


class SalesDocumentResource(JsonResource):
    model = SalesDocument

    def list_queryset(self, request, **kwargs):
        qs = SalesDocument.objects.all()
        doc_type = request.GET.get('type')
        if doc_type:
            qs = qs.filter(type=doc_type)
        branch_id = request.GET.get('branch_id')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        customer_id = request.GET.get('customer_id')
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        return RoleRules.visible_sales_documents(request.user, qs)

    def serialize(self, request, instance):
        return serialize_sales_document(instance)

    def apply_create(self, request, data, **kwargs):
        doc_type = data.get('type')
        if doc_type not in dict(SalesDocument.TYPE_CHOICES):
            raise ApiError(400, 'A valid type is required.')
        try:
            branch = Branch.objects.get(pk=data.get('branch_id'))
        except Branch.DoesNotExist:
            raise ApiError(400, 'branch_id is required and must exist.')
        try:
            customer = Customer.objects.get(pk=data.get('customer_id'))
        except Customer.DoesNotExist:
            raise ApiError(400, 'customer_id is required and must exist.')
        if not data.get('date'):
            raise ApiError(400, 'date is required.')

        reference = None
        if data.get('reference_id'):
            try:
                reference = SalesDocument.objects.get(pk=data['reference_id'])
            except SalesDocument.DoesNotExist:
                raise ApiError(400, 'reference_id does not exist.')
        _validate_reference(doc_type, reference)

        doc_number = (data.get('doc_number') or '').strip()
        if doc_number:
            bump_counter_to(branch, doc_type, doc_number)
        else:
            doc_number = allocate_next_number(branch, doc_type)

        document = SalesDocument(
            type=doc_type, doc_number=doc_number, branch=branch, customer=customer,
            reference=reference, created_by=request.user,
        )
        _apply_scalars(document, data)
        document.save()
        if data.get('items'):
            _replace_items(document, data['items'])
        _recompute_totals(document)
        if doc_type == SalesDocument.TYPE_DC:
            _auto_stock_out_from_dc(document, request.user)
        return document

    def _resolve_mutation_mode(self, request, document):
        if not RoleRules.can_edit_delete_sales_document(request.user, document):
            raise ApiError(403, 'A Sales Manager cannot edit or delete a Quotation.')
        if RoleRules.can_direct_edit_delete_sales_doc(request.user):
            return 'direct'
        if RoleRules.is_sales_manager(request.user):
            return 'approval'
        raise ApiError(403, 'You cannot edit this document.')

    def apply_update(self, request, instance, data, **kwargs):
        mode = self._resolve_mutation_mode(request, instance)
        if mode == 'direct':
            check_version(data, instance)
            _apply_scalars(instance, data)
            instance.version += 1
            instance.save()
            if 'items' in data:
                _replace_items(instance, data['items'])
            _recompute_totals(instance)
            return instance
        approval = ApprovalRequest.objects.create(
            type=ApprovalRequest.TYPE_EDIT, document=instance, proposed_data=data, requested_by=request.user,
        )
        return JsonResponse(
            {'approval_requested': True, 'approval': serialize_approval_request(approval)}, status=202
        )

    def apply_delete(self, request, instance, **kwargs):
        mode = self._resolve_mutation_mode(request, instance)
        if mode == 'direct':
            instance.delete()
            return None
        approval = ApprovalRequest.objects.create(
            type=ApprovalRequest.TYPE_DELETE, document=instance, requested_by=request.user,
        )
        return JsonResponse(
            {'approval_requested': True, 'approval': serialize_approval_request(approval)}, status=202
        )


class DocumentCallLogResource(JsonResource):
    """Append-only call log on a sales document (`cfg.hasCallLog`) — any
    staff who can see the document may add an entry; nothing is ever
    edited or deleted (matches the original's log-only usage)."""
    model = DocumentCallLog

    def list_queryset(self, request, document_id=None, **kwargs):
        visible_docs = RoleRules.visible_sales_documents(request.user, SalesDocument.objects.all())
        qs = DocumentCallLog.objects.filter(document__in=visible_docs)
        if document_id is not None:
            qs = qs.filter(document_id=document_id)
        return qs

    def serialize(self, request, instance):
        return serialize_document_call_log_entry(instance)

    def apply_create(self, request, data, document_id=None, **kwargs):
        document_id = document_id or data.get('document_id')
        visible_docs = RoleRules.visible_sales_documents(request.user, SalesDocument.objects.all())
        try:
            document = visible_docs.get(pk=document_id)
        except SalesDocument.DoesNotExist:
            raise ApiError(404, 'Document not found.')
        message = (data.get('message') or '').strip()
        if not message:
            raise ApiError(400, 'message is required.')
        return DocumentCallLog.objects.create(document=document, message=message, user=request.user)

    def apply_update(self, request, instance, data, **kwargs):
        raise ApiError(405, 'Call log entries cannot be edited.')

    def apply_delete(self, request, instance, **kwargs):
        raise ApiError(405, 'Call log entries cannot be deleted.')


class SupplyLogEntryResource(JsonResource):
    """DC/PO fulfilment tracking against an item's pending qty — logging
    supply is restricted the same way direct document edits are
    (Admin/Branch Manager/Branch Staff); a Sales Manager never logs supply
    directly, matching `can_direct_edit_delete_sales_doc`. The
    `autoStockOutFromDC` auto-stock-out hook on Delivery Challan save
    (original ~L12844-12856) is explicitly **not** ported here — it is
    Phase 3 scope (see docs/360/AUDIT.md §1, dormant Stock module note)."""
    model = SupplyLogEntry

    def list_queryset(self, request, item_id=None, **kwargs):
        visible_docs = RoleRules.visible_sales_documents(request.user, SalesDocument.objects.all())
        qs = SupplyLogEntry.objects.filter(item__document__in=visible_docs)
        if item_id is not None:
            qs = qs.filter(item_id=item_id)
        return qs

    def serialize(self, request, instance):
        return serialize_supply_log_entry(instance)

    def apply_create(self, request, data, item_id=None, **kwargs):
        item_id = item_id or data.get('item_id')
        if not RoleRules.can_direct_edit_delete_sales_doc(request.user):
            raise ApiError(403, 'You cannot log supply against this item.')
        visible_docs = RoleRules.visible_sales_documents(request.user, SalesDocument.objects.all())
        try:
            item = SalesDocumentItem.objects.filter(document__in=visible_docs).get(pk=item_id)
        except SalesDocumentItem.DoesNotExist:
            raise ApiError(404, 'Item not found.')
        if data.get('qty_supplied') is None or not data.get('date'):
            raise ApiError(400, 'qty_supplied and date are required.')
        return SupplyLogEntry.objects.create(
            item=item, date=parse_date_input(data['date'], 'date'), qty_supplied=data['qty_supplied'],
            remarks=data.get('remarks', ''), recorded_by=request.user,
        )

    def apply_update(self, request, instance, data, **kwargs):
        raise ApiError(405, 'Supply log entries cannot be edited.')

    def apply_delete(self, request, instance, **kwargs):
        raise ApiError(405, 'Supply log entries cannot be deleted.')
