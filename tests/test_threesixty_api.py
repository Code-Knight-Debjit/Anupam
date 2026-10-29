"""Phase 2 — API layer tests: per-record CRUD, pagination, optimistic
concurrency, CSRF enforcement, Aadhaar/PAN masking, and the role-based
mutation routing (direct vs approval-queue vs hard-403) verified against
docs/360/AUDIT.md §3. See threesixty/api/ for the implementation under
test.
"""
import json

import pytest
from django.contrib.auth.models import User
from django.middleware.csrf import _get_new_csrf_string
from django.test import Client
from django.urls import reverse

from threesixty.models import (
    ApprovalRequest, Branch, Customer, EmployeeProfile, SalesDocument,
)

pytestmark = pytest.mark.django_db


def make_employee(username, role, branches=(), password='x'):
    user = User.objects.create_user(username=username, password=password, is_staff=True)
    profile = EmployeeProfile.objects.create(user=user, role=role)
    if branches:
        profile.branches.set(branches)
    return user


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type='application/json')


def patch_json(client, url, data):
    return client.patch(url, data=json.dumps(data), content_type='application/json')


@pytest.fixture
def chennai():
    return Branch.objects.create(name='Chennai')


@pytest.fixture
def bengaluru():
    return Branch.objects.create(name='Bengaluru')


@pytest.fixture
def admin_client(chennai):
    # A dedicated Client() per role — tests that request two role clients at
    # once (e.g. sales_manager_client + admin_client) would otherwise share
    # pytest-django's single `client` fixture instance, so the second
    # fixture's login() would silently hijack the first one's session.
    own_client = Client()
    make_employee('admin1', EmployeeProfile.ADMIN, [chennai])
    own_client.login(username='admin1', password='x')
    return own_client


@pytest.fixture
def bm_client(chennai):
    own_client = Client()
    make_employee('bm1', EmployeeProfile.BRANCH_MANAGER, [chennai])
    own_client.login(username='bm1', password='x')
    return own_client


@pytest.fixture
def staff_client(chennai):
    own_client = Client()
    make_employee('staff1', EmployeeProfile.BRANCH_STAFF, [chennai])
    own_client.login(username='staff1', password='x')
    return own_client


@pytest.fixture
def sales_manager_client(chennai):
    own_client = Client()
    make_employee('sm1', EmployeeProfile.SALES_MANAGER, [chennai])
    own_client.login(username='sm1', password='x')
    return own_client


class TestMeAndBootstrap:
    def test_me_returns_identity_and_role_flags(self, admin_client):
        resp = admin_client.get(reverse('threesixty:threesixty_api:me'))
        assert resp.status_code == 200
        body = resp.json()
        assert body['user']['username'] == 'admin1'
        assert body['flags']['is_admin'] is True
        assert body['flags']['can_delete_customer_direct'] is True

    def test_bootstrap_returns_branches_and_lookups(self, admin_client, chennai):
        resp = admin_client.get(reverse('threesixty:threesixty_api:bootstrap'))
        assert resp.status_code == 200
        body = resp.json()
        assert any(b['id'] == chennai.id for b in body['branches'])
        assert 'lookups' in body and 'sales_persons' in body


class TestCsrfProtection:
    """No view in threesixty.api is `@csrf_exempt` — a POST without a valid
    CSRF token must be rejected by Django's own CsrfViewMiddleware."""

    def test_post_without_csrf_token_is_rejected(self, chennai):
        enforcing_client = Client(enforce_csrf_checks=True)
        make_employee('admin2', EmployeeProfile.ADMIN, [chennai])
        # `client.login()` is a test-only shortcut that establishes the
        # session directly (no HTTP request/template render involved) — no
        # CSRF cookie exists yet, and we deliberately don't attach one to
        # the POST below, to prove CsrfViewMiddleware genuinely rejects it.
        enforcing_client.login(username='admin2', password='x')
        resp = post_json(enforcing_client, reverse('threesixty:threesixty_api:branches'), {'name': 'Mumbai'})
        assert resp.status_code == 403
        assert not Branch.objects.filter(name='Mumbai').exists()

    def test_post_with_csrf_token_succeeds(self, chennai):
        enforcing_client = Client(enforce_csrf_checks=True)
        make_employee('admin3', EmployeeProfile.ADMIN, [chennai])
        enforcing_client.login(username='admin3', password='x')
        # Simulate the cookie a real browser would already hold from
        # visiting any page with {% csrf_token %} — set it directly rather
        # than rendering a template, to isolate this test from unrelated
        # static-asset/manifest concerns.
        token = _get_new_csrf_string()
        enforcing_client.cookies['csrftoken'] = token
        resp = enforcing_client.post(
            reverse('threesixty:threesixty_api:branches'),
            data=json.dumps({'name': 'Mumbai'}), content_type='application/json',
            HTTP_X_CSRFTOKEN=token,
        )
        assert resp.status_code == 201
        assert Branch.objects.filter(name='Mumbai').exists()


class TestOptimisticConcurrency:
    def test_stale_version_is_rejected_with_409(self, admin_client):
        create_resp = post_json(admin_client, reverse('threesixty:threesixty_api:customers'), {'name': 'Acme'})
        customer_id = create_resp.json()['id']
        assert create_resp.json()['version'] == 1

        url = reverse('threesixty:threesixty_api:customer-detail', args=[customer_id])
        stale = patch_json(admin_client, url, {'version': 0, 'city': 'Chennai'})
        assert stale.status_code == 409
        assert stale.json()['current_version'] == 1

        fresh = patch_json(admin_client, url, {'version': 1, 'city': 'Chennai'})
        assert fresh.status_code == 200
        assert fresh.json()['version'] == 2
        assert fresh.json()['city'] == 'Chennai'

    def test_update_without_version_is_400(self, admin_client):
        create_resp = post_json(admin_client, reverse('threesixty:threesixty_api:customers'), {'name': 'Acme'})
        url = reverse('threesixty:threesixty_api:customer-detail', args=[create_resp.json()['id']])
        resp = patch_json(admin_client, url, {'city': 'Chennai'})
        assert resp.status_code == 400


class TestAadhaarPanMasking:
    def test_admin_sees_unmasked_aadhaar_pan(self, admin_client, chennai):
        staff = make_employee('staff9', EmployeeProfile.BRANCH_STAFF, [chennai])
        profile = staff.threesixty_profile
        profile.aadhaar_number = '123456789012'
        profile.pan_number = 'ABCDE1234F'
        profile.save()

        resp = admin_client.get(reverse('threesixty:threesixty_api:employee-detail', args=[profile.id]))
        body = resp.json()
        assert body['aadhaar_number'] == '123456789012'
        assert body['pan_number'] == 'ABCDE1234F'

    def test_non_admin_sees_masked_aadhaar_pan_even_for_self(self, staff_client, chennai):
        profile = EmployeeProfile.objects.get(user__username='staff1')
        profile.aadhaar_number = '123456789012'
        profile.pan_number = 'ABCDE1234F'
        profile.save()

        resp = staff_client.get(reverse('threesixty:threesixty_api:employee-detail', args=[profile.id]))
        body = resp.json()
        assert body['aadhaar_number'] == 'XXXXXXXX9012'
        assert body['pan_number'] == 'XXXXXX234F'


class TestCustomerPermissionRouting:
    def test_admin_and_branch_manager_edit_delete_directly(self, admin_client):
        created = post_json(admin_client, reverse('threesixty:threesixty_api:customers'), {'name': 'Acme'}).json()
        url = reverse('threesixty:threesixty_api:customer-detail', args=[created['id']])
        resp = patch_json(admin_client, url, {'version': 1, 'city': 'Chennai'})
        assert resp.status_code == 200 and resp.json()['city'] == 'Chennai'
        resp = admin_client.delete(url)
        assert resp.status_code == 200
        assert not Customer.objects.filter(pk=created['id']).exists()

    def test_branch_staff_edits_directly_but_delete_goes_to_approval(self, staff_client):
        created = post_json(staff_client, reverse('threesixty:threesixty_api:customers'), {'name': 'Acme'}).json()
        url = reverse('threesixty:threesixty_api:customer-detail', args=[created['id']])
        resp = patch_json(staff_client, url, {'version': 1, 'city': 'Chennai'})
        assert resp.status_code == 200 and resp.json()['city'] == 'Chennai'

        resp = staff_client.delete(url)
        assert resp.status_code == 202
        assert resp.json()['approval_requested'] is True
        assert Customer.objects.filter(pk=created['id']).exists()  # not actually deleted yet
        assert ApprovalRequest.objects.filter(
            type=ApprovalRequest.TYPE_DELETE, customer_id=created['id']
        ).exists()

    def test_sales_manager_edit_and_delete_both_go_to_approval(self, sales_manager_client):
        # Created by the Sales Manager themselves, so `visible_customers`
        # makes it visible to them (visibility is a precondition for the
        # edit/delete routing check to even be reached).
        created = post_json(
            sales_manager_client, reverse('threesixty:threesixty_api:customers'), {'name': 'Acme'}
        ).json()
        url = reverse('threesixty:threesixty_api:customer-detail', args=[created['id']])

        edit_resp = patch_json(sales_manager_client, url, {'version': 1, 'city': 'Chennai'})
        assert edit_resp.status_code == 202
        assert edit_resp.json()['approval_requested'] is True
        unchanged = Customer.objects.get(pk=created['id'])
        assert unchanged.city == ''  # proposed_data not applied yet

        delete_resp = sales_manager_client.delete(url)
        assert delete_resp.status_code == 202
        assert Customer.objects.filter(pk=created['id']).exists()


class TestSalesDocumentEditRouting:
    def _make_customer_and_doc(self, client, doc_type):
        chennai = Branch.objects.first()
        customer = Customer.objects.create(name='Acme')
        customer.assigned_to.add(int(client.session['_auth_user_id']))   # visible to a Sales Manager
        payload = {'type': doc_type, 'branch_id': chennai.id, 'customer_id': customer.id, 'date': '2026-01-01'}
        if doc_type != SalesDocument.TYPE_ENQUIRY:
            payload['items'] = [{'item_name': 'Bearing 6205', 'qty': 2, 'rate': '100'}]
        resp = post_json(client, reverse('threesixty:threesixty_api:sales-documents'), payload)
        assert resp.status_code == 201, resp.content
        return resp.json()

    def test_REQ_ROLE_02_sales_manager_quotation_edit_and_delete_go_to_approval(
        self, sales_manager_client, chennai
    ):
        doc = self._make_customer_and_doc(sales_manager_client, SalesDocument.TYPE_QUOTATION)
        url = reverse('threesixty:threesixty_api:sales-document-detail', args=[doc['id']])

        edit_resp = patch_json(sales_manager_client, url, {'version': 1, 'remarks': 'x'})
        assert edit_resp.status_code == 202
        delete_resp = sales_manager_client.delete(url)
        assert delete_resp.status_code == 202
        assert SalesDocument.objects.get(pk=doc['id']).remarks == ''          # nothing applied yet
        assert ApprovalRequest.objects.filter(document_id=doc['id']).count() == 2

    def test_sales_manager_enquiry_edit_goes_to_approval_not_direct(
        self, sales_manager_client, chennai
    ):
        doc = self._make_customer_and_doc(sales_manager_client, SalesDocument.TYPE_ENQUIRY)
        url = reverse('threesixty:threesixty_api:sales-document-detail', args=[doc['id']])
        resp = patch_json(sales_manager_client, url, {'version': 1, 'remarks': 'please review'})
        assert resp.status_code == 202
        assert ApprovalRequest.objects.filter(document_id=doc['id'], type=ApprovalRequest.TYPE_EDIT).exists()

    def test_admin_edits_quotation_directly(self, admin_client, chennai):
        doc = self._make_customer_and_doc(admin_client, SalesDocument.TYPE_QUOTATION)
        url = reverse('threesixty:threesixty_api:sales-document-detail', args=[doc['id']])
        resp = patch_json(admin_client, url, {'version': 1, 'remarks': 'approved internally'})
        assert resp.status_code == 200
        assert resp.json()['remarks'] == 'approved internally'


class TestSalesDocumentNumbering:
    def test_create_allocates_sequential_doc_number(self, admin_client, chennai):
        customer = Customer.objects.create(name='Acme')
        payload = {
            'type': SalesDocument.TYPE_ENQUIRY, 'branch_id': chennai.id, 'customer_id': customer.id,
            'date': '2026-01-01',
        }
        first = post_json(admin_client, reverse('threesixty:threesixty_api:sales-documents'), payload).json()
        second = post_json(admin_client, reverse('threesixty:threesixty_api:sales-documents'), payload).json()
        assert first['doc_number'] == 'ENQ-0001'
        assert second['doc_number'] == 'ENQ-0002'


class TestAdminOnlyResources:
    def test_non_admin_cannot_create_branch(self, staff_client):
        resp = post_json(staff_client, reverse('threesixty:threesixty_api:branches'), {'name': 'Mumbai'})
        assert resp.status_code == 403
        assert not Branch.objects.filter(name='Mumbai').exists()

    def test_admin_can_create_branch(self, admin_client):
        resp = post_json(admin_client, reverse('threesixty:threesixty_api:branches'), {'name': 'Mumbai'})
        assert resp.status_code == 201

    def test_non_admin_cannot_create_employee(self, staff_client):
        resp = post_json(staff_client, reverse('threesixty:threesixty_api:employees'), {
            'username': 'newstaff', 'password': 'pw12345', 'role': EmployeeProfile.BRANCH_STAFF,
        })
        assert resp.status_code == 403
        assert not User.objects.filter(username='newstaff').exists()

    def test_admin_creates_employee_with_hashed_password(self, admin_client):
        resp = post_json(admin_client, reverse('threesixty:threesixty_api:employees'), {
            'username': 'newstaff', 'password': 'pw12345', 'role': EmployeeProfile.BRANCH_STAFF,
        })
        assert resp.status_code == 201
        user = User.objects.get(username='newstaff')
        assert user.password != 'pw12345'
        assert user.check_password('pw12345')


class TestApprovalApproveReject:
    def test_branch_manager_approves_request_from_staff_in_their_scope(self, chennai):
        bm = make_employee('bm2', EmployeeProfile.BRANCH_MANAGER, [chennai])
        staff = make_employee('staff2', EmployeeProfile.BRANCH_STAFF, [chennai])
        customer = Customer.objects.create(name='Acme', created_by=staff)

        staff_client = Client()
        staff_client.login(username='staff2', password='x')
        del_resp = staff_client.delete(reverse('threesixty:threesixty_api:customer-detail', args=[customer.id]))
        approval_id = del_resp.json()['approval']['id']

        bm_client = Client()
        bm_client.login(username='bm2', password='x')
        approve_resp = bm_client.post(reverse('threesixty:threesixty_api:approval-approve', args=[approval_id]))
        assert approve_resp.status_code == 200
        assert approve_resp.json()['status'] == ApprovalRequest.STATUS_APPROVED
        assert not Customer.objects.filter(pk=customer.id).exists()

    def test_branch_manager_outside_scope_cannot_see_or_approve_request(self, chennai, bengaluru):
        make_employee('bm3', EmployeeProfile.BRANCH_MANAGER, [bengaluru])
        staff = make_employee('staff3', EmployeeProfile.BRANCH_STAFF, [chennai])
        customer = Customer.objects.create(name='Acme', created_by=staff)

        staff_client = Client()
        staff_client.login(username='staff3', password='x')
        del_resp = staff_client.delete(reverse('threesixty:threesixty_api:customer-detail', args=[customer.id]))
        approval_id = del_resp.json()['approval']['id']

        bm_client = Client()
        bm_client.login(username='bm3', password='x')
        approve_resp = bm_client.post(reverse('threesixty:threesixty_api:approval-approve', args=[approval_id]))
        assert approve_resp.status_code == 404
        assert Customer.objects.filter(pk=customer.id).exists()

    def test_sales_manager_cannot_approve_anything(self, sales_manager_client, chennai):
        staff = make_employee('staff4', EmployeeProfile.BRANCH_STAFF, [chennai])
        customer = Customer.objects.create(name='Acme', created_by=staff)
        staff_client = Client()
        staff_client.login(username='staff4', password='x')
        del_resp = staff_client.delete(reverse('threesixty:threesixty_api:customer-detail', args=[customer.id]))
        approval_id = del_resp.json()['approval']['id']

        resp = sales_manager_client.post(reverse('threesixty:threesixty_api:approval-approve', args=[approval_id]))
        assert resp.status_code == 403


class TestPagination:
    def test_list_is_paginated_with_default_page_size(self, admin_client, settings):
        settings.DASHBOARD_PAGE_SIZE = 5
        for i in range(7):
            post_json(admin_client, reverse('threesixty:threesixty_api:customers'), {'name': f'Customer {i}'})
        resp = admin_client.get(reverse('threesixty:threesixty_api:customers'))
        body = resp.json()
        assert body['count'] == 7
        assert body['page_size'] == 5
        assert len(body['results']) == 5
        assert body['num_pages'] == 2
