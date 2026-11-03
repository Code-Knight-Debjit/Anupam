"""Phase 5/6 — importer smoke tests and /360/ response hardening."""
import json
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client

from threesixty.models import (
    ApprovalRequest, Branch, EmployeeProfile, Interaction, SalesDocument, Task,
)

pytestmark = pytest.mark.django_db

FIXTURE = Path(__file__).parent / 'fixtures' / 'threesixty_sample_backup.json'


def run_import(*extra):
    call_command('import_360_backup', str(FIXTURE), *extra)


class TestImporter:
    def test_dry_run_writes_nothing(self):
        run_import('--dry-run')
        assert Branch.objects.count() == 0
        assert User.objects.count() == 0

    def test_import_resolves_relations_and_hashes_passwords(self, settings):
        settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.PBKDF2PasswordHasher']   # production default
        run_import()
        quote = SalesDocument.objects.get(doc_number='QUO-CHN-0100')
        assert quote.reference.doc_number == 'ENQ-0001'
        assert quote.items.count() == 1 and quote.call_log.count() == 1
        assert Interaction.objects.get().linked_doc.doc_number == 'ENQ-0001'
        assert Task.objects.get().status == 'Open'
        admin = User.objects.get(username='admin')
        assert admin.password.startswith('pbkdf2_') and admin.check_password('secret123')
        assert EmployeeProfile.objects.get(user=admin).role == EmployeeProfile.ADMIN

    def test_pending_approval_is_translated_to_django_shape(self):
        run_import()
        approval = ApprovalRequest.objects.get()
        assert approval.status == ApprovalRequest.STATUS_PENDING
        assert 'assigned_to_ids' in approval.proposed_data
        assert 'assignedTo' not in approval.proposed_data

    def test_second_run_is_idempotent(self):
        run_import()
        counts = (SalesDocument.objects.count(), User.objects.count(), Interaction.objects.count())
        run_import()
        assert counts == (SalesDocument.objects.count(), User.objects.count(), Interaction.objects.count())


class TestHardening:
    def test_360_responses_are_noindex_and_uncached(self):
        user = User.objects.create_user('ops1', password='x', is_staff=True)
        EmployeeProfile.objects.create(user=user, role=EmployeeProfile.ADMIN)
        client = Client()
        client.force_login(user)
        for path in ('/360/', '/360/api/branches/'):
            response = client.get(path)
            assert 'noindex' in response['X-Robots-Tag'], path
            assert 'no-store' in response['Cache-Control'], path

    def test_unauthenticated_360_response_also_noindex(self):
        response = Client().get('/360/')
        assert 'noindex' in response['X-Robots-Tag']

    def test_public_pages_not_affected(self):
        assert 'X-Robots-Tag' not in Client().get('/robots.txt')

    def test_robots_txt_disallows_360(self):
        assert 'Disallow: /360/' in Client().get('/robots.txt').content.decode()


class TestImporterBranchShapes:
    """The reference stores an employee's branches as branch NAMES; older backups used ids. Both must land."""

    def _import_with(self, tmp_path, branches_of):
        data = json.loads(FIXTURE.read_text())
        for e in data['employees']:
            e['branches'] = branches_of(data)
        path = tmp_path / 'b.json'
        path.write_text(json.dumps(data))
        call_command('import_360_backup', str(path))
        return data

    def test_names(self, tmp_path):
        data = self._import_with(tmp_path, lambda d: [d['branches'][0]['name']])
        profile = EmployeeProfile.objects.filter(role=EmployeeProfile.BRANCH_STAFF).first() or EmployeeProfile.objects.exclude(role=EmployeeProfile.ADMIN).first()
        assert list(profile.branches.values_list('name', flat=True)) == [data['branches'][0]['name']]

    def test_ids(self, tmp_path):
        data = self._import_with(tmp_path, lambda d: [d['branches'][0]['id']])
        profile = EmployeeProfile.objects.exclude(role=EmployeeProfile.ADMIN).first()
        assert list(profile.branches.values_list('name', flat=True)) == [data['branches'][0]['name']]


class TestImporterCounters:
    def test_counters_catch_up_with_imported_documents(self, tmp_path):
        data = json.loads(FIXTURE.read_text())
        data['docCounters'] = {}
        path = tmp_path / 'c.json'; path.write_text(json.dumps(data))
        call_command('import_360_backup', str(path))
        from threesixty.services.numbering import peek_next_number
        quote = SalesDocument.objects.get(doc_number='QUO-CHN-0100')
        assert peek_next_number(quote.branch, 'quotation') != quote.doc_number
