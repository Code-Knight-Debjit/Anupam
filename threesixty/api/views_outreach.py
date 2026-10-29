"""Outreach/Calling-list assignment resources.

Assigning customers/outreach lists is Admin/Branch Manager only (AUDIT.md
§3: "Assign customers / outreach lists ✅ Admin ✅ Branch Manager ❌ Branch
Staff ❌ Sales Manager"); the assigned staff member (or Admin/Branch
Manager) may then update status/log attempts on their own assignment.
"""
from django.contrib.auth import get_user_model
from django.http import JsonResponse

from ..models import CallAssignment, CallAttempt, Contact, Customer
from ..permissions import RoleRules, staff_360_required
from ..services import contacts as contact_service
from ..services import outreach as outreach_service
from .fields import parse_date_input
from .http import ApiError, error_response, input_errors_as_400, parse_body
from .resources import JsonResource
from .serializers import serialize_call_assignment, serialize_call_attempt

User = get_user_model()


class CallAssignmentResource(JsonResource):
    model = CallAssignment

    def list_queryset(self, request, **kwargs):
        qs = CallAssignment.objects.select_related('assigned_to', 'assigned_by', 'called_by').prefetch_related('attempts__by')
        week_of = request.GET.get('week_of')
        if week_of:
            qs = qs.filter(week_of=week_of)
        if RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user):
            return qs
        return qs.filter(assigned_to=request.user)

    def serialize(self, request, instance):
        return serialize_call_assignment(instance)

    def apply_create(self, request, data, **kwargs):
        if not (RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user)):
            raise ApiError(403, 'Only Admin or Branch Manager can assign outreach.')
        if not data.get('customer_id') or not data.get('week_of') or not data.get('assigned_to_id'):
            raise ApiError(400, 'customer_id, week_of and assigned_to_id are required.')
        if not Customer.objects.filter(pk=data['customer_id']).exists():
            raise ApiError(400, 'customer_id does not exist.')
        if not User.objects.filter(pk=data['assigned_to_id'], is_active=True).exists():
            raise ApiError(400, 'assigned_to_id does not exist.')
        if data.get('contact_id') and not Contact.objects.filter(
                pk=data['contact_id'], customer_id=data['customer_id']).exists():
            raise ApiError(400, "contact_id does not belong to that customer.")
        if data.get('contact_id'):
            # REQ-OUT-GAP: the contact must be visible to the *assignee*, and not DND.
            assignee = User.objects.get(pk=data['assigned_to_id'])
            allowed = contact_service.visible_contacts(assignee, Customer.objects.get(pk=data['customer_id']))
            if not allowed.filter(pk=data['contact_id'], dnd=False).exists():
                raise ApiError(400, 'That contact is not available to this person (hidden or Do Not Disturb).')
        return CallAssignment.objects.create(
            customer_id=data['customer_id'], contact_id=data.get('contact_id'),
            week_of=parse_date_input(data['week_of'], 'week_of'),
            remarks=data.get('remarks', ''), assigned_to_id=data['assigned_to_id'], assigned_by=request.user,
        )

    def _can_touch(self, request, instance):
        return (
            RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user)
            or instance.assigned_to_id == request.user.id
        )

    def apply_update(self, request, instance, data, **kwargs):
        if not outreach_service.can_update(request.user, instance):
            raise ApiError(403, 'You cannot modify this assignment.')
        if data.get('status') == CallAssignment.STATUS_CALLED:
            outreach_service.mark_called(request.user, instance, data.get('remarks', ''))
        else:
            if 'status' in data:
                if data['status'] not in dict(CallAssignment.STATUS_CHOICES):
                    raise ApiError(400, 'Status must be Pending or Called.')
                instance.status = data['status']
            if 'remarks' in data:
                instance.remarks = data['remarks']
            instance.save()
        return instance

    def apply_delete(self, request, instance, **kwargs):
        if not (RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user)):
            raise ApiError(403, 'Only Admin or Branch Manager can remove an assignment.')
        instance.delete()


class CallAttemptResource(JsonResource):
    """'Not reached' attempt log on a CallAssignment — append-only."""
    model = CallAttempt

    def list_queryset(self, request, assignment_id=None, **kwargs):
        if RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user):
            qs = CallAttempt.objects.all()
        else:
            qs = CallAttempt.objects.filter(assignment__assigned_to=request.user)
        if assignment_id is not None:
            qs = qs.filter(assignment_id=assignment_id)
        return qs

    def serialize(self, request, instance):
        return serialize_call_attempt(instance)

    def apply_create(self, request, data, assignment_id=None, **kwargs):
        assignment_id = assignment_id or data.get('assignment_id')
        try:
            assignment = CallAssignment.objects.select_related('customer', 'contact', 'assigned_to').get(pk=assignment_id)
        except CallAssignment.DoesNotExist:
            raise ApiError(404, 'Assignment not found.')
        return outreach_service.log_not_reached(
            request.user, assignment, data.get('reason'), data.get('note', ''),
            parse_date_input(data.get('call_again_date'), 'call_again_date'))

    def apply_update(self, request, instance, data, **kwargs):
        raise ApiError(405, 'Call attempts cannot be edited.')

    def apply_delete(self, request, instance, **kwargs):
        raise ApiError(405, 'Call attempts cannot be deleted.')


@staff_360_required
@input_errors_as_400
def assign_outreach(request):
    """POST {customer_ids, assigned_to_id, week_of} — Admin / Branch Manager only."""
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    data = parse_body(request)
    try:
        assignee = User.objects.get(pk=data.get('assigned_to_id'), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError):
        return error_response(ApiError(400, 'assigned_to_id does not exist.'))
    if not data.get('week_of'):
        return error_response(ApiError(400, 'week_of is required.'))
    customers = Customer.objects.filter(pk__in=data.get('customer_ids') or []).order_by('name')
    summary = outreach_service.assign(request.user, customers, assignee, parse_date_input(data['week_of'], 'week_of'))
    return JsonResponse(summary)
