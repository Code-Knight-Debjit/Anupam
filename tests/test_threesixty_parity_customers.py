"""Customer parity with the reference: contacts are saved together with the customer, the list is one "cards" payload,
and a Sales Manager's edit (contacts included) waits for approval (docs/360/PARITY_TESTS.md C-07..C-09)."""
from datetime import date

import pytest
from django.core.cache import cache

from threesixty.models import Branch, Contact, ContactAccess, Customer, Interaction, LookupItem
from tests.helpers_360 import ADMIN, BM, BS, SM, call, client_for, make_customer, make_employee

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def team():
    chennai = Branch.objects.create(name='Chennai')
    return {'admin': make_employee('admin', ADMIN, [chennai], full_name='Sanjeev'),
            'bs': make_employee('bs', BS, [chennai], full_name='Staff'),
            'sm': make_employee('sm', SM, [chennai], full_name='Devdutt')}


def create(user, **extra):
    body = {'name': 'Sun Steels', 'contacts': [
        {'name': 'Ravi', 'job_title': 'Purchase', 'phone': '9840011111', 'email': 'ravi@x.com'},
        {'name': '', 'phone': '', 'phone2': '', 'email': ''},                  # blank row is ignored
        {'name': 'Meena', 'job_title': 'GM', 'phone2': '9840022222'}], **extra}
    return call(client_for(user), 'post', '/360/api/customers/', body)


class TestContactsWithTheCustomer:
    def test_create_saves_the_rows_and_ignores_blank_ones(self, team):
        res = create(team['admin'])
        assert res.status_code == 201
        assert list(Contact.objects.order_by('id').values_list('name', flat=True)) == ['Ravi', 'Meena']

    def test_update_changes_adds_and_removes_contacts(self, team):
        cid = create(team['admin']).json()['id']
        ravi, meena = Contact.objects.order_by('id')
        version = Customer.objects.get(pk=cid).version
        rows = [{'id': ravi.pk, 'name': 'Ravi Shankar', 'job_title': 'Purchase', 'phone': '9840011111'}, {'name': 'Joe', 'job_title': 'Stores', 'phone': '9840033333'}]
        res = call(client_for(team['admin']), 'patch', f'/360/api/customers/{cid}/', {'contacts': rows, 'version': version})
        assert res.status_code == 200
        assert sorted(Contact.objects.values_list('name', flat=True)) == ['Joe', 'Ravi Shankar']
        assert not Contact.objects.filter(pk=meena.pk).exists()

    def test_interactions_survive_when_the_contact_row_keeps_its_id(self, team):
        cid = create(team['admin']).json()['id']
        ravi = Contact.objects.get(name='Ravi')
        Interaction.objects.create(contact=ravi, type='Call', date=date(2026, 10, 1), created_by=team['admin'])
        version = Customer.objects.get(pk=cid).version
        call(client_for(team['admin']), 'patch', f'/360/api/customers/{cid}/', {'contacts': [{'id': ravi.pk, 'name': 'Ravi', 'phone': '1'}], 'version': version})
        assert ravi.interactions.count() == 1

    def test_contacts_hidden_from_the_editor_are_left_alone(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'], contacts=('A', 'B'))
        ContactAccess.objects.create(customer=customer, user=team['sm'], contact=contacts[0])
        customer.assigned_to.add(team['sm'])
        from threesixty.services import customers as customer_service
        customer_service.apply_contacts(customer, [{'id': contacts[0].pk, 'name': 'A2', 'phone': '1'}], team['sm'])
        assert sorted(Contact.objects.values_list('name', flat=True)) == ['A2', 'B']

    def test_wa_email_only_is_a_valid_potential(self, team):
        assert create(team['admin'], potential='WhatsApp/Email Only').status_code == 201

    def test_a_sales_managers_edit_waits_and_applies_contacts_on_approval(self, team):
        cid = create(team['sm']).json()['id']
        meena = Contact.objects.get(name='Meena')
        version = Customer.objects.get(pk=cid).version
        res = call(client_for(team['sm']), 'patch', f'/360/api/customers/{cid}/', {'city': 'Salem', 'contacts': [{'id': meena.pk, 'name': 'Meena Iyer', 'job_title': 'GM'}], 'version': version})
        assert res.status_code == 202
        assert Customer.objects.get(pk=cid).city == '' and Contact.objects.filter(name='Ravi').exists()      # nothing applied yet
        approval_id = res.json()['approval']['id']
        assert call(client_for(team['admin']), 'post', f'/360/api/approvals/{approval_id}/approve/', {}).status_code == 200
        assert Customer.objects.get(pk=cid).city == 'Salem'
        assert list(Contact.objects.values_list('name', flat=True)) == ['Meena Iyer']


class TestCards:
    def test_one_call_with_names_contacts_and_last_dates(self, team):
        lang = LookupItem.objects.create(kind=LookupItem.KIND_LANGUAGE, name='Tamil')
        cid = create(team['admin'], preferred_language_ids=[lang.pk], potential='High').json()['id']
        ravi = Contact.objects.get(name='Ravi')
        Interaction.objects.create(contact=ravi, type='Call', date=date(2026, 10, 1), created_by=team['admin'])
        Interaction.objects.create(contact=ravi, type='Visit', date=date(2026, 10, 5), created_by=team['admin'])
        card = call(client_for(team['admin']), 'get', '/360/api/customers/cards/').json()['results'][0]
        assert card['id'] == cid and card['preferred_languages'] == ['Tamil'] and card['created_by_name'] == 'Sanjeev'
        assert [c['name'] for c in card['contacts']] == ['Ravi', 'Meena']
        assert (card['last_call'], card['last_visit']) == ('2026-10-01', '2026-10-05') and card['pending_approval'] is False

    def test_a_sales_manager_only_gets_their_own_customers_and_visible_contacts(self, team):
        create(team['admin'], name='Not Mine')
        mine, contacts = make_customer('Mine', team['sm'], contacts=('A', 'B'))
        results = call(client_for(team['sm']), 'get', '/360/api/customers/cards/').json()['results']
        assert [r['name'] for r in results] == ['Mine'] and len(results[0]['contacts']) == 2

    def test_pending_requests_are_flagged(self, team):
        cid = create(team['admin']).json()['id']
        customer = Customer.objects.get(pk=cid)
        customer.assigned_to.add(team['sm'])
        call(client_for(team['sm']), 'patch', f'/360/api/customers/{cid}/', {'city': 'X', 'version': customer.version})
        card = call(client_for(team['admin']), 'get', '/360/api/customers/cards/').json()['results'][0]
        assert card['pending_approval'] is True


class TestProfile:
    def test_history_merges_interactions_doc_calls_and_outreach_attempts(self, team):
        from threesixty.models import CallAssignment, CallAttempt, DocumentCallLog, SalesDocument
        customer, contacts = make_customer('Sun Steels', team['admin'], contacts=('Ravi', 'Meena'))
        ravi, meena = contacts
        Interaction.objects.create(contact=ravi, type='Visit', date=date(2026, 10, 5), notes='demo', created_by=team['admin'])
        branch = Branch.objects.get()
        doc = SalesDocument.objects.create(type='quotation', doc_number='QUO-1', branch=branch, customer=customer, contact=ravi, date=date(2026, 10, 3), created_by=team['admin'])
        DocumentCallLog.objects.create(document=doc, message='Call not connecting', user=team['admin'])
        assignment = CallAssignment.objects.create(customer=customer, contact=ravi, week_of=date(2026, 10, 26), assigned_to=team['admin'])
        CallAttempt.objects.create(assignment=assignment, reason='Busy', by=team['admin'])
        body = call(client_for(team['admin']), 'get', f'/360/api/contacts/{ravi.pk}/profile/').json()
        assert sorted(h['type'] for h in body['history']) == ['Call', 'Call', 'Visit']
        assert any(h.get('via') == 'Sales panel contact log' and h['doc']['number'] == 'QUO-1' for h in body['history'])
        assert any(h['notes'] == 'Not answered (Busy)' for h in body['history'])
        assert [d['number'] for d in body['documents']] == ['QUO-1'] and [d['number'] for d in body['linkable']] == ['QUO-1']
        assert call(client_for(team['admin']), 'get', f'/360/api/contacts/{meena.pk}/profile/').json()['history'] == []

    def test_transactions(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'])
        body = call(client_for(team['admin']), 'get', f'/360/api/customers/{customer.pk}/transactions/').json()
        assert set(body) == {'enquiry', 'quotation', 'proforma', 'payments'}


class TestSalesFormSupport:
    def _doc(self, team):
        from threesixty.models import SalesDocument
        customer, contacts = make_customer('Sun Steels', team['admin'])
        branch = Branch.objects.get()
        return branch, call(client_for(team['admin']), 'post', '/360/api/sales-documents/',
                            {'type': 'enquiry', 'branch_id': branch.pk, 'customer_id': customer.pk, 'date': '2026-11-01'}).json()

    def test_next_number_preview_and_retyping_the_number_on_edit(self, team):
        branch, doc = self._doc(team)
        preview = call(client_for(team['bs']), 'get', f'/360/api/sales-documents/next-number/?type=enquiry&branch_id={branch.pk}').json()
        assert preview['number'] == 'ENQ-0002'
        res = call(client_for(team['admin']), 'patch', f"/360/api/sales-documents/{doc['id']}/", {'doc_number': 'ENQ-0010', 'version': doc['version']})
        assert res.json()['doc_number'] == 'ENQ-0010'
        assert call(client_for(team['admin']), 'get', f'/360/api/sales-documents/next-number/?type=enquiry&branch_id={branch.pk}').json()['number'] == 'ENQ-0011'
        assert call(client_for(team['admin']), 'get', '/360/api/sales-documents/next-number/?type=bogus&branch_id=1').status_code == 400
