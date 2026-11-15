"""UX fixes (docs/360/UX_FIXES_PLAN.md): moving a document to another branch re-numbers it, the branch default terms are
served fresh, and an Enquiry can be assigned to employees (the assignment is a task on their Task tab)."""
import pytest
from django.core.cache import cache

from threesixty.models import Branch, SalesDocument, Task
from tests.helpers_360 import ADMIN, BM, BS, SM, call, client_for, make_customer, make_employee

pytestmark = pytest.mark.django_db
API = '/360/api/'


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def branches():
    return Branch.objects.create(name='Chennai', terms='Old one\nOld two'), Branch.objects.create(name='Bengaluru')


@pytest.fixture
def team(branches):
    chn, blr = branches
    return {'admin': make_employee('admin', ADMIN, [chn, blr]), 'bm': make_employee('bm', BM, [chn]), 'bs': make_employee('bs', BS, [chn]),
            'sm': make_employee('sm', SM, [chn, blr], full_name='Sally Sales'), 'bs2': make_employee('bs2', BS, [chn], full_name='Bee Two')}


def new_doc(client, branch, customer, doc_type='quotation', **extra):
    body = {'type': doc_type, 'branch_id': branch.id, 'customer_id': customer.id, 'date': '2026-10-01',
            'items': [{'item_name': 'A', 'qty': 1, 'rate': 10}]} if doc_type != 'enquiry' else {'type': doc_type, 'branch_id': branch.id, 'customer_id': customer.id, 'date': '2026-10-01'}
    body.update(extra)
    r = call(client, 'post', API + 'sales-documents/', body)
    assert r.status_code == 201, r.content
    return r.json()


class TestBranchChangeRenumbers:
    def test_moving_a_quotation_takes_the_next_number_of_the_new_branch(self, branches, team):
        chn, blr = branches
        customer, _ = make_customer('Acme', team['admin'])
        c = client_for(team['admin'])
        first = new_doc(c, chn, customer)
        other = new_doc(c, blr, customer)                       # Bengaluru's counter is now at 1
        r = call(c, 'patch', f"{API}sales-documents/{first['id']}/", {'branch_id': blr.id, 'doc_number': first['doc_number'], 'version': first['version']})
        assert r.status_code == 200, r.content
        moved = r.json()
        assert moved['branch_id'] == blr.id
        assert moved['doc_number'] != first['doc_number'] and moved['doc_number'] != other['doc_number']
        nxt = call(c, 'get', f'{API}sales-documents/next-number/?type=quotation&branch_id={blr.id}').json()['number']
        assert nxt != moved['doc_number']                         # the counter moved on: nobody else gets that number

    def test_a_typed_number_is_kept(self, branches, team):
        chn, blr = branches
        customer, _ = make_customer('Acme', team['admin'])
        c = client_for(team['admin'])
        first = new_doc(c, chn, customer)
        r = call(c, 'patch', f"{API}sales-documents/{first['id']}/", {'branch_id': blr.id, 'doc_number': 'QUO-0099', 'version': first['version']})
        assert r.json()['doc_number'] == 'QUO-0099'

    def test_same_branch_keeps_the_number(self, branches, team):
        chn, _ = branches
        customer, _ = make_customer('Acme', team['admin'])
        c = client_for(team['admin'])
        first = new_doc(c, chn, customer)
        r = call(c, 'patch', f"{API}sales-documents/{first['id']}/", {'branch_id': chn.id, 'doc_number': first['doc_number'], 'version': first['version']})
        assert r.json()['doc_number'] == first['doc_number']

    def test_delivery_challan_cannot_move(self, branches, team):
        chn, blr = branches
        customer, _ = make_customer('Acme', team['admin'])
        c = client_for(team['admin'])
        dc = new_doc(c, chn, customer, 'dc')
        r = call(c, 'patch', f"{API}sales-documents/{dc['id']}/", {'branch_id': blr.id, 'version': dc['version']})
        assert r.status_code == 400
        assert SalesDocument.objects.get(pk=dc['id']).branch_id == chn.id

    def test_unknown_branch_is_refused(self, branches, team):
        chn, _ = branches
        customer, _ = make_customer('Acme', team['admin'])
        c = client_for(team['admin'])
        first = new_doc(c, chn, customer)
        assert call(c, 'patch', f"{API}sales-documents/{first['id']}/", {'branch_id': 9999, 'version': first['version']}).status_code == 400

    def test_a_sales_managers_move_waits_for_approval_then_renumbers(self, branches, team):
        chn, blr = branches
        customer, _ = make_customer('Acme', team['admin'])
        customer.assigned_to.add(team['sm'])
        sm, admin = client_for(team['sm']), client_for(team['admin'])
        doc = new_doc(sm, chn, customer)
        new_doc(admin, blr, customer)                           # Bengaluru already has its QUO-0001
        r = call(sm, 'patch', f"{API}sales-documents/{doc['id']}/", {'branch_id': blr.id, 'doc_number': doc['doc_number'], 'version': doc['version']})
        assert r.status_code == 202
        assert SalesDocument.objects.get(pk=doc['id']).branch_id == chn.id            # nothing moves until it is approved
        approval_id = r.json()['approval']['id']
        assert call(admin, 'post', f'{API}approvals/{approval_id}/approve/').status_code == 200
        moved = SalesDocument.objects.get(pk=doc['id'])
        assert moved.branch_id == blr.id and moved.doc_number != doc['doc_number']


class TestBranchDefaultTerms:
    def test_admin_saving_as_default_is_served_to_the_next_document(self, branches, team):
        chn, _ = branches
        customer, _ = make_customer('Acme', team['admin'])
        c = client_for(team['admin'])
        new_doc(c, chn, customer, terms=['Fresh term 1', 'Fresh term 2'], save_terms_as_default=True)
        got = call(c, 'get', f'{API}sales-documents/next-number/?type=quotation&branch_id={chn.id}').json()
        assert got['terms'] == ['Fresh term 1', 'Fresh term 2']
        chn.refresh_from_db()
        assert chn.terms == 'Fresh term 1\nFresh term 2'

    def test_editing_a_document_can_save_the_default_too(self, branches, team):
        chn, _ = branches
        customer, _ = make_customer('Acme', team['admin'])
        c = client_for(team['admin'])
        doc = new_doc(c, chn, customer)
        call(c, 'patch', f"{API}sales-documents/{doc['id']}/", {'terms': ['Edited'], 'save_terms_as_default': True, 'version': doc['version']})
        chn.refresh_from_db()
        assert chn.terms == 'Edited'


class TestAssignEnquiry:
    def make(self, branches, team):
        chn, _ = branches
        customer, _ = make_customer('Acme', team['admin'])
        return client_for(team['admin']), new_doc(client_for(team['admin']), chn, customer, 'enquiry')

    def test_assigning_creates_a_task_on_each_assignees_task_tab(self, branches, team):
        admin, enq = self.make(branches, team)
        r = call(admin, 'post', f"{API}sales-documents/{enq['id']}/assign/", {'assignee_ids': [team['bs'].id, team['bs2'].id], 'due_date': '2026-11-20'})
        assert r.status_code == 200, r.content
        body = r.json()
        assert [a['id'] for a in body['assignees']] == [team['bs'].id, team['bs2'].id]
        assert body['assignment_task_id']
        for who in ('bs', 'bs2'):
            mine = call(client_for(team[who]), 'get', f'{API}tasks/?scope=mine').json()['results']
            assert len(mine) == 1 and mine[0]['related_document']['id'] == enq['id'] and mine[0]['due_date'] == '2026-11-20'
            assert enq['doc_number'] in mine[0]['title']

    def test_assignees_are_told(self, branches, team):
        admin, enq = self.make(branches, team)
        call(admin, 'post', f"{API}sales-documents/{enq['id']}/assign/", {'assignee_ids': [team['bs'].id]})
        notes = call(client_for(team['bs']), 'get', f'{API}notifications/').json()['results']
        assert any(enq['doc_number'] in n['text'] for n in notes)

    def test_reassigning_changes_people_without_a_second_task(self, branches, team):
        admin, enq = self.make(branches, team)
        call(admin, 'post', f"{API}sales-documents/{enq['id']}/assign/", {'assignee_ids': [team['bs'].id]})
        r = call(admin, 'post', f"{API}sales-documents/{enq['id']}/assign/", {'assignee_ids': [team['bs2'].id]})
        assert [a['id'] for a in r.json()['assignees']] == [team['bs2'].id]
        assert Task.objects.filter(related_document_id=enq['id'], task_type='Enquiry').count() == 1
        assert call(client_for(team['bs']), 'get', f'{API}tasks/?scope=mine').json()['results'] == []

    def test_an_empty_list_takes_the_assignment_back(self, branches, team):
        admin, enq = self.make(branches, team)
        call(admin, 'post', f"{API}sales-documents/{enq['id']}/assign/", {'assignee_ids': [team['bs'].id]})
        r = call(admin, 'post', f"{API}sales-documents/{enq['id']}/assign/", {'assignee_ids': []})
        assert r.json()['assignees'] == [] and not Task.objects.filter(related_document_id=enq['id']).exists()

    def test_the_list_shows_who_an_enquiry_is_assigned_to(self, branches, team):
        admin, enq = self.make(branches, team)
        call(admin, 'post', f"{API}sales-documents/{enq['id']}/assign/", {'assignee_ids': [team['bs'].id]})
        rows = call(admin, 'get', f'{API}sales-documents/?type=enquiry').json()['results']
        assert rows[0]['assignees'][0]['id'] == team['bs'].id

    def test_only_enquiries_can_be_assigned(self, branches, team):
        chn, _ = branches
        customer, _ = make_customer('Acme', team['admin'])
        admin = client_for(team['admin'])
        quo = new_doc(admin, chn, customer)
        assert call(admin, 'post', f"{API}sales-documents/{quo['id']}/assign/", {'assignee_ids': [team['bs'].id]}).status_code == 400

    def test_branch_staff_who_did_not_raise_it_cannot_assign(self, branches, team):
        admin, enq = self.make(branches, team)
        assert call(client_for(team['bs']), 'post', f"{API}sales-documents/{enq['id']}/assign/", {'assignee_ids': [team['bs2'].id]}).status_code == 403

    def test_the_person_who_raised_it_can_assign_it(self, branches, team):
        chn, _ = branches
        customer, _ = make_customer('Acme', team['admin'])
        bs = client_for(team['bs'])
        enq = new_doc(bs, chn, customer, 'enquiry')
        assert call(bs, 'post', f"{API}sales-documents/{enq['id']}/assign/", {'assignee_ids': [team['bs2'].id]}).status_code == 200

    def test_unknown_or_inactive_people_are_refused(self, branches, team):
        admin, enq = self.make(branches, team)
        assert call(admin, 'post', f"{API}sales-documents/{enq['id']}/assign/", {'assignee_ids': [999999]}).status_code == 400


class TestChangeQuotationCustomer:
    def test_a_quotations_customer_and_contact_can_be_corrected(self, branches, team):
        chn, _ = branches
        old, oc = make_customer('Old Co', team['admin'])
        new, nc = make_customer('New Co', team['admin'])
        c = client_for(team['admin'])
        quo = new_doc(c, chn, old, contact_id=oc[0].id)
        task = Task.objects.create(title='Call', assigned_to=team['admin'], related_document_id=quo['id'], related_customer=old, related_contact=oc[0])
        r = call(c, 'patch', f"{API}sales-documents/{quo['id']}/", {'customer_id': new.id, 'contact_id': nc[1].id, 'version': quo['version']})
        assert r.status_code == 200, r.content
        body = r.json()
        assert body['customer_id'] == new.id and body['contact_id'] == nc[1].id and body['doc_number'] == quo['doc_number']
        task.refresh_from_db()
        assert task.related_customer_id == new.id and task.related_contact_id is None

    def test_a_contact_of_the_old_customer_is_refused(self, branches, team):
        chn, _ = branches
        old, oc = make_customer('Old Co', team['admin'])
        new, _ = make_customer('New Co', team['admin'])
        c = client_for(team['admin'])
        quo = new_doc(c, chn, old)
        r = call(c, 'patch', f"{API}sales-documents/{quo['id']}/", {'customer_id': new.id, 'contact_id': oc[0].id, 'version': quo['version']})
        assert r.status_code in (400, 404)
        assert SalesDocument.objects.get(pk=quo['id']).customer_id == old.id

    def test_no_contact_sent_clears_the_old_one(self, branches, team):
        chn, _ = branches
        old, oc = make_customer('Old Co', team['admin'])
        new, _ = make_customer('New Co', team['admin'])
        c = client_for(team['admin'])
        quo = new_doc(c, chn, old, contact_id=oc[0].id)
        r = call(c, 'patch', f"{API}sales-documents/{quo['id']}/", {'customer_id': new.id, 'version': quo['version']})
        assert r.json()['customer_id'] == new.id and r.json()['contact_id'] is None

    def test_a_customer_the_person_cannot_see_is_refused(self, branches, team):
        chn, _ = branches
        mine, _ = make_customer('Mine', team['admin'])
        hidden, _ = make_customer('Hidden', team['admin'])
        mine.assigned_to.add(team['sm'])
        sm, admin = client_for(team['sm']), client_for(team['admin'])
        quo = new_doc(sm, chn, mine)
        r = call(admin, 'patch', f"{API}sales-documents/{quo['id']}/", {'customer_id': 999999, 'version': quo['version']})
        assert r.status_code == 400

    def test_other_document_types_still_keep_their_customer(self, branches, team):
        chn, _ = branches
        old, _ = make_customer('Old Co', team['admin'])
        new, _ = make_customer('New Co', team['admin'])
        c = client_for(team['admin'])
        enq = new_doc(c, chn, old, 'enquiry')
        assert call(c, 'patch', f"{API}sales-documents/{enq['id']}/", {'customer_id': new.id, 'version': enq['version']}).status_code == 400

    def test_a_sales_managers_customer_change_waits_for_approval(self, branches, team):
        chn, _ = branches
        old, _ = make_customer('Old Co', team['admin'])
        new, _ = make_customer('New Co', team['admin'])
        old.assigned_to.add(team['sm']); new.assigned_to.add(team['sm'])
        sm, admin = client_for(team['sm']), client_for(team['admin'])
        quo = new_doc(sm, chn, old)
        r = call(sm, 'patch', f"{API}sales-documents/{quo['id']}/", {'customer_id': new.id, 'version': quo['version']})
        assert r.status_code == 202
        assert SalesDocument.objects.get(pk=quo['id']).customer_id == old.id
        assert call(admin, 'post', f"{API}approvals/{r.json()['approval']['id']}/approve/").status_code == 200
        assert SalesDocument.objects.get(pk=quo['id']).customer_id == new.id
