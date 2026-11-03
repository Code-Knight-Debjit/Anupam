"""Admin-page parity with the reference app: payment display fields, transporter / courier details, tax-rate lists,
the Backup page's figures, and the Users form's rules (docs/360/PARITY_TESTS.md P-*, ML-*, B-*, U-*)."""
from datetime import date, timedelta

import pytest
from django.core.cache import cache

from threesixty.models import Branch, LookupItem, PaymentCollection
from tests.helpers_360 import ADMIN, BM, BS, call, client_for, make_customer, make_employee

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def team():
    chennai = Branch.objects.create(name='Chennai')
    return {'admin': make_employee('admin', ADMIN, [chennai], full_name='Sanjeev'), 'chennai': chennai}


class TestPaymentDisplayFields:
    def test_a_payment_carries_the_names_and_phone_the_list_shows(self, team):
        customer, (contact, *_) = make_customer('Sundaram', team['admin'], plant='Plant 3', contacts=('Ravi',))
        contact.phone = '9000000001'
        contact.save()
        PaymentCollection.objects.create(branch=team['chennai'], customer=customer, contact=contact, amount=500, created_by=team['admin'], date=date.today())
        row = call(client_for(team['admin']), 'get', '/360/api/payment-collections/').json()['results'][0]
        assert row['customer_name'] == 'Sundaram — Plant 3' and row['branch_name'] == 'Chennai'
        assert row['contact_name'] == 'Ravi' and row['contact_phone'] == '9000000001'


class TestLists:
    def test_a_transporter_keeps_its_contact_details(self, team):
        client = client_for(team['admin'])
        res = call(client, 'post', '/360/api/lookups/', {'kind': 'transport', 'name': 'Sri Balaji', 'details': {'phone': '044 1', 'mobile': '9', 'gst': 'X', 'location': 'Peenya', 'address': 'St', 'junk': 'no'}})
        assert res.status_code == 201 and res.json()['details'] == {'phone': '044 1', 'mobile': '9', 'gst': 'X', 'location': 'Peenya', 'address': 'St'}
        item = LookupItem.objects.get(name='Sri Balaji')
        edited = call(client, 'patch', f'/360/api/lookups/{item.pk}/', {'name': 'Sri Balaji 2', 'details': {'phone': '1'}}).json()
        assert edited['name'] == 'Sri Balaji 2' and edited['details'] == {'phone': '1'}

    def test_a_tax_rate_must_be_a_number(self, team):
        client = client_for(team['admin'])
        assert call(client, 'post', '/360/api/lookups/', {'kind': 'tax_rate', 'name': 'abc'}).status_code == 400
        assert call(client, 'post', '/360/api/lookups/', {'kind': 'tax_rate', 'name': '7.5'}).status_code == 201
        item = LookupItem.objects.get(kind='tax_rate', name='7.5')
        assert call(client, 'patch', f'/360/api/lookups/{item.pk}/', {'name': 'x'}).status_code == 400

    def test_a_duplicate_entry_is_refused(self, team):
        client = client_for(team['admin'])
        assert call(client, 'post', '/360/api/lookups/', {'kind': 'brand', 'name': 'SKF'}).status_code == 201
        assert call(client, 'post', '/360/api/lookups/', {'kind': 'brand', 'name': 'SKF'}).status_code == 400


class TestBackupPage:
    def test_summary_counts_the_data_and_remembers_the_last_download(self, team):
        make_customer('A', team['admin'])
        client = client_for(team['admin'])
        first = call(client, 'get', '/360/api/backup/summary/').json()
        assert first['counts']['customers'] == 1 and first['counts']['users'] == 1 and first['last_backup_at'] is None
        assert call(client, 'get', '/360/api/backup/export/').status_code == 200
        assert call(client, 'get', '/360/api/backup/summary/').json()['last_backup_at']

    def test_describe_quotes_the_figures_of_a_file(self, team):
        make_customer('A', team['admin'])
        client = client_for(team['admin'])
        raw = call(client, 'get', '/360/api/backup/export/').content
        from django.core.files.uploadedfile import SimpleUploadedFile
        res = client.post('/360/api/backup/describe/', {'file': SimpleUploadedFile('b.json', raw)})
        assert res.status_code == 200 and res.json()['counts']['customers'] == 1

    def test_only_an_admin_may_see_it(self, team):
        bm = make_employee('bm', BM, [team['chennai']])
        assert call(client_for(bm), 'get', '/360/api/backup/summary/').status_code == 403


class TestUsersFormRules:
    def make(self, team, **extra):
        body = {'username': 'newbie', 'password': 'Zx9!kLm2pQ', 'role': BS, 'full_name': 'New Bie', 'branch_ids': [team['chennai'].pk]} | extra
        return call(client_for(team['admin']), 'post', '/360/api/employees/', body)

    def test_a_valid_person_is_created_with_an_email(self, team):
        res = self.make(team, email='n@example.com', phone='9876543210', aadhaar_number='1234 1234 1234', pan_number='abcde1234f')
        assert res.status_code == 201
        body = res.json()
        assert body['email'] == 'n@example.com' and body['aadhaar_number'] == '123412341234' and body['pan_number'] == 'ABCDE1234F'

    @pytest.mark.parametrize('extra, text', [
        ({'phone': '123'}, 'phone'), ({'email': 'nope'}, 'email'), ({'aadhaar_number': '12345'}, 'Aadhaar'), ({'pan_number': 'ABC'}, 'PAN'),
        ({'date_of_birth': (date.today() + timedelta(days=5)).isoformat()}, 'future'), ({'date_of_birth': '2000-01-01', 'date_of_joining': '1999-01-01'}, 'before the date of birth'),
        ({'branch_ids': []}, 'branch'),
    ])
    def test_the_reference_rules_hold_on_the_server(self, team, extra, text):
        res = self.make(team, **extra)
        assert res.status_code == 400 and text.lower() in res.json()['error'].lower()

    def test_aadhaar_and_pan_are_not_shared_and_the_user_id_is_not_case_sensitive(self, team):
        assert self.make(team, aadhaar_number='123412341234', pan_number='ABCDE1234F').status_code == 201
        assert 'Aadhaar' in self.make(team, username='other', aadhaar_number='123412341234').json()['error']
        assert 'PAN' in self.make(team, username='other', pan_number='ABCDE1234F').json()['error']
        assert 'User ID' in self.make(team, username='NEWBIE').json()['error']

    def test_the_user_id_can_be_changed_but_not_to_one_in_use(self, team):
        pk = self.make(team).json()['id']
        make_employee('taken', BS, [team['chennai']])
        client = client_for(team['admin'])
        assert call(client, 'patch', f'/360/api/employees/{pk}/', {'username': 'Taken'}).status_code == 400
        res = call(client, 'patch', f'/360/api/employees/{pk}/', {'username': 'renamed', 'email': 'r@example.com'})
        assert res.status_code == 200 and res.json()['username'] == 'renamed' and res.json()['email'] == 'r@example.com'


def _png(color=(200, 30, 30)):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (60, 20), color).save(buf, 'PNG')
    return buf.getvalue()


class TestBranding:
    def test_an_admin_sets_and_resets_the_app_and_sidebar_logos(self, team, settings, tmp_path):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from threesixty.services import branding
        settings.MEDIA_ROOT = str(tmp_path)
        client = client_for(team['admin'])
        assert branding.info('app') is None
        res = client.post('/360/api/branding/app/', {'file': SimpleUploadedFile('l.png', _png(), 'image/png'), 'aspect': '3'})
        assert res.status_code == 200 and res.json()['aspect'] == 3.0 and res.json()['url']
        assert branding.info('app')['path'].endswith('.png') and branding.info('sidebar') is None
        boot = call(client, 'get', '/360/api/bootstrap/').json()['site_settings']
        assert boot['appLogo']['url'] and 'sidebarLogo' not in boot
        assert call(client, 'delete', '/360/api/branding/app/').status_code == 200
        assert branding.info('app') is None

    def test_a_bad_file_or_a_non_admin_is_refused(self, team, settings, tmp_path):
        from django.core.files.uploadedfile import SimpleUploadedFile
        settings.MEDIA_ROOT = str(tmp_path)
        assert client_for(team['admin']).post('/360/api/branding/app/', {'file': SimpleUploadedFile('x.png', b'not an image', 'image/png')}).status_code == 400
        assert client_for(team['admin']).post('/360/api/branding/other/', {'file': SimpleUploadedFile('l.png', _png(), 'image/png')}).status_code == 404
        bm = make_employee('bm', BM, [team['chennai']])
        assert client_for(bm).post('/360/api/branding/app/', {'file': SimpleUploadedFile('l.png', _png(), 'image/png')}).status_code == 403

    def test_the_chosen_app_logo_is_the_default_letterhead_logo(self, team, settings, tmp_path):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from threesixty.services import branding, pdf_documents
        settings.MEDIA_ROOT = str(tmp_path)
        before = pdf_documents._default_logo_path()
        branding.set_logo('app', SimpleUploadedFile('l.png', _png(), 'image/png'))
        assert pdf_documents._default_logo_path() != before and str(tmp_path) in pdf_documents._default_logo_path()


class TestDefaultTaxRate:
    def test_the_admin_picks_a_default_from_the_tax_list(self, team):
        client = client_for(team['admin'])
        for rate in ('5', '12'):
            call(client, 'post', '/360/api/lookups/', {'kind': 'tax_rate', 'name': rate})
        assert call(client, 'post', '/360/api/lookups/default-tax/', {'rate': '12'}).json() == {'rate': '12'}
        assert call(client, 'get', '/360/api/bootstrap/').json()['site_settings']['defaultTaxRate'] == {'rate': '12'}
        assert call(client, 'post', '/360/api/lookups/default-tax/', {'rate': '99'}).status_code == 400

    def test_only_an_admin_may_change_it(self, team):
        bm = make_employee('bm', BM, [team['chennai']])
        assert call(client_for(bm), 'post', '/360/api/lookups/default-tax/', {'rate': '5'}).status_code == 403
