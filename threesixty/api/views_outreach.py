"""Outreach/Calling-list assignment resources.

Assigning customers/outreach lists is Admin/Branch Manager only (AUDIT.md
§3: "Assign customers / outreach lists ✅ Admin ✅ Branch Manager ❌ Branch
Staff ❌ Sales Manager"); the assigned staff member (or Admin/Branch
Manager) may then update status/log attempts on their own assignment.
"""
from django.contrib.auth import get_user_model
from django.utils import timezone

from ..models import CallAssignment, CallAttempt, Contact, Customer
from ..permissions import RoleRules
from .fields import parse_date_input
from .http import ApiError
from .resources import JsonResource
from .serializers import serialize_call_assignment, serialize_call_attempt

User = get_user_model()


class CallAssignmentResource(JsonResource):
    model = CallAssignment

    def list_queryset(self, request, **kwargs):
        qs = CallAssignment.objects.all()
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
        if not self._can_touch(request, instance):
            raise ApiError(403, 'You cannot modify this assignment.')
        if 'status' in data:
            instance.status = data['status']
            if data['status'] == CallAssignment.STATUS_CALLED and not instance.called_at:
                instance.called_at = timezone.now()
                instance.called_by = request.user
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
            assignment = CallAssignment.objects.get(pk=assignment_id)
        except CallAssignment.DoesNotExist:
            raise ApiError(404, 'Assignment not found.')
        if not (RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user)
                or assignment.assigned_to_id == request.user.id):
            raise ApiError(403, 'You cannot log an attempt on this assignment.')
        if not data.get('reason'):
            raise ApiError(400, 'reason is required.')
        return CallAttempt.objects.create(
            assignment=assignment, reason=data['reason'], note=data.get('note', ''),
            by=request.user, call_again_date=parse_date_input(data.get('call_again_date'), 'call_again_date'),
        )

    def apply_update(self, request, instance, data, **kwargs):
        raise ApiError(405, 'Call attempts cannot be edited.')

    def apply_delete(self, request, instance, **kwargs):
        raise ApiError(405, 'Call attempts cannot be deleted.')
