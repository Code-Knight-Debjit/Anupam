"""Pre-launch hardening regressions: stock-ledger privilege escalation,
employee removal, atomic approvals, leave-approval scope, bad-input 400s,
backup import without a password, and login rate limiting."""
import datetime
import json
from io import StringIO
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client

from stock_ledger.models import UserProfile
from threesixty.models import (
    ApprovalRequest, Branch, Customer, EmployeeProfile, LeaveRequest, Notification, PaymentCollection,
)

pytestmark = pytest.mark.django_db

FIXTURE = Path(__file__).parent / 'fixtures' / 'threesixty_sample_backup.json'


def make_employee(username, role, branches=(), password='x'):
    user = User.objects.create_user(username=username, password=password, is_staff=True)
    profile = EmployeeProfile.objects.create(user=user, role=role)
    if branches:
        profile.branches.set(branches)
    return user


def client_for(username, password='x'):
    client = Client()
    assert client.login(username=username, password=password)
    return client


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type='application/json')


def patch_json(client, url, data):
    return client.patch(url, data=json.dumps(data), content_type='application/json')


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()  # rate-limit counters live in the cache


@pytest.fixture
def chennai():
    return Branch.objects.create(name='Chennai')


@pytest.fixture
def bengaluru():
    return Branch.objects.create(name='Bengaluru')


class TestStockLedgerIsolation:
    def test_employee_created_via_api_is_not_stock_admin(self, chennai):
        make_employee('admin1', EmployeeProfile.ADMIN, [chennai])
        admin = client_for('admin1')
        res = post_json(admin, '/360/api/employees/', {
            'username': 'sm1', 'password': 'Pw-sm1-12345', 'role': EmployeeProfile.SALES_MANAGER,
        })
        assert res.status_code == 201
        user = User.objects.get(username='sm1')
        assert user.stock_profile.role == UserProfile.VIEWER

        # ...and it stays that way after later saves (the signal must not re-promote).
        user.first_name = 'Changed'
        user.save()
        user.refresh_from_db()
        assert user.stock_profile.role == UserProfile.VIEWER

    def test_new_employee_cannot_open_stock_admin_dashboard(self, chennai):
        make_employee('admin1', EmployeeProfile.ADMIN, [chennai])
        post_json(client_for('admin1'), '/360/api/employees/', {
            'username': 'sm1', 'password': 'Pw-sm1-12345', 'role': EmployeeProfile.SALES_MANAGER,
        })
        sm = client_for('sm1', 'Pw-sm1-12345')
        assert sm.get('/dashboard/').status_code == 403

    def test_fix_command_downgrades_only_non_admin_employees(self, chennai):
        sm = make_employee('sm1', EmployeeProfile.SALES_MANAGER, [chennai])
        owner = make_employee('owner', EmployeeProfile.ADMIN, [chennai])
        # make_employee relies on the signal, which is exactly the bug: both are stock ADMIN.
        assert sm.stock_profile.role == UserProfile.ADMIN

        out = StringIO()
        call_command('fix_360_stock_access', stdout=out)  # dry run
        sm.stock_profile.refresh_from_db()
        assert sm.stock_profile.role == UserProfile.ADMIN
        assert 'sm1' in out.getvalue() and 'owner' not in out.getvalue()

        call_command('fix_360_stock_access', '--apply', stdout=StringIO())
        sm.stock_profile.refresh_from_db()
        owner.stock_profile.refresh_from_db()
        assert sm.stock_profile.role == UserProfile.VIEWER
        assert owner.stock_profile.role == UserProfile.ADMIN


class TestEmployeeRemoval:
    def test_removed_employee_can_no_longer_log_in(self, chennai):
        make_employee('admin1', EmployeeProfile.ADMIN, [chennai])
        make_employee('gone', EmployeeProfile.BRANCH_STAFF, [chennai], password='old-pass-123')
        admin = client_for('admin1')
        victim_session = client_for('gone', 'old-pass-123')
        profile_id = EmployeeProfile.objects.get(user__username='gone').id

        assert admin.delete(f'/360/api/employees/{profile_id}/').status_code == 200

        user = User.objects.get(username='gone')  # row is kept for history
        assert not user.is_active and not user.is_staff and not user.has_usable_password()
        assert not Client().login(username='gone', password='old-pass-123')
        # an already-open session stops working too
        assert victim_session.get('/dashboard/').status_code in (302, 403)
        assert victim_session.get('/360/api/me/').status_code in (302, 403)


class TestApprovalIsAtomic:
    def test_failed_apply_leaves_request_pending(self, chennai):
        make_employee('admin1', EmployeeProfile.ADMIN, [chennai])
        sm = make_employee('sm1', EmployeeProfile.SALES_MANAGER, [chennai])
        customer = Customer.objects.create(name='Acme', created_by=sm)
        approval = ApprovalRequest.objects.create(
            type=ApprovalRequest.TYPE_EDIT, customer=customer, requested_by=sm,
            proposed_data={'plant_geo_lat': 'not-a-number'},
        )
        res = post_json(client_for('admin1'), f'/360/api/approvals/{approval.id}/approve/', {})
        assert res.status_code == 400
        approval.refresh_from_db()
        assert approval.status == ApprovalRequest.STATUS_PENDING
        assert approval.customer_id == customer.id
        assert not Notification.objects.filter(user=sm).exists()


class TestLeaveApprovalScope:
    def test_branch_manager_cannot_decide_leave_outside_their_branch(self, chennai, bengaluru):
        make_employee('bm1', EmployeeProfile.BRANCH_MANAGER, [chennai])
        other = make_employee('far', EmployeeProfile.BRANCH_STAFF, [bengaluru])
        leave = LeaveRequest.objects.create(
            user=other, date_from=datetime.date(2026, 1, 1), date_to=datetime.date(2026, 1, 2), reason='x',
        )
        res = post_json(client_for('bm1'), f'/360/api/leave-requests/{leave.id}/approve/', {})
        assert res.status_code == 403
        leave.refresh_from_db()
        assert leave.status == LeaveRequest.STATUS_PENDING

    def test_branch_manager_can_decide_leave_in_their_branch_and_admin_anywhere(self, chennai, bengaluru):
        make_employee('bm1', EmployeeProfile.BRANCH_MANAGER, [chennai])
        make_employee('admin1', EmployeeProfile.ADMIN)
        near = make_employee('near', EmployeeProfile.BRANCH_STAFF, [chennai])
        far = make_employee('far', EmployeeProfile.BRANCH_STAFF, [bengaluru])
        days = dict(date_from=datetime.date(2026, 1, 1), date_to=datetime.date(2026, 1, 2), reason='x')
        near_leave = LeaveRequest.objects.create(user=near, **days)
        far_leave = LeaveRequest.objects.create(user=far, **days)
        assert post_json(client_for('bm1'), f'/360/api/leave-requests/{near_leave.id}/approve/', {}).status_code == 200
        assert post_json(client_for('admin1'), f'/360/api/leave-requests/{far_leave.id}/reject/', {}).status_code == 200


class TestBadInputIs400:
    def test_wrong_type_on_resource_create(self, chennai):
        sm = make_employee('staff1', EmployeeProfile.BRANCH_STAFF, [chennai])
        customer = Customer.objects.create(name='Acme', created_by=sm)
        res = post_json(client_for('staff1'), '/360/api/payment-collections/', {
            'branch_id': chennai.id, 'customer_id': customer.id, 'amount': 'abc',
        })
        assert res.status_code == 400
        assert not PaymentCollection.objects.exists()

    def test_wrong_type_on_function_view(self, chennai):
        make_employee('staff1', EmployeeProfile.BRANCH_STAFF, [chennai])
        res = post_json(client_for('staff1'), '/360/api/attendance/check-in/', {'lat': 'north'})
        assert res.status_code == 400

    def test_nonexistent_foreign_key_is_400(self, chennai):
        make_employee('admin1', EmployeeProfile.ADMIN, [chennai])
        res = post_json(client_for('admin1'), '/360/api/call-assignments/', {
            'customer_id': 99999, 'week_of': '2026-01-05', 'assigned_to_id': 99999,
        })
        assert res.status_code == 400


class TestBackupImportWithoutPassword:
    def test_employee_without_password_imports_with_unusable_password_and_limited_stock_role(self, tmp_path):
        backup = json.loads(FIXTURE.read_text())
        for employee in backup['employees']:
            employee.pop('password', None)
        path = tmp_path / 'backup.json'
        path.write_text(json.dumps(backup))

        call_command('import_360_backup', str(path), stdout=StringIO())

        for employee in backup['employees']:
            user = User.objects.get(username=employee['userId'])
            assert not user.has_usable_password()
            assert user.stock_profile.role == UserProfile.VIEWER


class TestLoginRateLimit:
    def test_repeated_failures_on_one_account_get_429(self):
        make_employee('target', EmployeeProfile.BRANCH_STAFF, password='right-pass-1')
        client = Client()
        statuses = [
            client.post('/dashboard/login/', {'username': 'target', 'password': 'wrong'}).status_code
            for _ in range(12)
        ]
        assert statuses[:10] == [200] * 10
        assert statuses[10:] == [429, 429]

    def test_lockout_applies_even_with_the_correct_password(self):
        make_employee('target', EmployeeProfile.BRANCH_STAFF, password='right-pass-1')
        client = Client()
        for _ in range(10):
            client.post('/dashboard/login/', {'username': 'target', 'password': 'wrong'})
        res = client.post('/dashboard/login/', {'username': 'target', 'password': 'right-pass-1'})
        assert res.status_code == 429

    def test_other_accounts_are_unaffected(self):
        make_employee('target', EmployeeProfile.BRANCH_STAFF, password='right-pass-1')
        make_employee('bystander', EmployeeProfile.BRANCH_STAFF, password='ok-pass-123')
        client = Client()
        for _ in range(11):
            client.post('/dashboard/login/', {'username': 'target', 'password': 'wrong'})
        res = Client().post('/dashboard/login/', {'username': 'bystander', 'password': 'ok-pass-123'})
        assert res.status_code == 302

    def test_login_still_works_when_the_cache_is_down(self, monkeypatch):
        make_employee('target', EmployeeProfile.BRANCH_STAFF, password='right-pass-1')

        def boom(*args, **kwargs):
            raise ConnectionError('redis is down')

        monkeypatch.setattr('dashboard.views.is_ratelimited', boom)
        res = Client().post('/dashboard/login/', {'username': 'target', 'password': 'right-pass-1'})
        assert res.status_code == 302


class TestPostLoginRedirect:
    def _login(self, username, password, query=''):
        return Client().post(f'/dashboard/login/{query}', {'username': username, 'password': password})

    def _sales_manager(self):
        user = make_employee('sm1', EmployeeProfile.SALES_MANAGER, password='pw-sm1-12345')
        from threesixty.services.accounts import limit_stock_access
        limit_stock_access(user)

    def test_360_user_is_sent_back_to_where_they_were_going(self):
        self._sales_manager()
        res = self._login('sm1', 'pw-sm1-12345', '?next=/360/')
        assert res.status_code == 302 and res['Location'] == '/360/'

    def test_360_user_without_next_lands_in_360_not_stock(self):
        self._sales_manager()
        res = self._login('sm1', 'pw-sm1-12345')
        assert res['Location'] == '/360/'

    def test_offsite_next_is_ignored(self):
        self._sales_manager()
        res = self._login('sm1', 'pw-sm1-12345', '?next=https://evil.example/phish')
        assert res['Location'] == '/360/'

    def test_stock_admin_offsite_next_falls_back_to_dashboard(self):
        make_employee('boss', EmployeeProfile.ADMIN, password='pw-boss-12345')
        res = self._login('boss', 'pw-boss-12345', '?next=//evil.example/')
        assert res['Location'] == '/dashboard/'

    def test_stock_only_staff_still_land_on_stock_dashboard(self):
        user = User.objects.create_user('stockguy', password='pw-stock-12345', is_staff=True)
        UserProfile.objects.filter(user=user).update(role=UserProfile.BRANCH_STAFF)
        res = self._login('stockguy', 'pw-stock-12345', '?next=/360/')
        assert res['Location'] == '/dashboard/stock/'
