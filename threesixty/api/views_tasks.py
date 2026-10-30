"""Tasks, Notifications and the Approval queue — thin views over
`services.tasks` and `services.approvals`, which hold the rules.

Approve / reject (AUDIT §3): Admin sees and decides every pending request; a
Branch Manager only requests raised by people in their branch scope; Branch
Staff and Sales Managers are requesters, never approvers.
"""
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import JsonResponse

from ..models import ApprovalRequest, Customer, Notification, Task
from ..permissions import RoleRules, staff_360_required
from ..services import approvals as approval_service
from ..services import tasks as task_service
from .concurrency import check_version
from .fields import parse_date_input
from .http import ApiError, error_response, input_errors_as_400, parse_body
from .resources import JsonResource
from .serializers import serialize_approval_request, serialize_notification, serialize_task

User = get_user_model()


def _assignable_ids(ids):
    users = User.objects.filter(pk__in=ids or [], is_active=True, threesixty_profile__is_active_employee=True)
    found = list(users.values_list('pk', flat=True))
    if ids and len(set(map(int, ids))) != len(found):
        raise ApiError(400, 'One or more assignees do not exist or are inactive.')
    return found


class TaskResource(JsonResource):
    """`?scope=mine` (default) is the viewer's own tasks, `all` (Admin / Branch
    Manager) is everyone's, `assigned_by_me` is the panel under the calendar."""
    model = Task

    def list_queryset(self, request, **kwargs):
        base = Task.objects.select_related('assigned_to', 'created_by').prefetch_related('joint_with')
        scope = request.GET.get('scope', 'mine')
        if scope == 'assigned_by_me':
            qs = task_service.assigned_by_me(request.user, base)
        elif scope == 'all' and not (RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user)):
            raise ApiError(403, 'Only Admin or Branch Manager can see everyone’s tasks.')
        else:
            qs = task_service.main_list(request.user, base, scope)
        status = request.GET.get('status')
        if status:
            qs = qs.filter(status=task_service.normalize_status(status))
        return qs.order_by('due_date', '-created_at')

    def get_object(self, request, pk, **kwargs):
        # Detail / edit / delete work on anything the viewer may see, whichever list it is on.
        try:
            return task_service.visible_tasks(
                request.user, Task.objects.select_related('assigned_to', 'created_by').prefetch_related('joint_with')
            ).get(pk=pk)
        except Task.DoesNotExist:
            raise ApiError(404, 'Not found.')

    def serialize(self, request, instance):
        return serialize_task(instance)

    def apply_create(self, request, data, **kwargs):
        ids = data.get('assigned_to_ids') or ([data['assigned_to_id']] if data.get('assigned_to_id') else None)
        ids = _assignable_ids(ids) if ids else [request.user.pk]
        extra = _assignable_ids(data.get('joint_with_user_ids')) if data.get('joint_with_user_ids') else []
        return task_service.create_task(
            request.user, title=data.get('title'), assignee_user_ids=ids + [i for i in extra if i not in ids],
            due_date=parse_date_input(data.get('due_date'), 'due_date'), description=data.get('description', ''),
            priority=data.get('priority'), task_type=data.get('task_type', ''),
            customer=Customer.objects.filter(pk=data['related_customer_id']).first() if data.get('related_customer_id') else None,
        )

    def apply_update(self, request, instance, data, **kwargs):
        check_version(data, instance)
        status_only = set(data) <= {'status', 'version'}
        if 'status' in data:
            task_service.set_status(request.user, instance, data['status'])
        if not status_only:
            if not task_service.can_edit(request.user, instance):
                raise ApiError(403, 'Only Admin, Branch Manager or the creator can edit this task.')
            for field in ('title', 'description', 'priority', 'task_type', 'due_date'):
                if field in data:
                    value = parse_date_input(data[field], field) if field == 'due_date' else data[field]
                    setattr(instance, field, value)
            if not (instance.title or '').strip():
                raise ApiError(400, 'title is required.')
            if 'assigned_to_id' in data:
                instance.assigned_to_id = _assignable_ids([data['assigned_to_id']])[0]
            if 'joint_with_user_ids' in data:
                instance.joint_with.set(_assignable_ids(data['joint_with_user_ids']))
        instance.version += 1
        instance.save()
        return instance

    def apply_delete(self, request, instance, **kwargs):
        task_service.delete_task(request.user, instance)


class NotificationResource(JsonResource):
    """Own notifications only — scoping the queryset to `user=request.user`
    also makes another person's notification a 404."""
    model = Notification

    def list_queryset(self, request, **kwargs):
        qs = Notification.objects.filter(user=request.user)
        if request.GET.get('unread') == '1':
            qs = qs.filter(read=False)
        return qs.order_by('-created_at', '-id')

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


@staff_360_required
@input_errors_as_400
def notifications_read_all(request):
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    count = Notification.objects.filter(user=request.user, read=False).update(read=True)
    return JsonResponse({'marked': count})


class ApprovalRequestResource(JsonResource):
    model = ApprovalRequest

    def list_queryset(self, request, **kwargs):
        qs = ApprovalRequest.objects.select_related('requested_by', 'reviewed_by')
        status = request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        qs = RoleRules.visible_approval_requests(request.user, qs)
        if status in (None, '', ApprovalRequest.STATUS_PENDING):
            # A pending request whose record has since gone is dropped from the queue.
            qs = qs.filter(~Q(status=ApprovalRequest.STATUS_PENDING) | Q(customer__isnull=False)
                           | Q(contact__isnull=False) | Q(document__isnull=False))
        return qs

    def serialize(self, request, instance):
        return serialize_approval_request(instance)

    def apply_create(self, request, data, **kwargs):
        """Only `customer-access` requests are created directly; edit / delete
        requests are always a side effect of editing / deleting the record."""
        if data.get('type') != ApprovalRequest.TYPE_CUSTOMER_ACCESS:
            raise ApiError(400, 'Only customer-access requests can be created directly.')
        try:
            customer = Customer.objects.get(pk=data.get('customer_id'))
        except (Customer.DoesNotExist, ValueError, TypeError):
            raise ApiError(404, 'Customer not found.')
        approval = approval_service.request_customer_access(request.user, customer)
        approval.note = (data.get('note') or '')[:255]
        approval.save(update_fields=['note'])
        return approval

    def apply_update(self, request, instance, data, **kwargs):
        raise ApiError(405, 'Use the approve/reject actions, not a direct update.')

    def apply_delete(self, request, instance, **kwargs):
        if instance.requested_by_id != request.user.id and not RoleRules.is_admin(request.user):
            raise ApiError(403, 'You cannot withdraw this request.')
        if instance.status != ApprovalRequest.STATUS_PENDING:
            raise ApiError(400, 'Only a pending request can be withdrawn.')
        instance.delete()


def _decide(request, pk, action):
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    return JsonResponse(serialize_approval_request(action(request.user, pk)))


@staff_360_required
@input_errors_as_400
def approve_request(request, pk):
    return _decide(request, pk, approval_service.approve)


@staff_360_required
@input_errors_as_400
def reject_request(request, pk):
    return _decide(request, pk, approval_service.reject)


@staff_360_required
@input_errors_as_400
def approval_changes(request, pk):
    """"View what changed": before / after for each field the request alters."""
    qs = RoleRules.visible_approval_requests(request.user, ApprovalRequest.objects.all())
    try:
        approval = qs.get(pk=pk)
    except ApprovalRequest.DoesNotExist:
        return error_response(ApiError(404, 'Not found.'))
    return JsonResponse({
        'approval': serialize_approval_request(approval),
        'changes': approval_service.describe_changes(approval),
    })
