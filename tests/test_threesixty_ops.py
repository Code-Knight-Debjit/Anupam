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

    def test_import_resolves_relations_and_hashes_passwords(self):
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
