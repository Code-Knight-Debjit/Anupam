"""Attendance (REQ-ATT-01..05, REQ-AUT-09, §10).

The day-by-day decision (P / L / H / A / LV / O, late minutes, worked minutes)
is the spec's `att_day_status`, fed from the database in bulk; check-in/out,
leave and holiday workflows are here. "Today", the 10-minute grace and the
Monday-based weeks all use local time (Asia/Kolkata).
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, prefetch_related_objects
from django.utils import timezone

from ..models import AttendanceRecord, EmployeeProfile, Holiday, LeaveRequest, SiteSetting
from ..permissions import RoleRules
from ..rules import anupam_rules as rules
from .errors import ServiceError
from .notifications import active_profiles, notify

User = get_user_model()
GRACE_MINUTES = rules.ATT_GRACE_MIN
CODES = {'P': 'Present', 'L': 'Late', 'H': 'Half day', 'A': 'Absent', 'LV': 'Leave', 'O': 'Off / Holiday', '': ''}
MAX_REPORT_DAYS = 93


def hm(value) -> str:
    return value.strftime('%H:%M') if value else ''


# --------------------------------------------------------------------------- location & check in/out
def clean_location(data):
    """A location is required for EVERY role (REQ-ATT-04): latitude and longitude in range."""
    try:
        lat, lng = float(data.get('lat')), float(data.get('lng'))
    except (TypeError, ValueError):
        raise ServiceError(400, 'Your location is required to check in or out. Allow location access and try again.')
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ServiceError(400, 'That location is not valid.')
    accuracy = data.get('accuracy_m')
    try:
        accuracy = int(round(float(accuracy))) if accuracy not in (None, '') else None
    except (TypeError, ValueError):
        accuracy = None
    if accuracy is not None and accuracy < 0:
        accuracy = None
    return lat, lng, accuracy


@transaction.atomic
def check_in(user, data, now=None):
    lat, lng, accuracy = clean_location(data)
    now = now or timezone.localtime()
    record, _ = AttendanceRecord.objects.select_for_update().get_or_create(user=user, date=now.date())
    if record.check_in:
        raise ServiceError(400, 'Already checked in today.')
    record.check_in = now.time().replace(microsecond=0)
    record.in_loc_lat, record.in_loc_lng, record.in_loc_accuracy_m = lat, lng, accuracy
    record.save()
    return record


@transaction.atomic
def check_out(user, data, now=None):
    lat, lng, accuracy = clean_location(data)
    now = now or timezone.localtime()
    try:
        record = AttendanceRecord.objects.select_for_update().get(user=user, date=now.date())
    except AttendanceRecord.DoesNotExist:
        raise ServiceError(400, 'You have not checked in today.')
    if not record.check_in:
        raise ServiceError(400, 'You have not checked in today.')
    if record.check_out:
        raise ServiceError(400, 'Already checked out today.')
    if now.time().replace(microsecond=0) < record.check_in:
        raise ServiceError(400, 'Check-out cannot be before check-in.')
    record.check_out = now.time().replace(microsecond=0)
    record.out_loc_lat, record.out_loc_lng, record.out_loc_accuracy_m = lat, lng, accuracy
    record.save()
    return record


# --------------------------------------------------------------------------- team & scope
def team_profiles(user):
    """Who `user` may see: Admin = all active staff, Branch Manager = their team, anyone else = just themselves."""
    qs = active_profiles().select_related('user').prefetch_related('branches')
    if RoleRules.is_admin(user):
        return qs
    if RoleRules.is_branch_manager(user):
        return qs.filter(user_id__in=RoleRules.user_ids_in_manager_scope(user))
    return qs.filter(user=user)


def can_view_user(viewer, target_user_id) -> bool:
    return team_profiles(viewer).filter(user_id=target_user_id).exists()


def can_decide_leave(user, leave) -> bool:
    team_ids = set(RoleRules.user_ids_in_manager_scope(user)) if RoleRules.is_branch_manager(user) else set()
    role = 'Admin' if RoleRules.is_admin(user) else 'Branch Manager' if RoleRules.is_branch_manager(user) else ''
    return rules.can_decide_leave({'id': user.pk, 'role': role}, {'userId': leave.user_id}, team_ids)


# --------------------------------------------------------------------------- day status (bulk)
def attendance_start():
    row = SiteSetting.objects.filter(key='attendance_start').first()
    value = (row.value if row else None) or {}
    raw = value.get('date') if isinstance(value, dict) else value
    return str(raw) if raw else ''


def _emp_dict(profile):
    return {'id': profile.user_id, 'workStart': profile.work_start, 'weeklyOff': profile.weekly_off,
            'doj': profile.date_of_joining.isoformat() if profile.date_of_joining else '',
            'branches': [b.pk for b in profile.branches.all()]}


def _record_dict(r):
    return {'userId': r.user_id, 'date': r.date.isoformat(), 'checkIn': hm(r.check_in), 'checkOut': hm(r.check_out), 'status': r.status}


def compute_range(profiles, start: date, end: date, today=None):
    """{user_id: [ {date, code, late, worked, record} ... ]} for every day start..end."""
    today = (today or timezone.localdate()).isoformat()
    profiles = list(profiles)
    prefetch_related_objects(profiles, 'branches')        # no-op when already prefetched; never one query per person
    user_ids = [p.user_id for p in profiles]
    records = defaultdict(dict)
    for r in AttendanceRecord.objects.filter(user_id__in=user_ids, date__range=(start, end)):
        records[r.user_id][r.date] = r
    holidays = [{'from': h.date.isoformat(), 'to': h.date_to.isoformat(), 'all': h.is_all_branches,
                 'branches': [b.pk for b in h.branches.all()]}
                for h in Holiday.objects.filter(date_to__gte=start, date__lte=end).prefetch_related('branches')]
    leaves = [{'userId': l.user_id, 'from': l.date_from.isoformat(), 'to': l.date_to.isoformat(), 'status': l.status}
              for l in LeaveRequest.objects.filter(user_id__in=user_ids, date_to__gte=start, date_from__lte=end)]
    start_from = attendance_start()
    out = {}
    for p in profiles:
        emp = _emp_dict(p)
        rec_dicts = [_record_dict(r) for r in records[p.user_id].values()]
        days = []
        day = start
        while day <= end:
            status = rules.att_day_status(emp, day.isoformat(), rec_dicts, holidays, leaves, today, start_from)
            days.append({'date': day, 'code': status['code'], 'label': CODES[status['code']], 'late': status['late'],
                         'worked': status['worked'], 'record': records[p.user_id].get(day)})
            day += timedelta(days=1)
        out[p.user_id] = days
    return out


def tally(days) -> dict:
    return rules.att_tally([{'code': d['code'], 'worked': d['worked']} for d in days])


def month_bounds(text):
    """'YYYY-MM' (default: this month, local) -> first and last day."""
    try:
        first = datetime.strptime(text, '%Y-%m').date().replace(day=1) if text else timezone.localdate().replace(day=1)
    except ValueError:
        raise ServiceError(400, 'month must look like 2026-10.')
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first, nxt - timedelta(days=1)


def range_bounds(from_text, to_text):
    try:
        start = date.fromisoformat(from_text) if from_text else timezone.localdate().replace(day=1)
        end = date.fromisoformat(to_text) if to_text else timezone.localdate()
    except ValueError:
        raise ServiceError(400, 'from and to must be dates like 2026-10-01.')
    if end < start:
        raise ServiceError(400, 'The end date is before the start date.')
    if (end - start).days + 1 > MAX_REPORT_DAYS:
        raise ServiceError(400, f'Choose a range of at most {MAX_REPORT_DAYS} days.')
    return start, end


def summary(viewer, start, end):
    """Short summary first: one tally per person in the viewer's scope."""
    profiles = list(team_profiles(viewer).order_by('user__first_name', 'user__username'))
    computed = compute_range(profiles, start, end)
    return [{'user_id': p.user_id, 'name': p.user.get_full_name() or p.user.username, 'role': p.role,
             'work_start': p.work_start, **tally(computed[p.user_id])} for p in profiles]


def detailed_report(viewer, start, end, user_id=None):
    """Day-by-day rows. Locations are included only for Admin (and for your own record)."""
    profiles = team_profiles(viewer)
    if user_id:
        profiles = profiles.filter(user_id=user_id)
        if not profiles.exists():
            raise ServiceError(403, 'You cannot see that person’s attendance.')
    profiles = list(profiles.order_by('user__first_name', 'user__username'))
    computed = compute_range(profiles, start, end)
    rows = []
    for p in profiles:
        show_location = RoleRules.is_admin(viewer) or p.user_id == viewer.pk
        for d in computed[p.user_id]:
            r = d['record']
            row = {'user_id': p.user_id, 'name': p.user.get_full_name() or p.user.username, 'date': d['date'].isoformat(),
                   'code': d['code'], 'label': d['label'], 'late_minutes': d['late'], 'worked_minutes': d['worked'],
                   'check_in': hm(r.check_in) if r else '', 'check_out': hm(r.check_out) if r else '',
                   'note': r.note if r else ''}
            if show_location and r:
                row.update(in_location=_loc(r.in_loc_lat, r.in_loc_lng), out_location=_loc(r.out_loc_lat, r.out_loc_lng))
            rows.append(row)
    return rows


def _loc(lat, lng):
    return None if lat is None or lng is None else {'lat': lat, 'lng': lng,
                                                     'map_url': f'https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=17/{lat}/{lng}'}


# --------------------------------------------------------------------------- manual correction
@transaction.atomic
def correct_day(actor, target_user_id, day, status='', check_in=None, check_out=None, note=''):
    """Admin / Branch Manager (own team) set a day by hand; all four blank removes the record.
    A manual status beats the automatic calculation (REQ-ATT-03)."""
    if not (RoleRules.is_admin(actor) or RoleRules.is_branch_manager(actor)):
        raise ServiceError(403, 'Only Admin or Branch Manager can edit attendance.')
    if not RoleRules.is_admin(actor) and target_user_id not in RoleRules.user_ids_in_manager_scope(actor):
        raise ServiceError(403, 'That user is outside your branch scope.')
    if status and status not in dict(AttendanceRecord.STATUS_CHOICES):
        raise ServiceError(400, 'Unknown status.')
    if check_in and check_out and check_out < check_in:
        raise ServiceError(400, 'Check-out cannot be before check-in.')
    try:
        target = User.objects.get(pk=target_user_id)
    except (User.DoesNotExist, ValueError, TypeError):
        raise ServiceError(404, 'User not found.')
    record = AttendanceRecord.objects.filter(user=target, date=day).first()
    if not status and not check_in and not check_out and not (note or '').strip():
        if record:
            record.delete()
        return None
    record = record or AttendanceRecord(user=target, date=day)
    record.check_in, record.check_out, record.status, record.note = check_in, check_out, status, (note or '').strip()
    record.marked_by = actor
    record.save()
    return record


# --------------------------------------------------------------------------- leave (REQ-AUT-09)
def _name(user):
    return user.get_full_name() or user.username


@transaction.atomic
def request_leave(user, date_from, date_to, reason):
    if not date_from or not date_to or not (reason or '').strip():
        raise ServiceError(400, 'date_from, date_to and reason are required.')
    if date_to < date_from:
        raise ServiceError(400, 'The last day of leave is before the first day.')
    leave = LeaveRequest.objects.create(user=user, date_from=date_from, date_to=date_to, reason=reason.strip())
    for admin in active_profiles(EmployeeProfile.ADMIN).exclude(user=user):
        notify(admin.user_id, 'leave', f'{_name(user)} requested leave: {date_from.isoformat()} – {date_to.isoformat()}.')
    return leave


@transaction.atomic
def decide_leave(actor, leave, new_status, note=''):
    if leave.status != LeaveRequest.STATUS_PENDING:
        raise ServiceError(404, 'Pending leave request not found.')
    if not can_decide_leave(actor, leave):
        raise ServiceError(403, 'You cannot decide this leave request.')
    leave.status, leave.decided_by, leave.decided_at, leave.decision_note = new_status, actor, timezone.now(), (note or '')[:255]
    leave.save()
    text = f'Your leave ({leave.date_from.isoformat()} – {leave.date_to.isoformat()}) was {new_status.lower()} by {_name(actor)}.'
    notify(leave.user_id, 'leave', text + (f' {leave.decision_note}' if leave.decision_note else ''))
    return leave


# --------------------------------------------------------------------------- holidays (REQ-AUT-09)
@transaction.atomic
def add_holiday(name, date_from, date_to=None, branch_ids=None, all_branches=False):
    name = (name or '').strip()
    if not name or not date_from:
        raise ServiceError(400, 'date and name are required.')
    date_to = date_to or date_from
    if date_to < date_from:
        raise ServiceError(400, 'date_to cannot be before date.')
    chosen = list(branch_ids or [])
    if not all_branches and not chosen:
        raise ServiceError(400, 'Choose the branches this holiday applies to, or all branches.')
    holiday = Holiday.objects.create(date=date_from, date_to=date_to, name=name, is_all_branches=bool(all_branches))
    if chosen and not all_branches:
        holiday.branches.set(chosen)
    text = f'Holiday: {name} on {date_from.isoformat()}' + (f' – {date_to.isoformat()}' if date_to != date_from else '')
    people = active_profiles()
    if not all_branches:
        people = people.filter(branches__id__in=chosen).distinct()
    for p in people:
        notify(p.user_id, 'leave', text)
    return holiday
