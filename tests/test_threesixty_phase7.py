"""Phase 7 (Attendance) — check-in/out with location, grace/late, day codes, holidays,
leave workflow, team scope, short summary + detailed report."""
from datetime import date, datetime, time, timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from threesixty.models import AttendanceRecord, Branch, EmployeeProfile, Holiday, LeaveRequest, Notification, SiteSetting
from threesixty.services import attendance as att
from tests.helpers_360 import ADMIN, BM, BS, SM, call, client_for, make_employee

pytestmark = pytest.mark.django_db

SUN, MON, TUE = date(2026, 10, 25), date(2026, 10, 26), date(2026, 10, 27)
TODAY = date(2026, 10, 29)          # a Thursday
LOC = {'lat': 13.0285, 'lng': 77.5197, 'accuracy_m': 15}


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def chennai():
    return Branch.objects.create(name='Chennai')


@pytest.fixture
def bengaluru():
    return Branch.objects.create(name='Bengaluru')


@pytest.fixture
def team(chennai, bengaluru):
    return {
        'admin': make_employee('admin', ADMIN, [chennai], full_name='Sanjeev'),
        'bm': make_employee('bm', BM, [chennai], full_name='Bala'),
        'bs': make_employee('bs', BS, [chennai], full_name='Staff'),
        'sm': make_employee('sm', SM, [chennai], full_name='Devdutt'),
        'blr': make_employee('blr', BS, [bengaluru], full_name='Bengaluru Staff'),
    }


def record(user, day, check_in=None, check_out=None, **extra):
    return AttendanceRecord.objects.create(user=user, date=day, check_in=check_in, check_out=check_out, **extra)


def day(user, d, today=TODAY):
    profile = user.threesixty_profile
    return next(x for x in att.compute_range([profile], d, d, today)[user.pk])


def at(d, hh, mm):
    return timezone.make_aware(datetime(d.year, d.month, d.day, hh, mm))


# ----------------------------------------------------------------------------- check in / out
class TestCheckInOut:
    @pytest.mark.parametrize('who', ['admin', 'bm', 'bs', 'sm'])
    def test_REQ_ATT_04_location_is_required_for_every_role(self, team, who):
        c = client_for(team[who])
        assert call(c, 'post', '/360/api/attendance/check-in/', {}).status_code == 400
        assert call(c, 'post', '/360/api/attendance/check-in/', {'lat': 'x', 'lng': 1}).status_code == 400
        assert call(c, 'post', '/360/api/attendance/check-in/', {'lat': 95, 'lng': 10}).status_code == 400
        assert not AttendanceRecord.objects.exists()
        res = call(c, 'post', '/360/api/attendance/check-in/', LOC)
        assert res.status_code == 200 and res.json()['in_loc_lat'] == 13.0285 and res.json()['in_loc_accuracy_m'] == 15
        assert call(c, 'post', '/360/api/attendance/check-out/', {}).status_code == 400            # check-out needs a location too
        assert call(c, 'post', '/360/api/attendance/check-out/', LOC).status_code == 200

    def test_cannot_check_in_twice_or_out_twice_or_out_without_in(self, team):
        c = client_for(team['bs'])
        assert call(c, 'post', '/360/api/attendance/check-out/', LOC).status_code == 400
        call(c, 'post', '/360/api/attendance/check-in/', LOC)
        assert call(c, 'post', '/360/api/attendance/check-in/', LOC).status_code == 400
        call(c, 'post', '/360/api/attendance/check-out/', LOC)
        assert call(c, 'post', '/360/api/attendance/check-out/', LOC).status_code == 400

    def test_REQ_ATT_04_check_out_cannot_precede_check_in(self, team):
        att.check_in(team['bs'], LOC, now=at(TODAY, 10, 0))
        with pytest.raises(att.ServiceError) as exc:
            att.check_out(team['bs'], LOC, now=at(TODAY, 9, 59))
        assert 'before check-in' in exc.value.message
        assert att.check_out(team['bs'], LOC, now=at(TODAY, 10, 0)).check_out == time(10, 0)

    def test_times_are_local(self, team):
        record_ = att.check_in(team['bs'], LOC, now=timezone.make_aware(datetime(2026, 10, 29, 9, 5, 7)))
        assert record_.check_in == time(9, 5, 7) and record_.date == TODAY
        assert timezone.get_current_timezone_name() == 'Asia/Kolkata'

    def test_office_staff_can_check_in_from_anywhere(self, team):
        far = {'lat': 28.6, 'lng': 77.2}                        # no distance check against the office
        assert call(client_for(team['bs']), 'post', '/360/api/attendance/check-in/', far).status_code == 200

    def test_my_attendance_state(self, team):
        c = client_for(team['bs'])
        me = call(c, 'get', '/360/api/attendance/me/').json()
        assert me['can_check_in'] is True and me['can_check_out'] is False and me['grace_minutes'] == 10 and me['today'] is None
        call(c, 'post', '/360/api/attendance/check-in/', LOC)
        me = call(c, 'get', '/360/api/attendance/me/').json()
        assert me['can_check_in'] is False and me['can_check_out'] is True and me['today']['in_loc_lat'] == 13.0285


# ----------------------------------------------------------------------------- day status
class TestDayStatus:
    def test_REQ_ATT_01_ten_minute_grace_then_late_with_minutes(self, team):
        record(team['bs'], MON, time(9, 40))           # exactly 10 minutes after 09:30: still on time
        record(team['bs'], TUE, time(9, 41))
        assert day(team['bs'], MON)['code'] == 'P' and day(team['bs'], MON)['late'] == 0
        late = day(team['bs'], TUE)
        assert (late['code'], late['late']) == ('L', 11)

    def test_REQ_ATT_01_work_start_is_per_person(self, team):
        team['bs'].threesixty_profile.work_start = '08:00'
        team['bs'].threesixty_profile.save()
        record(team['bs'], MON, time(8, 15))
        assert (day(team['bs'], MON)['code'], day(team['bs'], MON)['late']) == ('L', 15)
        record(team['sm'], MON, time(8, 15))            # default 09:30
        assert day(team['sm'], MON)['code'] == 'P'

    def test_REQ_ATT_02_weekly_off_defaults_to_sunday_and_is_configurable(self, team):
        assert day(team['bs'], SUN)['code'] == 'O' and day(team['bs'], MON)['code'] == 'A'
        team['bs'].threesixty_profile.weekly_off = '0,6'
        team['bs'].threesixty_profile.save()
        assert day(team['bs'], date(2026, 10, 24))['code'] == 'O'         # Saturday
        team['bs'].threesixty_profile.weekly_off = ''
        team['bs'].threesixty_profile.save()
        assert day(team['bs'], SUN)['code'] == 'A'

    def test_REQ_ATT_02_holidays_for_all_or_selected_branches(self, team, chennai, bengaluru):
        everyone = Holiday.objects.create(date=MON, date_to=MON, name='Diwali', is_all_branches=True)
        only_blr = Holiday.objects.create(date=TUE, date_to=TUE, name='Local', is_all_branches=False)
        only_blr.branches.set([bengaluru])
        assert day(team['bs'], MON)['code'] == 'O' and day(team['blr'], MON)['code'] == 'O'
        assert day(team['blr'], TUE)['code'] == 'O' and day(team['bs'], TUE)['code'] == 'A'

    def test_REQ_ATT_02_approved_leave_only(self, team):
        LeaveRequest.objects.create(user=team['bs'], date_from=MON, date_to=MON, reason='x', status='Approved')
        LeaveRequest.objects.create(user=team['bs'], date_from=TUE, date_to=TUE, reason='x', status='Pending')
        assert day(team['bs'], MON)['code'] == 'LV' and day(team['bs'], TUE)['code'] == 'A'

    def test_REQ_ATT_02_absent_only_for_past_days(self, team):
        assert day(team['bs'], date(2026, 10, 28))['code'] == 'A'
        assert day(team['bs'], TODAY)['code'] == '' and day(team['bs'], date(2026, 10, 30))['code'] == ''

    def test_REQ_ATT_02_days_before_joining_or_attendance_start_are_blank(self, team):
        team['bs'].threesixty_profile.date_of_joining = TUE
        team['bs'].threesixty_profile.save()
        assert day(team['bs'], MON)['code'] == '' and day(team['bs'], TUE)['code'] == 'A'
        SiteSetting.objects.create(key='attendance_start', value={'date': '2026-10-28'})
        assert day(team['sm'], TUE)['code'] == '' and day(team['sm'], date(2026, 10, 28))['code'] == 'A'
        record(team['sm'], date(2026, 10, 20), time(9, 30))                # a record before the start still counts
        assert day(team['sm'], date(2026, 10, 20))['code'] == 'P'

    def test_REQ_ATT_03_manual_status_beats_the_automatic_one(self, team):
        record(team['bs'], MON, time(11, 0), status='Half day')
        assert day(team['bs'], MON)['code'] == 'H'
        record(team['bs'], TUE, None, status='Present')
        assert day(team['bs'], TUE)['code'] == 'P'
        record(team['sm'], MON, time(9, 30), status='Absent')
        assert day(team['sm'], MON)['code'] == 'A'
        record(team['sm'], TUE, None, status='Leave')
        assert day(team['sm'], TUE)['code'] == 'LV'
        record(team['sm'], date(2026, 10, 28), None, status='Off / Holiday')
        assert day(team['sm'], date(2026, 10, 28))['code'] == 'O'

    def test_REQ_ATT_03_monthly_tally_and_worked_minutes(self, team):
        record(team['bs'], date(2026, 10, 26), time(9, 30), time(18, 30))        # P, 540
        record(team['bs'], date(2026, 10, 27), time(10, 0), time(14, 0))         # L (30 late), 240
        record(team['bs'], date(2026, 10, 28), None, status='Half day')
        days = att.compute_range([team['bs'].threesixty_profile], date(2026, 10, 24), date(2026, 10, 28), TODAY)[team['bs'].pk]
        t = att.tally(days)
        assert (t['present'], t['late'], t['half'], t['absent'], t['off'], t['worked']) == (2, 1, 1, 1, 1, 780)

    def test_present_with_no_checkout_has_no_worked_minutes(self, team):
        record(team['bs'], MON, time(9, 30))
        assert day(team['bs'], MON)['worked'] is None


# ----------------------------------------------------------------------------- scope: team views, summary, report
class TestScopeAndReports:
    def test_REQ_ATT_05_who_sees_whom(self, team):
        ids = lambda who: {r['user_id'] for r in call(client_for(team[who]), 'get', '/360/api/attendance/summary/').json()['results']}
        everyone = {u.pk for u in team.values()}
        assert ids('admin') == everyone
        assert ids('bm') == {team['admin'].pk, team['bm'].pk, team['bs'].pk, team['sm'].pk}      # same branch only, not Bengaluru
        assert ids('bs') == {team['bs'].pk} and ids('sm') == {team['sm'].pk}

    def test_inactive_staff_are_not_listed(self, team):
        EmployeeProfile.objects.filter(user=team['bs']).update(is_active_employee=False)
        assert team['bs'].pk not in {r['user_id'] for r in call(client_for(team['admin']), 'get', '/360/api/attendance/summary/').json()['results']}

    def test_summary_has_a_tally_per_person(self, team):
        record(team['bs'], MON, time(9, 30), time(18, 0))
        res = call(client_for(team['admin']), 'get', '/360/api/attendance/summary/?month=2026-10').json()
        row = next(r for r in res['results'] if r['user_id'] == team['bs'].pk)
        assert row['present'] >= 1 and row['worked'] == 510 and 'absent' in row and res['from'] == '2026-10-01' and res['to'] == '2026-10-31'
        assert call(client_for(team['admin']), 'get', '/360/api/attendance/summary/?month=oct').status_code == 400

    def test_detailed_report_rows_and_validation(self, team):
        record(team['bs'], MON, time(9, 50), time(18, 30), note='train delay')
        rep = call(client_for(team['bm']), 'get', f'/360/api/attendance/report/?from={SUN}&to={TUE}&user_id={team["bs"].pk}').json()
        assert [(r['date'], r['code']) for r in rep['results']] == [(str(SUN), 'O'), (str(MON), 'L'), (str(TUE), 'A')]
        late = rep['results'][1]
        assert (late['check_in'], late['check_out'], late['late_minutes'], late['worked_minutes'], late['note']) == ('09:50', '18:30', 20, 520, 'train delay')
        c = client_for(team['admin'])
        assert call(c, 'get', '/360/api/attendance/report/?from=2026-10-10&to=2026-10-01').status_code == 400
        assert call(c, 'get', '/360/api/attendance/report/?from=2026-01-01&to=2026-12-31').status_code == 400
        assert call(c, 'get', '/360/api/attendance/report/?from=nope').status_code == 400

    def test_nobody_reads_attendance_outside_their_scope(self, team):
        record(team['blr'], MON, time(9, 30))
        for who in ('bm', 'bs', 'sm'):
            c = client_for(team[who])
            assert call(c, 'get', f'/360/api/attendance/report/?from={MON}&to={MON}&user_id={team["blr"].pk}').status_code == 403, who
        listing = call(client_for(team['bm']), 'get', '/360/api/attendance/').json()['results']
        assert all(r['user']['id'] != team['blr'].pk for r in listing)
        assert call(client_for(team['bs']), 'get', f'/360/api/attendance/{AttendanceRecord.objects.get().pk}/').status_code == 404

    def test_REQ_ATT_04_only_admin_sees_other_peoples_locations(self, team):
        record(team['bs'], MON, time(9, 30), time(18, 30), in_loc_lat=13.1, in_loc_lng=80.2, out_loc_lat=13.2, out_loc_lng=80.3)
        url = f'/360/api/attendance/report/?from={MON}&to={MON}&user_id={team["bs"].pk}'
        admin_row = call(client_for(team['admin']), 'get', url).json()['results'][0]
        assert admin_row['in_location']['lat'] == 13.1 and 'openstreetmap.org' in admin_row['in_location']['map_url'] and admin_row['out_location']['lng'] == 80.3
        assert 'in_location' not in call(client_for(team['bm']), 'get', url).json()['results'][0]
        assert call(client_for(team['bs']), 'get', url).json()['results'][0]['in_location']['lat'] == 13.1      # your own
        row = call(client_for(team['bm']), 'get', '/360/api/attendance/').json()['results'][0]
        assert 'in_loc_lat' not in row
        assert call(client_for(team['admin']), 'get', '/360/api/attendance/').json()['results'][0]['in_loc_lat'] == 13.1

    def test_report_exports(self, team):
        record(team['bs'], MON, time(9, 30), time(18, 30))
        base = f'/360/api/attendance/report/?from={MON}&to={TUE}'
        x = client_for(team['admin']).get(base + '&format=xlsx')
        p = client_for(team['admin']).get(base + '&format=pdf')
        assert x['Content-Type'].startswith('application/vnd.openxml') and p.content[:4] == b'%PDF'


# ----------------------------------------------------------------------------- correction
class TestCorrection:
    def fix(self, who, target, **data):
        return call(client_for(team_[who]), 'post', '/360/api/attendance/correct/', {'user_id': target.pk, 'date': str(MON), **data})

    @pytest.fixture(autouse=True)
    def _team(self, team):
        global team_
        team_ = team

    def test_admin_and_manager_set_and_clear_a_day(self, team):
        res = self.fix('admin', team['bs'], status='Present', check_in='09:30', check_out='18:30', note='manual')
        assert res.status_code == 200 and res.json()['marked_by']['id'] == team['admin'].pk
        assert day(team['bs'], MON)['code'] == 'P'
        assert self.fix('bm', team['bs']).json() == {'deleted': True} and not AttendanceRecord.objects.exists()

    def test_manager_limited_to_own_team_and_others_refused(self, team):
        assert self.fix('bm', team['blr'], status='Present').status_code == 403
        for who in ('bs', 'sm'):
            assert self.fix(who, team['bs'], status='Present').status_code == 403

    def test_validation(self, team):
        assert self.fix('admin', team['bs'], status='Sleeping').status_code == 400
        assert self.fix('admin', team['bs'], check_in='18:00', check_out='09:00').status_code == 400
        assert call(client_for(team['admin']), 'post', '/360/api/attendance/correct/', {}).status_code == 400


# ----------------------------------------------------------------------------- leave & holidays
class TestLeave:
    def request(self, who, **extra):
        body = {'date_from': '2026-11-02', 'date_to': '2026-11-03', 'reason': 'Family function', **extra}
        return call(client_for(team_[who]), 'post', '/360/api/leave-requests/', body)

    @pytest.fixture(autouse=True)
    def _team(self, team):
        global team_
        team_ = team

    def test_REQ_AUT_09_request_notifies_admins_but_not_the_requester(self, team):
        make_employee('admin2', ADMIN)
        assert self.request('bs').status_code == 201
        assert Notification.objects.filter(user=team['admin'], text='Staff requested leave: 2026-11-02 – 2026-11-03.').count() == 1
        assert Notification.objects.filter(user__username='admin2', type='leave').count() == 1
        assert not Notification.objects.filter(user=team['bs']).exists() and not Notification.objects.filter(user=team['bm']).exists()

    def test_an_admin_requesting_leave_does_not_notify_themself(self, team):
        self.request('admin')
        assert not Notification.objects.filter(user=team['admin']).exists()

    def test_leave_validation(self, team):
        assert self.request('bs', date_to='2026-11-01').status_code == 400
        assert self.request('bs', reason='  ').status_code == 400
        assert self.request('bs', date_from=None).status_code == 400

    def test_REQ_AUT_09_decision_notifies_the_employee(self, team):
        leave_id = self.request('bs').json()['id']
        res = call(client_for(team['bm']), 'post', f'/360/api/leave-requests/{leave_id}/approve/', {'note': 'Enjoy'})
        assert res.status_code == 200 and res.json()['status'] == 'Approved'
        note = Notification.objects.get(user=team['bs'], type='leave')
        assert note.text == 'Your leave (2026-11-02 – 2026-11-03) was approved by Bala. Enjoy'
        assert day(team['bs'], date(2026, 11, 2), today=date(2026, 11, 5))['code'] == 'LV'

    def test_rejection_message(self, team):
        leave_id = self.request('bs').json()['id']
        call(client_for(team['admin']), 'post', f'/360/api/leave-requests/{leave_id}/reject/', {})
        assert Notification.objects.get(user=team['bs']).text == 'Your leave (2026-11-02 – 2026-11-03) was rejected by Sanjeev.'

    def test_REQ_ATT_05_who_may_decide(self, team):
        mine = self.request('bm').json()['id']
        theirs = self.request('bs').json()['id']
        elsewhere = self.request('blr').json()['id']
        bm = client_for(team['bm'])
        assert call(bm, 'post', f'/360/api/leave-requests/{mine}/approve/', {}).status_code == 403              # not their own
        assert call(bm, 'post', f'/360/api/leave-requests/{elsewhere}/approve/', {}).status_code == 403          # not their team
        assert call(bm, 'post', f'/360/api/leave-requests/{theirs}/approve/', {}).status_code == 200
        assert call(client_for(team['admin']), 'post', f'/360/api/leave-requests/{mine}/approve/', {}).status_code == 200
        for who in ('bs', 'sm'):
            assert call(client_for(team[who]), 'post', f'/360/api/leave-requests/{elsewhere}/approve/', {}).status_code == 403

    def test_a_request_is_decided_once(self, team):
        leave_id = self.request('bs').json()['id']
        call(client_for(team['admin']), 'post', f'/360/api/leave-requests/{leave_id}/approve/', {})
        assert call(client_for(team['admin']), 'post', f'/360/api/leave-requests/{leave_id}/reject/', {}).status_code == 404

    def test_owner_can_cancel_while_pending_only(self, team):
        a, b = self.request('bs').json()['id'], self.request('bs').json()['id']
        call(client_for(team['admin']), 'post', f'/360/api/leave-requests/{b}/approve/', {})
        bs = client_for(team['bs'])
        assert call(bs, 'delete', f'/360/api/leave-requests/{a}/').status_code == 200
        assert call(bs, 'delete', f'/360/api/leave-requests/{b}/').status_code == 400
        other = self.request('sm').json()['id']
        assert call(bs, 'delete', f'/360/api/leave-requests/{other}/').status_code in (403, 404)

    def test_who_sees_which_requests(self, team):
        mine = self.request('bs').json()['id']
        far = self.request('blr').json()['id']
        ids = lambda who: {r['id'] for r in call(client_for(team[who]), 'get', '/360/api/leave-requests/').json()['results']}
        assert ids('admin') == {mine, far} and ids('bm') == {mine} and ids('bs') == {mine} and ids('sm') == set() and ids('blr') == {far}


class TestHolidays:
    def add(self, who='admin', **extra):
        body = {'date': '2026-11-14', 'name': 'Diwali', 'is_all_branches': True, **extra}
        return call(client_for(team_[who]), 'post', '/360/api/holidays/', body)

    @pytest.fixture(autouse=True)
    def _team(self, team):
        global team_
        team_ = team

    def test_REQ_AUT_09_holiday_for_all_branches_notifies_everyone(self, team):
        assert self.add().status_code == 201
        assert set(Notification.objects.values_list('user__username', flat=True)) == {'admin', 'bm', 'bs', 'sm', 'blr'}
        assert Notification.objects.filter(user=team['bs']).get().text == 'Holiday: Diwali on 2026-11-14'

    def test_REQ_AUT_09_branch_holiday_notifies_only_those_branches(self, team, bengaluru):
        res = self.add(is_all_branches=False, branch_ids=[bengaluru.id], date_to='2026-11-16')
        assert res.status_code == 201
        assert set(Notification.objects.values_list('user__username', flat=True)) == {'blr'}
        assert Notification.objects.get().text == 'Holiday: Diwali on 2026-11-14 – 2026-11-16'

    def test_holiday_needs_branches_or_all_and_valid_dates(self, team):
        assert self.add(is_all_branches=False).status_code == 400
        assert self.add(date_to='2026-11-01').status_code == 400
        assert self.add(name='  ').status_code == 400

    def test_only_admin_adds_and_removes_holidays(self, team):
        for who in ('bm', 'bs', 'sm'):
            assert self.add(who).status_code == 403
        h = self.add().json()
        assert call(client_for(team['bm']), 'delete', f'/360/api/holidays/{h["id"]}/').status_code == 403
        assert call(client_for(team['admin']), 'delete', f'/360/api/holidays/{h["id"]}/').status_code == 200
        assert not Holiday.objects.exists()

    def test_inactive_staff_get_no_holiday_notice(self, team):
        EmployeeProfile.objects.filter(user=team['sm']).update(is_active_employee=False)
        self.add()
        assert not Notification.objects.filter(user=team['sm']).exists()
