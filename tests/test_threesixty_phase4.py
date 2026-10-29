"""Phase 4 (Sales documents) — validation, numbering, Win/Lose, PO supply, challan
invoicing, stock-OUT, contact log, clone, approvals, visibility."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone

from threesixty.models import (
    ApprovalRequest, Branch, BranchNumbering, ContactAccess, Notification, SalesDocument, StockTransaction, Task,
)
from threesixty.rules import anupam_rules as R
from threesixty.services import contacts as contact_service
from tests.helpers_360 import ADMIN, BM, BS, SM, call, client_for, make_customer, make_employee

pytestmark = pytest.mark.django_db


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
def team(chennai):
    return {
        'admin': make_employee('admin', ADMIN, [chennai], full_name='Sanjeev'),
        'bm': make_employee('bm', BM, [chennai]),
        'bs': make_employee('bs', BS, [chennai]),
        'sm': make_employee('sm', SM, [chennai], full_name='Devdutt'),
        'sm2': make_employee('sm2', SM, [chennai]),
    }


@pytest.fixture
def cust(team):
    customer, contacts = make_customer('Sun Steels', team['admin'], area='Ambattur')
    customer.assigned_to.add(team['sm'])
    return customer, contacts


ITEM = {'item_name': '6205 ZZ', 'make': 'SKF', 'qty': 10, 'unit': 'Nos', 'rate': '100', 'discount': '10', 'tax': '18'}


def payload(doc_type, customer, branch, **extra):
    data = {'type': doc_type, 'branch_id': branch.id, 'customer_id': customer.id, 'date': '2026-10-01'}
    if doc_type != 'enquiry':
        data['items'] = [dict(ITEM)]
    data.update(extra)
    return data


def create(user, doc_type, customer, branch, **extra):
    return call(client_for(user), 'post', '/360/api/sales-documents/', payload(doc_type, customer, branch, **extra))


def make_doc(user, doc_type, customer, branch, **extra):
    res = create(user, doc_type, customer, branch, **extra)
    assert res.status_code == 201, res.content
    return res.json()


# ----------------------------------------------------------------------------- validation & access
class TestValidationAndAccess:
    def test_REQ_DOC_06_customer_branch_and_items_are_required(self, team, cust, chennai):
        admin = client_for(team['admin'])
        url = '/360/api/sales-documents/'
        base = payload('quotation', cust[0], chennai)
        assert call(admin, 'post', url, {**base, 'customer_id': ''}).json()['error'] == 'Select a customer first.'
        assert call(admin, 'post', url, {**base, 'branch_id': ''}).json()['error'] == 'Select a branch first.'
        assert call(admin, 'post', url, {**base, 'items': []}).json()['error'] == 'Add at least one item.'
        assert call(admin, 'post', url, {**base, 'items': [{'item_name': '', 'qty': 0}]}).json()['error'] == 'Add at least one item.'
        assert call(admin, 'post', url, payload('enquiry', cust[0], chennai)).status_code == 201     # enquiries have no items
        doc = call(admin, 'post', url, {**base, 'items': [dict(ITEM), {'item_name': '', 'qty': 0}]}).json()
        assert len(doc['items']) == 1                                                             # blank rows dropped

    def test_item_numbers_are_checked(self, team, cust, chennai):
        for bad in ({'qty': -1}, {'rate': -5}, {'discount': 120}, {'tax': 'abc'}):
            res = create(team['admin'], 'quotation', cust[0], chennai, items=[{**ITEM, **bad}])
            assert res.status_code == 400, bad

    def test_sales_manager_can_only_raise_enquiry_and_quotation(self, team, cust, chennai):
        assert create(team['sm'], 'enquiry', cust[0], chennai).status_code == 201
        assert create(team['sm'], 'quotation', cust[0], chennai).status_code == 201
        for t in ('proforma', 'po', 'dc'):
            assert create(team['sm'], t, cust[0], chennai).status_code == 403, t

    def test_sales_manager_cannot_raise_a_document_for_a_customer_they_cannot_see(self, team, chennai):
        other, _ = make_customer('Other Co', team['admin'])
        assert create(team['sm'], 'enquiry', other, chennai).status_code == 400

    def test_contact_must_belong_to_the_customer_and_be_visible(self, team, cust, chennai):
        customer, contacts = cust
        other, other_contacts = make_customer('Other Co', team['admin'])
        assert create(team['admin'], 'quotation', customer, chennai, contact_id=other_contacts[0].id).status_code == 400
        contact_service.assign_customer(customer, team['sm'], [contacts[0].id])
        assert create(team['sm'], 'quotation', customer, chennai, contact_id=contacts[3].id).status_code == 400
        assert create(team['sm'], 'quotation', customer, chennai, contact_id=contacts[0].id).status_code == 201

    def test_REQ_DOC_05_visibility_by_role_and_type(self, team, cust, chennai):
        customer, _ = cust
        enq = make_doc(team['admin'], 'enquiry', customer, chennai)
        quo = make_doc(team['admin'], 'quotation', customer, chennai)
        dc = make_doc(team['admin'], 'dc', customer, chennai)
        mine = make_doc(team['sm'], 'quotation', customer, chennai)
        ids = lambda who, t: {d['id'] for d in call(client_for(team[who]), 'get', f'/360/api/sales-documents/?type={t}').json()['results']}
        # Sales Manager: created by me, or enquiry/quotation of a customer assigned to me; nothing else
        assert ids('sm', 'enquiry') == {enq['id']} and ids('sm', 'quotation') == {quo['id'], mine['id']}
        assert ids('sm', 'dc') == set()
        assert ids('sm2', 'quotation') == set()
        for who in ('admin', 'bm', 'bs'):
            assert dc['id'] in ids(who, 'dc')
        assert call(client_for(team['sm']), 'get', f'/360/api/sales-documents/{dc["id"]}/').status_code == 404
        assert call(client_for(team['sm2']), 'get', f'/360/api/sales-documents/{quo["id"]}/').status_code == 404

    def test_a_document_cannot_be_moved_to_another_customer(self, team, cust, chennai):
        doc = make_doc(team['admin'], 'enquiry', cust[0], chennai)
        other, _ = make_customer('Other Co', team['admin'])
        res = call(client_for(team['admin']), 'patch', f'/360/api/sales-documents/{doc["id"]}/', {'version': 1, 'customer_id': other.id})
        assert res.status_code == 400


# ----------------------------------------------------------------------------- numbering via the API
class TestNumbering:
    def test_REQ_DOC_01_number_is_filled_in_per_type_and_branch(self, team, cust, chennai, bengaluru):
        nums = [make_doc(team['admin'], t, cust[0], b)['doc_number'] for t, b in [
            ('quotation', chennai), ('quotation', chennai), ('quotation', bengaluru), ('enquiry', chennai), ('proforma', chennai), ('dc', chennai)]]
        assert nums == ['QUO-0001', 'QUO-0002', 'QUO-0001', 'ENQ-0001', 'PI-0001', 'DC-0001']

    def test_a_hand_typed_higher_number_moves_the_counter_and_numbers_stay_editable(self, team, cust, chennai):
        make_doc(team['admin'], 'quotation', cust[0], chennai, doc_number='QUO-0010')
        assert make_doc(team['admin'], 'quotation', cust[0], chennai)['doc_number'] == 'QUO-0011'
        doc = make_doc(team['admin'], 'quotation', cust[0], chennai)
        res = call(client_for(team['admin']), 'patch', f'/360/api/sales-documents/{doc["id"]}/', {'version': 1, 'remarks': 'x'})
        assert res.json()['doc_number'] == 'QUO-0012'

    def test_REQ_DOC_02_branch_settings_are_used(self, team, cust, chennai):
        BranchNumbering.objects.create(branch=chennai, doc_type='quotation', prefix='CHN/Q', suffix='26-27', start_at=100)
        assert make_doc(team['admin'], 'quotation', cust[0], chennai)['doc_number'] == 'CHN/Q-0100-26-27'

    def test_REQ_DOC_02_pending_po_keeps_the_customers_own_number(self, team, cust, chennai):
        assert make_doc(team['admin'], 'po', cust[0], chennai, doc_number='CUST/77')['doc_number'] == 'CUST/77'
        assert make_doc(team['admin'], 'po', cust[0], chennai)['doc_number'] == ''
        assert not BranchNumbering.objects.filter(doc_type='po').exists()


# ----------------------------------------------------------------------------- totals
class TestTotals:
    def test_REQ_DOC_03_line_and_total_math_matches_the_spec_rules(self, team, cust, chennai):
        items = [{'item_name': 'A', 'qty': 10, 'rate': '100', 'discount': '10', 'tax': '18'},
                 {'item_name': 'B', 'qty': 1, 'rate': '50', 'discount': '0', 'tax': '0'}]
        doc = make_doc(team['admin'], 'quotation', cust[0], chennai, items=items, packing_charges='100', packing_tax='18',
                       freight_charges='200', round_off='-0.5')
        spec = R.doc_total([{'qty': 10, 'rate': 100, 'discount': 10, 'tax': 18}, {'qty': 1, 'rate': 50, 'discount': 0, 'tax': 0}],
                           packing=100, packing_tax=18, freight=200, round_off=-0.5)
        assert Decimal(doc['sub_total']) == Decimal(str(round(spec['subTotal'], 2))) == Decimal('1112.00')
        assert Decimal(doc['total_amount']) == Decimal(str(round(spec['totalAmount'], 2))) == Decimal('1429.50')
        assert doc['items'][0]['amount'] == '106.20' and doc['items'][0]['value'] == '1062.00'

    def test_money_rounds_half_up_not_half_even(self, team, cust, chennai):
        doc = make_doc(team['admin'], 'quotation', cust[0], chennai,
                       items=[{'item_name': 'A', 'qty': 1, 'rate': '1.005', 'discount': '0', 'tax': '0'}])
        assert doc['items'][0]['amount'] == '1.01'                      # 1.005 -> 1.01 (JS Math.round semantics)

    def test_enquiry_and_po_have_no_charges_total(self, team, cust, chennai):
        po = make_doc(team['admin'], 'po', cust[0], chennai, doc_number='P1', packing_charges='500')
        assert po['total_amount'] == '0.00'

    def test_totals_cannot_be_set_by_the_client(self, team, cust, chennai):
        doc = make_doc(team['admin'], 'quotation', cust[0], chennai, total_amount='1', sub_total='1')
        assert doc['total_amount'] != '1.00'


# ----------------------------------------------------------------------------- statuses, Win / Lose, enquiry
class TestStatusesAndOutcome:
    def test_default_statuses(self, team, cust, chennai):
        assert [make_doc(team['admin'], t, cust[0], chennai)['order_status'] for t in ('enquiry', 'quotation', 'proforma', 'po', 'dc')] == \
            ['Pending', 'Pending', 'Pending', 'Pending', '']

    def test_REQ_AUT_12_win_needs_an_order_value_and_lose_stores_a_reason(self, team, cust, chennai):
        quo = make_doc(team['admin'], 'quotation', cust[0], chennai)
        url = f'/360/api/sales-documents/{quo["id"]}/outcome/'
        admin = client_for(team['admin'])
        assert call(admin, 'post', url, {'status': 'Win'}).status_code == 400
        won = call(admin, 'post', url, {'status': 'Win', 'order_value': '95000'}).json()
        assert (won['order_status'], won['order_value'], won['lost_reason']) == ('Win', '95000.00', '')
        lost = call(admin, 'post', url, {'status': 'Lose', 'lost_reason': ' price too high '}).json()
        assert (lost['order_status'], lost['order_value'], lost['lost_reason']) == ('Lose', None, 'price too high')
        again = call(admin, 'post', url, {'status': 'Win', 'order_value': '1'}).json()          # switching clears the other
        assert again['lost_reason'] == '' and again['order_value'] == '1.00'

    def test_win_lose_only_for_quotation_and_proforma(self, team, cust, chennai):
        enq = make_doc(team['admin'], 'enquiry', cust[0], chennai)
        res = call(client_for(team['admin']), 'post', f'/360/api/sales-documents/{enq["id"]}/outcome/', {'status': 'Win', 'order_value': '1'})
        assert res.status_code == 400
        pro = make_doc(team['admin'], 'proforma', cust[0], chennai)
        assert call(client_for(team['admin']), 'post', f'/360/api/sales-documents/{pro["id"]}/outcome/', {'status': 'Win', 'order_value': '5'}).status_code == 200

    def test_win_cannot_be_set_through_a_plain_edit(self, team, cust, chennai):
        quo = make_doc(team['admin'], 'quotation', cust[0], chennai)
        res = call(client_for(team['admin']), 'patch', f'/360/api/sales-documents/{quo["id"]}/', {'version': 1, 'order_status': 'Win'})
        assert res.status_code == 400
        res = call(client_for(team['admin']), 'patch', f'/360/api/sales-documents/{quo["id"]}/', {'version': 1, 'order_status': 'Bogus'})
        assert res.status_code == 400

    def test_reopening_to_pending_clears_the_outcome(self, team, cust, chennai):
        quo = make_doc(team['admin'], 'quotation', cust[0], chennai)
        admin = client_for(team['admin'])
        call(admin, 'post', f'/360/api/sales-documents/{quo["id"]}/outcome/', {'status': 'Win', 'order_value': '10'})
        res = call(admin, 'patch', f'/360/api/sales-documents/{quo["id"]}/', {'version': 2, 'order_status': 'Pending'}).json()
        assert res['order_status'] == 'Pending' and res['order_value'] is None

    def test_enquiry_statuses(self, team, cust, chennai):
        enq = make_doc(team['admin'], 'enquiry', cust[0], chennai)
        admin = client_for(team['admin'])
        assert call(admin, 'patch', f'/360/api/sales-documents/{enq["id"]}/', {'version': 1, 'order_status': 'Regretted'}).json()['order_status'] == 'Regretted'

    def test_REQ_AUT_11_quotation_from_an_enquiry_completes_it_and_tells_the_user(self, team, cust, chennai):
        enq = make_doc(team['admin'], 'enquiry', cust[0], chennai)
        res = create(team['admin'], 'quotation', cust[0], chennai, reference_id=enq['id'])
        assert res.status_code == 201 and res.json()['enquiry_completed'] == enq['doc_number']
        assert SalesDocument.objects.get(pk=enq['id']).order_status == 'Completed'
        note = Notification.objects.get(user=team['admin'], type='enquiry_completed')
        assert enq['doc_number'] in note.text and res.json()['doc_number'] in note.text

    def test_REQ_AUT_11_second_quotation_does_not_notify_again(self, team, cust, chennai):
        enq = make_doc(team['admin'], 'enquiry', cust[0], chennai)
        create(team['admin'], 'quotation', cust[0], chennai, reference_id=enq['id'])
        res = create(team['admin'], 'quotation', cust[0], chennai, reference_id=enq['id'])
        assert 'enquiry_completed' not in res.json() and Notification.objects.filter(type='enquiry_completed').count() == 1

    def test_reference_chain_types_are_enforced(self, team, cust, chennai):
        quo = make_doc(team['admin'], 'quotation', cust[0], chennai)
        assert create(team['admin'], 'quotation', cust[0], chennai, reference_id=quo['id']).status_code == 400   # needs an enquiry
        assert create(team['admin'], 'proforma', cust[0], chennai, reference_id=quo['id']).status_code == 201
        assert create(team['admin'], 'enquiry', cust[0], chennai, reference_id=quo['id']).status_code == 400


# ----------------------------------------------------------------------------- Pending PO supply
class TestPendingPO:
    def po(self, team, cust, chennai, qty=10):
        return make_doc(team['admin'], 'po', cust[0], chennai, doc_number='P-1', items=[{**ITEM, 'qty': qty}])

    def supply(self, user, item_id, qty, **extra):
        return call(client_for(user), 'post', f'/360/api/sales-document-items/{item_id}/supply-log/',
                    {'qty_supplied': qty, 'date': '2026-10-05', **extra})

    def status(self, doc_id):
        return SalesDocument.objects.get(pk=doc_id).order_status

    def test_REQ_PO_01_status_follows_the_supply_log(self, team, cust, chennai):
        po = self.po(team, cust, chennai)
        item = po['items'][0]['id']
        assert self.status(po['id']) == 'Pending'
        assert self.supply(team['bs'], item, 4).status_code == 201 and self.status(po['id']) == 'Part Pending'
        assert self.supply(team['bs'], item, 6).status_code == 201 and self.status(po['id']) == 'Completed'

    def test_REQ_PO_03_pending_is_ordered_minus_supplied_and_never_negative(self, team, cust, chennai):
        po = self.po(team, cust, chennai)
        item = po['items'][0]['id']
        self.supply(team['admin'], item, 4)
        self.supply(team['admin'], item, 9, confirm_over=True)
        row = call(client_for(team['admin']), 'get', f'/360/api/sales-documents/{po["id"]}/').json()['items'][0]
        assert (row['supplied'], row['pending']) == ('13.00', '0.00')

    def test_REQ_PO_04_quantity_must_be_positive_and_over_supply_needs_confirmation(self, team, cust, chennai):
        po = self.po(team, cust, chennai)
        item = po['items'][0]['id']
        assert self.supply(team['admin'], item, 0).status_code == 400
        assert self.supply(team['admin'], item, -3).status_code == 400
        res = self.supply(team['admin'], item, 11)
        assert res.status_code == 409 and res.json()['needs_confirmation'] is True and res.json()['balance'] == '10.00'
        assert self.status(po['id']) == 'Pending'
        assert self.supply(team['admin'], item, 11, confirm_over=True).status_code == 201 and self.status(po['id']) == 'Completed'

    def test_REQ_PO_02_hold_is_never_overwritten_by_the_automatic_status(self, team, cust, chennai):
        po = self.po(team, cust, chennai)
        item = po['items'][0]['id']
        call(client_for(team['admin']), 'patch', f'/360/api/sales-documents/{po["id"]}/', {'version': 1, 'order_status': 'Hold'})
        assert self.supply(team['admin'], item, 10).status_code == 201
        assert self.status(po['id']) == 'Hold'
        res = call(client_for(team['admin']), 'patch', f'/360/api/sales-documents/{po["id"]}/', {'version': 2, 'order_status': 'Pending'})
        assert res.json()['order_status'] == 'Completed'                    # releasing the hold recomputes

    def test_REQ_PO_05_deleting_a_supply_entry_recalculates_and_hold_stays(self, team, cust, chennai):
        po = self.po(team, cust, chennai)
        item = po['items'][0]['id']
        entry = self.supply(team['admin'], item, 10).json()
        assert self.status(po['id']) == 'Completed'
        assert call(client_for(team['admin']), 'delete', f'/360/api/supply-log/{entry["id"]}/').status_code == 200
        assert self.status(po['id']) == 'Pending'
        entry = self.supply(team['admin'], item, 3).json()
        call(client_for(team['admin']), 'patch', f'/360/api/sales-documents/{po["id"]}/', {'version': 1, 'order_status': 'Hold'})
        call(client_for(team['admin']), 'delete', f'/360/api/supply-log/{entry["id"]}/')
        assert self.status(po['id']) == 'Hold'

    def test_supply_entries_can_be_edited(self, team, cust, chennai):
        po = self.po(team, cust, chennai)
        entry = self.supply(team['admin'], po['items'][0]['id'], 3).json()
        res = call(client_for(team['admin']), 'patch', f'/360/api/supply-log/{entry["id"]}/', {'qty_supplied': 10})
        assert res.status_code == 200 and self.status(po['id']) == 'Completed'
        res = call(client_for(team['admin']), 'patch', f'/360/api/supply-log/{entry["id"]}/', {'qty_supplied': 11})
        assert res.status_code == 409

    def test_REQ_PO_05_editing_a_po_keeps_each_lines_supply_history(self, team, cust, chennai):
        po = make_doc(team['admin'], 'po', cust[0], chennai, doc_number='P-1',
                      items=[{**ITEM, 'item_name': 'A', 'qty': 10}, {**ITEM, 'item_name': 'B', 'qty': 5}])
        a, b = po['items']
        self.supply(team['admin'], a['id'], 10)
        res = call(client_for(team['admin']), 'patch', f'/360/api/sales-documents/{po["id"]}/', {'version': 1, 'items': [
            {**ITEM, 'id': a['id'], 'item_name': 'A', 'qty': 12}, {**ITEM, 'item_name': 'C', 'qty': 1}, {**ITEM, 'item_name': '', 'qty': 0}]})
        body = res.json()
        assert [i['item_name'] for i in body['items']] == ['A', 'C']
        assert body['items'][0]['id'] == a['id'] and body['items'][0]['supplied'] == '10.00' and body['items'][1]['supplied'] == '0.00'
        assert body['order_status'] == 'Part Pending'                            # 12 ordered, 10 supplied of 13 total

    def test_sales_manager_cannot_record_supply(self, team, cust, chennai):
        po = self.po(team, cust, chennai)
        assert self.supply(team['sm'], po['items'][0]['id'], 1).status_code == 404       # cannot even see it
        assert self.supply(team['bs'], po['items'][0]['id'], 1).status_code == 201

    def test_supply_only_on_po_items(self, team, cust, chennai):
        quo = make_doc(team['admin'], 'quotation', cust[0], chennai)
        assert self.supply(team['admin'], quo['items'][0]['id'], 1).status_code == 400


# ----------------------------------------------------------------------------- challan: invoicing and stock-OUT
class TestDeliveryChallan:
    def invoice(self, user, item_id, **data):
        body = {'bill_number': 'INV-1', 'bill_date': '2026-10-06', 'qty_invoiced': 4, **data}
        return call(client_for(user), 'post', f'/360/api/sales-document-items/{item_id}/invoice-log/', body)

    def test_REQ_AUT_13_new_challan_writes_one_stock_out_per_item_and_edit_does_not_repeat(self, team, cust, chennai):
        dc = make_doc(team['admin'], 'dc', cust[0], chennai,
                      items=[{**ITEM, 'item_name': '6205', 'qty': 4}, {**ITEM, 'item_name': '6206', 'qty': 0}, {**ITEM, 'item_name': '6207', 'qty': 2}])
        out = StockTransaction.objects.all()
        assert sorted((t.item_name, t.type, t.qty, t.source, t.branch_id) for t in out) == [
            ('6205', 'OUT', Decimal('4.00'), 'Delivery Challan', chennai.id), ('6207', 'OUT', Decimal('2.00'), 'Delivery Challan', chennai.id)]
        assert all(t.ref_document_id == dc['id'] and t.recorded_by == team['admin'] for t in out)
        call(client_for(team['admin']), 'patch', f'/360/api/sales-documents/{dc["id"]}/', {'version': 1, 'remarks': 'edited'})
        assert StockTransaction.objects.count() == 2

    def test_other_document_types_write_no_stock_entries(self, team, cust, chennai):
        make_doc(team['admin'], 'quotation', cust[0], chennai)
        make_doc(team['admin'], 'po', cust[0], chennai, doc_number='P')
        assert not StockTransaction.objects.exists()

    def test_REQ_DC_01_invoice_done_rules(self, team, cust, chennai):
        dc = make_doc(team['admin'], 'dc', cust[0], chennai, items=[{**ITEM, 'qty': 10}])
        item = dc['items'][0]['id']
        assert self.invoice(team['admin'], item, bill_number=' ').status_code == 400
        assert self.invoice(team['admin'], item, qty_invoiced=0).status_code == 400
        assert self.invoice(team['admin'], item, qty_invoiced=4).status_code == 201
        res = self.invoice(team['admin'], item, qty_invoiced=7)
        assert res.status_code == 409 and res.json()['balance'] == '6.00'
        assert self.invoice(team['admin'], item, qty_invoiced=6).status_code == 201
        body = call(client_for(team['admin']), 'get', f'/360/api/sales-documents/{dc["id"]}/').json()
        assert body['items'][0]['balance'] == '0.00' and body['invoice_pending'] is False

    def test_REQ_DC_01_challan_is_pending_while_any_item_has_a_balance(self, team, cust, chennai):
        dc = make_doc(team['admin'], 'dc', cust[0], chennai, items=[{**ITEM, 'item_name': 'A', 'qty': 2}, {**ITEM, 'item_name': 'B', 'qty': 2}])
        a, b = dc['items']
        self.invoice(team['admin'], a['id'], qty_invoiced=2)
        pending = lambda: call(client_for(team['admin']), 'get', '/360/api/sales-documents/?type=dc&pending=1').json()['count']
        assert pending() == 1
        self.invoice(team['admin'], b['id'], qty_invoiced=2)
        assert pending() == 0

    def test_over_invoice_with_confirmation_is_allowed(self, team, cust, chennai):
        dc = make_doc(team['admin'], 'dc', cust[0], chennai, items=[{**ITEM, 'qty': 1}])
        assert self.invoice(team['admin'], dc['items'][0]['id'], qty_invoiced=3, confirm_over=True).status_code == 201

    def test_sales_manager_cannot_invoice(self, team, cust, chennai):
        dc = make_doc(team['admin'], 'dc', cust[0], chennai)
        assert self.invoice(team['sm'], dc['items'][0]['id']).status_code == 404

    def test_invoicing_only_on_challan_items(self, team, cust, chennai):
        quo = make_doc(team['admin'], 'quotation', cust[0], chennai)
        assert self.invoice(team['admin'], quo['items'][0]['id']).status_code == 400


# ----------------------------------------------------------------------------- contact log
class TestContactLog:
    def log(self, user, doc_id, **data):
        return call(client_for(user), 'post', f'/360/api/sales-documents/{doc_id}/calls/', {'message': 'Spoke to buyer', **data})

    def test_REQ_LOG_01_call_me_later_creates_a_call_task_for_the_logger(self, team, cust, chennai):
        customer, contacts = cust
        quo = make_doc(team['admin'], 'quotation', customer, chennai, contact_id=contacts[0].id)
        res = self.log(team['bs'], quo['id'], call_later_date='2026-11-10')
        assert res.status_code == 201 and res.json()['call_later_date'] == '2026-11-10'
        task = Task.objects.get()
        assert (task.title, task.task_type, str(task.due_date), task.assigned_to, task.created_by) == \
            ('Call Ravi — Sun Steels', 'Call', '2026-11-10', team['bs'], team['bs'])
        assert task.related_document_id == quo['id']

    def test_a_plain_message_creates_no_task_and_empty_is_refused(self, team, cust, chennai):
        quo = make_doc(team['admin'], 'quotation', cust[0], chennai)
        assert self.log(team['admin'], quo['id']).status_code == 201 and not Task.objects.exists()
        assert self.log(team['admin'], quo['id'], message='  ').status_code == 400

    def test_outcomes_are_validated(self, team, cust, chennai):
        quo = make_doc(team['admin'], 'quotation', cust[0], chennai)
        assert self.log(team['admin'], quo['id'], outcome='Busy').json()['outcome'] == 'Busy'
        assert self.log(team['admin'], quo['id'], outcome='Whatever').status_code == 400

    def test_enquiry_and_po_have_no_contact_log(self, team, cust, chennai):
        enq = make_doc(team['admin'], 'enquiry', cust[0], chennai)
        assert self.log(team['admin'], enq['id']).status_code == 400

    def test_REQ_LOG_02_last_contact_and_call_later_buckets_are_list_filters(self, team, cust, chennai):
        today = timezone.localdate()
        docs = {k: make_doc(team['admin'], 'quotation', cust[0], chennai) for k in ('overdue', 'today', 'upcoming', 'none')}
        self.log(team['admin'], docs['overdue']['id'], call_later_date=(today - timedelta(days=2)).isoformat())
        self.log(team['admin'], docs['today']['id'], call_later_date=today.isoformat())
        self.log(team['admin'], docs['upcoming']['id'], call_later_date=(today + timedelta(days=3)).isoformat())
        admin = client_for(team['admin'])
        for bucket, key in [('overdue', 'overdue'), ('today', 'today'), ('upcoming', 'upcoming'), ('none', 'none')]:
            res = call(admin, 'get', f'/360/api/sales-documents/?type=quotation&call_later={bucket}').json()
            assert [d['id'] for d in res['results']] == [docs[key]['id']], bucket
        body = call(admin, 'get', f'/360/api/sales-documents/{docs["today"]["id"]}/').json()
        assert body['last_contact_on'] and body['call_later_bucket'] == 'today'
        assert call(admin, 'get', f'/360/api/sales-documents/{docs["none"]["id"]}/').json()['last_contact_on'] is None

    def test_latest_call_later_date_wins(self, team, cust, chennai):
        quo = make_doc(team['admin'], 'quotation', cust[0], chennai)
        self.log(team['admin'], quo['id'], call_later_date='2026-11-01')
        self.log(team['admin'], quo['id'], call_later_date='2026-12-01')
        assert call(client_for(team['admin']), 'get', f'/360/api/sales-documents/{quo["id"]}/').json()['call_later_date'] == '2026-12-01'

    def test_log_entries_cannot_be_edited_or_deleted(self, team, cust, chennai):
        quo = make_doc(team['admin'], 'quotation', cust[0], chennai)
        self.log(team['admin'], quo['id'])
        assert call(client_for(team['admin']), 'patch', '/360/api/sales-documents/%d/calls/' % quo['id'], {}).status_code == 405


# ----------------------------------------------------------------------------- clone, list filters, schedule
class TestCloneFiltersSchedule:
    def test_clone_gets_a_new_number_today_and_none_of_the_history(self, team, cust, chennai):
        quo = make_doc(team['admin'], 'quotation', cust[0], chennai, packing_charges='100')
        admin = client_for(team['admin'])
        call(admin, 'post', f'/360/api/sales-documents/{quo["id"]}/calls/', {'message': 'x'})
        call(admin, 'post', f'/360/api/sales-documents/{quo["id"]}/outcome/', {'status': 'Win', 'order_value': '5'})
        clone = call(admin, 'post', f'/360/api/sales-documents/{quo["id"]}/clone/').json()
        assert clone['doc_number'] == 'QUO-0002' and clone['date'] == timezone.localdate().isoformat()
        assert clone['order_status'] == 'Pending' and clone['order_value'] is None and clone['call_log'] == []
        assert clone['packing_charges'] == '100.00' and clone['items'][0]['item_name'] == '6205 ZZ' and clone['items'][0]['id'] != quo['items'][0]['id']

    def test_cloning_a_challan_writes_stock_out_for_the_new_challan(self, team, cust, chennai):
        dc = make_doc(team['admin'], 'dc', cust[0], chennai)
        call(client_for(team['admin']), 'post', f'/360/api/sales-documents/{dc["id"]}/clone/')
        assert StockTransaction.objects.count() == 2

    def test_cannot_clone_what_you_cannot_see(self, team, cust, chennai):
        dc = make_doc(team['admin'], 'dc', cust[0], chennai)
        assert call(client_for(team['sm']), 'post', f'/360/api/sales-documents/{dc["id"]}/clone/').status_code == 404

    def test_list_filters(self, team, cust, chennai):
        other, _ = make_customer('Ram Industries', team['admin'])
        a = make_doc(team['admin'], 'quotation', cust[0], chennai, date='2026-09-01', items=[{**ITEM, 'item_name': 'Taper 30205'}])
        b = make_doc(team['admin'], 'quotation', other, chennai, date='2026-10-15')
        admin = client_for(team['admin'])
        ids = lambda q: [d['id'] for d in call(admin, 'get', f'/360/api/sales-documents/?type=quotation&{q}').json()['results']]
        assert ids(f'customer_id={other.id}') == [b['id']] and ids('number=0001') == [a['id']] and ids('item=taper') == [a['id']]
        assert ids('date_from=2026-10-01') == [b['id']] and ids('date_to=2026-09-30') == [a['id']]
        assert set(ids('status=Pending')) == {a['id'], b['id']}
        assert ids(f'branch_id={chennai.id + 99}') == []

    def test_history_lists_filter_by_win_and_lose(self, team, cust, chennai):
        a = make_doc(team['admin'], 'quotation', cust[0], chennai)
        b = make_doc(team['admin'], 'quotation', cust[0], chennai)
        admin = client_for(team['admin'])
        call(admin, 'post', f'/360/api/sales-documents/{a["id"]}/outcome/', {'status': 'Win', 'order_value': '5'})
        call(admin, 'post', f'/360/api/sales-documents/{b["id"]}/outcome/', {'status': 'Lose', 'lost_reason': 'x'})
        assert [d['id'] for d in call(admin, 'get', '/360/api/sales-documents/?type=quotation&status=Win').json()['results']] == [a['id']]
        assert [d['id'] for d in call(admin, 'get', '/360/api/sales-documents/?type=quotation&status=Lose').json()['results']] == [b['id']]

    def test_REQ_AUT_08_schedule_follow_up_endpoint(self, team, cust, chennai):
        customer, contacts = cust
        quo = make_doc(team['admin'], 'quotation', customer, chennai, contact_id=contacts[1].id)
        res = call(client_for(team['admin']), 'post', f'/360/api/sales-documents/{quo["id"]}/schedule/',
                   {'kind': 'Visit', 'due_date': '2026-11-20', 'assigned_to_id': team['bs'].id})
        assert res.status_code == 201 and res.json()['title'] == 'Visit Meena — Sun Steels'
        assert Notification.objects.filter(user=team['bs'], type='task').exists()
        assert call(client_for(team['admin']), 'post', f'/360/api/sales-documents/{quo["id"]}/schedule/', {'kind': 'Dance', 'due_date': '2026-11-20'}).status_code == 400


# ----------------------------------------------------------------------------- approvals for documents
class TestDocumentApprovals:
    def test_REQ_ROLE_02_sales_manager_enquiry_edit_applies_only_on_approval(self, team, cust, chennai):
        enq = make_doc(team['sm'], 'enquiry', cust[0], chennai, remarks='old')
        res = call(client_for(team['sm']), 'patch', f'/360/api/sales-documents/{enq["id"]}/', {'version': 1, 'remarks': 'new'})
        assert res.status_code == 202
        assert SalesDocument.objects.get(pk=enq['id']).remarks == 'old'
        approval = ApprovalRequest.objects.get()
        assert approval.before_data['remarks'] == 'old'
        call(client_for(team['bm']), 'post', f'/360/api/approvals/{approval.id}/approve/')
        assert SalesDocument.objects.get(pk=enq['id']).remarks == 'new'

    def test_approved_quotation_edit_replaces_items_and_recomputes(self, team, cust, chennai):
        quo = make_doc(team['sm'], 'quotation', cust[0], chennai)
        call(client_for(team['sm']), 'patch', f'/360/api/sales-documents/{quo["id"]}/', {
            'version': 1, 'items': [{'item_name': 'New part', 'qty': 2, 'rate': '50', 'discount': '0', 'tax': '0'}]})
        approval = ApprovalRequest.objects.get()
        changes = call(client_for(team['admin']), 'get', f'/360/api/approvals/{approval.id}/changes/').json()['changes']
        assert changes[0]['field'] == 'items' and changes[0]['before'][0]['item_name'] == '6205 ZZ'
        call(client_for(team['admin']), 'post', f'/360/api/approvals/{approval.id}/approve/')
        doc = SalesDocument.objects.get(pk=quo['id'])
        assert [i.item_name for i in doc.items.all()] == ['New part'] and doc.total_amount == Decimal('100.00')

    def test_approved_delete_removes_the_document_but_not_its_number(self, team, cust, chennai):
        quo = make_doc(team['sm'], 'quotation', cust[0], chennai)
        assert call(client_for(team['sm']), 'delete', f'/360/api/sales-documents/{quo["id"]}/').status_code == 202
        approval = ApprovalRequest.objects.get()
        call(client_for(team['admin']), 'post', f'/360/api/approvals/{approval.id}/approve/')
        assert not SalesDocument.objects.filter(pk=quo['id']).exists()
        assert make_doc(team['admin'], 'quotation', cust[0], chennai)['doc_number'] == 'QUO-0002'

    def test_branch_staff_edit_and_delete_documents_directly(self, team, cust, chennai):
        quo = make_doc(team['admin'], 'quotation', cust[0], chennai)
        bs = client_for(team['bs'])
        assert call(bs, 'patch', f'/360/api/sales-documents/{quo["id"]}/', {'version': 1, 'remarks': 'x'}).status_code == 200
        assert call(bs, 'delete', f'/360/api/sales-documents/{quo["id"]}/').status_code == 200
        assert not ApprovalRequest.objects.exists()

    def test_stale_version_is_a_conflict(self, team, cust, chennai):
        quo = make_doc(team['admin'], 'quotation', cust[0], chennai)
        admin = client_for(team['admin'])
        call(admin, 'patch', f'/360/api/sales-documents/{quo["id"]}/', {'version': 1, 'remarks': 'a'})
        assert call(admin, 'patch', f'/360/api/sales-documents/{quo["id"]}/', {'version': 1, 'remarks': 'b'}).status_code == 409

    def test_one_pending_request_rule_applies_to_documents(self, team, cust, chennai):
        enq = make_doc(team['sm'], 'enquiry', cust[0], chennai)
        sm = client_for(team['sm'])
        assert call(sm, 'patch', f'/360/api/sales-documents/{enq["id"]}/', {'version': 1, 'remarks': 'a'}).status_code == 202
        assert call(sm, 'patch', f'/360/api/sales-documents/{enq["id"]}/', {'version': 1, 'remarks': 'b'}).status_code == 409
