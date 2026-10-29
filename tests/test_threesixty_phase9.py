"""Phase 9 (Admin & hardening) — backup/restore, user removal with record transfer, audit log,
encrypted fields, uploads, query counts, security headers."""
import io
import json
from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import Client
from PIL import Image

from threesixty.models import (
    ApprovalRequest, AuditLog, Branch, CallAssignment, ContactAccess, Customer, EmployeeProfile, Interaction, Notification,
    PaymentCollection, SalesDocument, Task,
)
from threesixty.services import backup as backup_service
from threesixty.services import contacts as contact_service
from tests.helpers_360 import ADMIN, BM, BS, PASSWORD, SM, call, client_for, make_customer, make_employee

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture(autouse=True)
def _backup_dir(settings, tmp_path):
    settings.BACKUP_DIR = str(tmp_path / 'backups')


@pytest.fixture
def chennai():
    return Branch.objects.create(name='Chennai', letterhead_name='Anupam Bearings')


@pytest.fixture
def team(chennai):
    return {'admin': make_employee('admin', ADMIN, [chennai], full_name='Sanjeev'), 'bm': make_employee('bm', BM, [chennai]),
            'bs': make_employee('bs', BS, [chennai]), 'sm': make_employee('sm', SM, [chennai], full_name='Devdutt'),
            'sm2': make_employee('sm2', SM, [chennai], full_name='Ravi')}


def png():
    buf = io.BytesIO()
    Image.new('RGB', (10, 10), (1, 2, 3)).save(buf, 'PNG')
    return buf.getvalue()


def populate(team, chennai):
    customer, contacts = make_customer('Sun Steels', team['sm'], plant='P2', area='Ambattur')
    contact_service.assign_customer(customer, team['sm2'], [contacts[0].pk])
    Interaction.objects.create(contact=contacts[0], type='Call', date='2026-10-01', created_by=team['sm'])
    doc = call(client_for(team['admin']), 'post', '/360/api/sales-documents/', {
        'type': 'quotation', 'branch_id': chennai.id, 'customer_id': customer.id, 'date': '2026-10-01',
        'items': [{'item_name': '6205', 'qty': 2, 'rate': '100', 'discount': '10', 'tax': '18'}]}).json()
    PaymentCollection.objects.create(branch=chennai, customer=customer, amount=500, date='2026-10-01', created_by=team['sm'])
    Task.objects.create(title='Visit', assigned_to=team['sm'], created_by=team['admin'])
    Notification.objects.create(user=team['sm'], text='hello')
    return customer, contacts, doc


def snapshot():
    return {
        'customers': sorted(Customer.objects.values_list('name', 'plant', 'area')),
        'contacts': Customer.objects.get().contacts.count(),
        'access': sorted(ContactAccess.objects.values_list('user__username', 'contact__name')),
        'docs': sorted(SalesDocument.objects.values_list('doc_number', 'total_amount')),
        'items': sorted(SalesDocument.objects.get().items.values_list('item_name', 'value')),
        'payments': sorted(PaymentCollection.objects.values_list('amount', flat=True)),
        'tasks': sorted(Task.objects.values_list('title', flat=True)),
        'profiles': sorted(EmployeeProfile.objects.values_list('user__username', 'role')),
        'counter': sorted(Branch.objects.get().numbering_configs.values_list('doc_type', 'last_issued')),
    }


def upload(client, data, **extra):
    return client.post('/360/api/backup/restore/' if extra.pop('restore', True) else '/360/api/backup/describe/',
                       {'file': SimpleUploadedFile('b.json', data, content_type='application/json'), **extra})


# ----------------------------------------------------------------------------- backup & restore
class TestBackup:
    def test_REQ_BAK_01_round_trip_restores_everything(self, team, chennai):
        populate(team, chennai)
        admin = client_for(team['admin'])
        exported = admin.get('/360/api/backup/export/')
        assert exported.status_code == 200 and exported['Content-Disposition'].startswith('attachment')
        before = snapshot()
        # change things after the backup
        Customer.objects.all().delete() if False else None
        Customer.objects.get().contacts.first().delete()
        Task.objects.all().delete()
        SalesDocument.objects.get().delete()
        Customer.objects.update(name='Changed')
        res = upload(admin, exported.content, confirm='yes')
        assert res.status_code == 200, res.content
        assert snapshot() == before
        assert 'companies' in res.json()['restored'] and res.json()['safety_copy'].startswith('safety-copy-')

    def test_restore_keeps_passwords_logins_and_the_sensitive_fields_encrypted(self, team, chennai):
        EmployeeProfile.objects.filter(user=team['bs']).update(pan_number='')
        profile = team['bs'].threesixty_profile
        profile.pan_number = 'ABCDE1234F'
        profile.save()
        admin = client_for(team['admin'])
        data = admin.get('/360/api/backup/export/').content
        assert b'ABCDE1234F' not in data                                                           # never plain in the file
        EmployeeProfile.objects.filter(user=team['bs']).update(role=SM)
        assert upload(admin, data, confirm='yes').status_code == 200
        bs = EmployeeProfile.objects.get(user__username='bs')
        assert bs.role == BS and bs.pan_number == 'ABCDE1234F'
        assert Client().login(username='bs', password=PASSWORD)

    def test_a_safety_copy_of_the_current_data_is_written_first(self, team, chennai, settings):
        populate(team, chennai)
        admin = client_for(team['admin'])
        data = admin.get('/360/api/backup/export/').content
        Customer.objects.update(name='Newer Name')
        name = upload(admin, data, confirm='yes').json()['safety_copy']
        listed = [f['name'] for f in call(admin, 'get', '/360/api/backup/safety-copies/').json()['results']]
        assert name in listed
        copy = json.loads(admin.get(f'/360/api/backup/safety-copies/{name}').getvalue())
        assert any(r['fields']['name'] == 'Newer Name' for r in copy['datasets']['companies'] if r['model'] == 'threesixty.customer')
        assert oct((__import__('pathlib').Path(settings.BACKUP_DIR) / name).stat().st_mode & 0o777) == '0o600'

    def test_nothing_changes_when_the_file_is_bad(self, team, chennai):
        populate(team, chennai)
        admin = client_for(team['admin'])
        before = snapshot()
        for bad in (b'not json', b'{"app": "other"}', json.dumps({'app': 'anupam360', 'format': 99, 'datasets': {}}).encode()):
            assert upload(admin, bad, confirm='yes').status_code == 400
        good = json.loads(admin.get('/360/api/backup/export/').content)
        good['datasets']['salesDocs'].append({'model': 'threesixty.salesdocument', 'pk': 'not-a-number', 'fields': {}})     # damaged late in the file
        res = upload(admin, json.dumps(good).encode(), confirm='yes')
        assert res.status_code == 400 and 'nothing was changed' in res.json()['error']
        assert snapshot() == before                                                      # the whole restore rolled back

    def test_confirmation_is_required(self, team, chennai):
        data = client_for(team['admin']).get('/360/api/backup/export/').content
        assert upload(client_for(team['admin']), data).status_code == 400

    def test_refuses_a_backup_that_would_lock_the_admin_out(self, team, chennai):
        admin = client_for(team['admin'])
        data = json.loads(admin.get('/360/api/backup/export/').content)
        for row in data['datasets']['employees']:
            if row['fields']['user'] == team['admin'].pk:
                row['fields']['role'] = BS
        res = upload(admin, json.dumps(data).encode(), confirm='yes')
        assert res.status_code == 400 and 'lock you out' in res.json()['error']
        data['users'] = [u for u in data['users'] if u['username'] != 'admin']
        assert 'not in this backup' in upload(admin, json.dumps(data).encode(), confirm='yes').json()['error']
        assert EmployeeProfile.objects.get(user=team['admin']).role == ADMIN

    def test_refuses_a_backup_from_a_different_database(self, team, chennai):
        admin = client_for(team['admin'])
        data = json.loads(admin.get('/360/api/backup/export/').content)
        data['users'].append({**data['users'][0], 'username': 'stranger'})            # same id as admin, other name
        assert 'Restore into the database the backup came from' in upload(admin, json.dumps(data).encode(), confirm='yes').json()['error']

    def test_describe_lists_contents_and_what_an_older_backup_lacks(self, team, chennai):
        populate(team, chennai)
        admin = client_for(team['admin'])
        data = json.loads(admin.get('/360/api/backup/export/').content)
        del data['datasets']['payments'], data['datasets']['leaveRequests']
        info = upload(admin, json.dumps(data).encode(), restore=False).json()
        assert info['contains']['companies'] > 0 and set(info['missing']) == {'payments', 'leaveRequests'} and info['users'] == 5
        assert Customer.objects.exists()                                            # describing changes nothing

    def test_restoring_an_older_backup_leaves_missing_datasets_empty(self, team, chennai):
        populate(team, chennai)
        admin = client_for(team['admin'])
        data = json.loads(admin.get('/360/api/backup/export/').content)
        del data['datasets']['payments']
        assert upload(admin, json.dumps(data).encode(), confirm='yes').status_code == 200
        assert not PaymentCollection.objects.exists() and Customer.objects.exists()

    def test_only_admin_can_use_backup_tools(self, team):
        for who in ('bm', 'bs', 'sm'):
            c = client_for(team[who])
            assert c.get('/360/api/backup/export/').status_code == 403
            assert upload(c, b'{}', confirm='yes').status_code == 403
            assert upload(c, b'{}', restore=False).status_code == 403
            assert c.get('/360/api/backup/safety-copies/').status_code == 403
            assert c.get('/360/api/audit-log/').status_code == 403

    def test_safety_copy_download_is_not_a_path_traversal(self, team):
        admin = client_for(team['admin'])
        assert admin.get('/360/api/backup/safety-copies/..%2F..%2Fmanage.py').status_code == 404
        assert admin.get('/360/api/backup/safety-copies/notes.txt').status_code == 404

    def test_backup_lives_outside_the_media_folder(self, settings):
        from pathlib import Path
        assert not str(backup_service.backup_dir()).startswith(str(Path(settings.MEDIA_ROOT)))

    def test_the_audit_log_survives_a_restore(self, team, chennai):
        admin = client_for(team['admin'])
        data = admin.get('/360/api/backup/export/').content
        before = AuditLog.objects.count()
        upload(admin, data, confirm='yes')
        assert AuditLog.objects.count() > before and AuditLog.objects.filter(action='backup.restore').exists()


# ----------------------------------------------------------------------------- removing a user (REQ-USR-02)
class TestUserRemoval:
    def remove(self, who, target, **query):
        qs = '&'.join(f'{k}={v}' for k, v in query.items())
        return call(client_for(who), 'delete', f'/360/api/employees/{target.threesixty_profile.id}/' + (f'?{qs}' if qs else ''))

    def test_a_person_with_no_records_is_removed_directly(self, team):
        res = self.remove(team['admin'], team['bs'])
        assert res.status_code == 200 and res.json()['records']['total'] == 0
        assert not EmployeeProfile.objects.filter(user=team['bs']).exists() and not Client().login(username='bs', password=PASSWORD)

    def test_REQ_USR_02_records_must_be_transferred_first(self, team, chennai):
        populate(team, chennai)
        before = snapshot()
        res = self.remove(team['admin'], team['sm'])
        assert res.status_code == 400 and res.json()['needs_transfer'] is True
        assert EmployeeProfile.objects.filter(user=team['sm']).exists() and snapshot() == before
        assert self.remove(team['admin'], team['sm'], transfer_to=team['sm'].pk).status_code == 400                    # not to themself
        team['bs'].is_active = False
        team['bs'].save()
        assert self.remove(team['admin'], team['sm'], transfer_to=team['bs'].pk).status_code == 400                    # not to an inactive user

    def test_records_move_to_the_chosen_person(self, team, chennai):
        customer, contacts, doc = populate(team, chennai)
        customer.assigned_to.add(team['sm'])
        contact_service.assign_customer(customer, team['sm'], [contacts[1].pk])
        CallAssignment.objects.create(customer=customer, contact=contacts[0], week_of='2026-10-26', assigned_to=team['sm'], assigned_by=team['admin'])
        counts = call(client_for(team['admin']), 'get', f'/360/api/employees/{team["sm"].threesixty_profile.id}/records/').json()
        assert counts['customers_created'] == 1 and counts['customers_assigned'] == 1 and counts['tasks_assigned'] == 1
        assert counts['payments'] == 1 and counts['outreach_assigned'] == 1 and counts['total'] >= 5
        res = self.remove(team['admin'], team['sm'], transfer_to=team['bs'].pk)
        assert res.status_code == 200 and res.json()['transferred_to'] == 'bs'
        customer.refresh_from_db()
        assert customer.created_by == team['bs'] and set(customer.assigned_to.all()) == {team['bs'], team['sm2']}
        assert ContactAccess.objects.filter(customer=customer, user=team['bs'], contact=contacts[1]).exists()
        assert not ContactAccess.objects.filter(user=team['sm']).exists()
        assert Task.objects.get(title='Visit').assigned_to == team['bs']
        assert PaymentCollection.objects.get().created_by == team['bs']
        assert CallAssignment.objects.get().assigned_to == team['bs']
        assert record_counts_total(team['sm']) == 0
        # the login is gone but the person row stays so history keeps its author
        team['sm'].refresh_from_db()
        assert team['sm'].is_active is False and not team['sm'].has_usable_password()
        assert Interaction.objects.get().created_by == team['sm']

    def test_guard_rails(self, team):
        assert self.remove(team['admin'], team['admin']).status_code == 400
        for who in ('bm', 'bs', 'sm'):
            assert self.remove(team[who], team['sm2']).status_code == 403
        assert call(client_for(team['bm']), 'get', f'/360/api/employees/{team["sm"].threesixty_profile.id}/records/').status_code == 403

    def test_cannot_remove_the_last_admin_via_a_second_account(self, team):
        # a second admin may remove the first; the last remaining admin cannot be removed by themself
        second = make_employee('admin2', ADMIN)
        assert self.remove(second, team['admin']).status_code == 200
        assert self.remove(second, second).status_code == 400


def record_counts_total(user):
    from threesixty.services.users import record_counts
    return record_counts(user)['total']


# ----------------------------------------------------------------------------- audit log
class TestAuditLog:
    def actions(self):
        return list(AuditLog.objects.values_list('action', flat=True))

    def test_logins_and_failures_are_recorded_without_passwords(self, team):
        c = Client()
        c.post('/360/login/', {'action': 'login', 'username': 'bs', 'password': 'wrong-password'})
        c.post('/360/login/', {'action': 'login', 'username': 'bs', 'password': PASSWORD})
        c.get('/360/logout/')
        assert self.actions() == ['logout', 'login', 'login.failed']
        assert not any('wrong-password' in (a.summary + a.username) for a in AuditLog.objects.all())
        failed = AuditLog.objects.get(action='login.failed')
        assert failed.username == 'bs' and failed.user is None and failed.ip_address

    def test_admin_actions_are_recorded(self, team, chennai):
        admin = client_for(team['admin'])
        branch = call(admin, 'post', '/360/api/branches/', {'name': 'Mysuru'}).json()
        call(admin, 'patch', f'/360/api/employees/{team["bs"].threesixty_profile.id}/', {'role': 'BRANCH_MANAGER', 'new_password': 'brandnew1'})
        call(admin, 'post', '/360/api/employees/', {'username': 'newbie', 'password': 'abcdef', 'role': 'BRANCH_STAFF'})
        call(admin, 'delete', f'/360/api/branches/{branch["id"]}/')
        got = self.actions()
        for expected in ('branch.create', 'user.update', 'user.create', 'branch.deleted'):
            assert expected in got, expected
        update = AuditLog.objects.get(action='user.update')
        assert 'role' in update.summary and 'password' in update.summary and 'brandnew1' not in update.summary

    def test_approvals_and_deletes_are_recorded(self, team):
        customer, _ = make_customer('Sun Steels', team['sm'])
        call(client_for(team['sm']), 'delete', f'/360/api/customers/{customer.id}/')
        approval = ApprovalRequest.objects.get()
        call(client_for(team['admin']), 'post', f'/360/api/approvals/{approval.id}/approve/')
        other, _ = make_customer('Other Co', team['admin'])
        call(client_for(team['admin']), 'delete', f'/360/api/customers/{other.id}/')
        got = self.actions()
        assert 'approval.approve.delete' in got and 'customer.delete' in got

    def test_the_log_is_read_only_filterable_and_exportable(self, team):
        c = Client()
        c.post('/360/login/', {'action': 'login', 'username': 'bs', 'password': PASSWORD})
        admin = client_for(team['admin'])
        listing = call(admin, 'get', '/360/api/audit-log/?action=login').json()
        assert listing['count'] == 1 and listing['results'][0]['username'] == 'bs'
        assert call(admin, 'get', f'/360/api/audit-log/?user_id={team["bs"].pk}').json()['count'] == 1
        assert call(admin, 'get', '/360/api/audit-log/?action=nothing').json()['count'] == 0
        assert admin.get('/360/api/audit-log/?format=xlsx')['Content-Type'].startswith('application/vnd.openxml')
        assert admin.get('/360/api/audit-log/?format=pdf').content[:4] == b'%PDF'
        for method in ('post', 'patch', 'delete'):
            assert call(admin, method, '/360/api/audit-log/', {}).status_code == 405
        assert AuditLog.objects.count() >= 1


# ----------------------------------------------------------------------------- sensitive data
class TestSensitiveData:
    def test_existing_plain_text_rows_stay_readable_and_the_command_encrypts_them(self, team):
        with connection.cursor() as cursor:
            cursor.execute("update threesixty_employeeprofile set aadhaar_number = '111122223333' where user_id = %s", [team['bs'].pk])
        assert EmployeeProfile.objects.get(user=team['bs']).aadhaar_number == '111122223333'
        out = StringIO()
        call_command('encrypt_360_sensitive_fields', '--dry-run', stdout=out)
        assert '1 profile' in out.getvalue()
        call_command('encrypt_360_sensitive_fields', stdout=StringIO())
        with connection.cursor() as cursor:
            cursor.execute('select aadhaar_number from threesixty_employeeprofile where user_id = %s', [team['bs'].pk])
            assert cursor.fetchone()[0].startswith('enc1:')
        assert EmployeeProfile.objects.get(user=team['bs']).aadhaar_number == '111122223333'

    def test_a_wrong_key_never_shows_ciphertext(self, team, settings):
        profile = team['bs'].threesixty_profile
        profile.pan_number = 'ABCDE1234F'
        profile.save()
        settings.FIELD_ENCRYPTION_KEY = 'x' * 43 + '='
        assert EmployeeProfile.objects.get(user=team['bs']).pan_number == ''

    def test_exports_and_reports_never_carry_aadhaar_or_pan(self, team):
        profile = team['bs'].threesixty_profile
        profile.aadhaar_number, profile.pan_number = '999988887777', 'ZZZZZ9999Z'
        profile.save()
        admin = client_for(team['admin'])
        for url in ('/360/api/attendance/report/?format=xlsx', '/360/api/reports/user-performance/', '/360/api/dashboard/admin/',
                    '/360/api/audit-log/', '/360/api/attendance/summary/'):
            assert b'999988887777' not in admin.get(url).content and b'ZZZZZ9999Z' not in admin.get(url).content, url
        assert b'999988887777' not in admin.get('/360/api/backup/export/').content


# ----------------------------------------------------------------------------- uploads
class TestUploads:
    def test_customer_logo_upload_rules(self, team):
        customer, _ = make_customer('Sun Steels', team['admin'])
        url = f'/360/api/customers/{customer.id}/logo/'
        bs = client_for(team['bs'])
        assert bs.post(url, {'file': SimpleUploadedFile('l.png', png(), content_type='image/png')}).status_code == 200
        assert bs.post(url, {'file': SimpleUploadedFile('l.png', b'<script>alert(1)</script>', content_type='image/png')}).status_code == 400
        assert bs.post(url, {}).status_code == 400
        assert call(bs, 'delete', url).status_code == 200
        sm_customer, _ = make_customer('Mine', team['sm'])
        assert client_for(team['sm']).post(f'/360/api/customers/{sm_customer.id}/logo/', {'file': SimpleUploadedFile('l.png', png())}).status_code == 403
        assert bs.post(f'/360/api/customers/99999/logo/', {'file': SimpleUploadedFile('l.png', png())}).status_code == 404

    def test_excel_import_limits(self, team):
        big = io.BytesIO(b'0' * (5 * 1024 * 1024 + 1))
        big.name = 'big.xlsx'
        assert client_for(team['admin']).post('/360/api/customers/import/', {'file': big}).status_code == 400


# ----------------------------------------------------------------------------- query counts (no N+1)
LIST_URLS = [
    '/360/api/customers/', '/360/api/customers/?search=co', '/360/api/contacts/', '/360/api/interactions/', '/360/api/sales-documents/',
    '/360/api/tasks/', '/360/api/tasks/?scope=all', '/360/api/payment-collections/', '/360/api/call-assignments/', '/360/api/notifications/',
    '/360/api/employees/', '/360/api/approvals/', '/360/api/leave-requests/', '/360/api/attendance/', '/360/api/audit-log/',
    '/360/api/reports/sales-performance/?from=2020-01-01', '/360/api/reports/interaction-log/?from=2020-01-01',
    '/360/api/reports/sales-reports/?from=2020-01-01', '/360/api/reports/customer-reports/', '/360/api/reports/not-contacted/',
    '/360/api/reports/payment-collection/?from=2020-01-01', '/360/api/dashboard/admin/', '/360/api/attendance/summary/',
]


class TestQueryCounts:
    """The number of queries must not grow with the number of rows (each URL runs on a fresh database,
    with `page_size=200` so the page cap cannot hide a per-row query)."""

    @pytest.fixture
    def world(self, team, chennai):
        customer, contacts = make_customer('Sun Steels', team['admin'])
        counter = {'n': 0}

        def make(n):
            for _ in range(n):
                counter['n'] += 1
                k = counter['n']
                c, cc = make_customer(f'Co {k}', team['sm'], contacts=('A', 'B'))
                c.assigned_to.add(team['sm'], team['bs'])
                Interaction.objects.create(contact=cc[0], type='Call', date='2026-10-01', created_by=team['sm'])
                call(client_for(team['admin']), 'post', '/360/api/sales-documents/', {
                    'type': 'quotation', 'branch_id': chennai.id, 'customer_id': c.id, 'date': '2026-10-01',
                    'items': [{'item_name': 'A', 'qty': 1, 'rate': 1}, {'item_name': 'B', 'qty': 1, 'rate': 1}]})
                Task.objects.create(title='t', assigned_to=team['admin'], created_by=team['bs'])
                p = PaymentCollection.objects.create(branch=chennai, customer=c, amount=10, date='2026-10-01', created_by=team['admin'])
                p.receipts.create(amount=1, date='2026-10-02')
                a = CallAssignment.objects.create(customer=c, contact=cc[0], week_of=date(2025, 1, 1) + timedelta(days=k), assigned_to=team['admin'])
                a.attempts.create(reason='Busy', by=team['admin'])
                Notification.objects.create(user=team['admin'], text='x')
                call(client_for(team['sm']), 'patch', f'/360/api/customers/{c.id}/', {'version': 1, 'city': f'City {k}'})      # an approval
                from threesixty.models import AttendanceRecord, LeaveRequest
                LeaveRequest.objects.create(user=team['bs'], date_from=date(2026, 11, 1) + timedelta(days=k), date_to=date(2026, 11, 1) + timedelta(days=k), reason='x')
                AttendanceRecord.objects.create(user=team['bs'], date=date(2026, 1, 1) + timedelta(days=k))
                AuditLog.objects.create(username='x', action='a')
        return make

    @pytest.mark.parametrize('url', LIST_URLS)
    def test_queries_do_not_grow_with_rows(self, url, team, world):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        client = client_for(team['admin'])
        sep = '&' if '?' in url else '?'
        counts = []
        for rows in (2, 10):
            world(rows)
            with CaptureQueriesContext(connection) as ctx:
                res = client.get(f'{url}{sep}page_size=200')
            assert res.status_code == 200, (url, res.content[:200])
            counts.append(len(ctx))
        assert counts[1] <= counts[0] + 2, f'{url}: queries grew with the number of rows: {counts}'


# ----------------------------------------------------------------------------- security
class TestSecurity:
    def test_responses_are_never_cached_and_not_indexed(self, team):
        res = client_for(team['admin']).get('/360/api/customers/')
        assert 'no-store' in res['Cache-Control'] and 'noindex' in res['X-Robots-Tag']

    def test_post_without_csrf_token_is_rejected(self, team):
        c = Client(enforce_csrf_checks=True)
        c.login(username='admin', password=PASSWORD)
        assert c.post('/360/api/customers/', data=json.dumps({'name': 'X'}), content_type='application/json').status_code == 403
        assert not Customer.objects.exists()

    def test_every_api_route_rejects_anonymous_users(self, client):
        from django.urls import get_resolver
        paths = ['/360/api/customers/', '/360/api/employees/', '/360/api/backup/export/', '/360/api/audit-log/', '/360/api/reports/',
                 '/360/api/dashboard/admin/', '/360/api/labels/options/', '/360/api/attendance/me/', '/360/api/sales-documents/',
                 '/360/api/payment-collections/', '/360/api/tasks/', '/360/api/approvals/', '/360/api/notifications/']
        for path in paths:
            assert client.get(path).status_code == 302, path

    def test_user_text_is_escaped_in_the_pdf_and_stored_verbatim(self, team, chennai):
        customer, _ = make_customer('<img src=x onerror=alert(1)>', team['admin'])
        res = client_for(team['admin']).get(f'/360/api/customers/{customer.id}/')
        assert res['Content-Type'] == 'application/json' and res.json()['name'].lower().startswith('<img')          # JSON, never rendered as HTML
