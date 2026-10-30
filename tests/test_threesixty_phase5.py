"""Phase 5 (Printing) — printed totals, amount in words, PDF, Excel export."""
import io
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import load_workbook
from PIL import Image

from threesixty.models import Branch, Customer, SalesDocument, SalesDocumentItem
from threesixty.rules import anupam_rules as R
from threesixty.services import pdf_documents
from threesixty.services.printing import amount_in_words, js_round, print_totals, quotation_value_of
from tests.helpers_360 import ADMIN, BM, BS, SM, call, client_for, make_customer, make_employee

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def chennai():
    return Branch.objects.create(name='Chennai', letterhead_name='Anupam Bearings', letterhead_address='12 Mount Road\nChennai 600002',
                                 letterhead_gstin='33ABCDE1234F1Z5', bank_name='HDFC Bank', bank_account_no='5010012345',
                                 bank_ifsc='HDFC0000123', terms='Goods once sold will not be taken back\nPayment within 30 days')


@pytest.fixture
def team(chennai):
    return {'admin': make_employee('admin', ADMIN, [chennai]), 'bm': make_employee('bm', BM, [chennai]),
            'sm': make_employee('sm', SM, [chennai]), 'sm2': make_employee('sm2', SM, [chennai])}


def png(color=(200, 80, 0), size=(40, 40)):
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'PNG')
    return buf.getvalue()


def make_doc(branch, doc_type='quotation', items=None, **fields):
    customer, contacts = make_customer('Sun Steels', None, area='Ambattur', city='Chennai', address='12 mount road', gst_number='33AAA')
    doc = SalesDocument.objects.create(type=doc_type, doc_number=f'{doc_type[:3].upper()}-0001', branch=branch, customer=customer,
                                       contact=contacts[0], date='2026-10-01', **fields)
    for pos, row in enumerate(items or [dict(item_name='6205 ZZ', make='SKF', qty=10, unit='Nos', rate=100, discount=10, tax=18)]):
        SalesDocumentItem.objects.create(document=doc, position=pos, **row)
    return SalesDocument.objects.get(pk=doc.pk)          # re-read: dates etc. as the database returns them


# ----------------------------------------------------------------------------- printed totals
class TestPrintedTotals:
    def spec_doc(self, doc):
        return {'showDiscountInPdf': doc.show_discount_in_pdf, 'packingCharges': float(doc.packing_charges), 'packingTax': float(doc.packing_tax),
                'freightCharges': float(doc.freight_charges), 'freightTax': float(doc.freight_tax), 'otherCharges': float(doc.other_charges),
                'otherChargesTax': float(doc.other_charges_tax), 'roundOff': float(doc.round_off),
                'items': [{'itemName': i.item_name, 'make': i.make, 'qty': float(i.qty), 'rate': float(i.rate), 'discount': float(i.discount),
                           'tax': float(i.tax)} for i in doc.items.all()]}

    @pytest.mark.parametrize('show', [False, True])
    def test_REQ_PRN_01_02_printed_totals_equal_the_spec_rules(self, chennai, show):
        doc = make_doc(chennai, show_discount_in_pdf=show, packing_charges=100, packing_tax=18, freight_charges=250.5, other_charges=10,
                       other_charges_tax=5, round_off=-0.45, items=[
                           dict(item_name='A', make='SKF', qty=3, rate=105, discount=10, tax=18), dict(item_name='B', qty=7, rate='33.33', discount=12.5, tax=12),
                           dict(item_name='C', qty=1, rate=99.5, discount=0, tax=0)])
        mine, spec = print_totals(doc), R.quotation_print_totals(self.spec_doc(doc))
        assert round(float(mine['sub_total']), 2) == round(spec['subTotal'], 2)
        assert round(float(mine['tax_total']), 2) == round(spec['taxTotal'], 2)
        assert round(float(mine['total']), 2) == round(spec['total'], 2)
        for got, want in zip(mine['lines'], spec['lines']):
            assert (got['sr'], got['name']) == (want['sr'], want['name'])
            assert round(float(got['rate']), 2) == round(want['rate'], 2) and round(float(got['amount']), 2) == round(want['amount'], 2)

    def test_discounted_rate_is_rounded_half_up_to_a_whole_rupee(self, chennai):
        doc = make_doc(chennai, items=[dict(item_name='A', qty=2, rate=105, discount=10, tax=0)])      # 94.5 -> 95 (not banker's 94)
        line = print_totals(doc)['lines'][0]
        assert line['rate'] == Decimal(95) and line['amount'] == Decimal(190)
        assert js_round(Decimal('2.5')) == 3 and js_round(Decimal('3.5')) == 4 and js_round(Decimal('0.49')) == 0

    def test_show_discount_keeps_the_entered_rate(self, chennai):
        doc = make_doc(chennai, show_discount_in_pdf=True, items=[dict(item_name='A', qty=2, rate=105, discount=10, tax=0)])
        line = print_totals(doc)['lines'][0]
        assert line['rate'] == Decimal(105) and line['amount'] == Decimal('189.00')

    def test_line_tax_is_one_tax_amount_not_in_the_line(self, chennai):
        doc = make_doc(chennai, show_discount_in_pdf=True, items=[dict(item_name='A', qty=1, rate=100, discount=0, tax=18),
                                                                  dict(item_name='B', qty=1, rate=200, discount=0, tax=5)])
        t = print_totals(doc)
        assert [l['amount'] for l in t['lines']] == [100, 200] and t['sub_total'] == 300 and t['tax_total'] == 28 and t['total'] == 328

    def test_make_is_shown_in_brackets_after_the_item_name(self, chennai):
        doc = make_doc(chennai, 'dc', items=[dict(item_name='6205', make='SKF', qty=1, rate=1), dict(item_name='6206', qty=1, rate=1), dict(qty=1, rate=1)])
        assert [l['name'] for l in print_totals(doc)['lines']] == ['6205 (SKF)', '6206', '—']

    def test_REQ_PRN_03_amount_in_words_matches_the_spec_rules(self):
        for value in ('0', '1', '0.5', '19', '100', '1000', '99999.99', '123456.5', '1234567', '12345678.9', '10000000', '100000', '-45.25', '0.01'):
            assert amount_in_words(Decimal(value)) == R.amount_in_words(float(value)), value
        assert amount_in_words(Decimal('123456.5')) == 'Rupees One Lakh Twenty Three Thousand Four Hundred Fifty Six and Fifty Paise Only'
        assert amount_in_words(Decimal('10000000')) == 'Rupees One Crore Only'

    def test_REQ_PRN_04_report_value_prefers_stored_total_then_items_then_legacy(self, chennai):
        stored = make_doc(chennai, total_amount=500)
        assert quotation_value_of(stored) == 500
        from_items = make_doc(chennai, total_amount=0)
        SalesDocumentItem.objects.filter(document=from_items).update(value=Decimal('250.00'))
        assert quotation_value_of(from_items) == 250
        legacy = make_doc(chennai, total_amount=0, quotation_value=Decimal('99'), items=[dict(item_name='A', qty=1, rate=1, value=0)])
        assert quotation_value_of(legacy) == 99


# ----------------------------------------------------------------------------- PDF
def pdf_text(document, compress=False):
    return pdf_documents.build_pdf(document, compress=compress)


class TestPdf:
    def test_pdf_has_the_expected_content(self, chennai):
        doc = make_doc(chennai, packing_charges=100)
        body = pdf_text(doc)
        assert body.startswith(b'%PDF')
        for text in (b'QUOTATION', b'QUO-0001', b'Sun Steels', rb'6205 ZZ \(SKF\)', b'Tax Amount', b'Sub Total', b'TOTAL',
                     b'Amount in words', b'Rupees', b'Terms & conditions', b'Payment within 30 days', b'Bank details',
                     b'HDFC Bank', b'Anupam Bearings', b'33ABCDE1234F1Z5', b'For Anupam Bearings'):
            assert text in body, text

    def test_the_printed_total_and_words_agree(self, chennai):
        doc = make_doc(chennai, show_discount_in_pdf=True, items=[dict(item_name='A', qty=1, rate=100000, discount=0, tax=23.456)])
        body = pdf_text(doc)
        assert amount_in_words(print_totals(doc)['total']).encode() in body

    def test_proforma_and_challan_titles(self, chennai):
        assert b'PROFORMA INVOICE' in pdf_text(make_doc(chennai, 'proforma'))
        assert b'DELIVERY CHALLAN' in pdf_text(make_doc(chennai, 'dc', vehicle='TN01 AB 1234', transport='VRL'))

    def test_challan_has_no_bank_or_qr_block_but_quotation_does(self, chennai):
        chennai.payment_qr.save('qr.png', SimpleUploadedFile('qr.png', png()))
        assert b'Bank details' not in pdf_text(make_doc(chennai, 'dc')) and b'Scan to pay' not in pdf_text(make_doc(chennai, 'dc'))
        quotation = pdf_text(make_doc(chennai, 'quotation'))
        assert b'Bank details' in quotation and b'Scan to pay' in quotation and b'/Subtype /Image' in quotation   # QR is embedded

    def test_logo_is_printed(self, chennai):
        without = pdf_text(make_doc(chennai))
        chennai.logo.save('logo.png', SimpleUploadedFile('logo.png', png((0, 0, 200))))
        assert b'/Subtype /Image' not in without and b'/Subtype /Image' in pdf_text(make_doc(chennai))

    def test_formats_one_and_two_differ_but_share_header_and_footer(self, chennai):
        doc = make_doc(chennai)
        one = pdf_text(doc)
        chennai.doc_format = 2
        chennai.save()
        doc.branch.refresh_from_db()
        two = pdf_text(SalesDocument.objects.get(pk=doc.pk))
        assert one != two
        for body in (one, two):
            assert b'Anupam Bearings' in body and b'33ABCDE1234F1Z5' in body and rb'6205 ZZ \(SKF\)' in body

    def test_watermark_text_and_logo(self, chennai):
        assert b'CONFIDENTIAL' not in pdf_text(make_doc(chennai))
        chennai.watermark_enabled, chennai.watermark_type, chennai.watermark_text = True, 'text', 'CONFIDENTIAL'
        chennai.save()
        assert b'CONFIDENTIAL' in pdf_text(SalesDocument.objects.get(type='quotation'))
        chennai.watermark_type = 'logo'
        chennai.logo.save('logo.png', SimpleUploadedFile('logo.png', png()))
        assert b'/Subtype /Image' in pdf_text(SalesDocument.objects.get(type='quotation'))

    def test_a_branch_without_images_still_prints(self):
        bare = Branch.objects.create(name='Bare')
        assert pdf_text(make_doc(bare)).startswith(b'%PDF')

    def test_terms_from_the_document_win_over_the_branch_default(self, chennai):
        doc = make_doc(chennai, terms=['Delivery in 2 weeks'])
        body = pdf_text(doc)
        assert b'Delivery in 2 weeks' in body and b'Payment within 30 days' not in body

    def test_long_documents_paginate(self, chennai):
        doc = make_doc(chennai, 'dc', items=[dict(item_name=f'Item {n}', qty=1, rate=10) for n in range(60)])
        body = pdf_text(doc)
        assert body.count(b'/Type /Page\n') >= 2 or body.count(b'/Type /Page ') >= 2
        assert b'Item 59' in body and b'Page 2' in body

    def test_text_is_escaped(self, chennai):
        doc = make_doc(chennai, remarks='<b>bold</b> & more', items=[dict(item_name='A <script>', qty=1, rate=1)])
        body = pdf_text(doc)
        assert body[:4] == b'%PDF' and b'(A <) Tj (script) Tj (>) Tj' in body and b'(<) Tj (b) Tj (>) Tj (bold)' in body    # printed literally, not parsed as markup

    def test_enquiry_and_po_cannot_be_printed(self, chennai):
        from threesixty.services.errors import ServiceError
        with pytest.raises(ServiceError):
            pdf_documents.build_pdf(make_doc(chennai, 'enquiry'))


class TestPdfEndpoints:
    def test_preview_print_and_download_are_the_same_pdf(self, chennai, team):
        doc = make_doc(chennai)
        admin = client_for(team['admin'])
        inline, printed, download = (admin.get(f'/360/api/sales-documents/{doc.id}/pdf/'), admin.get(f'/360/api/sales-documents/{doc.id}/print/'),
                                     admin.get(f'/360/api/sales-documents/{doc.id}/pdf/?download=1'))
        assert inline['Content-Type'] == 'application/pdf' and inline.content[:4] == b'%PDF'
        assert inline['Content-Disposition'].startswith('inline') and 'QUO-0001.pdf' in inline['Content-Disposition']
        assert download['Content-Disposition'].startswith('attachment')
        assert printed['Content-Disposition'].startswith('inline')
        assert len(inline.content) == len(printed.content) == len(download.content)

    def test_documents_the_user_cannot_see_are_404(self, chennai, team):
        doc = make_doc(chennai, 'dc')                                    # not created by / assigned to the Sales Manager
        for path in ('pdf/', 'print/', 'export.xlsx'):
            assert client_for(team['sm']).get(f'/360/api/sales-documents/{doc.id}/{path}').status_code == 404
        assert client_for(team['sm']).get('/360/api/sales-documents/%d/pdf/' % 99999).status_code == 404

    def test_sales_manager_can_print_a_quotation_they_can_see(self, chennai, team):
        doc = make_doc(chennai, created_by=team['sm'])
        assert client_for(team['sm']).get(f'/360/api/sales-documents/{doc.id}/pdf/').status_code == 200

    def test_enquiry_pdf_is_a_clear_error(self, chennai, team):
        doc = make_doc(chennai, 'enquiry')
        assert client_for(team['admin']).get(f'/360/api/sales-documents/{doc.id}/pdf/').status_code == 400

    def test_unauthenticated_gets_redirected(self, chennai, client):
        doc = make_doc(chennai)
        assert client.get(f'/360/api/sales-documents/{doc.id}/pdf/').status_code == 302

    def test_save_as_default_terms_is_admin_only(self, chennai, team):
        customer, _ = make_customer('Acme', team['admin'])
        customer.assigned_to.add(team['sm'])
        body = {'type': 'quotation', 'branch_id': chennai.id, 'customer_id': customer.id, 'date': '2026-10-01',
                'items': [{'item_name': 'A', 'qty': 1, 'rate': 1}], 'terms': ['New term one', 'New term two'], 'save_terms_as_default': True}
        call(client_for(team['sm']), 'post', '/360/api/sales-documents/', body)
        chennai.refresh_from_db()
        assert 'New term one' not in chennai.terms
        call(client_for(team['admin']), 'post', '/360/api/sales-documents/', body)
        chennai.refresh_from_db()
        assert chennai.terms == 'New term one\nNew term two'


# ----------------------------------------------------------------------------- Excel
class TestExcel:
    def sheet(self, response):
        return load_workbook(io.BytesIO(response.content)).active

    def test_single_document_export_uses_printed_totals(self, chennai, team):
        doc = make_doc(chennai, items=[dict(item_name='A', qty=2, rate=105, discount=10, tax=18)])
        rows = list(self.sheet(client_for(team['admin']).get(f'/360/api/sales-documents/{doc.id}/export.xlsx')).values)
        flat = [c for r in rows for c in r if c is not None]
        assert 'A' in flat and 190.0 in flat and 34.2 in flat and 224.2 in flat       # amount, tax, total

    def test_list_export_respects_visibility_and_filters(self, chennai, team):
        mine = make_doc(chennai, created_by=team['sm'])
        make_doc(chennai, 'dc')
        rows = list(self.sheet(client_for(team['sm']).get('/360/api/sales-documents/export/?type=quotation')).values)
        assert [r[0] for r in rows[1:]] == [mine.doc_number]
        assert client_for(team['sm']).get('/360/api/sales-documents/export/?type=dc').status_code == 400      # nothing visible -> nothing to export
        pdf = client_for(team['admin']).get('/360/api/sales-documents/export/?format=pdf')
        assert pdf.content[:4] == b'%PDF'

    def test_spreadsheet_formulas_are_neutralised(self, chennai, team):
        customer = Customer.objects.create(name='=HYPERLINK("http://evil","x")')
        SalesDocument.objects.create(type='quotation', doc_number='Q1', branch=chennai, customer=customer, date='2026-10-01')
        rows = list(self.sheet(client_for(team['admin']).get('/360/api/sales-documents/export/?type=quotation')).values)
        assert rows[1][4].startswith("'=")

    def test_customer_export_is_admin_and_manager_only(self, chennai, team):
        make_customer('Acme', team['sm'])
        assert client_for(team['sm']).get('/360/api/customers/export/').status_code == 403
        rows = list(self.sheet(client_for(team['bm']).get('/360/api/customers/export/')).values)
        assert rows[0][0] == 'Customer' and rows[1][0] == 'Acme' and rows[1][-1] == 4
        assert client_for(team['admin']).get('/360/api/customers/export/?format=pdf').content[:4] == b'%PDF'

    def test_nothing_to_export_message(self, chennai, team):
        res = client_for(team['admin']).get('/360/api/customers/export/')
        assert res.status_code == 400 and res.json()['error'] == 'Nothing to export.'
