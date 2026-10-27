"""Task Manager, Notifications, and the Approval queue.

Approve/reject follow AUDIT.md §3 exactly: Admin sees and may decide on
every pending request; a Branch Manager only sees/decides requests raised
by staff in their own branch scope (`namesInManagerScope`, ~L8201); Branch
Staff and Sales Manager can never approve/reject (they are requesters,
not approvers).
"""
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone

from ..models import ApprovalRequest, Customer, Notification, Task
from ..permissions import RoleRules, staff_360_required
from .concurrency import check_version
from .fields import parse_date_input
from .http import INPUT_ERROR_MESSAGE, INPUT_ERRORS, ApiError, error_response
from .resources import JsonResource
from .serializers import serialize_approval_request, serialize_notification, serialize_task
from .views_customers import _apply_customer_m2m, _apply_customer_scalars
from .views_sales import _apply_scalars as _apply_document_scalars
from .views_sales import _recompute_totals, _replace_items


class TaskResource(JsonResource):
    model = Task

    def list_queryset(self, request, **kwargs):
        qs = Task.objects.all()
        status = request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        if RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user):
            return qs
        user = request.user
        return qs.filter(Q(assigned_to=user) | Q(created_by=user) | Q(joint_with=user)).distinct()

    def serialize(self, request, instance):
        return serialize_task(instance)

    def _can_modify(self, request, instance):
        user = request.user
        return (
            RoleRules.is_admin(user) or RoleRules.is_branch_manager(user)
            or instance.assigned_to_id == user.id or instance.created_by_id == user.id
        )

    def apply_create(self, request, data, **kwargs):
        title = (data.get('title') or '').strip()
        if not title:
            raise ApiError(400, 'title is required.')
        task = Task.objects.create(
            title=title, description=data.get('description', ''),
            assigned_to_id=data.get('assigned_to_id') or request.user.id,
            priority=data.get('priority', Task.PRIORITY_MEDIUM), task_type=data.get('task_type', ''),
            due_date=parse_date_input(data.get('due_date'), 'due_date'),
            related_customer_id=data.get('related_customer_id'),
            related_contact_id=data.get('related_contact_id'),
            related_document_id=data.get('related_document_id'), created_by=request.user,
        )
        if 'joint_with_user_ids' in data:
            task.joint_with.set(data['joint_with_user_ids'])
        return task

    def apply_update(self, request, instance, data, **kwargs):
        if not self._can_modify(request, instance):
            raise ApiError(403, 'You cannot modify this task.')
        check_version(data, instance)
        for field in ('title', 'description', 'priority', 'task_type', 'due_date'):
            if field in data:
                value = data[field]
                if field == 'due_date':
                    value = parse_date_input(value, field)
                setattr(instance, field, value)
        if 'status' in data:
            if data['status'] == Task.STATUS_COMPLETED and instance.status != Task.STATUS_COMPLETED:
                instance.completed_at = timezone.now()
            instance.status = data['status']
        instance.version += 1
        instance.save()
        if 'joint_with_user_ids' in data:
            instance.joint_with.set(data['joint_with_user_ids'])
        return instance

    def apply_delete(self, request, instance, **kwargs):
        if not self._can_modify(request, instance):
            raise ApiError(403, 'You cannot delete this task.')
        instance.delete()


class NotificationResource(JsonResource):
    """Own-notifications only — `list_queryset` scoping to `user=request.user`
    also makes `get_object` naturally 404 on another user's notification."""
    model = Notification

    def list_queryset(self, request, **kwargs):
        qs = Notification.objects.filter(user=request.user)
        if request.GET.get('unread') == '1':
            qs = qs.filter(read=False)
        return qs

    def serialize(self, request, instance):
        return serialize_notification(instance)

    def apply_create(self, request, data, **kwargs):
        raise ApiError(405, 'Notifications are created automatically by other actions.')

    def apply_update(self, request, instance, data, **kwargs):
        if 'read' in data:
            instance.read = bool(data['read'])
            instance.save(update_fields=['read'])
        return instance

    def apply_delete(self, request, instance, **kwargs):
        instance.delete()


class ApprovalRequestResource(JsonResource):
    model = ApprovalRequest

    def list_queryset(self, request, **kwargs):
        qs = ApprovalRequest.objects.all()
        status = request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return RoleRules.visible_approval_requests(request.user, qs)

    def serialize(self, request, instance):
        return serialize_approval_request(instance)

    def apply_create(self, request, data, **kwargs):
        """Only `customer-access` requests are created directly through
        this endpoint — `edit`/`delete` requests are always a side effect
        of a mutation attempt on the target resource itself (see
        `CustomerResource`/`SalesDocumentResource`), never user-authored."""
        if data.get('type') != ApprovalRequest.TYPE_CUSTOMER_ACCESS:
            raise ApiError(400, 'Only customer-access requests can be created directly.')
        try:
            customer = Customer.objects.get(pk=data.get('customer_id'))
        except Customer.DoesNotExist:
            raise ApiError(400, 'customer_id is required and must exist.')
        return ApprovalRequest.objects.create(
            type=ApprovalRequest.TYPE_CUSTOMER_ACCESS, customer=customer,
            note=data.get('note', ''), requested_by=request.user,
        )

    def apply_update(self, request, instance, data, **kwargs):
        raise ApiError(405, 'Use the approve/reject actions, not a direct update.')

    def apply_delete(self, request, instance, **kwargs):
        if instance.requested_by_id != request.user.id and not RoleRules.is_admin(request.user):
            raise ApiError(403, 'You cannot withdraw this request.')
        if instance.status != ApprovalRequest.STATUS_PENDING:
            raise ApiError(400, 'Only a pending request can be withdrawn.')
        instance.delete()


def _require_approver(request):
    if not (RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user)):
        raise ApiError(403, 'Only Admin or Branch Manager can approve/reject requests.')


def _get_pending_in_scope(request, pk):
    qs = RoleRules.visible_approval_requests(
        request.user, ApprovalRequest.objects.filter(status=ApprovalRequest.STATUS_PENDING)
    )
    try:
        return qs.get(pk=pk)
    except ApprovalRequest.DoesNotExist:
        raise ApiError(404, 'Pending approval request not found in your scope.')


def _apply_approval(approval):
    """Applies the approved change to its target. `edit` merges
    `proposed_data` onto the target exactly as the direct-edit path would
    have (reusing the same field-apply helpers), then bumps `version`;
    `delete` removes the target; `customer-access` grants `assigned_to`.

    For `delete`, the caller must persist `approval` (with its `customer`/
    `document` FK already nulled out) *before* this is invoked — `customer`
    and `document` are `on_delete=CASCADE`, so deleting the target while
    this row still points at it in the database would cascade-delete the
    approval request itself out from under us."""
    if approval.type == ApprovalRequest.TYPE_DELETE:
        target = getattr(approval, '_delete_target', None) or approval.customer or approval.document
        if target is not None:
            target.delete()
        return
    if approval.type == ApprovalRequest.TYPE_EDIT:
        data = dict(approval.proposed_data or {})
        data.pop('version', None)
        if approval.customer_id:
            customer = approval.customer
            _apply_customer_scalars(customer, data)
            customer.version += 1
            customer.save()
            _apply_customer_m2m(customer, data)
        elif approval.document_id:
            document = approval.document
            _apply_document_scalars(document, data)
            document.version += 1
            document.save()
            if 'items' in data:
                _replace_items(document, data['items'])
            _recompute_totals(document)
        return
    if approval.type == ApprovalRequest.TYPE_CUSTOMER_ACCESS:
        if approval.customer_id and approval.requested_by_id:
            approval.customer.assigned_to.add(approval.requested_by)


@staff_360_required
def approve_request(request, pk):
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    try:
        _require_approver(request)
        # One transaction: if applying the change fails (bad proposed data,
        # DB error) the approval stays pending instead of half-applied.
        with transaction.atomic():
            approval = _get_pending_in_scope(request, pk)
            approval.status = ApprovalRequest.STATUS_APPROVED
            approval.reviewed_by = request.user
            approval.reviewed_at = timezone.now()
            if approval.type == ApprovalRequest.TYPE_DELETE:
                approval._delete_target = approval.customer or approval.document
                approval.customer = None
                approval.document = None
                approval.save()
            _apply_approval(approval)
            if approval.type != ApprovalRequest.TYPE_DELETE:
                approval.save()
            if approval.requested_by_id:
                Notification.objects.create(
                    user=approval.requested_by, type='approval',
                    text=f'Your {approval.get_type_display()} request was approved.',
                )
    except ApiError as exc:
        return error_response(exc)
    except INPUT_ERRORS:
        return error_response(ApiError(400, INPUT_ERROR_MESSAGE))
    return JsonResponse(serialize_approval_request(approval))


@staff_360_required
def reject_request(request, pk):
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    try:
        _require_approver(request)
        approval = _get_pending_in_scope(request, pk)
        approval.status = ApprovalRequest.STATUS_REJECTED
        approval.reviewed_by = request.user
        approval.reviewed_at = timezone.now()
        approval.save()
        if approval.requested_by_id:
            Notification.objects.create(
                user=approval.requested_by, type='approval',
                text=f'Your {approval.get_type_display()} request was rejected.',
            )
    except ApiError as exc:
        return error_response(exc)
    return JsonResponse(serialize_approval_request(approval))
