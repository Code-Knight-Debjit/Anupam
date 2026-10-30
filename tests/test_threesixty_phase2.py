"""Phase 2 (Customers) — contact-level access, approvals, search, pins, imports, exports."""
import io

import pytest
from django.core.cache import cache
from openpyxl import Workbook

from threesixty.models import (
    ApprovalRequest, Branch, Contact, ContactAccess, Customer, EmployeeProfile, Interaction, Notification,
)
from threesixty.services import contacts as contact_service
from threesixty.services import customers as customer_service
from tests.helpers_360 import ADMIN, BM, BS, SM, call, client_for, make_customer, make_employee

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def chennai():
    return Branch.objects.create(name='Chennai')


@pytest.fixture
def team(chennai):
    return {
        'admin': make_employee('admin', ADMIN, [chennai]),
        'bm': make_employee('bm', BM, [chennai]),
        'bs': make_employee('bs', BS, [chennai]),
        'sm': make_employee('sm', SM, [chennai]),
        'sm2': make_employee('sm2', SM, [chennai]),
    }


# ----------------------------------------------------------------------------- visibility
class TestVisibility:
    def test_REQ_CUS_01_roles_and_sales_manager_scope(self, team):
        mine, _ = make_customer('Mine Co', team['sm'])
        assigned, _ = make_customer('Assigned Co', team['admin'])
        assigned.assigned_to.add(team['sm'])
        other, _ = make_customer('Other Co', team['admin'])
        theirs, _ = make_customer('Ravis Co', team['sm2'])
        names = lambda who: {r['name'] for r in call(client_for(team[who]), 'get', '/360/api/customers/').json()['results']}
        assert names('sm') == {'Mine Co', 'Assigned Co'}
        for role in ('admin', 'bm', 'bs'):
            assert names(role) == {'Mine Co', 'Assigned Co', 'Other Co', 'Ravis Co'}

    def test_sales_manager_cannot_reach_other_customers_by_guessing_ids(self, team):
        other, contacts = make_customer('Other Co', team['admin'])
        inter = Interaction.objects.create(contact=contacts[0], type='Call', date='2026-01-01', created_by=team['admin'])
        sm = client_for(team['sm'])
        for method, url, body in [
            ('get', f'/360/api/customers/{other.id}/', None),
            ('patch', f'/360/api/customers/{other.id}/', {'name': 'Hacked', 'version': 1}),
            ('delete', f'/360/api/customers/{other.id}/', None),
            ('get', f'/360/api/contacts/{contacts[0].id}/', None),
            ('patch', f'/360/api/contacts/{contacts[0].id}/', {'name': 'Hacked'}),
            ('get', f'/360/api/interactions/{inter.id}/', None),
            ('post', f'/360/api/customers/{other.id}/assign/', {'user_id': team['sm'].id}),
        ]:
            res = call(sm, method, url, body)
            assert res.status_code in (403, 404), (method, url, res.status_code)
        other.refresh_from_db()
        assert other.name == 'Other Co' and ApprovalRequest.objects.count() == 0
        # list endpoints return nothing rather than someone else's rows
        assert call(sm, 'get', f'/360/api/customers/{other.id}/contacts/').json()['results'] == []
        assert call(sm, 'get', f'/360/api/contacts/{contacts[0].id}/interactions/').json()['results'] == []
        assert call(sm, 'get', '/360/api/contacts/').json()['results'] == []
        assert call(sm, 'get', '/360/api/interactions/').json()['results'] == []

    def test_title_case_on_save(self, team):
        res = call(client_for(team['admin']), 'post', '/360/api/customers/',
                   {'name': 'sun steels-ltd', 'address': '12 mount road', 'area': 'ambattur', 'city': 'chennai'})
        assert res.status_code == 201
        body = res.json()
        assert (body['name'], body['address'], body['area'], body['city']) == ('Sun Steels-Ltd', '12 Mount Road', 'Ambattur', 'Chennai')
        assert body['created_by_role'] == ADMIN


# ----------------------------------------------------------------------------- contact-level access
class TestContactAccess:
    def test_REQ_CUS_02_assigned_person_sees_only_shared_contacts(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'])
        contact_service.assign_customer(customer, team['sm'], [contacts[0].id, contacts[1].id])
        sm = client_for(team['sm'])
        names = {c['name'] for c in call(sm, 'get', f'/360/api/customers/{customer.id}/contacts/').json()['results']}
        assert names == {'Ravi', 'Meena'}
        assert call(sm, 'get', f'/360/api/contacts/{contacts[2].id}/').status_code == 404
        assert {c['name'] for c in call(sm, 'get', '/360/api/contacts/').json()['results']} == {'Ravi', 'Meena'}
        # hidden contact's interactions are hidden too
        hidden = Interaction.objects.create(contact=contacts[2], type='Call', date='2026-01-01', created_by=team['admin'])
        assert call(sm, 'get', f'/360/api/interactions/{hidden.id}/').status_code == 404

    def test_REQ_CUS_02_admin_bm_staff_and_creator_still_see_all(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm2'])      # created by sm2
        contact_service.assign_customer(customer, team['sm'], [contacts[0].id])
        for who in ('admin', 'bm', 'bs', 'sm2'):
            assert len(call(client_for(team[who]), 'get', f'/360/api/customers/{customer.id}/contacts/').json()['results']) == 4, who

    def test_REQ_CUS_03_selecting_all_or_none_leaves_no_restriction(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'])
        contact_service.assign_customer(customer, team['sm'], [c.id for c in contacts])
        assert not ContactAccess.objects.exists()
        contact_service.assign_customer(customer, team['sm'], None)
        assert not ContactAccess.objects.exists()
        contact_service.assign_customer(customer, team['sm'], [contacts[0].id])
        assert ContactAccess.objects.count() == 1
        contact_service.assign_customer(customer, team['sm'], [c.id for c in contacts])    # widen again
        assert not ContactAccess.objects.exists()

    def test_REQ_CUS_04_deassign_removes_restriction(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'])
        contact_service.assign_customer(customer, team['sm'], [contacts[0].id])
        contact_service.deassign_customer(customer, team['sm'])
        assert not ContactAccess.objects.exists() and not customer.assigned_to.filter(pk=team['sm'].pk).exists()

    def test_REQ_CUS_05_several_people_each_with_own_selection(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'])
        contact_service.assign_customer(customer, team['sm'], [contacts[0].id, contacts[1].id])
        contact_service.assign_customer(customer, team['sm2'], [contacts[3].id])
        assert {c.name for c in contact_service.visible_contacts(team['sm'], customer)} == {'Ravi', 'Meena'}
        assert {c.name for c in contact_service.visible_contacts(team['sm2'], customer)} == {'Anu'}

    def test_REQ_CUS_06_creator_always_sees_all(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        ContactAccess.objects.create(customer=customer, user=team['sm'], contact=contacts[0])   # stray row
        assert contact_service.visible_contacts(team['sm'], customer).count() == 4

    def test_deleting_the_only_shared_contact_does_not_widen_access(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'])
        contact_service.assign_customer(customer, team['sm'], [contacts[0].id])
        contact_service.delete_contact(contacts[0])
        assert not customer.assigned_to.filter(pk=team['sm'].pk).exists()
        assert call(client_for(team['sm']), 'get', f'/360/api/customers/{customer.id}/').status_code == 404

    def test_assign_api_only_admin_and_manager(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'])
        url = f'/360/api/customers/{customer.id}/assign/'
        assert call(client_for(team['bs']), 'post', url, {'user_id': team['sm'].id}).status_code == 403
        assert call(client_for(team['sm']), 'post', url, {'user_id': team['sm'].id}).status_code in (403, 404)
        res = call(client_for(team['bm']), 'post', url, {'user_id': team['sm'].id, 'contact_ids': [contacts[0].id]})
        assert res.status_code == 200 and res.json()['assigned_to_ids'] == [team['sm'].id]
        access = call(client_for(team['admin']), 'get', f'/360/api/customers/{customer.id}/contact-access/').json()['access']
        assert access == [{'user_id': team['sm'].id, 'contact_ids': [contacts[0].id]}]
        assert call(client_for(team['bm']), 'delete', f'/360/api/customers/{customer.id}/assign/?user_id={team["sm"].id}').status_code == 200
        assert not ContactAccess.objects.exists()

    def test_branch_manager_can_only_assign_within_own_branches(self, team):
        elsewhere = make_employee('far', SM, [Branch.objects.create(name='Bengaluru')])
        customer, _ = make_customer('Sun Steels', team['admin'])
        res = call(client_for(team['bm']), 'post', f'/360/api/customers/{customer.id}/assign/', {'user_id': elsewhere.id})
        assert res.status_code == 403

    def test_bulk_assign(self, team):
        a, _ = make_customer('A Co', team['admin'])
        b, _ = make_customer('B Co', team['admin'])
        res = call(client_for(team['admin']), 'post', '/360/api/customers/bulk-assign/',
                   {'customer_ids': [a.id, b.id], 'user_ids': [team['sm'].id, team['sm2'].id]})
        assert res.status_code == 200 and res.json()['assigned'] == 4
        assert call(client_for(team['bs']), 'post', '/360/api/customers/bulk-assign/', {'customer_ids': [a.id], 'user_ids': [team['sm'].id]}).status_code == 403

    def test_the_customer_form_can_assign_but_only_for_admin_and_manager(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'])
        contact_service.assign_customer(customer, team['sm2'], [contacts[0].id])
        url = f'/360/api/customers/{customer.id}/'
        # Branch Staff sending a different list is refused and nothing changes
        res = call(client_for(team['bs']), 'patch', url, {'version': 1, 'assigned_to_ids': [team['sm'].id]})
        assert res.status_code == 403 and set(customer.assigned_to.all()) == {team['sm2']}
        # ...but sending the unchanged list (as the form does on every save) is fine
        assert call(client_for(team['bs']), 'patch', url, {'version': 1, 'city': 'X', 'assigned_to_ids': [team['sm2'].id]}).status_code == 200
        # a Sales Manager cannot smuggle an assignment into an approval request either
        sm = make_customer('Mine', team['sm'])[0]
        res = call(client_for(team['sm']), 'patch', f'/360/api/customers/{sm.id}/', {'version': 1, 'assigned_to_ids': [team['sm2'].id]})
        assert res.status_code == 403 and not ApprovalRequest.objects.exists()
        # Admin / Branch Manager: adds and removes, and removing also drops the contact restriction
        res = call(client_for(team['bm']), 'patch', url, {'version': 2, 'assigned_to_ids': [team['sm'].id]})
        assert res.status_code == 200 and set(customer.assigned_to.all()) == {team['sm']}
        assert not ContactAccess.objects.exists()

    def test_creating_a_customer_with_an_assignment_is_admin_or_manager_only(self, team):
        body = {'name': 'New Co', 'assigned_to_ids': [team['sm'].id]}
        assert call(client_for(team['bs']), 'post', '/360/api/customers/', body).status_code == 403
        assert not Customer.objects.exists()
        res = call(client_for(team['admin']), 'post', '/360/api/customers/', body)
        assert res.status_code == 201 and res.json()['assigned_to_ids'] == [team['sm'].id]


# ----------------------------------------------------------------------------- labels, search, duplicates
class TestSearchAndLabels:
    def test_REQ_CUS_07_label_is_name_plant_area_never_city(self):
        c = Customer.objects.create(name='Sun Steels', plant='Plant 2', area='Ambattur', city='Chennai')
        assert c.select_label == 'Sun Steels, Plant 2, Ambattur'
        assert Customer.objects.create(name='Solo Co', city='Chennai').select_label == 'Solo Co'

    def test_REQ_CUS_08_word_based_search_order(self, team):
        for name in ('Bright Sun Ltd', 'Sunrise Foods', 'Mid Resume Co', 'Asuka Corp', 'Zeta'):
            Customer.objects.create(name=name)
        res = call(client_for(team['admin']), 'get', '/360/api/customers/?search=su')
        assert [r['name'] for r in res.json()['results']] == ['Sunrise Foods', 'Bright Sun Ltd', 'Asuka Corp', 'Mid Resume Co']

    def test_REQ_CUS_09_duplicate_warning_includes_customers_the_user_cannot_see(self, team):
        make_customer('Sun Steels', team['admin'])
        res = call(client_for(team['sm']), 'get', '/360/api/customers/duplicate-check/?name=Sun Steel')
        match = res.json()['matches'][0]
        assert match['label'] == 'Sun Steels' and match['has_access'] is False and match['access_request_pending'] is False
        assert call(client_for(team['sm']), 'get', '/360/api/customers/duplicate-check/?name=Ram Industries').json()['matches'] == []

    def test_smart_filters(self, team):
        a, ac = make_customer('A Co', team['admin'], state='TN', potential='High', industry='Fans')
        b, bc = make_customer('B Co', team['admin'], state='KA', potential='Low')
        Interaction.objects.create(contact=ac[0], type='Call', date='2026-10-20', created_by=team['admin'])
        ac[0].job_title = 'Purchase'
        ac[0].save()
        c = client_for(team['admin'])
        get = lambda q: [r['name'] for r in call(c, 'get', f'/360/api/customers/?{q}').json()['results']]
        assert get('state=TN') == ['A Co'] and get('potential=low') == ['B Co'] and get('designation=purchase') == ['A Co']
        assert get('industry=fans') == ['A Co']
        assert get('added_by=%d' % team['admin'].id) == ['A Co', 'B Co']
        assert get('last_call=never') == ['B Co']
        assert get('last_call=30') == ['A Co']


# ----------------------------------------------------------------------------- pins
class TestPins:
    def test_REQ_GEO_01_pin_text_and_link_and_provenance(self, team):
        c = client_for(team['admin'])
        res = call(c, 'post', '/360/api/customers/', {'name': 'Pinned', 'plant_geo': 'https://www.google.com/maps/@13.0285,77.5197,17z'})
        body = res.json()
        assert (body['plant_geo_lat'], body['plant_geo_lng']) == (13.0285, 77.5197)
        assert body['plant_geo_set_by']['id'] == team['admin'].id and body['plant_geo_set_at']
        res = call(c, 'patch', f'/360/api/customers/{body["id"]}/', {'version': 1, 'plant_geo': '12.9; 80.2'})
        assert (res.json()['plant_geo_lat'], res.json()['plant_geo_lng']) == (12.9, 80.2)
        res = call(c, 'patch', f'/360/api/customers/{body["id"]}/', {'version': 2, 'plant_geo': ''})   # remove pin
        assert res.json()['plant_geo_lat'] is None and res.json()['plant_geo_set_by'] is None

    def test_REQ_GEO_01_invalid_pins_are_rejected_with_a_message(self, team):
        c = client_for(team['admin'])
        for bad in ('not a place', '95, 10', '10, 190'):
            res = call(c, 'post', '/360/api/customers/', {'name': 'Bad Pin', 'plant_geo': bad})
            assert res.status_code == 400 and 'valid location' in res.json()['error'], bad
        assert call(c, 'get', '/360/api/geo/parse/?text=13.1,80.3').json() == {'lat': 13.1, 'lng': 80.3}
        assert call(c, 'get', '/360/api/geo/parse/?text=zzz').status_code == 400

    def test_REQ_GEO_02_visit_shows_distance_from_plant(self, team):
        customer, contacts = make_customer('Pinned', team['admin'], plant_geo_lat=13.0, plant_geo_lng=80.0)
        res = call(client_for(team['admin']), 'post', f'/360/api/contacts/{contacts[0].id}/interactions/',
                   {'type': 'Visit', 'date': '2026-10-20', 'location_lat': 13.0, 'location_lng': 80.01, 'location_accuracy_m': 12})
        body = res.json()
        assert res.status_code == 201 and body['distance_from_plant'] == '1.1 km' and body['location_accuracy_m'] == 12

    def test_nearby_lists_only_visible_customers_closest_first(self, team):
        make_customer('Near', team['sm'], plant_geo_lat=13.0, plant_geo_lng=80.0)
        make_customer('Nearer', team['sm'], plant_geo_lat=13.0, plant_geo_lng=80.001)
        make_customer('Far', team['sm'], plant_geo_lat=20.0, plant_geo_lng=80.0)
        make_customer('Hidden', team['admin'], plant_geo_lat=13.0, plant_geo_lng=80.0005)
        res = call(client_for(team['sm']), 'get', '/360/api/customers/nearby/?lat=13.0&lng=80.0&radius_km=5')
        assert [r['label'] for r in res.json()['results']] == ['Near', 'Nearer']


# ----------------------------------------------------------------------------- approvals
class TestApprovals:
    def test_REQ_ROLE_02_sales_manager_edit_queues_and_changes_nothing(self, team):
        customer, _ = make_customer('Sun Steels', team['sm'], city='Chennai')
        res = call(client_for(team['sm']), 'patch', f'/360/api/customers/{customer.id}/', {'version': 1, 'city': 'Madurai'})
        assert res.status_code == 202 and res.json()['approval_requested'] is True
        customer.refresh_from_db()
        assert customer.city == 'Chennai'
        approval = ApprovalRequest.objects.get()
        assert approval.before_data['city'] == 'Chennai' and approval.proposed_data['city'] == 'Madurai'
        # the approvers were told
        assert Notification.objects.filter(user=team['admin'], type='approval-request').exists()
        assert Notification.objects.filter(user=team['bm'], type='approval-request').exists()

    def test_REQ_AUT_04_approval_applies_the_edit(self, team):
        customer, _ = make_customer('Sun Steels', team['sm'], city='Chennai')
        call(client_for(team['sm']), 'patch', f'/360/api/customers/{customer.id}/', {'version': 1, 'city': 'madurai'})
        approval = ApprovalRequest.objects.get()
        res = call(client_for(team['bm']), 'post', f'/360/api/approvals/{approval.id}/approve/')
        assert res.status_code == 200 and res.json()['status'] == 'approved'
        customer.refresh_from_db()
        assert customer.city == 'Madurai'
        assert Notification.objects.filter(user=team['sm'], text__icontains='approved').exists()
        # no longer pending
        assert call(client_for(team['admin']), 'get', '/360/api/approvals/?status=pending').json()['results'] == []

    def test_REQ_AUT_04_approval_applies_the_delete(self, team):
        customer, _ = make_customer('Sun Steels', team['sm'])
        res = call(client_for(team['sm']), 'delete', f'/360/api/customers/{customer.id}/')
        assert res.status_code == 202 and Customer.objects.filter(pk=customer.pk).exists()
        approval = ApprovalRequest.objects.get()
        assert call(client_for(team['admin']), 'post', f'/360/api/approvals/{approval.id}/approve/').status_code == 200
        assert not Customer.objects.filter(pk=customer.pk).exists()
        approval.refresh_from_db()
        assert approval.status == 'approved' and approval.target_label.startswith('Customer Sun Steels')

    def test_rejecting_changes_nothing_and_tells_the_requester(self, team):
        customer, _ = make_customer('Sun Steels', team['sm'], city='Chennai')
        call(client_for(team['sm']), 'patch', f'/360/api/customers/{customer.id}/', {'version': 1, 'city': 'Madurai'})
        approval = ApprovalRequest.objects.get()
        assert call(client_for(team['admin']), 'post', f'/360/api/approvals/{approval.id}/reject/').status_code == 200
        customer.refresh_from_db()
        assert customer.city == 'Chennai' and Notification.objects.filter(user=team['sm'], text__icontains='rejected').exists()

    def test_one_pending_request_per_person_target_and_kind(self, team):
        customer, _ = make_customer('Sun Steels', team['sm'])
        sm = client_for(team['sm'])
        assert call(sm, 'patch', f'/360/api/customers/{customer.id}/', {'version': 1, 'city': 'A'}).status_code == 202
        assert call(sm, 'patch', f'/360/api/customers/{customer.id}/', {'version': 1, 'city': 'B'}).status_code == 409
        assert call(sm, 'delete', f'/360/api/customers/{customer.id}/').status_code == 202       # different kind: fine
        assert call(sm, 'delete', f'/360/api/customers/{customer.id}/').status_code == 409

    def test_view_what_changed(self, team):
        customer, _ = make_customer('Sun Steels', team['sm'], city='Chennai', state='TN')
        call(client_for(team['sm']), 'patch', f'/360/api/customers/{customer.id}/',
             {'version': 1, 'city': 'Madurai', 'state': 'TN'})
        approval = ApprovalRequest.objects.get()
        body = call(client_for(team['admin']), 'get', f'/360/api/approvals/{approval.id}/changes/').json()
        assert body['changes'] == [{'field': 'city', 'before': 'Chennai', 'after': 'Madurai'}]   # unchanged state not listed

    def test_sales_manager_contact_edit_and_delete_need_approval(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        sm = client_for(team['sm'])
        assert call(sm, 'patch', f'/360/api/contacts/{contacts[0].id}/', {'phone': '111'}).status_code == 202
        assert call(sm, 'delete', f'/360/api/contacts/{contacts[1].id}/').status_code == 202
        contacts[0].refresh_from_db()
        assert contacts[0].phone != '111' and Contact.objects.filter(pk=contacts[1].pk).exists()
        for approval in ApprovalRequest.objects.all():
            call(client_for(team['admin']), 'post', f'/360/api/approvals/{approval.id}/approve/')
        contacts[0].refresh_from_db()
        assert contacts[0].phone == '111' and not Contact.objects.filter(pk=contacts[1].pk).exists()

    def test_branch_staff_edits_directly_but_delete_needs_approval(self, team):
        customer, _ = make_customer('Sun Steels', team['admin'], city='Chennai')
        bs = client_for(team['bs'])
        assert call(bs, 'patch', f'/360/api/customers/{customer.id}/', {'version': 1, 'city': 'Madurai'}).status_code == 200
        assert call(bs, 'delete', f'/360/api/customers/{customer.id}/').status_code == 202
        assert Customer.objects.filter(pk=customer.pk).exists()

    def test_only_approvers_decide_and_branch_manager_sees_only_their_scope(self, team):
        elsewhere = make_employee('far', SM, [Branch.objects.create(name='Bengaluru')])
        c1, _ = make_customer('Near Co', team['sm'])
        c2, _ = make_customer('Far Co', elsewhere)
        call(client_for(team['sm']), 'delete', f'/360/api/customers/{c1.id}/')
        call(client_for(elsewhere), 'delete', f'/360/api/customers/{c2.id}/')
        bm_view = call(client_for(team['bm']), 'get', '/360/api/approvals/').json()['results']
        assert [a['target_label'] for a in bm_view] == ['Customer Near Co']
        assert len(call(client_for(team['admin']), 'get', '/360/api/approvals/').json()['results']) == 2
        far = ApprovalRequest.objects.get(customer=c2)
        assert call(client_for(team['bm']), 'post', f'/360/api/approvals/{far.id}/approve/').status_code == 404
        for who in ('bs', 'sm', 'sm2'):
            near = ApprovalRequest.objects.get(customer=c1)
            assert call(client_for(team[who]), 'post', f'/360/api/approvals/{near.id}/approve/').status_code in (403, 404)

    def test_pending_request_for_a_vanished_record_is_dropped(self, team):
        customer, _ = make_customer('Sun Steels', team['sm'])
        call(client_for(team['sm']), 'patch', f'/360/api/customers/{customer.id}/', {'version': 1, 'city': 'X'})
        customer.delete()
        assert call(client_for(team['admin']), 'get', '/360/api/approvals/?status=pending').json()['results'] == []


class TestAccessRequests:
    def test_REQ_AUT_02_request_notifies_every_admin_and_manager_and_only_one_pending(self, team):
        make_employee('admin_b', ADMIN)
        customer, _ = make_customer('Sun Steels', team['admin'])
        sm = client_for(team['sm'])
        res = call(sm, 'post', '/360/api/approvals/', {'type': 'customer-access', 'customer_id': customer.id})
        assert res.status_code == 201
        for who in ('admin', 'bm'):
            assert Notification.objects.filter(user=team[who], type='customer-access-request').count() == 1
        assert Notification.objects.filter(user__username='admin_b', type='customer-access-request').count() == 1
        assert not Notification.objects.filter(user=team['sm']).exists()
        assert call(sm, 'post', '/360/api/approvals/', {'type': 'customer-access', 'customer_id': customer.id}).status_code == 409

    def test_cannot_request_access_you_already_have(self, team):
        customer, _ = make_customer('Mine', team['sm'])
        res = call(client_for(team['sm']), 'post', '/360/api/approvals/', {'type': 'customer-access', 'customer_id': customer.id})
        assert res.status_code == 400
        bs_customer, _ = make_customer('Any', team['admin'])
        assert call(client_for(team['bs']), 'post', '/360/api/approvals/', {'type': 'customer-access', 'customer_id': bs_customer.id}).status_code == 400

    def test_REQ_AUT_02_approval_assigns_requester_and_tells_them(self, team):
        customer, _ = make_customer('Sun Steels', team['admin'])
        call(client_for(team['sm']), 'post', '/360/api/approvals/', {'type': 'customer-access', 'customer_id': customer.id})
        approval = ApprovalRequest.objects.get()
        call(client_for(team['bm']), 'post', f'/360/api/approvals/{approval.id}/approve/')
        assert customer.assigned_to.filter(pk=team['sm'].pk).exists()
        assert Notification.objects.filter(user=team['sm'], type='customer-access-approved').exists()
        assert call(client_for(team['sm']), 'get', f'/360/api/customers/{customer.id}/').status_code == 200

    def test_REQ_AUT_03_rejected_access_request_changes_nothing_and_tells_the_requester(self, team):
        customer, _ = make_customer('Sun Steels', team['admin'])
        call(client_for(team['sm']), 'post', '/360/api/approvals/', {'type': 'customer-access', 'customer_id': customer.id})
        approval = ApprovalRequest.objects.get()
        call(client_for(team['admin']), 'post', f'/360/api/approvals/{approval.id}/reject/')
        assert not customer.assigned_to.exists()
        assert Notification.objects.filter(user=team['sm'], type='customer-access-declined').exists()


# ----------------------------------------------------------------------------- exports & import
class TestExportsAndImport:
    def test_REQ_CUS_10_emails_are_deduplicated_and_vcf_has_the_fields(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'], contacts=('P1', 'P2', 'P3'))
        Contact.objects.filter(pk=contacts[1].pk).update(email=contacts[0].email)
        Contact.objects.filter(pk=contacts[2].pk).update(email='')
        contacts[0].job_title = 'Purchase'
        contacts[0].save()
        ids = ','.join(str(c.id) for c in contacts)
        c = client_for(team['bm'])
        assert call(c, 'get', f'/360/api/contacts/export/?contact_ids={ids}').json()['emails'] == ['p1@x.com']
        vcf = c.get(f'/360/api/contacts/export/?contact_ids={ids}&format=vcf')
        text = vcf.content.decode()
        assert text.count('BEGIN:VCARD') == 3 and 'ORG:Sun Steels' in text and 'TITLE:Purchase' in text and 'TEL;TYPE=CELL:9840000000' in text

    def test_REQ_CUS_10_empty_selection_refused_and_sales_manager_cannot_export(self, team):
        assert call(client_for(team['admin']), 'get', '/360/api/contacts/export/').status_code == 400
        customer, contacts = make_customer('Sun Steels', team['sm'])
        assert call(client_for(team['sm']), 'get', f'/360/api/contacts/export/?contact_ids={contacts[0].id}').status_code == 403

    def test_exports_leave_out_contacts_hidden_from_the_requester(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm2'])
        ContactAccess.objects.create(customer=customer, user=team['bm'], contact=contacts[0])    # irrelevant: BM sees all
        ids = ','.join(str(c.id) for c in contacts)
        assert call(client_for(team['bm']), 'get', f'/360/api/contacts/export/?contact_ids={ids}').json()['count'] == 4

    def _xlsx(self, rows):
        wb = Workbook()
        ws = wb.active
        header = list(rows[0].keys())
        ws.append(header)
        for r in rows:
            ws.append([r.get(h, '') for h in header])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = 'import.xlsx'
        return buf

    def test_REQ_IMP_01_import_rules(self, team):
        existing, _ = make_customer('Sun Steels', team['admin'], contacts=('Ravi',), city='Chennai')
        Contact.objects.filter(customer=existing).update(phone='111')
        rows = [
            {'company': 'sun steels', 'City': '', 'POTENTIAL': 'high', 'Contact  Name': 'ravi', 'Phone': '111'},
            {'Company': 'sun steels', 'Contact Name': 'meena kumar', 'Phone': '222', 'Assigned To': 'Sm, Nobody'},
            {'Company': 'new tech ltd', 'Address': '12 mount road', 'GST Number': ' 33abc ', 'Potential': 'Urgent',
             'Contact Name': 'joe', 'Plant Location': '13.1, 80.2', 'Preferred Languages': 'Tamil, Hindi'},
        ]
        # the header row comes from the first row's keys; build a uniform sheet
        keys = ['Company', 'City', 'Potential', 'Contact Name', 'Phone', 'Assigned To', 'Address', 'GST Number', 'Plant Location', 'Preferred Languages']
        uniform = [{k: ({kk.lower().replace('  ', ' '): v for kk, v in r.items()}.get(k.lower(), '')) for k in keys} for r in rows]
        res = call(client_for(team['admin']), 'post', '/360/api/customers/import/', None)
        assert res.status_code == 400
        resp = client_for(team['admin']).post('/360/api/customers/import/', {'file': self._xlsx(uniform)})
        body = resp.json()
        assert resp.status_code == 200 and (body['new'], body['updated'], body['contacts']) == (1, 2, 2)
        assert any('Nobody' in w for w in body['warnings']) and any('Urgent' in w for w in body['warnings'])
        existing.refresh_from_db()
        assert existing.city == 'Chennai' and existing.potential == 'High'                # blank keeps value
        assert list(existing.assigned_to.values_list('username', flat=True)) == ['sm']
        assert [c.name for c in existing.contacts.order_by('id')] == ['Ravi', 'Meena Kumar']   # same name+phone skipped
        new = Customer.objects.get(name='New Tech Ltd')
        assert new.address == '12 Mount Road' and new.gst_number == '33ABC' and new.potential == ''
        assert (new.plant_geo_lat, new.plant_geo_lng) == (13.1, 80.2)
        assert new.preferred_languages.count() == 2

    def test_import_is_admin_only_and_rejects_non_workbooks(self, team):
        assert client_for(team['bm']).post('/360/api/customers/import/', {'file': io.BytesIO(b'x')}).status_code == 403
        bad = io.BytesIO(b'not an excel file')
        bad.name = 'a.xlsx'
        assert client_for(team['admin']).post('/360/api/customers/import/', {'file': bad}).status_code == 400
        assert client_for(team['bm']).get('/360/api/customers/import/template/').status_code == 403
        assert client_for(team['admin']).get('/360/api/customers/import/template/')['Content-Type'].startswith('application/vnd.openxml')
