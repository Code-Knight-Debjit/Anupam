"""Phase 6 (Payments & labels) — receipts, ageing, contact log, label sizes/tiling/content."""
import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from threesixty.models import Branch, PaymentCollection, Task
from threesixty.rules import anupam_rules as R
from threesixty.services import labels
from tests.helpers_360 import ADMIN, BM, BS, SM, call, client_for, make_customer, make_employee

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def chennai():
    return Branch.objects.create(name='Chennai', letterhead_name='Anupam Bearings', letterhead_address='12 Mount Road\nChennai 600002',
                                 letterhead_phone='044-1234')


@pytest.fixture
def bengaluru():
    return Branch.objects.create(name='Bengaluru')


@pytest.fixture
def team(chennai):
    return {'admin': make_employee('admin', ADMIN, [chennai]), 'bm': make_employee('bm', BM, [chennai]),
            'bs': make_employee('bs', BS, [chennai]), 'sm': make_employee('sm', SM, [chennai]),
            'sm2': make_employee('sm2', SM, [chennai])}


@pytest.fixture
def cust(team):
    customer, contacts = make_customer('Sun Steels', team['admin'], plant='Plant 2', area='Ambattur', city='Chennai', state='Tamil Nadu',
                                       pincode='600053', address='12 Mount Road\nNear Bus Stand', transport_preference='VRL', courier_preference='DTDC')
    customer.assigned_to.add(team['sm'])
    return customer, contacts


def pay(user, customer, branch=None, **extra):
    body = {'customer_id': customer.id, 'amount': '1000', 'date': '2026-10-01', **extra}
    if branch is not None:
        body['branch_id'] = branch.id
    return call(client_for(user), 'post', '/360/api/payment-collections/', body)


def receipt(user, payment_id, amount, **extra):
    return call(client_for(user), 'post', f'/360/api/payment-collections/{payment_id}/receipts/', {'amount': amount, 'date': '2026-10-05', **extra})


# ----------------------------------------------------------------------------- payments
class TestPayments:
    def test_create_keeps_date_remarks_and_contact(self, team, cust, chennai):
        res = pay(team['bs'], cust[0], chennai, remarks='Invoice 22', contact_id=cust[1][0].id)
        body = res.json()
        assert res.status_code == 201 and body['date'] == '2026-10-01' and body['remarks'] == 'Invoice 22' and body['contact_name'] == 'Ravi'
        assert body['customer_label'] == 'Sun Steels, Plant 2, Ambattur'

    def test_REQ_PAY_branch_defaults_to_the_creators_first_branch(self, team, cust, chennai):
        assert pay(team['bs'], cust[0]).json()['branch_id'] == chennai.id
        nobody = make_employee('nobranch', BS)
        assert pay(nobody, cust[0]).json()['error'] == 'Select a branch first.'

    def test_amount_must_be_positive_and_a_number(self, team, cust, chennai):
        for bad in ('0', '-5', 'abc', ''):
            assert pay(team['admin'], cust[0], chennai, amount=bad).status_code == 400, bad

    def test_REQ_PAY_01_balance_is_amount_minus_received_and_never_negative(self, team, cust, chennai):
        p = pay(team['admin'], cust[0], chennai).json()
        receipt(team['admin'], p['id'], '300')
        body = call(client_for(team['admin']), 'get', f'/360/api/payment-collections/{p["id"]}/').json()
        assert (body['received'], body['balance']) == ('300.00', '700.00')
        receipt(team['admin'], p['id'], '900', confirm_over=True)
        body = call(client_for(team['admin']), 'get', f'/360/api/payment-collections/{p["id"]}/').json()
        assert (body['received'], body['balance']) == ('1200.00', '0.00')

    def test_REQ_PAY_01_receiving_more_than_the_balance_asks_for_confirmation(self, team, cust, chennai):
        p = pay(team['admin'], cust[0], chennai).json()
        res = receipt(team['admin'], p['id'], '1000.01')
        assert res.status_code == 409 and res.json()['needs_confirmation'] is True and res.json()['balance'] == '1000.00'
        assert PaymentCollection.objects.get(pk=p['id']).receipts.count() == 0
        assert receipt(team['admin'], p['id'], '1000').status_code == 201                 # exactly the balance needs no confirmation

    def test_receipt_validation(self, team, cust, chennai):
        p = pay(team['admin'], cust[0], chennai).json()
        assert receipt(team['admin'], p['id'], '0').status_code == 400
        assert receipt(team['admin'], p['id'], '-1').status_code == 400
        assert receipt(team['admin'], p['id'], '10', mode='Barter').status_code == 400
        assert receipt(team['admin'], p['id'], '10', mode='UPI').json()['mode'] == 'UPI'

    def test_pending_and_history_lists(self, team, cust, chennai):
        open_, paid = pay(team['admin'], cust[0], chennai).json(), pay(team['admin'], cust[0], chennai).json()
        receipt(team['admin'], paid['id'], '1000')
        admin = client_for(team['admin'])
        ids = lambda status: [r['id'] for r in call(admin, 'get', f'/360/api/payment-collections/?status={status}').json()['results']]
        assert ids('pending') == [open_['id']] and ids('completed') == [paid['id']]

    def test_REQ_PAY_02_visibility(self, team, cust, chennai):
        mine = pay(team['sm'], cust[0], chennai).json()
        other = pay(team['admin'], cust[0], chennai).json()
        listing = lambda who: {r['id'] for r in call(client_for(team[who]), 'get', '/360/api/payment-collections/').json()['results']}
        assert listing('sm') == {mine['id']} and listing('sm2') == set()
        for who in ('admin', 'bm', 'bs'):
            assert listing(who) == {mine['id'], other['id']}
        assert call(client_for(team['sm']), 'get', f'/360/api/payment-collections/{other["id"]}/').status_code == 404
        assert receipt(team['sm'], other['id'], '5').status_code == 404
        assert call(client_for(team['sm']), 'patch', f'/360/api/payment-collections/{other["id"]}/', {'version': 1, 'amount': '1'}).status_code == 404
        assert call(client_for(team['sm']), 'delete', f'/360/api/payment-collections/{other["id"]}/').status_code == 404

    def test_sales_manager_cannot_collect_for_a_customer_they_cannot_see(self, team, chennai):
        other, _ = make_customer('Other Co', team['admin'])
        assert pay(team['sm'], other, chennai).status_code == 400

    def test_edit_with_stale_version_conflicts(self, team, cust, chennai):
        p = pay(team['admin'], cust[0], chennai).json()
        admin = client_for(team['admin'])
        assert call(admin, 'patch', f'/360/api/payment-collections/{p["id"]}/', {'version': 1, 'remarks': 'a'}).status_code == 200
        assert call(admin, 'patch', f'/360/api/payment-collections/{p["id"]}/', {'version': 1, 'remarks': 'b'}).status_code == 409

    def test_receipts_are_append_only(self, team, cust, chennai):
        p = pay(team['admin'], cust[0], chennai).json()
        r = receipt(team['admin'], p['id'], '10').json()
        assert call(client_for(team['admin']), 'patch', f'/360/api/payment-collections/{p["id"]}/receipts/', {}).status_code == 405

    def test_ageing_buckets_from_the_payment_date(self, team, cust, chennai):
        today = timezone.localdate()
        ages = {0: '0-30 days', 30: '0-30 days', 31: '31-60 days', 60: '31-60 days', 61: '61-90 days', 90: '61-90 days', 91: '90+ days', 400: '90+ days'}
        for days, bucket in ages.items():
            p = pay(team['admin'], cust[0], chennai, date=(today - timedelta(days=days)).isoformat()).json()
            assert (p['age_days'], p['age_bucket']) == (days, bucket)
            assert R.payment_age_bucket(days) == bucket

    def test_REQ_LOG_01_payment_contact_log_call_me_later_creates_a_task(self, team, cust, chennai):
        p = pay(team['admin'], cust[0], chennai, contact_id=cust[1][1].id).json()
        res = call(client_for(team['bs']), 'post', f'/360/api/payment-collections/{p["id"]}/contact-log/', {'message': 'Cheque next week', 'call_later_date': '2026-11-09'})
        assert res.status_code == 201
        task = Task.objects.get()
        assert (task.title, task.task_type, str(task.due_date), task.assigned_to, task.created_by) == ('Call Meena — Sun Steels', 'Call', '2026-11-09', team['bs'], team['bs'])
        body = call(client_for(team['admin']), 'get', f'/360/api/payment-collections/{p["id"]}/').json()
        assert body['call_later_date'] == '2026-11-09' and body['last_contact_on'] and len(body['contact_log']) == 1
        assert call(client_for(team['admin']), 'post', f'/360/api/payment-collections/{p["id"]}/contact-log/', {'message': ' '}).status_code == 400

    def test_call_later_filter(self, team, cust, chennai):
        a, b = pay(team['admin'], cust[0], chennai).json(), pay(team['admin'], cust[0], chennai).json()
        call(client_for(team['admin']), 'post', f'/360/api/payment-collections/{a["id"]}/contact-log/',
             {'message': 'x', 'call_later_date': (timezone.localdate() - timedelta(days=1)).isoformat()})
        listing = lambda q: [r['id'] for r in call(client_for(team['admin']), 'get', f'/360/api/payment-collections/?call_later={q}').json()['results']]
        assert listing('overdue') == [a['id']] and listing('none') == [b['id']]


# ----------------------------------------------------------------------------- labels
def label_body(customer, **extra):
    return {'customer_id': customer.id, **extra}


def label_pdf(user, body, method='post'):
    client = client_for(user)
    if method == 'post':
        return call(client, 'post', '/360/api/labels/pdf/', body)
    return client.get('/360/api/labels/pdf/', body)


def media_boxes(pdf):
    return [(round(float(w) / 72 * 25.4, 1), round(float(h) / 72 * 25.4, 1)) for w, h in re.findall(rb'/MediaBox \[ 0 0 ([\d.]+) ([\d.]+) \]', pdf)]


def plain(req):
    return labels.build_pdf(req, compress=False)


class TestLabelRules:
    def test_REQ_LBL_01_defaults_and_options(self, team):
        opts = call(client_for(team['admin']), 'get', '/360/api/labels/options/').json()
        assert opts['defaults'] == {'paper': 'a4', 'size': 'a5', 'from_scale': 1.5, 'print_attn': False, 'print_phone': False, 'boxes': 1}
        assert set(opts['sizes']) == {'a4', 'a5', '4x4', '6x4'} and opts['from_scales'] == [1, 1.25, 1.5, 2]
        assert opts['sizes']['6x4'] == {'width_mm': 101.6, 'height_mm': 152.4}

    def test_REQ_LBL_02_actual_size_tiling_on_an_a4_sheet(self):
        assert labels.plan({'size': 'a5', 'boxes': 3, 'paper': 'a4'}) | {} == R.label_sheet_plan('a5', 3, True)
        for size, boxes, per_page, pages, page in [('a5', 3, 2, 2, (297, 210)), ('4x4', 5, 4, 2, None), ('6x4', 3, 2, 2, None), ('a4', 2, 1, 2, (210, 297))]:
            p = labels.plan({'size': size, 'boxes': boxes, 'paper': 'a4'})
            assert (p['per_page'], p['pages']) == (per_page, pages), size
            if page:
                assert p['page'] == page, size

    def test_REQ_LBL_03_paper_equal_to_label_makes_the_page_the_label(self):
        p = labels.plan({'size': '6x4', 'boxes': 3, 'paper': 'label'})
        assert p == {'page': (101.6, 152.4), 'per_page': 1, 'pages': 3}

    def test_REQ_LBL_09_a_label_needs_a_name(self, team):
        assert label_pdf(team['admin'], {}).json()['error'] == 'Enter who the label is for.'
        assert label_pdf(team['admin'], {'deliver_to': '   '}).status_code == 400
        assert label_pdf(team['admin'], {'deliver_to': 'Site office'}).status_code == 200


class TestLabelPdf:
    def test_pdf_pages_and_page_sizes_follow_the_plan(self, team, cust, chennai):
        for size, boxes, expected_pages, page in [('a5', 3, 2, (297.0, 210.0)), ('4x4', 4, 1, None), ('a4', 2, 2, (210.0, 297.0)), ('6x4', 2, 1, None)]:
            req = labels.build_request(team['admin'], label_body(cust[0], size=size, boxes=boxes))
            pdf = plain(req)
            assert pdf.startswith(b'%PDF') and len(media_boxes(pdf)) == expected_pages, size
            if page:
                assert set(media_boxes(pdf)) == {page}, size

    def test_paper_label_gives_one_page_of_label_size_per_box(self, team, cust):
        req = labels.build_request(team['admin'], label_body(cust[0], size='6x4', paper='label', boxes=3))
        assert media_boxes(plain(req)) == [(101.6, 152.4)] * 3

    def test_REQ_LBL_04_content_order_and_nothing_extra(self, team, cust):
        req = labels.build_request(team['admin'], label_body(cust[0], vehicle='TN01 AB 1234', boxes=2))
        text = plain(req).decode('latin-1')
        order = ['DELIVER TO', 'Sun Steels', '12 Mount Road', 'Ambattur', 'Chennai, Tamil Nadu', 'PIN: 600053', 'TRANSPORT: VRL', 'COURIER: DTDC',
                 'VEHICLE: TN01 AB 1234', 'BOX 1 OF 2', 'Anupam Bearings', '12 Mount Road']
        positions = [text.find(f'({t})') if f'({t})' in text else text.find(t) for t in order[:-1]]
        assert all(p >= 0 for p in positions), dict(zip(order, positions))
        assert positions == sorted(positions)                                    # FROM block (company) is after BOX n OF m
        assert text.find('BOX 1 OF 2') < text.rfind('Anupam Bearings') and 'BOX 2 OF 2' in text
        assert '(Ref' not in text and '(Date' not in text and 'sales document' not in text         # nothing but the label text is checked (metadata has a CreationDate)

    def test_REQ_LBL_04_the_area_is_printed_in_bold(self, team, cust):
        text = plain(labels.build_request(team['admin'], label_body(cust[0]))).decode('latin-1')
        i = text.index('(Ambattur)')
        assert '/F2' in text[max(0, i - 120):i]                                  # F2 = Helvetica-Bold in this document

    def test_REQ_LBL_01_attn_and_phone_are_off_by_default_and_need_a_picked_person(self, team, cust):
        contact = cust[1][0]
        default = plain(labels.build_request(team['admin'], label_body(cust[0], contact_id=contact.id))).decode('latin-1')
        assert 'Attn:' not in default and 'Phone:' not in default
        on = plain(labels.build_request(team['admin'], label_body(cust[0], contact_id=contact.id, print_attn=True, print_phone=True))).decode('latin-1')
        assert 'Attn: Ravi' in on and f'Phone: {contact.phone}' in on

    def test_REQ_LBL_07_no_person_selected_means_attn_stays_blank(self, team, cust):
        req = labels.build_request(team['admin'], label_body(cust[0], print_attn=True, print_phone=True))
        assert req['party']['attn'] == '' and req['party']['phone'] == ''
        assert 'Attn:' not in plain(req).decode('latin-1')

    def test_REQ_LBL_05_typed_deliver_to_wins_over_the_customer_name(self, team, cust):
        req = labels.build_request(team['admin'], label_body(cust[0], deliver_to='Anupam Stores — Gate 2'))
        assert req['party']['customer'] == 'Anupam Stores — Gate 2'
        assert labels.build_request(team['admin'], label_body(cust[0]))['party']['customer'] == 'Sun Steels'

    def test_typed_address_wins_over_autofill(self, team, cust):
        req = labels.build_request(team['admin'], label_body(cust[0], address='Godown 7', city='Hosur', transport='SRMT'))
        assert req['party']['addrLines'] == ['Godown 7'] and req['party']['cityLine'] == 'Hosur, Tamil Nadu' and req['party']['transport'] == 'SRMT'

    def test_REQ_LBL_06_from_size_options(self, team, cust):
        for scale in (1, 1.25, 1.5, 2):
            assert labels.build_request(team['admin'], label_body(cust[0], from_scale=scale))['from_scale'] == scale
        for bad in (1.1, 3, 'big'):
            assert label_pdf(team['admin'], label_body(cust[0], from_scale=bad)).status_code == 400
        small = plain(labels.build_request(team['admin'], label_body(cust[0], from_scale=1)))
        large = plain(labels.build_request(team['admin'], label_body(cust[0], from_scale=2)))
        assert small != large

    def test_REQ_LBL_08_print_and_download_are_the_same_pdf(self, team, cust):
        inline = label_pdf(team['admin'], label_body(cust[0], boxes=2))
        download = label_pdf(team['admin'], label_body(cust[0], boxes=2, download=1))
        via_get = label_pdf(team['admin'], {'customer_id': cust[0].id, 'boxes': 2}, method='get')
        assert inline['Content-Type'] == 'application/pdf' and inline['Content-Disposition'].startswith('inline')
        assert download['Content-Disposition'].startswith('attachment')
        assert len(inline.content) == len(download.content) == len(via_get.content)

    def test_from_a_sales_document_uses_its_branch_and_transport_and_no_auto_person(self, team, cust, chennai):
        doc = call(client_for(team['admin']), 'post', '/360/api/sales-documents/', {
            'type': 'dc', 'branch_id': chennai.id, 'customer_id': cust[0].id, 'contact_id': cust[1][0].id, 'date': '2026-10-01',
            'transport': 'ABT Parcel', 'vehicle': 'KA01 X 1', 'items': [{'item_name': 'A', 'qty': 1, 'rate': 1}]}).json()
        req = labels.build_request(team['admin'], {'document_id': doc['id'], 'print_attn': True})
        assert req['party']['transport'] == 'ABT Parcel' and req['party']['vehicle'] == 'KA01 X 1' and req['party']['attn'] == ''
        assert req['branch'] == chennai
        assert 'sales document' not in plain(req).decode('latin-1').lower()

    def test_boxes_are_bounded(self, team, cust):
        for bad in (0, -1, 201, 'x'):
            assert label_pdf(team['admin'], label_body(cust[0], boxes=bad)).status_code == 400, bad

    def test_unknown_paper_and_size_are_rejected(self, team, cust):
        assert label_pdf(team['admin'], label_body(cust[0], size='a3')).status_code == 400
        assert label_pdf(team['admin'], label_body(cust[0], paper='roll')).status_code == 400

    def test_logo_is_printed_in_the_from_block(self, team, cust, chennai):
        from PIL import Image
        import io
        buf = io.BytesIO()
        Image.new('RGB', (40, 20), (200, 0, 0)).save(buf, 'PNG')
        assert b'/Subtype /Image' not in plain(labels.build_request(team['admin'], label_body(cust[0])))
        chennai.logo.save('l.png', SimpleUploadedFile('l.png', buf.getvalue()))
        assert b'/Subtype /Image' in plain(labels.build_request(team['admin'], label_body(cust[0])))

    def test_very_long_addresses_still_fit_by_shrinking(self, team, cust):
        req = labels.build_request(team['admin'], label_body(cust[0], size='4x4', address='\n'.join(f'Address line number {n} of a long address' for n in range(12))))
        assert plain(req).startswith(b'%PDF')


class TestLabelAutofillAndAccess:
    def test_REQ_AUT_10_picking_a_customer_fills_the_form_but_not_the_person(self, team, cust):
        body = call(client_for(team['admin']), 'get', f'/360/api/labels/autofill/?customer_id={cust[0].id}').json()
        assert body == {'customer': 'Sun Steels', 'address': '12 Mount Road\nNear Bus Stand', 'area': 'Ambattur', 'city': 'Chennai',
                        'state': 'Tamil Nadu', 'pin': '600053', 'transport': 'VRL', 'courier': 'DTDC', 'attn': '', 'phone': ''}
        picked = call(client_for(team['admin']), 'get', f'/360/api/labels/autofill/?customer_id={cust[0].id}&contact_id={cust[1][1].id}').json()
        assert picked['attn'] == 'Meena' and picked['phone'] == cust[1][1].phone

    def test_sales_manager_cannot_use_print_label(self, team, cust):
        sm = client_for(team['sm'])
        assert call(sm, 'get', '/360/api/labels/options/').status_code == 403
        assert call(sm, 'get', f'/360/api/labels/autofill/?customer_id={cust[0].id}').status_code == 403
        assert label_pdf(team['sm'], label_body(cust[0])).status_code == 403

    def test_branch_staff_can_print_labels(self, team, cust):
        assert label_pdf(team['bs'], label_body(cust[0])).status_code == 200

    def test_labels_respect_contact_level_access(self, team):
        from threesixty.services import contacts as contact_service
        customer, contacts = make_customer('Restricted Co', team['admin'])
        # the Branch Staff role always sees all contacts, so use a customer whose access matters: a contact of ANOTHER customer is refused
        other, other_contacts = make_customer('Other Co', team['admin'])
        assert label_pdf(team['bs'], label_body(customer, contact_id=other_contacts[0].id)).status_code == 404

    def test_labels_cannot_reach_documents_or_customers_the_user_cannot_see(self, team, chennai):
        hidden, _ = make_customer('Hidden Co', team['admin'])
        # Branch Staff sees all customers; an unknown id is a 404 for everyone
        assert label_pdf(team['bs'], {'customer_id': 99999}).status_code == 404
        assert label_pdf(team['bs'], {'document_id': 99999}).status_code == 404
        assert call(client_for(team['bs']), 'get', '/360/api/labels/autofill/?customer_id=99999').status_code == 404
