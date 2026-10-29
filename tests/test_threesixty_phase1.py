"""Phase 1 (Foundation) — Django tests, named after the REQ-ID they prove.

Covers: roles & menu visibility (REQ-ROLE-*), branches / letterhead / numbering
(REQ-DOC-01/02), pick-lists and branch removal (REQ-LST-01), users, activation
and password reset (REQ-USR-01/03), login.
"""
import io
import json

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from threesixty.models import (
    Branch, BranchNumbering, Customer, EmployeeProfile, LookupItem, SalesDocument, SalesPerson,
)
from threesixty.services.accounts import limit_stock_access
from threesixty.services.numbering import allocate_next_number, bump_counter_to, peek_next_number

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()  # rate-limit counters live in the cache


def make_employee(username, role, branches=(), password='secret-pw-1', **profile_kwargs):
    user = User.objects.create_user(username=username, password=password, is_staff=True)
    limit_stock_access(user)  # as the Users API does, so /dashboard/login/ sends 360 staff to /360/
    profile = EmployeeProfile.objects.create(user=user, role=role, **profile_kwargs)
    if branches:
        profile.branches.set(branches)
    return user


def client_for(username, password='secret-pw-1'):
    c = Client()
    assert c.login(username=username, password=password)
    return c


def send(client, method, url, data=None):
    return getattr(client, method)(url, data=json.dumps(data or {}), content_type='application/json')


@pytest.fixture
def chennai():
    return Branch.objects.create(name='Chennai')


@pytest.fixture
def bengaluru():
    return Branch.objects.create(name='Bengaluru')


@pytest.fixture
def admin(chennai):
    make_employee('admin1', EmployeeProfile.ADMIN, [chennai])
    return client_for('admin1')


def role_client(role, chennai, name=None):
    name = name or role.lower()
    make_employee(name, role, [chennai])
    return client_for(name)


def png_bytes(size=(8, 8)):
    buf = io.BytesIO()
    Image.new('RGB', size, (200, 80, 0)).save(buf, 'PNG')
    return buf.getvalue()


# ----------------------------------------------------------------------------- roles & menus
class TestMenusByRole:
    def test_REQ_ROLE_03_only_admin_sees_admin_menus(self, chennai):
        for role, expect_admin_menus in [
            (EmployeeProfile.ADMIN, True), (EmployeeProfile.BRANCH_MANAGER, False),
            (EmployeeProfile.BRANCH_STAFF, False), (EmployeeProfile.SALES_MANAGER, False),
        ]:
            nav = role_client(role, chennai).get('/360/api/me/').json()['nav']
            for item in ('Manage lists', 'Import Excel', 'Users', 'Branch'):
                assert (item in nav) is expect_admin_menus, (role, item)

    def test_REQ_ROLE_04_sales_manager_hides_back_office_menus(self, chennai):
        nav = role_client(EmployeeProfile.SALES_MANAGER, chennai).get('/360/api/me/').json()['nav']
        for item in ('Proforma Invoice', 'Delivery Challan', 'Pending PO', 'Payment Collection', 'Print Label'):
            assert item not in nav
        assert 'Enquiry' in nav and 'Quotation' in nav

    def test_REQ_RPT_01_sales_manager_report_tabs(self, chennai):
        tabs = role_client(EmployeeProfile.SALES_MANAGER, chennai).get('/360/api/me/').json()['report_tabs']
        assert 'Sales Performance' not in tabs and 'Customer Activity' not in tabs and 'Not Contacted' in tabs

    def test_REQ_ROLE_03_admin_only_endpoints_reject_other_roles(self, chennai):
        """Menu hiding is cosmetic — the server refuses the writes."""
        for role in (EmployeeProfile.BRANCH_MANAGER, EmployeeProfile.BRANCH_STAFF, EmployeeProfile.SALES_MANAGER):
            c = role_client(role, chennai)
            assert send(c, 'post', '/360/api/branches/', {'name': 'X'}).status_code == 403
            assert send(c, 'post', '/360/api/lookups/', {'kind': 'source', 'name': 'X'}).status_code == 403
            assert send(c, 'post', '/360/api/sales-persons/', {'name': 'X'}).status_code == 403
            assert send(c, 'post', '/360/api/employees/', {'username': 'n', 'password': 'abcdef', 'role': 'BRANCH_STAFF'}).status_code == 403
            assert send(c, 'patch', f'/360/api/branches/{chennai.id}/numbering/quotation/', {'prefix': 'Z'}).status_code == 403
            upload = SimpleUploadedFile('a.png', png_bytes(), content_type='image/png')
            assert c.post(f'/360/api/branches/{chennai.id}/images/logo/', {'file': upload}).status_code == 403

    def test_REQ_ROLE_02_needs_approval_matrix_on_roles(self, chennai):
        from threesixty.permissions import RoleRules
        sm = User.objects.get(username=make_employee('sm', EmployeeProfile.SALES_MANAGER).username)
        bs = make_employee('bs', EmployeeProfile.BRANCH_STAFF)
        assert RoleRules.needs_approval(sm, 'customer.edit') and RoleRules.needs_approval(sm, 'salesdoc.delete')
        assert not RoleRules.needs_approval(bs, 'customer.edit') and RoleRules.needs_approval(bs, 'customer.delete')


# ----------------------------------------------------------------------------- numbering
class TestNumbering:
    def test_REQ_DOC_01_sequence_per_type_and_branch(self, chennai, bengaluru):
        assert [allocate_next_number(chennai, 'quotation') for _ in range(3)] == ['QUO-0001', 'QUO-0002', 'QUO-0003']
        assert allocate_next_number(bengaluru, 'quotation') == 'QUO-0001'     # branches independent
        assert allocate_next_number(chennai, 'enquiry') == 'ENQ-0001'         # types independent
        assert allocate_next_number(chennai, 'proforma') == 'PI-0001'
        assert allocate_next_number(chennai, 'dc') == 'DC-0001'

    def test_REQ_DOC_01_counter_only_moves_forward(self, chennai):
        allocate_next_number(chennai, 'quotation')                    # 1
        allocate_next_number(chennai, 'quotation')                    # 2
        bump_counter_to(chennai, 'quotation', 'QUO-0001')             # older number never lowers it
        assert peek_next_number(chennai, 'quotation') == 'QUO-0003'
        bump_counter_to(chennai, 'quotation', 'QUO-0010')             # manual higher number pushes it up
        assert allocate_next_number(chennai, 'quotation') == 'QUO-0011'

    def test_REQ_DOC_01_deleting_a_document_never_frees_its_number(self, chennai):
        customer = Customer.objects.create(name='Acme')
        number = allocate_next_number(chennai, 'quotation')
        doc = SalesDocument.objects.create(type='quotation', doc_number=number, branch=chennai,
                                           customer=customer, date='2026-01-01')
        doc.delete()
        assert allocate_next_number(chennai, 'quotation') == 'QUO-0002'

    def test_REQ_DOC_02_prefix_suffix_start(self, chennai):
        BranchNumbering.objects.create(branch=chennai, doc_type='quotation', prefix='CHN/Q', suffix='26-27', start_at=100)
        assert allocate_next_number(chennai, 'quotation') == 'CHN/Q-0100-26-27'
        assert allocate_next_number(chennai, 'quotation') == 'CHN/Q-0101-26-27'
        bump_counter_to(chennai, 'quotation', 'CHN/Q-0300-26-27')     # sequence = first digits, not the year
        assert allocate_next_number(chennai, 'quotation') == 'CHN/Q-0301-26-27'

    def test_REQ_DOC_02_blank_prefix_falls_back_to_default(self, chennai):
        BranchNumbering.objects.create(branch=chennai, doc_type='quotation', prefix='', suffix='')
        assert allocate_next_number(chennai, 'quotation') == 'QUO-0001'

    def test_REQ_DOC_02_pending_po_has_no_generated_number(self, chennai, admin):
        with pytest.raises(ValueError):
            allocate_next_number(chennai, 'po')
        assert peek_next_number(chennai, 'po') == ''
        assert admin.get(f'/360/api/branches/{chennai.id}/numbering/po/').status_code == 400

    def test_REQ_DOC_02_pending_po_created_without_number_stays_blank(self, admin, chennai):
        customer = Customer.objects.create(name='Acme')
        res = send(admin, 'post', '/360/api/sales-documents/', {
            'type': 'po', 'branch_id': chennai.id, 'customer_id': customer.id, 'date': '2026-01-01', 'doc_number': 'CUST/PO/77',
            'items': [{'item_name': 'Bearing', 'qty': 1}],
        })
        assert res.status_code == 201, res.content
        assert res.json()['doc_number'] == 'CUST/PO/77'
        assert not BranchNumbering.objects.filter(branch=chennai, doc_type='po').exists()

    def test_REQ_DOC_02_numbering_api_settings_and_preview(self, admin, chennai):
        url = f'/360/api/branches/{chennai.id}/numbering/quotation/'
        res = send(admin, 'patch', url, {'prefix': 'CHN/Q', 'suffix': '26-27', 'start_at': 100})
        assert res.status_code == 200 and res.json()['next_number'] == 'CHN/Q-0100-26-27'
        res = send(admin, 'patch', url, {'prefix': ''})               # blank prefix -> default
        assert res.json()['next_number'] == 'QUO-0100-26-27' and res.json()['effective_prefix'] == 'QUO'
        assert send(admin, 'patch', url, {'start_at': 0}).status_code == 400
        assert send(admin, 'patch', url, {'start_at': 'x'}).status_code == 400

    def test_REQ_DOC_01_numbers_are_independent_per_branch_through_the_api(self, admin, chennai, bengaluru):
        customer = Customer.objects.create(name='Acme')

        def create(branch):
            res = send(admin, 'post', '/360/api/sales-documents/', {
                'type': 'quotation', 'branch_id': branch.id, 'customer_id': customer.id, 'date': '2026-01-01',
                'items': [{'item_name': 'Bearing', 'qty': 1, 'rate': '10'}],
            })
            assert res.status_code == 201, res.content
            return res.json()['doc_number']
        assert [create(chennai), create(chennai), create(bengaluru)] == ['QUO-0001', 'QUO-0002', 'QUO-0001']


# ----------------------------------------------------------------------------- branches
class TestBranches:
    def test_branch_letterhead_bank_format_and_watermark_roundtrip(self, admin):
        res = send(admin, 'post', '/360/api/branches/', {
            'name': 'Mysuru', 'letterhead_name': 'Anupam Bearings', 'letterhead_mobile': '98400', 'letterhead_website': 'x.in',
            'udyam_number': 'UDYAM-1', 'bank_name': 'HDFC', 'bank_branch': 'T Nagar', 'bank_account_no': '123', 'bank_ifsc': 'HDFC0001',
            'doc_format': 2, 'accent_color': '#a14000', 'watermark_enabled': True, 'watermark_type': 'text',
            'watermark_text': 'ANUPAM', 'watermark_size': 40, 'terms': 'Payment in 30 days',
        })
        assert res.status_code == 201, res.content
        body = res.json()
        assert body['bank_ifsc'] == 'HDFC0001' and body['doc_format'] == 2 and body['watermark_text'] == 'ANUPAM'
        assert body['terms'] == 'Payment in 30 days' and body['logo_url'] == ''

    def test_watermark_text_required_when_type_is_text(self, admin):
        res = send(admin, 'post', '/360/api/branches/', {'name': 'B', 'watermark_enabled': True, 'watermark_type': 'text'})
        assert res.status_code == 400 and 'Watermark text' in res.json()['error']

    def test_invalid_colour_format_and_size_rejected(self, admin, chennai):
        url = f'/360/api/branches/{chennai.id}/'
        assert send(admin, 'patch', url, {'accent_color': 'orange'}).status_code == 400
        assert send(admin, 'patch', url, {'doc_format': 3}).status_code == 400
        assert send(admin, 'patch', url, {'watermark_size': 5}).status_code == 400

    def test_duplicate_branch_name_rejected(self, admin, chennai):
        assert send(admin, 'post', '/360/api/branches/', {'name': 'chennai'}).status_code == 400

    def test_REQ_LST_01_branch_in_use_is_deactivated_not_deleted(self, admin, chennai):
        customer = Customer.objects.create(name='Acme')
        doc = SalesDocument.objects.create(type='enquiry', doc_number='ENQ-0001', branch=chennai,
                                           customer=customer, date='2026-01-01')
        res = admin.delete(f'/360/api/branches/{chennai.id}/')
        assert res.status_code == 200 and res.json() == {'deleted': False, 'deactivated': True}
        doc.refresh_from_db(); chennai.refresh_from_db()
        assert doc.branch_id == chennai.id and chennai.is_active is False
        assert chennai.id not in [b['id'] for b in admin.get('/360/api/bootstrap/').json()['branches']]

    def test_REQ_LST_01_unused_branch_is_deleted(self, admin):
        spare = Branch.objects.create(name='Spare')
        assert admin.delete(f'/360/api/branches/{spare.id}/').json()['deleted'] is True
        assert not Branch.objects.filter(pk=spare.pk).exists()


class TestBranchImages:
    def upload(self, client, branch, kind, data, name='a.png', ctype='image/png'):
        return client.post(f'/360/api/branches/{branch.id}/images/{kind}/',
                           {'file': SimpleUploadedFile(name, data, content_type=ctype)})

    def test_valid_png_is_stored_and_can_be_removed(self, admin, chennai, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        res = self.upload(admin, chennai, 'payment_qr', png_bytes())
        assert res.status_code == 200 and res.json()['payment_qr_url'].endswith('.png')
        res = admin.delete(f'/360/api/branches/{chennai.id}/images/payment_qr/')
        assert res.status_code == 200 and res.json()['payment_qr_url'] == ''

    def test_non_image_content_is_rejected_even_with_image_name(self, admin, chennai, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        assert self.upload(admin, chennai, 'logo', b'<?php echo 1;', name='evil.png').status_code == 400

    def test_svg_is_rejected(self, admin, chennai, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        assert self.upload(admin, chennai, 'logo', svg, name='a.svg', ctype='image/svg+xml').status_code == 400

    def test_oversized_image_is_rejected(self, admin, chennai, settings, tmp_path, monkeypatch):
        settings.MEDIA_ROOT = tmp_path
        monkeypatch.setattr('threesixty.services.uploads.MAX_IMAGE_BYTES', 100)
        assert self.upload(admin, chennai, 'logo', png_bytes((64, 64))).status_code == 400

    def test_unknown_image_kind_404(self, admin, chennai):
        assert self.upload(admin, chennai, 'wallpaper', png_bytes()).status_code == 404


# ----------------------------------------------------------------------------- pick-lists
class TestPickLists:
    def test_REQ_LST_01_value_used_by_customers_is_hidden_not_deleted(self, admin):
        tamil = LookupItem.objects.create(kind='language', name='Tamil')
        customer = Customer.objects.create(name='Acme')
        customer.preferred_languages.add(tamil)
        res = admin.delete(f'/360/api/lookups/{tamil.id}/')
        assert res.json() == {'deleted': False, 'deactivated': True}
        assert list(customer.preferred_languages.values_list('name', flat=True)) == ['Tamil']
        assert 'Tamil' not in [i['name'] for i in admin.get('/360/api/bootstrap/').json()['lookups'].get('language', [])]

    def test_REQ_LST_01_unused_value_is_deleted_and_text_fields_untouched(self, admin):
        src = LookupItem.objects.create(kind='source', name='Referral')
        customer = Customer.objects.create(name='Acme', source='Referral')
        assert admin.delete(f'/360/api/lookups/{src.id}/').json()['deleted'] is True
        customer.refresh_from_db()
        assert customer.source == 'Referral'

    def test_adding_a_removed_value_again_reactivates_it(self, admin):
        tamil = LookupItem.objects.create(kind='language', name='Tamil', is_active=False)
        res = send(admin, 'post', '/360/api/lookups/', {'kind': 'language', 'name': 'Tamil'})
        assert res.status_code == 201 and res.json()['id'] == tamil.id and res.json()['is_active'] is True

    def test_adding_an_existing_active_value_is_rejected(self, admin):
        LookupItem.objects.create(kind='language', name='Tamil')
        assert send(admin, 'post', '/360/api/lookups/', {'kind': 'language', 'name': 'Tamil'}).status_code == 400

    def test_REQ_LST_01_removed_sales_person_keeps_name_on_documents(self, admin, chennai):
        person = SalesPerson.objects.create(name='Ravi Kumar')
        customer = Customer.objects.create(name='Acme')
        doc = SalesDocument.objects.create(type='quotation', doc_number='QUO-0001', branch=chennai, customer=customer,
                                           date='2026-01-01', sales_person=person)
        assert admin.delete(f'/360/api/sales-persons/{person.id}/').status_code == 200
        doc.refresh_from_db()
        assert doc.sales_person_id is None and doc.sales_person_name == 'Ravi Kumar'
        assert admin.get(f'/360/api/sales-documents/{doc.id}/').json()['sales_person_name'] == 'Ravi Kumar'

    def test_every_required_list_kind_exists(self):
        kinds = {k for k, _ in LookupItem.KIND_CHOICES}
        assert {'source', 'job_title', 'industry', 'brand', 'product', 'category', 'unit', 'tax_rate',
                'payment_term', 'language', 'transport', 'courier'} <= kinds


# ----------------------------------------------------------------------------- users
class TestUsers:
    def new_user(self, admin, **extra):
        data = {'username': 'newbie', 'password': 'abcdef', 'role': 'BRANCH_STAFF', 'full_name': 'New Bie'}
        data.update(extra)
        return send(admin, 'post', '/360/api/employees/', data)

    def test_created_user_password_is_hashed(self, admin, settings):
        settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.PBKDF2PasswordHasher']   # the production default
        assert self.new_user(admin).status_code == 201
        stored = User.objects.get(username='newbie').password
        assert stored != 'abcdef' and stored.startswith(('pbkdf2_', 'argon2', 'bcrypt', 'scrypt'))

    def test_REQ_USR_03_minimum_password_length_on_create_and_change(self, admin):
        assert self.new_user(admin, password='abc').status_code == 400
        emp = self.new_user(admin).json()
        assert send(admin, 'patch', f'/360/api/employees/{emp["id"]}/', {'new_password': 'abc'}).status_code == 400

    def test_work_hours_and_weekly_off_are_validated(self, admin):
        assert self.new_user(admin, work_start='9am').status_code == 400
        assert self.new_user(admin, work_start='10:00', work_end='09:00').status_code == 400
        assert self.new_user(admin, weekly_off='0,9').status_code == 400
        ok = self.new_user(admin, work_start='08:30', work_end='17:30', weekly_off='6, 0')
        assert ok.status_code == 201 and ok.json()['weekly_off'] == '0,6'

    def test_REQ_USR_01_inactive_user_cannot_sign_in(self, admin):
        emp = self.new_user(admin).json()
        assert send(admin, 'patch', f'/360/api/employees/{emp["id"]}/', {'is_active': False}).status_code == 200
        user = User.objects.get(username='newbie')
        assert user.is_active is False and user.threesixty_profile.is_active_employee is False
        res = Client().post('/360/login/', {'action': 'login', 'username': 'newbie', 'password': 'abcdef'})
        assert res.status_code == 200 and b'inactive' in res.content
        assert not Client().login(username='newbie', password='abcdef')

    def test_REQ_USR_01_reactivating_restores_sign_in(self, admin):
        emp = self.new_user(admin).json()
        send(admin, 'patch', f'/360/api/employees/{emp["id"]}/', {'is_active': False})
        send(admin, 'patch', f'/360/api/employees/{emp["id"]}/', {'is_active': True})
        res = Client().post('/360/login/', {'action': 'login', 'username': 'newbie', 'password': 'abcdef'})
        assert res.status_code == 302

    def test_REQ_USR_01_profile_marked_inactive_is_locked_out_of_an_open_session(self, chennai):
        make_employee('stale', EmployeeProfile.BRANCH_STAFF, [chennai])
        c = client_for('stale')
        assert c.get('/360/').status_code == 200
        EmployeeProfile.objects.filter(user__username='stale').update(is_active_employee=False)
        assert c.get('/360/').status_code == 403
        assert c.get('/360/api/me/').status_code == 403

    def test_REQ_USR_01_cannot_deactivate_yourself(self, admin):
        mine = EmployeeProfile.objects.get(user__username='admin1')
        res = send(admin, 'patch', f'/360/api/employees/{mine.id}/', {'is_active': False})
        assert res.status_code == 400 and 'own account' in res.json()['error']

    def test_REQ_USR_01_last_active_admin_is_protected(self, admin, chennai):
        make_employee('admin2', EmployeeProfile.ADMIN, [chennai])
        admin2 = EmployeeProfile.objects.get(user__username='admin2')
        c2 = client_for('admin2')
        mine = EmployeeProfile.objects.get(user__username='admin1')
        # admin2 deactivates admin1: allowed (admin2 stays active)
        assert send(c2, 'patch', f'/360/api/employees/{mine.id}/', {'is_active': False}).status_code == 200
        # admin2 is now the only active admin: cannot be demoted by another admin
        make_employee('admin3', EmployeeProfile.ADMIN, [chennai])
        EmployeeProfile.objects.filter(user__username='admin3').update(is_active_employee=False)
        res = send(c2, 'patch', f'/360/api/employees/{admin2.id}/', {'role': 'BRANCH_STAFF'})
        assert res.status_code == 400 and 'at least one active admin' in res.json()['error'].lower()

    def test_REQ_USR_01_only_admin_changes_status(self, chennai):
        make_employee('victim', EmployeeProfile.BRANCH_STAFF, [chennai])
        bm = role_client(EmployeeProfile.BRANCH_MANAGER, chennai)
        victim = EmployeeProfile.objects.get(user__username='victim')
        assert send(bm, 'patch', f'/360/api/employees/{victim.id}/', {'is_active': False}).status_code == 403

    def test_aadhaar_and_pan_are_masked_for_everyone_but_admin(self, admin, chennai):
        make_employee('hr', EmployeeProfile.BRANCH_STAFF, [chennai], aadhaar_number='123456789012', pan_number='ABCDE1234F')
        listing = admin.get('/360/api/employees/').json()['results']
        hr = next(e for e in listing if e['username'] == 'hr')
        assert hr['aadhaar_number'] == '123456789012'
        staff_view = role_client(EmployeeProfile.BRANCH_MANAGER, chennai).get('/360/api/employees/').json()['results']
        hr = next(e for e in staff_view if e['username'] == 'hr')
        assert hr['aadhaar_number'] == 'XXXXXXXX9012' and hr['pan_number'] == 'XXXXXX234F'


# ----------------------------------------------------------------------------- login & reset
class TestLoginAndReset:
    def reset(self, **fields):
        data = {'action': 'reset', 'username': 'staff1', 'new_password': 'brandnew1', 'confirm_password': 'brandnew1',
                'verifier_username': 'admin1', 'verifier_password': 'secret-pw-1'}
        data.update(fields)
        return Client().post('/360/login/', data)

    @pytest.fixture
    def setup(self, chennai):
        make_employee('admin1', EmployeeProfile.ADMIN, [chennai])
        make_employee('staff1', EmployeeProfile.BRANCH_STAFF, [chennai])

    def test_unauthenticated_visit_goes_to_360_login(self, client):
        res = client.get('/360/')
        assert res.status_code == 302 and res.url.startswith('/360/login/')

    def test_sign_in_and_out(self, setup):
        c = Client()
        res = c.post('/360/login/', {'action': 'login', 'username': 'staff1', 'password': 'secret-pw-1'})
        assert res.status_code == 302 and res.url == '/360/'
        assert c.get('/360/').status_code == 200
        assert c.get('/360/logout/').status_code == 302
        assert c.get('/360/').status_code == 302

    def test_wrong_password_shows_generic_error(self, setup):
        res = Client().post('/360/login/', {'action': 'login', 'username': 'staff1', 'password': 'nope'})
        assert res.status_code == 200 and b'Invalid user ID or password' in res.content

    def test_open_redirect_via_next_is_ignored(self, setup):
        res = Client().post('/360/login/', {'action': 'login', 'username': 'staff1', 'password': 'secret-pw-1',
                                            'next': 'https://evil.example/'})
        assert res.url == '/360/'

    def test_login_is_rate_limited_per_account(self, setup):
        c = Client()
        codes = [c.post('/360/login/', {'action': 'login', 'username': 'staff1', 'password': 'bad'}).status_code
                 for _ in range(12)]
        assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]

    def test_REQ_USR_03_another_admin_confirms_and_password_is_changed_and_hashed(self, setup):
        res = self.reset()
        assert res.status_code == 200 and b'Password changed' in res.content
        user = User.objects.get(username='staff1')
        assert user.check_password('brandnew1') and user.password != 'brandnew1'
        assert Client().login(username='staff1', password='brandnew1')

    def test_REQ_USR_03_wrong_verifier_password_is_refused(self, setup):
        res = self.reset(verifier_password='wrong')
        assert res.status_code == 403 and b"admin&#x27;s password is incorrect" in res.content
        assert not User.objects.get(username='staff1').check_password('brandnew1')

    def test_REQ_USR_03_verifier_must_be_an_admin_other_than_the_target(self, setup, chennai):
        make_employee('staff2', EmployeeProfile.BRANCH_STAFF, [chennai])
        assert self.reset(verifier_username='staff2').status_code == 403            # not an admin
        make_employee('admin2', EmployeeProfile.ADMIN, [chennai])
        assert self.reset(username='admin1', verifier_username='admin1').status_code == 403   # self-verification

    def test_REQ_USR_03_inactive_admin_cannot_verify(self, setup):
        EmployeeProfile.objects.filter(user__username='admin1').update(is_active_employee=False)
        assert self.reset().status_code == 403

    def test_REQ_USR_03_password_rules(self, setup):
        assert self.reset(new_password='abc', confirm_password='abc').status_code == 400
        res = self.reset(confirm_password='different')
        assert res.status_code == 400 and b"match" in res.content

    def test_REQ_USR_03_sole_admin_resets_without_a_verifier(self, chennai):
        make_employee('admin1', EmployeeProfile.ADMIN, [chennai])
        res = self.reset(username='admin1', verifier_username='', verifier_password='')
        assert res.status_code == 200 and b'Password changed' in res.content
        assert User.objects.get(username='admin1').check_password('brandnew1')

    def test_REQ_USR_03_unknown_user_gets_the_generic_refusal(self, setup):
        assert self.reset(username='ghost').status_code == 403

    def test_REQ_USR_03_reset_is_rate_limited(self, setup):
        codes = [self.reset(verifier_password='bad').status_code for _ in range(7)]
        assert codes[:5] == [403] * 5 and codes[5:] == [429, 429]

    def test_first_admin_form_only_while_no_admin_exists(self, chennai):
        c = Client()
        assert b'Create the first admin' in c.get('/360/login/').content
        res = c.post('/360/login/', {'action': 'first_admin', 'username': 'boss', 'password': 'bosspw1', 'full_name': 'The Boss'})
        assert res.status_code == 302 and res.url == '/360/'
        assert EmployeeProfile.objects.get(user__username='boss').role == EmployeeProfile.ADMIN
        res = Client().post('/360/login/', {'action': 'first_admin', 'username': 'intruder', 'password': 'intrude1'})
        assert res.status_code == 403 and not User.objects.filter(username='intruder').exists()
        assert b'Create the first admin' not in Client().get('/360/login/').content

    def test_first_admin_password_minimum(self):
        res = Client().post('/360/login/', {'action': 'first_admin', 'username': 'boss', 'password': 'abc'})
        assert res.status_code == 400 and not User.objects.filter(username='boss').exists()

    def test_dashboard_login_still_works_for_360_staff(self, setup):
        res = Client().post('/dashboard/login/', {'username': 'staff1', 'password': 'secret-pw-1'})
        assert res.status_code == 302 and res.url == '/360/'
