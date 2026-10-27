"""Phase 3 — golden-sample tests for the ported sales-document totals math
(`threesixty/services/totals.py`) and the `autoStockOutFromDC` auto-log,
hand-verified against the original save-time formula at
`contact_management.html` ~L11370-11436 (items) and ~L12844-12856
(stock-out). These are NOT the separate print-time `computeQuotationDocData`
math (~L8805-8850) — that's PDF-rendering-only and ported separately.
"""
import json
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from threesixty.models import Branch, Customer, EmployeeProfile, SalesDocument, StockTransaction
from threesixty.services.totals import compute_document_totals, compute_item_fields

pytestmark = pytest.mark.django_db


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type='application/json')


class TestComputeItemFields:
    def test_quotation_item_folds_discount_then_tax(self):
        # qty=10, rate=100, discount=10%, tax=18%
        # unitFinal = 100 * 0.9 = 90; unitFinal *= 1.18 = 106.2
        # amount = 106.2; value = 10 * 106.2 = 1062
        amount, value = compute_item_fields('quotation', {'qty': 10, 'rate': 100, 'discount': 10, 'tax': 18})
        assert amount == Decimal('106.2')
        assert value == Decimal('1062.0')

    def test_po_item_has_discount_but_no_tax(self):
        # qty=5, rate=200, discount=5% -> unitFinal = 200 * 0.95 = 190 (no tax fold — po has no hasTax)
        amount, value = compute_item_fields('po', {'qty': 5, 'rate': 200, 'discount': 5, 'tax': 18})
        assert amount == Decimal('190.0')
        assert value == Decimal('950.0')

    def test_zero_discount_and_tax_is_a_plain_multiply(self):
        amount, value = compute_item_fields('dc', {'qty': 3, 'rate': 50, 'discount': 0, 'tax': 0})
        assert amount == Decimal('50.0')
        assert value == Decimal('150.0')


class TestComputeDocumentTotals:
    def test_quotation_charges_and_round_off(self):
        items = [{'qty': 10, 'rate': 100, 'discount': 10, 'tax': 18}]
        sub_total, total_amount = compute_document_totals(
            'quotation', items,
            packing=50, packing_tax=5, freight=30, freight_tax=0, other=0, other_tax=0, round_off=-0.5,
        )
        assert sub_total == Decimal('1062.0')
        # 1062 + 52.5 (packing incl. 5% tax) + 30 (freight) + 0 (other) - 0.5 (round off) = 1144.0
        assert total_amount == Decimal('1144.00')

    def test_enquiry_and_po_never_compute_charges(self):
        items = [{'qty': 5, 'rate': 200, 'discount': 5, 'tax': 18}]
        assert compute_document_totals('enquiry', items, 10, 0, 10, 0, 10, 0, 0) == (Decimal('0'), Decimal('0'))
        assert compute_document_totals('po', items, 10, 0, 10, 0, 10, 0, 0) == (Decimal('0'), Decimal('0'))


@pytest.fixture
def chennai():
    return Branch.objects.create(name='Chennai')


@pytest.fixture
def admin_client(chennai):
    from django.contrib.auth.models import User
    user = User.objects.create_user(username='admin1', password='x', is_staff=True)
    EmployeeProfile.objects.create(user=user, role=EmployeeProfile.ADMIN).branches.set([chennai])
    client = Client()
    client.login(username='admin1', password='x')
    return client


class TestSalesDocumentApiRecomputesTotals:
    def test_quotation_create_persists_computed_item_and_document_totals(self, admin_client, chennai):
        customer = Customer.objects.create(name='Acme')
        resp = post_json(admin_client, reverse('threesixty:threesixty_api:sales-documents'), {
            'type': SalesDocument.TYPE_QUOTATION, 'branch_id': chennai.id, 'customer_id': customer.id,
            'date': '2026-01-01', 'packing_charges': 50, 'packing_tax': 5, 'freight_charges': 30,
            'round_off': -0.5,
            'items': [{'item_name': 'Bearing', 'qty': 10, 'rate': 100, 'discount': 10, 'tax': 18}],
            # a client-submitted amount/value/sub_total/total_amount must be IGNORED —
            # these are always server-derived now.
            'sub_total': 1, 'total_amount': 1,
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body['sub_total'] == '1062.00'
        assert body['total_amount'] == '1144.00'
        item = body['items'][0]
        assert item['amount'] == '106.20'
        assert item['value'] == '1062.00'

    def test_po_create_has_no_charges_or_tax_fold(self, admin_client, chennai):
        customer = Customer.objects.create(name='Acme')
        resp = post_json(admin_client, reverse('threesixty:threesixty_api:sales-documents'), {
            'type': SalesDocument.TYPE_PO, 'branch_id': chennai.id, 'customer_id': customer.id,
            'date': '2026-01-01',
            'items': [{'item_name': 'Bearing', 'qty': 5, 'rate': 200, 'discount': 5, 'tax': 18}],
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body['sub_total'] == '0.00'
        assert body['total_amount'] == '0.00'
        assert body['items'][0]['value'] == '950.00'


class TestAutoStockOutFromDC:
    def test_new_delivery_challan_logs_stock_out_per_item(self, admin_client, chennai):
        customer = Customer.objects.create(name='Acme')
        resp = post_json(admin_client, reverse('threesixty:threesixty_api:sales-documents'), {
            'type': SalesDocument.TYPE_DC, 'branch_id': chennai.id, 'customer_id': customer.id,
            'date': '2026-01-01',
            'items': [
                {'item_name': 'Bearing', 'qty': 4, 'rate': 10},
                {'item_name': '', 'qty': 2, 'rate': 10},  # no item_name -> skipped, matches original
                {'item_name': 'Washer', 'qty': 0, 'rate': 10},  # qty 0 -> skipped, matches original
            ],
        })
        assert resp.status_code == 201
        doc_id = resp.json()['id']
        transactions = StockTransaction.objects.filter(ref_document_id=doc_id)
        assert transactions.count() == 1
        txn = transactions.first()
        assert txn.item_name == 'Bearing' and txn.qty == 4 and txn.type == StockTransaction.TYPE_OUT
        assert txn.source == 'Delivery Challan'

    def test_updating_a_dc_does_not_log_stock_out_again(self, admin_client, chennai):
        customer = Customer.objects.create(name='Acme')
        created = post_json(admin_client, reverse('threesixty:threesixty_api:sales-documents'), {
            'type': SalesDocument.TYPE_DC, 'branch_id': chennai.id, 'customer_id': customer.id,
            'date': '2026-01-01', 'items': [{'item_name': 'Bearing', 'qty': 4, 'rate': 10}],
        }).json()
        url = reverse('threesixty:threesixty_api:sales-document-detail', args=[created['id']])
        resp = admin_client.patch(
            url, data=json.dumps({'version': 1, 'remarks': 'updated'}), content_type='application/json'
        )
        assert resp.status_code == 200
        assert StockTransaction.objects.filter(ref_document_id=created['id']).count() == 1
