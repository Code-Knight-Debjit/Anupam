"""Sales documents (enquiry / quotation / proforma / pending PO / delivery
challan) — thin views over `services.documents`.

Edit / delete (REQ-ROLE-02, AUDIT §3): Admin, Branch Manager and Branch Staff
act directly; a Sales Manager's edit or delete of ANY sales document (including
a Quotation) queues an approval request holding before/after data.
"""
from django.db.models import Prefetch
from django.http import JsonResponse

from ..models import (
    ApprovalRequest, DocumentCallLog, InvoiceLogEntry, SalesDocument, SalesDocumentItem, SupplyLogEntry,
)
from ..permissions import RoleRules, staff_360_required
from ..services import approvals as approval_service
from ..services import documents as doc_service
from ..services import tasks as task_service
from .concurrency import check_version
from .http import ApiError, error_response, input_errors_as_400, parse_body
from .resources import JsonResource
from .serializers import (
    serialize_approval_request, serialize_document_call_log_entry, serialize_invoice_log_entry,
    serialize_sales_document, serialize_supply_log_entry,
)

from django.contrib.auth import get_user_model

User = get_user_model()


def document_queryset(user):
    return doc_service.visible_documents(user).select_related(
        'customer', 'branch', 'contact', 'reference', 'created_by', 'sales_person').prefetch_related(
        Prefetch('items', queryset=SalesDocumentItem.objects.prefetch_related('supply_log', 'invoice_log')),
        'call_log')


class SalesDocumentResource(JsonResource):
    model = SalesDocument

    def list_queryset(self, request, **kwargs):
        qs = doc_service.filter_documents(document_queryset(request.user), request.GET)
        return qs.order_by('-date', '-id')

    def get(self, request, pk=None, **kwargs):
        if pk is None and any(request.GET.get(k) for k in ('call_later', 'last_contact_days', 'pending')):
            # Filters that depend on the contact log run over the (prefetched) rows.
            from .pagination import paginate
            rows = doc_service.post_filter(list(self.list_queryset(request)), request.GET)
            return JsonResponse(paginate(request, rows, lambda o: self.serialize(request, o)))
        return super().get(request, pk=pk, **kwargs)

    def serialize(self, request, instance):
        return serialize_sales_document(instance)

    def apply_create(self, request, data, **kwargs):
        document, info = doc_service.create_document(request.user, data)
        request._enquiry_completed = info.get('enquiry_completed')
        return document

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        completed = getattr(request, '_enquiry_completed', None)
        if completed and response.status_code == 201:
            import json
            body = json.loads(response.content)
            body['enquiry_completed'] = completed
            return JsonResponse(body, status=201)
        return response

    def apply_update(self, request, instance, data, **kwargs):
        if RoleRules.needs_approval(request.user, 'salesdoc.edit'):
            return _approval(approval_service.request_change(
                request.user, ApprovalRequest.TYPE_EDIT, instance, proposed=data))
        check_version(data, instance)
        doc_service.apply_edit(instance, data, request.user)
        return _document_or_404(request, instance.pk)          # fresh copy: the prefetched rows are stale

    def apply_delete(self, request, instance, **kwargs):
        if RoleRules.needs_approval(request.user, 'salesdoc.delete'):
            return _approval(approval_service.request_change(request.user, ApprovalRequest.TYPE_DELETE, instance))
        instance.delete()


def _approval(approval):
    return JsonResponse({'approval_requested': True, 'approval': serialize_approval_request(approval)}, status=202)


def _document_or_404(request, pk):
    try:
        return document_queryset(request.user).get(pk=pk)
    except SalesDocument.DoesNotExist:
        raise ApiError(404, 'Document not found.')


@staff_360_required
@input_errors_as_400
def document_outcome(request, pk):
    """POST {status: Win|Lose, order_value?, lost_reason?} — REQ-AUT-12."""
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    data = parse_body(request)
    document = doc_service.mark_outcome(
        _document_or_404(request, pk), data.get('status'), data.get('order_value'), data.get('lost_reason', ''))
    return JsonResponse(serialize_sales_document(_document_or_404(request, document.pk)))


@staff_360_required
@input_errors_as_400
def document_clone(request, pk):
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    source = _document_or_404(request, pk)
    clone, _info = doc_service.clone_document(request.user, source)
    return JsonResponse(serialize_sales_document(_document_or_404(request, clone.pk)), status=201)


@staff_360_required
@input_errors_as_400
def document_schedule(request, pk):
    """POST {kind, due_date, assigned_to_id?} — "Schedule follow-up" (REQ-AUT-08)."""
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    data = parse_body(request)
    document = _document_or_404(request, pk)
    try:
        assignee = User.objects.get(pk=data.get('assigned_to_id') or request.user.pk, is_active=True,
                                    threesixty_profile__is_active_employee=True)
    except (User.DoesNotExist, ValueError, TypeError):
        return error_response(ApiError(400, 'assigned_to_id does not exist.'))
    if not data.get('due_date'):
        return error_response(ApiError(400, 'due_date is required.'))
    task = task_service.schedule_from_document(
        request.user, document, data.get('kind'), doc_service._parse_date(data['due_date'], 'due_date'), assignee)
    return JsonResponse({'task_id': task.pk, 'title': task.title}, status=201)


class DocumentCallLogResource(JsonResource):
    """Contact log on a quotation / proforma / challan: append-only. A
    "call me later" date also creates a Call task for the person logging it."""
    model = DocumentCallLog

    def list_queryset(self, request, document_id=None, **kwargs):
        qs = DocumentCallLog.objects.filter(document__in=doc_service.visible_documents(request.user)).select_related('user')
        if document_id is not None:
            qs = qs.filter(document_id=document_id)
        return qs.order_by('timestamp', 'id')

    def serialize(self, request, instance):
        return serialize_document_call_log_entry(instance)

    def apply_create(self, request, data, document_id=None, **kwargs):
        document = _document_or_404(request, document_id or data.get('document_id'))
        return doc_service.add_contact_log(
            request.user, document, data.get('message'), data.get('call_later_date'), data.get('outcome', ''))

    def apply_update(self, request, instance, data, **kwargs):
        raise ApiError(405, 'Call log entries cannot be edited.')

    def apply_delete(self, request, instance, **kwargs):
        raise ApiError(405, 'Call log entries cannot be deleted.')


def _item_or_404(request, item_id):
    try:
        return SalesDocumentItem.objects.select_related('document').prefetch_related('supply_log', 'invoice_log').filter(
            document__in=doc_service.visible_documents(request.user)).get(pk=item_id)
    except (SalesDocumentItem.DoesNotExist, ValueError, TypeError):
        raise ApiError(404, 'Item not found.')


class SupplyLogEntryResource(JsonResource):
    """Manual supply entries against Pending PO items: add (quantity above the
    pending balance needs `confirm_over`), edit, delete. Every change
    recomputes the PO status; Hold stays."""
    model = SupplyLogEntry

    def list_queryset(self, request, item_id=None, **kwargs):
        qs = SupplyLogEntry.objects.filter(item__document__in=doc_service.visible_documents(request.user))
        if item_id is not None:
            qs = qs.filter(item_id=item_id)
        return qs.select_related('recorded_by').order_by('date', 'id')

    def serialize(self, request, instance):
        return serialize_supply_log_entry(instance)

    def apply_create(self, request, data, item_id=None, **kwargs):
        item = _item_or_404(request, item_id or data.get('item_id'))
        return doc_service.add_supply(request.user, item, data.get('qty_supplied'), data.get('date'),
                                      data.get('remarks', ''), bool(data.get('confirm_over')))

    def apply_update(self, request, instance, data, **kwargs):
        return doc_service.update_supply(request.user, instance, data, bool(data.get('confirm_over')))

    def apply_delete(self, request, instance, **kwargs):
        doc_service.delete_supply(request.user, instance)


class InvoiceLogEntryResource(JsonResource):
    """'Invoice Done' entries on delivery-challan items."""
    model = InvoiceLogEntry

    def list_queryset(self, request, item_id=None, **kwargs):
        qs = InvoiceLogEntry.objects.filter(item__document__in=doc_service.visible_documents(request.user))
        if item_id is not None:
            qs = qs.filter(item_id=item_id)
        return qs.select_related('recorded_by').order_by('created_at', 'id')

    def serialize(self, request, instance):
        return serialize_invoice_log_entry(instance)

    def apply_create(self, request, data, item_id=None, **kwargs):
        item = _item_or_404(request, item_id or data.get('item_id'))
        return doc_service.add_invoice(request.user, item, data.get('bill_number'), data.get('bill_date'),
                                       data.get('qty_invoiced'), bool(data.get('confirm_over')))

    def apply_update(self, request, instance, data, **kwargs):
        raise ApiError(405, 'Invoice entries cannot be edited.')

    def apply_delete(self, request, instance, **kwargs):
        raise ApiError(405, 'Invoice entries cannot be deleted.')
