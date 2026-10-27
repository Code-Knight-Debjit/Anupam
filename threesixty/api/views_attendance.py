"""Attendance (check-in/check-out with geolocation) and Leave requests.

Check-in/out are dedicated actions rather than generic resource create/
update, matching the original's `attCheckIn`/`attCheckOut` behaviour of
one record per user per day that's filled in across two calls — a
generic PATCH-any-field endpoint would let a user silently rewrite
someone else's attendance history, which the original never allowed
either (each browser only ever wrote its own current user's record).
"""
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.utils import timezone

from ..models import AttendanceRecord, LeaveRequest
from ..permissions import RoleRules, staff_360_required
from .fields import parse_date_input, parse_time_input
from .http import ApiError, error_response, input_errors_as_400, parse_body
from .resources import JsonResource
from .serializers import serialize_attendance_record, serialize_leave_request

User = get_user_model()


class AttendanceRecordResource(JsonResource):
    model = AttendanceRecord

    def list_queryset(self, request, **kwargs):
        qs = AttendanceRecord.objects.all()
        if RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user):
            user_id = request.GET.get('user_id')
            if user_id:
                qs = qs.filter(user_id=user_id)
            return qs
        return qs.filter(user=request.user)

    def serialize(self, request, instance):
        return serialize_attendance_record(instance)

    def apply_create(self, request, data, **kwargs):
        raise ApiError(405, 'Use /attendance/check-in/ to create a record.')

    def apply_update(self, request, instance, data, **kwargs):
        raise ApiError(405, 'Use /attendance/check-out/ to update a record.')

    def apply_delete(self, request, instance, **kwargs):
        if not RoleRules.is_admin(request.user):
            raise ApiError(403, 'Only Admin can delete attendance records.')
        instance.delete()


@staff_360_required
@input_errors_as_400
def check_in(request):
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    data = parse_body(request)
    today = timezone.localdate()
    record, _ = AttendanceRecord.objects.get_or_create(user=request.user, date=today)
    if record.check_in:
        return error_response(ApiError(400, 'Already checked in today.'))
    record.check_in = timezone.localtime().time()
    record.in_loc_lat = data.get('lat')
    record.in_loc_lng = data.get('lng')
    record.in_loc_accuracy_m = data.get('accuracy_m')
    record.save()
    return JsonResponse(serialize_attendance_record(record))


@staff_360_required
@input_errors_as_400
def check_out(request):
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    data = parse_body(request)
    today = timezone.localdate()
    try:
        record = AttendanceRecord.objects.get(user=request.user, date=today)
    except AttendanceRecord.DoesNotExist:
        return error_response(ApiError(400, 'You have not checked in today.'))
    if not record.check_in:
        return error_response(ApiError(400, 'You have not checked in today.'))
    if record.check_out:
        return error_response(ApiError(400, 'Already checked out today.'))
    record.check_out = timezone.localtime().time()
    record.out_loc_lat = data.get('lat')
    record.out_loc_lng = data.get('lng')
    record.out_loc_accuracy_m = data.get('accuracy_m')
    record.save()
    return JsonResponse(serialize_attendance_record(record))


@staff_360_required
@input_errors_as_400
def correct_day(request):
    """Admin/Branch-Manager manual correction for one user's one-day record
    (original `attOpenDay`/`attDaySave`, ~L12543-12570): set check_in/
    check_out/status/note, or — if all four come back empty — delete the
    record entirely. Branch Manager is limited to their own team scope
    (`attTeam`); Admin can correct anyone."""
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    if not (RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user)):
        return error_response(ApiError(403, 'Only Admin or Branch Manager can edit attendance.'))
    data = parse_body(request)
    user_id, date_str = data.get('user_id'), data.get('date')
    if not user_id or not date_str:
        return error_response(ApiError(400, 'user_id and date are required.'))
    if not RoleRules.is_admin(request.user) and user_id not in RoleRules.user_ids_in_manager_scope(request.user):
        return error_response(ApiError(403, 'That user is outside your branch scope.'))
    try:
        target_user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return error_response(ApiError(404, 'User not found.'))
    date = parse_date_input(date_str, 'date')
    status = data.get('status') or ''
    check_in = parse_time_input(data.get('check_in'), 'check_in') if data.get('check_in') else None
    check_out = parse_time_input(data.get('check_out'), 'check_out') if data.get('check_out') else None
    note = (data.get('note') or '').strip()
    if check_in and check_out and check_out < check_in:
        return error_response(ApiError(400, 'Check-out cannot be before check-in.'))

    record = AttendanceRecord.objects.filter(user=target_user, date=date).first()
    if not status and not check_in and not check_out and not note:
        if record:
            record.delete()
        return JsonResponse({'deleted': True})

    if not record:
        record = AttendanceRecord(user=target_user, date=date)
    record.check_in, record.check_out, record.note, record.status = check_in, check_out, note, status
    record.marked_by = request.user
    record.save()
    return JsonResponse(serialize_attendance_record(record))


class LeaveRequestResource(JsonResource):
    model = LeaveRequest

    def list_queryset(self, request, **kwargs):
        qs = LeaveRequest.objects.all()
        if RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user):
            return qs
        return qs.filter(user=request.user)

    def serialize(self, request, instance):
        return serialize_leave_request(instance)

    def apply_create(self, request, data, **kwargs):
        if not data.get('date_from') or not data.get('date_to') or not data.get('reason'):
            raise ApiError(400, 'date_from, date_to and reason are required.')
        return LeaveRequest.objects.create(
            user=request.user, date_from=parse_date_input(data['date_from'], 'date_from'),
            date_to=parse_date_input(data['date_to'], 'date_to'), reason=data['reason'],
        )

    def apply_update(self, request, instance, data, **kwargs):
        if instance.user_id != request.user.id:
            raise ApiError(403, 'You cannot edit someone else’s leave request.')
        if instance.status != LeaveRequest.STATUS_PENDING:
            raise ApiError(400, 'Only a pending request can be edited.')
        for field in ('date_from', 'date_to', 'reason'):
            if field in data:
                value = data[field]
                if field in ('date_from', 'date_to'):
                    value = parse_date_input(value, field)
                setattr(instance, field, value)
        instance.save()
        return instance

    def apply_delete(self, request, instance, **kwargs):
        if instance.user_id != request.user.id and not RoleRules.is_admin(request.user):
            raise ApiError(403, 'You cannot withdraw this leave request.')
        if instance.status != LeaveRequest.STATUS_PENDING:
            raise ApiError(400, 'Only a pending request can be withdrawn.')
        instance.delete()


def _decide_leave_request(request, pk, new_status):
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    if not (RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user)):
        return error_response(ApiError(403, 'Only Admin or Branch Manager can decide leave requests.'))
    try:
        leave = LeaveRequest.objects.get(pk=pk, status=LeaveRequest.STATUS_PENDING)
    except LeaveRequest.DoesNotExist:
        return error_response(ApiError(404, 'Pending leave request not found.'))
    if not RoleRules.is_admin(request.user) and leave.user_id not in RoleRules.user_ids_in_manager_scope(request.user):
        return error_response(ApiError(403, 'That user is outside your branch scope.'))
    data = parse_body(request)
    leave.status = new_status
    leave.decided_by = request.user
    leave.decided_at = timezone.now()
    leave.decision_note = data.get('note', '')
    leave.save()
    return JsonResponse(serialize_leave_request(leave))


@staff_360_required
@input_errors_as_400
def approve_leave_request(request, pk):
    return _decide_leave_request(request, pk, LeaveRequest.STATUS_APPROVED)


@staff_360_required
@input_errors_as_400
def reject_leave_request(request, pk):
    return _decide_leave_request(request, pk, LeaveRequest.STATUS_REJECTED)
