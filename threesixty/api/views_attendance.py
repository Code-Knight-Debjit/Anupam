"""Attendance, leave and the attendance reports — thin views over
`services.attendance`.

Check-in and check-out are dedicated actions (one record per person per day,
filled across two calls) and need a location for every role. The short
summary comes first; the detailed report is a separate call. Locations are
returned only to Admin and to the person themselves.
"""
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse

from ..models import AttendanceRecord, LeaveRequest
from ..permissions import RoleRules, staff_360_required
from ..services import attendance as att
from ..services import exports
from .fields import parse_date_input, parse_time_input
from .http import ApiError, error_response, input_errors_as_400, parse_body
from .resources import JsonResource
from .serializers import serialize_attendance_record, serialize_leave_request

User = get_user_model()


class AttendanceRecordResource(JsonResource):
    model = AttendanceRecord

    def list_queryset(self, request, **kwargs):
        qs = AttendanceRecord.objects.select_related('user', 'marked_by').filter(user__in=att.team_profiles(request.user).values('user'))
        if request.GET.get('user_id'):
            qs = qs.filter(user_id=request.GET['user_id'])
        if request.GET.get('date_from'):
            qs = qs.filter(date__gte=parse_date_input(request.GET['date_from'], 'date_from'))
        if request.GET.get('date_to'):
            qs = qs.filter(date__lte=parse_date_input(request.GET['date_to'], 'date_to'))
        return qs.order_by('-date', 'user_id')

    def serialize(self, request, instance):
        return serialize_attendance_record(instance, request.user)

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
    return JsonResponse(serialize_attendance_record(att.check_in(request.user, parse_body(request)), request.user))


@staff_360_required
@input_errors_as_400
def check_out(request):
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    return JsonResponse(serialize_attendance_record(att.check_out(request.user, parse_body(request)), request.user))


@staff_360_required
@input_errors_as_400
def correct_day(request):
    """Admin / Branch Manager (own team): set one person's day by hand, or clear it."""
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    data = parse_body(request)
    if not data.get('user_id') or not data.get('date'):
        return error_response(ApiError(400, 'user_id and date are required.'))
    record = att.correct_day(
        request.user, data['user_id'], parse_date_input(data['date'], 'date'), data.get('status') or '',
        parse_time_input(data.get('check_in'), 'check_in') if data.get('check_in') else None,
        parse_time_input(data.get('check_out'), 'check_out') if data.get('check_out') else None, data.get('note', ''))
    return JsonResponse({'deleted': True} if record is None else serialize_attendance_record(record, request.user))


@staff_360_required
@input_errors_as_400
def my_attendance(request):
    """Today's state (for the check-in button) and this month's days."""
    start, end = att.month_bounds(request.GET.get('month'))
    profile = request.user.threesixty_profile
    days = att.compute_range([profile], start, end)[profile.user_id]
    today = AttendanceRecord.objects.filter(user=request.user, date=att.timezone.localdate()).first()
    return JsonResponse({
        'today': serialize_attendance_record(today, request.user) if today else None,
        'can_check_in': not (today and today.check_in), 'can_check_out': bool(today and today.check_in and not today.check_out),
        'work_start': profile.work_start, 'work_end': profile.work_end, 'grace_minutes': att.GRACE_MINUTES,
        'days': [{'date': d['date'].isoformat(), 'code': d['code'], 'label': d['label'], 'late': d['late'], 'worked': d['worked']} for d in days],
        'tally': att.tally(days),
    })


@staff_360_required
@input_errors_as_400
def attendance_summary(request):
    start, end = att.month_bounds(request.GET.get('month'))
    return JsonResponse({'from': start.isoformat(), 'to': end.isoformat(), 'results': att.summary(request.user, start, end)})


@staff_360_required
@input_errors_as_400
def attendance_report(request):
    """The detailed report (button on the summary); `?format=xlsx|pdf` exports it."""
    start, end = att.range_bounds(request.GET.get('from'), request.GET.get('to'))
    rows = att.detailed_report(request.user, start, end, request.GET.get('user_id') or None)
    fmt = request.GET.get('format')
    if fmt in ('xlsx', 'pdf'):
        headers = ['Name', 'Date', 'Status', 'Check in', 'Check out', 'Late (min)', 'Worked (min)', 'Note']
        table = [[r['name'], r['date'], r['label'], r['check_in'], r['check_out'], r['late_minutes'] or '', r['worked_minutes'] or '', r['note']]
                 for r in rows]
        if fmt == 'pdf':
            body, ctype = exports.table_pdf('Attendance report', headers, table), 'application/pdf'
        else:
            body, ctype = exports.table_xlsx('Attendance', headers, table), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response = HttpResponse(body, content_type=ctype)
        response['Content-Disposition'] = f'attachment; filename="attendance.{fmt}"'
        return response
    return JsonResponse({'from': start.isoformat(), 'to': end.isoformat(), 'results': rows})


class LeaveRequestResource(JsonResource):
    model = LeaveRequest

    def list_queryset(self, request, **kwargs):
        qs = LeaveRequest.objects.select_related('user')
        if RoleRules.is_admin(request.user):
            return qs
        scope = att.team_profiles(request.user).values('user')
        return qs.filter(user__in=scope)

    def serialize(self, request, instance):
        return serialize_leave_request(instance)

    def apply_create(self, request, data, **kwargs):
        return att.request_leave(request.user, parse_date_input(data.get('date_from'), 'date_from'),
                                 parse_date_input(data.get('date_to'), 'date_to'), data.get('reason'))

    def apply_update(self, request, instance, data, **kwargs):
        if instance.user_id != request.user.id:
            raise ApiError(403, 'You cannot edit someone else’s leave request.')
        if instance.status != LeaveRequest.STATUS_PENDING:
            raise ApiError(400, 'Only a pending request can be edited.')
        for field in ('date_from', 'date_to', 'reason'):
            if field in data:
                setattr(instance, field, parse_date_input(data[field], field) if field != 'reason' else data[field])
        if instance.date_to < instance.date_from:
            raise ApiError(400, 'The last day of leave is before the first day.')
        instance.save()
        return instance

    def apply_delete(self, request, instance, **kwargs):
        """A leave request can be cancelled by its owner while it is pending."""
        if instance.user_id != request.user.id and not RoleRules.is_admin(request.user):
            raise ApiError(403, 'You cannot withdraw this leave request.')
        if instance.status != LeaveRequest.STATUS_PENDING:
            raise ApiError(400, 'Only a pending request can be withdrawn.')
        instance.delete()


def _decide(request, pk, status):
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    try:
        leave = LeaveRequest.objects.select_related('user').get(pk=pk)
    except LeaveRequest.DoesNotExist:
        return error_response(ApiError(404, 'Pending leave request not found.'))
    return JsonResponse(serialize_leave_request(att.decide_leave(request.user, leave, status, parse_body(request).get('note', ''))))


@staff_360_required
@input_errors_as_400
def approve_leave_request(request, pk):
    return _decide(request, pk, LeaveRequest.STATUS_APPROVED)


@staff_360_required
@input_errors_as_400
def reject_leave_request(request, pk):
    return _decide(request, pk, LeaveRequest.STATUS_REJECTED)
