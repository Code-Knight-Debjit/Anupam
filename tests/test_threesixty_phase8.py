"""Phase 8 (Dashboards & reports) — scope by role, numbers with drill-downs, exports."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone

from threesixty.models import (
    ApprovalRequest, Branch, CallAssignment, CallAttempt, Customer, DocumentCallLog, EmployeeProfile, Interaction, PaymentCollection,
    PaymentContactLog, PaymentReceipt, SalesDocument, SalesDocumentItem, Task,
)
from threesixty.rules import anupam_rules as R
from threesixty.services import reports as report_service
from tests.helpers_360 import ADMIN, BM, BS, SM, call, client_for, make_customer, make_employee

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
D = lambda n: (TODAY - timedelta(days=n)).isoformat()


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
def team(chennai, bengaluru):
    return {'admin': make_employee('admin', ADMIN, [chennai], full_name='Sanjeev'), 'bm': make_employee('bm', BM, [chennai], full_name='Bala'),
            'bs': make_employee('bs', BS, [chennai], full_name='Staff'), 'sm': make_employee('sm', SM, [chennai], full_name='Devdutt'),
            'sm2': make_employee('sm2', SM, [bengaluru], full_name='Ravi')}


def get(user, path, **params):
    return client_for(user).get(f'/360/api/{path}', params)


def doc(branch, customer, user, doc_type='quotation', status='Pending', value='1000', day=0, **extra):
    d = SalesDocument.objects.create(type=doc_type, doc_number=f'{doc_type[:3].upper()}-{SalesDocument.objects.count() + 1:04d}', branch=branch,
                                     customer=customer, date=D(day), created_by=user, order_status=status, total_amount=Decimal(value), **extra)
    return d


def interact(contact, user, kind='Call', day=1, **extra):
    return Interaction.objects.create(contact=contact, type=kind, date=D(day), created_by=user, **extra)


# ----------------------------------------------------------------------------- access
class TestReportAccess:
    NAMES = ['sales-performance', 'customer-activity', 'not-contacted', 'user-performance', 'sales-reports', 'customer-reports',
             'payment-collection', 'interaction-log']

    def test_REQ_RPT_01_sales_manager_has_no_sales_performance_or_customer_activity(self, team):
        index = get(team['sm'], 'reports/').json()
        assert [r['key'] for r in index['reports']] == ['not-contacted', 'user-performance', 'sales-reports', 'customer-reports',
                                                         'payment-collection', 'interaction-log']
        for name in ('sales-performance', 'customer-activity'):
            assert get(team['sm'], f'reports/{name}/').status_code == 403
        for name in self.NAMES[2:]:
            assert get(team['sm'], f'reports/{name}/').status_code == 200, name

    def test_every_report_opens_for_the_other_roles(self, team):
        for who in ('admin', 'bm', 'bs'):
            for name in self.NAMES:
                assert get(team[who], f'reports/{name}/').status_code == 200, (who, name)
        assert get(team['bs'], 'reports/').json()['can_pick_user'] is False and get(team['bm'], 'reports/').json()['can_pick_user'] is True

    def test_unknown_report_and_unauthenticated(self, team, client):
        assert get(team['admin'], 'reports/nope/').status_code == 404
        assert client.get('/360/api/reports/sales-reports/').status_code == 302

    def test_only_admin_and_manager_may_pick_another_user(self, team):
        assert get(team['bs'], 'reports/sales-reports/', user_id=team['sm'].pk).status_code == 403
        assert get(team['sm'], 'reports/user-performance/', user_id=team['bs'].pk).status_code == 403
        assert get(team['sm'], 'reports/sales-reports/', user_id=team['sm'].pk).status_code == 200
        assert get(team['bm'], 'reports/sales-reports/', user_id=team['sm'].pk).status_code == 200

    def test_filters_are_validated(self, team):
        assert get(team['admin'], 'reports/sales-reports/', **{'from': 'x'}).status_code == 400
        assert get(team['admin'], 'reports/sales-reports/', **{'from': D(0), 'to': D(5)}).status_code == 400


# ----------------------------------------------------------------------------- sales performance & customer activity
class TestSalesPerformance:
    @pytest.fixture
    def data(self, team, chennai, bengaluru):
        a, _ = make_customer('Alpha Co', team['admin'])
        b, _ = make_customer('Beta Co', team['admin'])
        c, _ = make_customer('Gamma Co', team['admin'])
        for customer in (a, b, c):
            doc(chennai, customer, team['bs'], 'enquiry', value='0')
        win = doc(chennai, a, team['bs'], status='Win', value='1000', order_value=Decimal('900'))
        doc(chennai, b, team['bs'], status='Pending', value='500')
        doc(bengaluru, c, team['sm'], status='Lose', value='250')
        doc(chennai, a, team['bs'], 'quotation', status='Win', value='3000', order_value=Decimal('2800'), day=200)       # out of range
        return a, b, c

    def test_summary_matches_the_spec_conversion_rules(self, team, data):
        s = get(team['admin'], 'reports/sales-performance/', **{'from': D(30)}).json()['summary']
        assert (s['enquiries'], s['quotations'], s['orders_won']) == (3, 3, 1)
        assert (s['enquiry_to_quotation_pct'], s['quotation_to_win_pct']) == (100, 33)
        spec = R.sales_conversion([{}] * 3, [{'orderStatus': 'Win', 'totalAmount': 1000}, {'orderStatus': 'Pending', 'totalAmount': 500}, {'orderStatus': 'Lose', 'totalAmount': 250}])
        assert (s['enquiry_to_quotation_pct'], s['quotation_to_win_pct']) == (spec['enq_to_quo_pct'], spec['quo_to_win_pct'])
        assert (s['quotation_value'], s['won_value'], s['lost_value'], s['pending_value'], s['order_value']) == ('1750.00', '1000.00', '250.00', '500.00', '900.00')

    def test_by_branch_and_by_person_tables(self, team, data):
        r = get(team['admin'], 'reports/sales-performance/', **{'from': D(30)}).json()
        assert {x['branch']: (x['quotations'], x['won']) for x in r['by_branch']} == {'Chennai': (2, 1), 'Bengaluru': (1, 0)}
        assert {x['person']: x['quotations'] for x in r['by_person']} == {'Staff': 2, 'Devdutt': 1}
        only_blr = get(team['admin'], 'reports/sales-performance/', **{'from': D(30), 'branch_id': Branch.objects.get(name='Bengaluru').pk}).json()
        assert only_blr['summary']['quotations'] == 1

    def test_REQ_RPT_03_every_number_drills_down_to_customers(self, team, data):
        n = get(team['admin'], 'reports/sales-performance/', **{'from': D(30)}).json()['numbers']
        assert {k: v['count'] for k, v in n.items()} == {'enquiries': 3, 'quotations': 3, 'won': 1, 'lost': 1, 'pending': 1}
        assert n['won']['items'][0]['label'] == 'Alpha Co' and n['won']['items'][0]['documents'] == ['Quotation QUO-0004']
        assert {i['label'] for i in n['lost']['items']} == {'Gamma Co'}

    def test_branch_staff_see_only_their_own_documents(self, team, data):
        s = get(team['bs'], 'reports/sales-performance/', **{'from': D(30)}).json()['summary']
        assert (s['enquiries'], s['quotations']) == (3, 2)
        assert get(team['bm'], 'reports/sales-performance/', **{'from': D(30), 'user_id': team['sm'].pk}).json()['summary']['quotations'] == 1

    def test_date_range_decides_what_is_counted(self, team, data):
        s = get(team['admin'], 'reports/sales-performance/', **{'from': D(300), 'to': D(100)}).json()['summary']
        assert (s['quotations'], s['orders_won'], s['won_value']) == (1, 1, '3000.00')

    def test_customer_activity_top_customers_and_new_customers(self, team, data):
        r = get(team['admin'], 'reports/customer-activity/', **{'from': D(30)}).json()
        assert [(t['customer'], t['won_value'], t['orders']) for t in r['top_customers']] == [('Alpha Co', '900.00', 1)]
        assert {c['label'] for c in r['new_customers']} == {'Alpha Co', 'Beta Co', 'Gamma Co'}


# ----------------------------------------------------------------------------- not contacted
class TestNotContacted:
    @pytest.fixture
    def data(self, team):
        called_recently, c1 = make_customer('Called Recently', team['admin'], contacts=('A',), state='TN', area='Guindy')
        old, c2 = make_customer('Called Long Ago', team['admin'], contacts=('B',), state='KA')
        never, _ = make_customer('Never Touched', team['admin'], contacts=('C',), state='TN')
        visited_only, c4 = make_customer('Visited Only', team['admin'], contacts=('D',))
        interact(c1[0], team['admin'], 'Call', 3)
        interact(c1[0], team['admin'], 'Visit', 5)
        interact(c2[0], team['admin'], 'Call', 100)
        interact(c2[0], team['admin'], 'Visit', 120)
        interact(c4[0], team['admin'], 'Visit', 2)
        return called_recently, old, never, visited_only

    def names(self, user, **params):
        res = get(user, 'reports/not-contacted/', **params).json()
        return [r['customer'] for r in res['results']]

    def test_modes_follow_the_spec_rule(self, team, data):
        assert self.names(team['admin'], days=30, mode='both') == ['Never Touched', 'Called Long Ago']       # neither called nor visited
        assert set(self.names(team['admin'], days=30, mode='call')) == {'Never Touched', 'Called Long Ago', 'Visited Only'}
        assert set(self.names(team['admin'], days=30, mode='visit')) == {'Never Touched', 'Called Long Ago'}
        assert set(self.names(team['admin'], days=30, mode='either')) == {'Never Touched', 'Called Long Ago', 'Visited Only'}
        assert self.names(team['admin'], days=30, mode='neither') == self.names(team['admin'], days=30, mode='both')

    def test_never_is_counted_and_longest_gap_comes_first(self, team, data):
        res = get(team['admin'], 'reports/not-contacted/', days=30, mode='either').json()['results']
        assert res[0]['customer'] == 'Never Touched' and res[0]['days_since_call'] is None and res[0]['days_since_visit'] is None
        # "never called" counts as longer than any real gap (spec sort key), so Visited Only (never called) outranks the 120-day gap
        assert [r['customer'] for r in res] == ['Never Touched', 'Visited Only', 'Called Long Ago']
        assert (res[2]['days_since_call'], res[2]['days_since_visit']) == (100, 120)

    def test_days_state_and_area_filters(self, team, data):
        assert self.names(team['admin'], days=200, mode='both') == ['Never Touched']
        assert self.names(team['admin'], days=30, mode='both', state='ka') == ['Called Long Ago']
        assert self.names(team['admin'], days=30, mode='call', area='Guindy') == []
        assert get(team['admin'], 'reports/not-contacted/', mode='sometimes').status_code == 400
        assert get(team['admin'], 'reports/not-contacted/', days='abc').status_code == 400

    def test_REQ_RPT_01_non_admins_only_see_their_related_customers(self, team, data):
        called, old, never, visited = data
        never.assigned_to.add(team['sm'])
        old.created_by = team['sm']
        old.save()
        assert set(self.names(team['sm'], days=30, mode='both')) == {'Never Touched', 'Called Long Ago'}
        assert self.names(team['sm2'], days=30, mode='both') == []
        assert len(self.names(team['bm'], days=30, mode='either')) == 3
        assert self.names(team['bs'], days=30, mode='either') == []                     # Branch Staff: related customers only

    def test_user_filter_for_managers(self, team, data):
        data[2].assigned_to.add(team['sm'])
        assert self.names(team['bm'], days=30, mode='both', user_id=team['sm'].pk) == ['Never Touched']


# ----------------------------------------------------------------------------- user performance
class TestUserPerformance:
    @pytest.fixture
    def data(self, team, chennai):
        customer, contacts = make_customer('Sun Steels', team['admin'], contacts=('A', 'B', 'C'))
        other, oc = make_customer('Other Co', team['admin'], contacts=('X',))
        sm = team['sm']
        interact(contacts[0], sm, 'Call', 2)
        interact(contacts[1], sm, 'Call', 2)
        interact(oc[0], sm, 'Cold Call', 3)                       # an older "Cold Call" counts as a call
        interact(contacts[0], sm, 'Visit', 1)
        interact(contacts[2], sm, 'Visit', 1, is_copy=True, met_with_name='A')       # copies are not counted
        interact(contacts[0], sm, 'Appointment', 10, followup_date=D(9))
        interact(contacts[1], sm, 'Appointment', 10, followup_date=D(9))
        joint = interact(oc[0], team['bs'], 'Visit', 1)
        joint.joint_with.add(sm)
        d = doc(chennai, customer, sm)
        DocumentCallLog.objects.create(document=d, message='asked about price', user=sm)
        pay = PaymentCollection.objects.create(branch=chennai, customer=customer, amount=100, date=D(1), created_by=sm)
        PaymentContactLog.objects.create(payment=pay, message='reminder', user=sm)
        return customer, contacts, other

    def row(self, user, who, **params):
        res = get(user, 'reports/user-performance/', **{'from': D(30), **params}).json()
        return next(r for r in res['results'] if r['user_id'] == who.pk)

    def test_counts_per_person(self, team, data):
        r = self.row(team['admin'], team['sm'])
        assert (r['calls'], r['visits'], r['appointments']) == (3, 2, 2)                    # own visit + the joint one; copy ignored
        assert (r['customers_called'], r['customers_visited']) == (2, 2)                    # distinct customers, not events
        assert r['follow_up_calls'] == 2                                                    # sales log + payment log, kept apart from calls

    def test_REQ_INT_06_appointments_visited_percentage(self, team, data):
        r = self.row(team['admin'], team['sm'])
        assert (r['appointments_visited'], r['appointments_not_visited'], r['visit_pct']) == (1, 1, 50)

    def test_every_number_drills_down(self, team, data):
        r = self.row(team['admin'], team['sm'])
        n = r['numbers']
        assert n['calls']['count'] == 3 and n['visits']['count'] == 2 and n['appointments_not_visited']['count'] == 1
        assert n['customers_called']['count'] == 2 and n['follow_up_calls']['count'] == 2
        assert n['calls']['items'][0]['kind'] == 'interaction' and 'customer' in n['calls']['items'][0]

    def test_includes_a_short_attendance_summary(self, team, data):
        assert set(self.row(team['admin'], team['sm'])['attendance']) >= {'present', 'late', 'absent', 'leave', 'half', 'off', 'worked'}

    def test_non_admins_get_only_themselves(self, team, data):
        res = get(team['sm'], 'reports/user-performance/', **{'from': D(30)}).json()['results']
        assert [r['user_id'] for r in res] == [team['sm'].pk]
        everyone = get(team['bm'], 'reports/user-performance/', **{'from': D(30)}).json()['results']
        assert len(everyone) == 5

    def test_inactive_staff_are_left_out(self, team, data):
        EmployeeProfile.objects.filter(user=team['bs']).update(is_active_employee=False)
        assert team['bs'].pk not in [r['user_id'] for r in get(team['admin'], 'reports/user-performance/').json()['results']]


# ----------------------------------------------------------------------------- sales / customer reports
class TestTabularReports:
    def test_sales_reports_filters_and_own_data(self, team, chennai, bengaluru):
        c, _ = make_customer('Alpha Co', team['admin'])
        doc(chennai, c, team['bs'], 'quotation', 'Win', '100')
        doc(chennai, c, team['bs'], 'proforma', 'Pending', '50')
        doc(bengaluru, c, team['sm'], 'quotation', 'Lose', '25')
        a = get(team['admin'], 'reports/sales-reports/', **{'from': D(30)}).json()
        assert len(a['results']) == 3 and a['total_value'] == '175.00'
        assert len(get(team['admin'], 'reports/sales-reports/', type='quotation').json()['results']) == 2
        assert len(get(team['admin'], 'reports/sales-reports/', status='Win').json()['results']) == 1
        assert len(get(team['bs'], 'reports/sales-reports/').json()['results']) == 2
        assert len(get(team['sm'], 'reports/sales-reports/').json()['results']) == 1
        assert a['numbers']['documents']['count'] == 3

    def test_customer_reports_filters_and_own_data(self, team):
        make_customer('Alpha Co', team['sm'], state='TN', industry='Fans', potential='High')
        make_customer('Beta Co', team['admin'], state='KA')
        assert [r['customer'] for r in get(team['admin'], 'reports/customer-reports/').json()['results']] == ['Alpha Co', 'Beta Co']
        assert [r['customer'] for r in get(team['admin'], 'reports/customer-reports/', state='ka').json()['results']] == ['Beta Co']
        assert [r['customer'] for r in get(team['sm'], 'reports/customer-reports/').json()['results']] == ['Alpha Co']
        assert get(team['sm2'], 'reports/customer-reports/').json()['results'] == []
        row = get(team['admin'], 'reports/customer-reports/', industry='fans').json()['results'][0]
        assert row['contacts'] == 4 and row['potential'] == 'High'


# ----------------------------------------------------------------------------- payments & interaction log
class TestPaymentAndInteractionReports:
    def test_payment_ageing_by_customer_and_own_data(self, team, chennai):
        a, _ = make_customer('Alpha Co', team['admin'])
        b, _ = make_customer('Beta Co', team['admin'])
        for customer, amount, age, user in [(a, 1000, 10, team['bs']), (a, 500, 45, team['bs']), (b, 200, 100, team['sm']), (b, 300, 70, team['bs'])]:
            PaymentCollection.objects.create(branch=chennai, customer=customer, amount=amount, date=D(age), created_by=user)
        paid = PaymentCollection.objects.create(branch=chennai, customer=a, amount=400, date=D(5), created_by=team['bs'])
        PaymentReceipt.objects.create(payment=paid, amount=400, date=D(1))
        PaymentReceipt.objects.create(payment=PaymentCollection.objects.get(amount=1000), amount=250, date=D(1))
        r = get(team['admin'], 'reports/payment-collection/', **{'from': D(365)}).json()
        assert {x['bucket']: (x['count'], x['balance']) for x in r['ageing']} == {
            '0-30 days': (1, '750.00'), '31-60 days': (1, '500.00'), '61-90 days': (1, '300.00'), '90+ days': (1, '200.00')}
        assert r['total_outstanding'] == '1750.00'
        assert {x['customer']: (x['invoiced'], x['received'], x['balance']) for x in r['by_customer']} == {
            'Alpha Co': ('1900.00', '650.00', '1250.00'), 'Beta Co': ('500.00', '0.00', '500.00')}
        assert r['numbers']['90+ days']['count'] == 1
        mine = get(team['sm'], 'reports/payment-collection/', **{'from': D(365)}).json()
        assert mine['total_outstanding'] == '200.00'

    def test_interaction_log_tiles_and_type_filter(self, team, chennai):
        customer, contacts = make_customer('Sun Steels', team['admin'], contacts=('A',))
        interact(contacts[0], team['bs'], 'Call', 1)
        interact(contacts[0], team['bs'], 'Cold Call', 1)
        interact(contacts[0], team['bs'], 'Visit', 1)
        interact(contacts[0], team['sm'], 'Appointment', 1, followup_date=D(0))
        d = doc(chennai, customer, team['sm'])
        DocumentCallLog.objects.create(document=d, message='x', user=team['sm'])
        pay = PaymentCollection.objects.create(branch=chennai, customer=customer, amount=10, date=D(1), created_by=team['sm'])
        PaymentContactLog.objects.create(payment=pay, message='y', user=team['sm'])
        assignment = CallAssignment.objects.create(customer=customer, contact=contacts[0], week_of=D(3), assigned_to=team['bs'], status='Called',
                                                   called_at=timezone.now(), called_by=team['bs'])
        CallAttempt.objects.create(assignment=assignment, reason='Busy', by=team['bs'])
        r = get(team['admin'], 'reports/interaction-log/', **{'from': D(7)}).json()
        assert r['tiles'] == {'Call': 2, 'Visit': 1, 'Appointment': 1, 'Sales Log': 1, 'Payment Log': 1, 'Outreach': 2}
        assert [x['label'].split(' — ')[0] for x in get(team['admin'], 'reports/interaction-log/', interaction_type='Visit').json()['results']] == ['Visit']
        assert get(team['admin'], 'reports/interaction-log/', interaction_type='Dance').status_code == 400
        sm_view = get(team['sm'], 'reports/interaction-log/', **{'from': D(7)}).json()['tiles']
        assert sm_view['Call'] == 0 and sm_view['Appointment'] == 1 and sm_view['Sales Log'] == 1


# ----------------------------------------------------------------------------- exports
class TestExports:
    @pytest.mark.parametrize('name', TestReportAccess.NAMES)
    def test_every_report_exports_to_excel_and_pdf(self, team, chennai, name):
        c, contacts = make_customer('Alpha Co', team['admin'])
        doc(chennai, c, team['admin'], 'enquiry', value='0')
        doc(chennai, c, team['admin'], 'quotation', 'Win', '100', order_value=Decimal('90'))
        interact(contacts[0], team['admin'], 'Call', 1)
        PaymentCollection.objects.create(branch=chennai, customer=c, amount=10, date=D(1), created_by=team['admin'])
        params = {'from': D(30), 'mode': 'either', 'days': 0}
        x = get(team['admin'], f'reports/{name}/', format='xlsx', **params)
        p = get(team['admin'], f'reports/{name}/', format='pdf', **params)
        assert x.status_code == 200 and x['Content-Type'].startswith('application/vnd.openxml'), (name, x.content[:200])
        assert p.status_code == 200 and p.content[:4] == b'%PDF', name

    def test_empty_report_says_nothing_to_export(self, team):
        res = get(team['admin'], 'reports/sales-reports/', format='xlsx')
        assert res.status_code == 400 and res.json()['error'] == 'Nothing to export.'

    def test_sales_manager_cannot_export_a_hidden_report(self, team):
        assert get(team['sm'], 'reports/sales-performance/', format='xlsx').status_code == 403


# ----------------------------------------------------------------------------- dashboards
class TestDashboards:
    def test_REQ_ROLE_05_only_admin_gets_the_company_dashboard(self, team):
        assert get(team['admin'], 'dashboard/admin/').status_code == 200
        for who in ('bm', 'bs', 'sm'):
            assert get(team[who], 'dashboard/admin/').status_code == 403
            assert get(team[who], 'dashboard/personal/').status_code == 200
        assert get(team['admin'], 'dashboard/personal/').status_code == 200

    def test_admin_pipeline_payments_and_approvals(self, team, chennai):
        c, contacts = make_customer('Sun Steels', team['sm'])
        for t, status in [('enquiry', 'Pending'), ('enquiry', 'Completed'), ('quotation', 'Pending'), ('quotation', 'Win'), ('proforma', 'Pending'), ('po', 'Part Pending'), ('po', 'Completed')]:
            doc(chennai, c, team['admin'], t, status)
        dc = doc(chennai, c, team['admin'], 'dc', '')
        SalesDocumentItem.objects.create(document=dc, item_name='A', qty=5)
        done = doc(chennai, c, team['admin'], 'dc', '')
        item = SalesDocumentItem.objects.create(document=done, item_name='A', qty=5)
        item.invoice_log.create(bill_number='B1', qty_invoiced=5)
        for n, amount in enumerate([100, 700, 300, 50, 900, 20, 600, 5]):
            PaymentCollection.objects.create(branch=chennai, customer=c, amount=amount, date=D(n), created_by=team['admin'])
        call(client_for(team['sm']), 'delete', f'/360/api/customers/{c.pk}/')
        r = get(team['admin'], 'dashboard/admin/').json()
        assert r['pipeline'] == {'open_enquiries': 1, 'open_quotations': 1, 'open_proformas': 1, 'pending_pos': 1, 'challans_pending_invoicing': 1}
        assert r['payments']['outstanding_total'] == '2675.00' and [p['balance'] for p in r['payments']['top']] == ['900.00', '700.00', '600.00', '300.00', '100.00', '50.00']
        assert r['approvals']['pending'] == 1 and r['approvals']['latest'][0]['by'] == 'Devdutt'

    def test_admin_employee_table_activity_feed_and_drill(self, team, chennai):
        c, contacts = make_customer('Sun Steels', team['sm'])
        doc(chennai, c, team['sm'], 'quotation')
        doc(chennai, c, team['sm'], 'enquiry')
        interact(contacts[0], team['sm'], 'Call', 1)
        r = get(team['admin'], 'dashboard/admin/').json()
        row = next(e for e in r['employees'] if e['user_id'] == team['sm'].pk)
        assert (row['customers_added'], row['contacts_added'], row['documents_raised']) == (1, 4, 2) and row['last_activity']
        assert len(r['activity']) <= 10 and any('raised Quotation' in a['text'] for a in r['activity'])
        assert len(get(team['admin'], 'dashboard/admin/', activity_limit=2).json()['activity']) == 2
        drill = get(team['admin'], 'dashboard/admin/drill/', user_id=team['sm'].pk, what='documents').json()
        assert drill['count'] == 2
        assert get(team['admin'], 'dashboard/admin/drill/', user_id=team['sm'].pk, what='customers').json()['items'][0]['label'] == 'Sun Steels'
        assert get(team['admin'], 'dashboard/admin/drill/', user_id=team['sm'].pk, what='contacts').json()['count'] == 4
        assert get(team['admin'], 'dashboard/admin/drill/', user_id=1, what='nope').status_code == 400
        assert get(team['bm'], 'dashboard/admin/drill/', user_id=1, what='customers').status_code == 403

    def test_admin_attendance_strip_and_calendar(self, team, chennai):
        Task.objects.create(title='Visit Sun', assigned_to=team['sm'], due_date=TODAY, created_by=team['admin'])
        r = get(team['admin'], 'dashboard/admin/').json()
        assert sum(r['attendance_today'].values()) == 5 and r['calendar'][TODAY.isoformat()][0]['title'] == 'Visit Sun'

    def test_personal_dashboard_numbers(self, team, chennai):
        sm = team['sm']
        c, contacts = make_customer('Sun Steels', sm)
        Task.objects.create(title='A', assigned_to=sm, due_date=TODAY - timedelta(days=2), created_by=team['admin'])
        Task.objects.create(title='B', assigned_to=sm, due_date=TODAY, created_by=team['admin'])
        Task.objects.create(title='C', assigned_to=sm, due_date=TODAY + timedelta(days=3), created_by=team['admin'])
        Task.objects.create(title='D', assigned_to=sm, status='Completed', due_date=TODAY, created_by=team['admin'])
        Task.objects.create(title='Not mine', assigned_to=team['bs'], due_date=TODAY, created_by=team['admin'])
        CallAssignment.objects.create(customer=c, contact=contacts[0], week_of=D(1), assigned_to=sm)
        CallAssignment.objects.create(customer=c, contact=contacts[1], week_of=D(1), assigned_to=sm, status='Called')
        interact(contacts[0], sm, 'Call', 1)
        interact(contacts[0], sm, 'Appointment', 5, followup_date=D(4))
        interact(contacts[1], sm, 'Appointment', 5, followup_date=D(4))
        interact(contacts[0], sm, 'Visit', 2)
        doc(chennai, c, sm, 'enquiry')
        doc(chennai, c, sm, 'quotation')
        doc(chennai, c, sm, 'quotation', 'Win')
        doc(chennai, c, team['admin'], 'quotation')                                      # someone else's
        pay = PaymentCollection.objects.create(branch=chennai, customer=c, amount=100, date=D(1), created_by=sm)
        PaymentCollection.objects.create(branch=chennai, customer=c, amount=50, date=D(1), created_by=sm)
        PaymentReceipt.objects.create(payment=pay, amount=100, date=D(0))
        r = get(sm, 'dashboard/personal/', **{'from': D(30)}).json()
        assert r['tasks'] == {'pending': 3, 'due_today': 1, 'overdue': 1}
        assert r['outreach_pending'] == 1
        assert r['activity'] == {'calls_done': 1, 'appointments_taken': 2, 'visits_made': 1, 'appointments_not_visited': 1, 'visit_pct': 50}
        assert r['pending'] == {'enquiries': 1, 'quotations': 1, 'proformas': 0, 'challans': 0, 'pos': 0}
        assert r['payments'] == {'pending': 1, 'completed': 1}
        assert {t['title'] for t in r['calendar'][TODAY.isoformat()]} == {'B', 'D'}            # the viewer's own tasks, by due date
        assert 'month' in r['attendance'] and r['period']['from'] == D(30)

    def test_personal_dashboard_period_filter(self, team):
        c, contacts = make_customer('Sun Steels', team['sm'])
        interact(contacts[0], team['sm'], 'Call', 1)
        interact(contacts[0], team['sm'], 'Call', 60)
        assert get(team['sm'], 'dashboard/personal/', **{'from': D(30)}).json()['activity']['calls_done'] == 1
        assert get(team['sm'], 'dashboard/personal/', **{'from': D(90)}).json()['activity']['calls_done'] == 2

    def test_personal_dashboard_ignores_a_user_id(self, team):
        c, contacts = make_customer('Sun Steels', team['sm'])
        interact(contacts[0], team['sm'], 'Call', 1)
        assert get(team['bs'], 'dashboard/personal/', user_id=team['sm'].pk).json()['activity']['calls_done'] == 0
