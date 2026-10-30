"""Phase 3 (Activity) — interactions, tasks, outreach, notifications."""
from datetime import date, timedelta

import pytest
from django.core.cache import cache

from threesixty.models import (
    Branch, CallAssignment, ContactAccess, Interaction, Notification, SalesDocument, Task,
)
from threesixty.services import contacts as contact_service
from threesixty.services import interactions as interaction_service
from threesixty.services import outreach as outreach_service
from threesixty.services import tasks as task_service
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
        'admin': make_employee('admin', ADMIN, [chennai], full_name='Sanjeev'),
        'bm': make_employee('bm', BM, [chennai], full_name='Bala'),
        'bs': make_employee('bs', BS, [chennai], full_name='Staff'),
        'sm': make_employee('sm', SM, [chennai], full_name='Devdutt'),
        'sm2': make_employee('sm2', SM, [chennai], full_name='Ravi'),
    }


def log(user, contact, type_='Call', day='2026-10-20', **kwargs):
    return call(client_for(user), 'post', f'/360/api/contacts/{contact.id}/interactions/',
                {'type': type_, 'date': day, **kwargs})


# ----------------------------------------------------------------------------- interactions
class TestInteractions:
    def test_REQ_INT_01_followup_date_creates_a_task_for_the_logger(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        res = log(team['sm'], contacts[0], 'Call', followup_date='2026-11-01')
        assert res.status_code == 201
        task = Task.objects.get()
        assert (task.assigned_to, task.due_date, task.task_type, task.created_by) == (team['sm'], date(2026, 11, 1), 'Call', team['sm'])
        assert task.title == 'Call Ravi — Sun Steels' and task.related_contact == contacts[0]

    def test_no_followup_no_task(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        log(team['sm'], contacts[0], 'Call')
        assert not Task.objects.exists()

    def test_REQ_INT_02_appointment_needs_its_date(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        res = log(team['sm'], contacts[0], 'Appointment')
        assert res.status_code == 400 and 'appointment date' in res.json()['error']
        assert log(team['sm'], contacts[0], 'Appointment', followup_date='2026-11-02').status_code == 201

    def test_unknown_type_rejected(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        assert log(team['sm'], contacts[0], 'Email').status_code == 400

    def test_REQ_INT_03_visit_closes_open_appointment_tasks_for_that_contact_only(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        log(team['sm'], contacts[0], 'Appointment', followup_date='2026-11-02')
        log(team['sm'], contacts[1], 'Appointment', followup_date='2026-11-02')
        manual_call = Task.objects.create(title='Call Ravi', task_type='Call', assigned_to=team['sm'],
                                          related_contact=contacts[0], created_by=team['sm'])
        log(team['sm'], contacts[0], 'Visit', day='2026-11-02')
        closed = Task.objects.get(related_contact=contacts[0], task_type='Appointment')
        assert closed.status == 'Completed' and closed.auto_closed_by_visit
        assert Task.objects.get(related_contact=contacts[1], task_type='Appointment').status == 'Open'
        manual_call.refresh_from_db()
        assert manual_call.status == 'Open'

    def test_REQ_INT_03_title_prefixed_appointment_task_is_closed_too(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        Task.objects.create(title='Appointment with Ravi', assigned_to=team['sm'], related_contact=contacts[0], created_by=team['sm'])
        log(team['sm'], contacts[0], 'Visit')
        assert Task.objects.get().status == 'Completed'

    def test_REQ_INT_04_each_joint_member_gets_their_own_task_and_a_notification(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        res = log(team['sm'], contacts[0], 'Visit', joint_with_user_ids=[team['bs'].id, team['sm2'].id, team['sm'].id])
        assert res.status_code == 201 and sorted(res.json()['joint_with_user_ids']) == sorted([team['bs'].id, team['sm2'].id])
        joint = Task.objects.filter(title__startswith='Joint visit with Devdutt')
        assert {t.assigned_to for t in joint} == {team['bs'], team['sm2']}
        assert all(t.created_by == team['sm'] and t.due_date == date(2026, 10, 20) for t in joint)
        assert Notification.objects.filter(user=team['bs'], type='task').exists()
        assert not Notification.objects.filter(user=team['sm']).exists()

    def test_joint_is_ignored_for_calls(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        res = log(team['sm'], contacts[0], 'Call', joint_with_user_ids=[team['bs'].id])
        assert res.json()['joint_with_user_ids'] == [] and not Task.objects.exists()

    def test_REQ_INT_05_also_met_contacts_get_a_flagged_copy(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        res = log(team['sm'], contacts[0], 'Visit', also_met_contact_ids=[contacts[1].id, contacts[2].id])
        assert res.status_code == 201
        copies = Interaction.objects.filter(is_copy=True)
        assert {c.contact for c in copies} == {contacts[1], contacts[2]}
        assert all(c.met_with_name == 'Ravi' and c.type == 'Visit' for c in copies)
        original = Interaction.objects.get(is_copy=False)
        assert original.visit_group and {c.visit_group for c in copies} == {original.visit_group}

    def test_also_met_cannot_include_contacts_the_logger_cannot_see(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'])
        contact_service.assign_customer(customer, team['sm'], [contacts[0].id, contacts[1].id])
        log(team['sm'], contacts[0], 'Visit', also_met_contact_ids=[contacts[1].id, contacts[3].id])
        assert {c.contact for c in Interaction.objects.filter(is_copy=True)} == {contacts[1]}

    def test_cannot_log_on_a_contact_hidden_by_contact_access(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'])
        contact_service.assign_customer(customer, team['sm'], [contacts[0].id])
        assert log(team['sm'], contacts[3], 'Call').status_code == 404

    def test_GPS_only_stored_for_visits(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        visit = log(team['sm'], contacts[0], 'Visit', location_lat=13.0, location_lng=80.0, location_accuracy_m=20).json()
        phone = log(team['sm'], contacts[0], 'Call', location_lat=13.0, location_lng=80.0).json()
        assert visit['location_lat'] == 13.0 and phone['location_lat'] is None

    def test_REQ_INT_06_appointment_to_visit_percentage(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        log(team['sm'], contacts[0], 'Appointment', day='2026-10-01', followup_date='2026-10-02')
        log(team['sm'], contacts[1], 'Appointment', day='2026-10-01', followup_date='2026-10-02')
        log(team['sm'], contacts[0], 'Visit', day='2026-10-03')
        not_visited = interaction_service.appointments_not_visited(team['sm'])
        assert [i.contact for i in not_visited] == [contacts[1]]
        assert interaction_service.visit_percent(2, 1) == 50 and interaction_service.visit_percent(0, 0) == 0

    def test_REQ_INT_07_cold_call_counts_as_a_call(self):
        assert Interaction.TYPE_COLD_CALL in interaction_service.CALL_TYPES

    def test_only_logger_admin_or_manager_may_edit_an_interaction(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        iid = log(team['sm'], contacts[0], 'Call').json()['id']
        customer.assigned_to.add(team['sm2'])
        assert call(client_for(team['sm2']), 'patch', f'/360/api/interactions/{iid}/', {'notes': 'x'}).status_code in (403, 404)
        assert call(client_for(team['bm']), 'patch', f'/360/api/interactions/{iid}/', {'notes': 'x'}).status_code == 200


# ----------------------------------------------------------------------------- tasks
def mk_task(creator, assignee, title='Do it', **kwargs):
    return task_service.create_task(creator, title=title, assignee_user_ids=[assignee.pk], **kwargs)


class TestTasks:
    def ids(self, user, query=''):
        res = call(client_for(user), 'get', f'/360/api/tasks/{query}')
        assert res.status_code == 200, res.content
        return {t['title'] for t in res.json()['results']}

    def test_REQ_TSK_01_main_list_is_my_own_tasks_only(self, team):
        mk_task(team['admin'], team['admin'], 'Mine')
        mk_task(team['admin'], team['sm'], 'For Devdutt')
        mk_task(team['sm'], team['sm2'], 'Devdutt to Ravi')
        assert self.ids(team['admin']) == {'Mine'}
        assert self.ids(team['sm']) == {'For Devdutt'}
        assert self.ids(team['sm2']) == {'Devdutt to Ravi'}

    def test_REQ_TSK_01_admin_and_manager_can_switch_to_everyone(self, team):
        mk_task(team['sm'], team['sm2'], 'Private-ish')
        for who in ('admin', 'bm'):
            assert 'Private-ish' in self.ids(team[who], '?scope=all')
        for who in ('bs', 'sm', 'sm2'):
            assert call(client_for(team[who]), 'get', '/360/api/tasks/?scope=all').status_code == 403

    def test_REQ_TSK_02_assigned_by_me_panel(self, team):
        mk_task(team['admin'], team['sm'], 'Follow up with Devdutt')
        mk_task(team['admin'], team['admin'], 'Self task')
        assert self.ids(team['admin'], '?scope=assigned_by_me') == {'Follow up with Devdutt'}
        assert 'Follow up with Devdutt' in self.ids(team['sm'])
        assert self.ids(team['sm'], '?scope=assigned_by_me') == set()

    def test_REQ_TSK_03_only_the_creator_can_remove(self, team):
        task = mk_task(team['admin'], team['sm'])
        url = f'/360/api/tasks/{task.id}/'
        for who in ('sm', 'bm'):
            assert call(client_for(team[who]), 'delete', url).status_code == 403, who
        assert Task.objects.filter(pk=task.pk).exists()
        assert call(client_for(team['admin']), 'delete', url).status_code == 200
        assert not Task.objects.exists()

    def test_REQ_TSK_03_creatorless_task_can_be_removed_by_admin_only(self, team):
        task = Task.objects.create(title='Old', assigned_to=team['sm'])
        assert call(client_for(team['bm']), 'delete', f'/360/api/tasks/{task.id}/').status_code == 403
        assert call(client_for(team['admin']), 'delete', f'/360/api/tasks/{task.id}/').status_code == 200

    def test_REQ_TSK_04_assignee_may_update_status_but_not_edit(self, team):
        task = mk_task(team['admin'], team['sm'], 'Ship it')
        sm = client_for(team['sm'])
        url = f'/360/api/tasks/{task.id}/'
        assert call(sm, 'patch', url, {'version': 1, 'status': 'Done'}).json()['status'] == 'Completed'
        assert call(sm, 'patch', url, {'version': 2, 'title': 'Renamed'}).status_code == 403
        assert call(client_for(team['sm2']), 'patch', url, {'version': 2, 'status': 'Open'}).status_code == 404

    def test_REQ_TSK_05_multiple_assignees_and_kind(self, team):
        task = task_service.create_task(team['admin'], title='Visit Sun Steels', assignee_user_ids=[team['sm'].pk, team['sm2'].pk, team['bs'].pk])
        assert task_service.assignee_ids(task) == {team['sm'].pk, team['sm2'].pk, team['bs'].pk}
        for who in ('sm', 'sm2', 'bs'):
            assert 'Visit Sun Steels' in self.ids(team[who])
        assert task_service.kind_of(task) == 'Visit'
        assert task_service.kind_of(Task(title='Callback later')) == 'Task'      # "Callback" is not "Call"
        assert task_service.kind_of(Task(title='x', task_type='Appointment')) == 'Appointment'

    def test_REQ_TSK_06_who_can_edit(self, team):
        task = mk_task(team['sm'], team['sm2'], 'Edit me')
        assert task_service.can_edit(team['admin'], task) and task_service.can_edit(team['bm'], task)
        assert task_service.can_edit(team['sm'], task) and not task_service.can_edit(team['sm2'], task)
        assert call(client_for(team['sm']), 'patch', f'/360/api/tasks/{task.id}/', {'version': 1, 'title': 'Edited'}).status_code == 200

    def test_REQ_AUT_07_assignees_except_the_creator_are_notified(self, team):
        res = call(client_for(team['admin']), 'post', '/360/api/tasks/',
                   {'title': 'Collect cheque', 'assigned_to_ids': [team['sm'].id, team['admin'].id, team['bs'].id]})
        assert res.status_code == 201
        assert Notification.objects.filter(user=team['sm'], type='task', text__contains='Collect cheque').count() == 1
        assert Notification.objects.filter(user=team['bs'], type='task').count() == 1
        assert not Notification.objects.filter(user=team['admin']).exists()

    def test_cannot_assign_to_an_inactive_or_unknown_user(self, team):
        team['sm2'].is_active = False
        team['sm2'].save()
        assert call(client_for(team['admin']), 'post', '/360/api/tasks/', {'title': 'x', 'assigned_to_id': team['sm2'].id}).status_code == 400

    def test_REQ_AUT_05_creator_told_to_verify_on_fresh_completion_only(self, team):
        task = mk_task(team['admin'], team['sm'], 'Send quote')
        sm = client_for(team['sm'])
        call(sm, 'patch', f'/360/api/tasks/{task.id}/', {'version': 1, 'status': 'Done'})
        assert Notification.objects.filter(user=team['admin'], type='task_done', text__contains='verify').count() == 1
        call(sm, 'patch', f'/360/api/tasks/{task.id}/', {'version': 2, 'status': 'Done'})        # already Done
        assert Notification.objects.filter(type='task_done').count() == 1
        own = mk_task(team['sm'], team['sm'], 'Self')
        call(sm, 'patch', f'/360/api/tasks/{own.id}/', {'version': 1, 'status': 'Done'})         # self-assigned
        assert Notification.objects.filter(type='task_done').count() == 1

    def test_REQ_AUT_06_removing_a_done_task_tells_assignees_it_was_verified(self, team):
        task = mk_task(team['admin'], team['sm'], 'Send quote')
        task_service.set_status(team['sm'], task, 'Done')
        call(client_for(team['admin']), 'delete', f'/360/api/tasks/{task.id}/')
        assert Notification.objects.filter(user=team['sm'], type='task_verified', text__contains='verified and marked').count() == 1

    def test_REQ_AUT_06_removing_an_open_task_does_not_tell_assignees(self, team):
        task = mk_task(team['admin'], team['sm'], 'Send quote')
        Notification.objects.all().delete()
        call(client_for(team['admin']), 'delete', f'/360/api/tasks/{task.id}/')
        assert not Notification.objects.exists()           # creator removed it themself; assignee not pinged

    def test_REQ_AUT_08_schedule_follow_up_from_a_document(self, team, chennai):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        doc = SalesDocument.objects.create(type='quotation', doc_number='QUO-0001', branch=chennai, customer=customer,
                                           contact=contacts[0], date='2026-10-01', created_by=team['sm'])
        task = task_service.schedule_from_document(team['sm'], doc, 'Appointment', date(2026, 11, 5), team['bs'])
        assert task.title == 'Appointment with Ravi — Sun Steels' and task.related_document == doc
        assert task.task_type == 'Appointment' and task.assigned_to == team['bs']
        assert Notification.objects.get(user=team['bs']).text.startswith('Devdutt scheduled a appointment')
        mine = task_service.schedule_from_document(team['sm'], doc, 'Call', date(2026, 11, 6), team['sm'])
        assert mine.title == 'Call Ravi — Sun Steels' and Notification.objects.count() == 1

    def test_branch_staff_see_their_branch_scope_in_detail_but_not_other_branches(self, team):
        elsewhere = make_employee('far', BS, [Branch.objects.create(name='Bengaluru')])
        near = mk_task(team['admin'], team['sm'], 'Near task')
        far = mk_task(elsewhere, elsewhere, 'Far task')
        bs = client_for(team['bs'])
        assert call(bs, 'get', f'/360/api/tasks/{near.id}/').status_code == 200
        assert call(bs, 'get', f'/360/api/tasks/{far.id}/').status_code == 404

    def test_sales_manager_cannot_read_or_change_other_peoples_tasks_by_id(self, team):
        task = mk_task(team['admin'], team['sm2'], 'Not yours')
        sm = client_for(team['sm'])
        assert call(sm, 'get', f'/360/api/tasks/{task.id}/').status_code == 404
        assert call(sm, 'patch', f'/360/api/tasks/{task.id}/', {'version': 1, 'status': 'Done'}).status_code == 404
        assert call(sm, 'delete', f'/360/api/tasks/{task.id}/').status_code == 404


# ----------------------------------------------------------------------------- outreach
class TestOutreach:
    def assign(self, user, customers, assignee, week='2026-10-22'):
        return call(client_for(user), 'post', '/360/api/call-assignments/assign/',
                    {'customer_ids': [c.id for c in customers], 'assigned_to_id': assignee.id, 'week_of': week})

    def test_REQ_AUT_01_one_entry_per_contact_week_is_the_monday_and_no_duplicates(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'], contacts=('A', 'B', 'C'))
        res = self.assign(team['admin'], [customer], team['bs'], week='2026-10-22')          # a Thursday
        assert res.json() == {'added': 3, 'skipped': 0, 'dnd_skipped': 0, 'week_of': '2026-10-19'}
        assert {a.week_of for a in CallAssignment.objects.all()} == {date(2026, 10, 19)}
        again = self.assign(team['bm'], [customer], team['bs'], week='2026-10-25').json()     # same week (Sunday)
        assert (again['added'], again['skipped']) == (0, 3)
        assert self.assign(team['admin'], [customer], team['bs'], week='2026-10-26').json()['added'] == 3   # next week

    def test_REQ_AUT_01_dnd_contacts_are_skipped(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'], contacts=('A', 'B', 'C'))
        contacts[1].dnd = True
        contacts[1].save()
        res = self.assign(team['admin'], [customer], team['bs']).json()
        assert (res['added'], res['dnd_skipped']) == (2, 1)
        assert not CallAssignment.objects.filter(contact=contacts[1]).exists()

    def test_REQ_AUT_01_customer_without_contacts_gets_one_blank_entry(self, team):
        customer, _ = make_customer('Empty Co', team['admin'], contacts=())
        self.assign(team['admin'], [customer], team['bs'])
        self.assign(team['admin'], [customer], team['bs'])
        assert CallAssignment.objects.filter(customer=customer, contact__isnull=True).count() == 1

    def test_REQ_OUT_GAP_assignee_contact_access_is_respected(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'], contacts=('A', 'B', 'C', 'D'))
        contact_service.assign_customer(customer, team['sm'], [contacts[0].id, contacts[1].id])
        res = self.assign(team['admin'], [customer], team['sm']).json()
        assert res['added'] == 2
        assert {a.contact for a in CallAssignment.objects.all()} == {contacts[0], contacts[1]}
        # an unrestricted colleague still gets all four
        assert self.assign(team['admin'], [customer], team['sm2']).json()['added'] == 4

    def test_REQ_OUT_GAP_single_entry_endpoint_refuses_a_hidden_contact(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'])
        contact_service.assign_customer(customer, team['sm'], [contacts[0].id])
        res = call(client_for(team['admin']), 'post', '/360/api/call-assignments/', {
            'customer_id': customer.id, 'contact_id': contacts[3].id, 'week_of': '2026-10-19', 'assigned_to_id': team['sm'].id})
        assert res.status_code == 400
        contacts[0].dnd = True
        contacts[0].save()
        res = call(client_for(team['admin']), 'post', '/360/api/call-assignments/', {
            'customer_id': customer.id, 'contact_id': contacts[0].id, 'week_of': '2026-10-19', 'assigned_to_id': team['sm'].id})
        assert res.status_code == 400

    def test_only_admin_and_manager_assign(self, team):
        customer, _ = make_customer('Sun Steels', team['admin'])
        for who in ('bs', 'sm'):
            assert self.assign(team[who], [customer], team['sm2']).status_code == 403
        assert self.assign(team['bm'], [customer], team['bs']).status_code == 200

    def test_manager_cannot_assign_customers_they_cannot_see(self, team):
        # a Branch Manager sees every customer, a Sales Manager is the only restricted assigner role
        customer, _ = make_customer('Sun Steels', team['sm'])
        assert self.assign(team['bm'], [customer], team['bs']).json()['added'] == 4

    def test_REQ_OUT_01_first_called_logs_a_call_interaction(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'], contacts=('A',))
        self.assign(team['admin'], [customer], team['bs'])
        a = CallAssignment.objects.get()
        bs = client_for(team['bs'])
        assert call(bs, 'patch', f'/360/api/call-assignments/{a.id}/', {'status': 'Called'}).status_code == 200
        interaction = Interaction.objects.get()
        assert (interaction.type, interaction.notes, interaction.created_by) == ('Call', 'Outreach — call completed.', team['bs'])
        call(bs, 'patch', f'/360/api/call-assignments/{a.id}/', {'status': 'Called', 'remarks': 'again'})
        assert Interaction.objects.count() == 1                                  # first time only
        a.refresh_from_db()
        assert a.status == 'Called' and a.called_by == team['bs']

    def test_REQ_OUT_01_remarks_become_the_interaction_notes(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'], contacts=('A',))
        self.assign(team['admin'], [customer], team['bs'])
        a = CallAssignment.objects.get()
        call(client_for(team['bs']), 'patch', f'/360/api/call-assignments/{a.id}/', {'status': 'Called', 'remarks': 'Wants a quote'})
        assert Interaction.objects.get().notes == 'Wants a quote'

    def test_REQ_OUT_02_not_reached_keeps_attempts_and_makes_a_task_for_the_assigned_staff(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'], contacts=('A',))
        self.assign(team['admin'], [customer], team['bs'])
        a = CallAssignment.objects.get()
        url = f'/360/api/call-assignments/{a.id}/attempts/'
        res = call(client_for(team['admin']), 'post', url, {'reason': 'Not reachable', 'call_again_date': '2026-10-30'})
        assert res.status_code == 201
        call(client_for(team['bs']), 'post', url, {'reason': 'Busy', 'note': 'in a meeting'})
        task = Task.objects.get()
        assert (task.assigned_to, task.due_date, task.task_type, task.created_by) == (team['bs'], date(2026, 10, 30), 'Call', team['admin'])
        assert task.title == 'Call A — Sun Steels'
        assert a.attempts.count() == 2

    def test_nobody_else_can_log_attempts_or_update(self, team):
        customer, contacts = make_customer('Sun Steels', team['admin'], contacts=('A',))
        self.assign(team['admin'], [customer], team['bs'])
        a = CallAssignment.objects.get()
        sm2 = client_for(team['sm2'])
        assert call(sm2, 'patch', f'/360/api/call-assignments/{a.id}/', {'status': 'Called'}).status_code == 404
        assert call(sm2, 'post', f'/360/api/call-assignments/{a.id}/attempts/', {'reason': 'x'}).status_code in (403, 404)

    def test_sales_manager_only_sees_own_call_list(self, team):
        customer, _ = make_customer('Sun Steels', team['admin'], contacts=('A',))
        self.assign(team['admin'], [customer], team['sm'])
        self.assign(team['admin'], [customer], team['sm2'])
        assert len(call(client_for(team['sm']), 'get', '/360/api/call-assignments/').json()['results']) == 1


# ----------------------------------------------------------------------------- notifications bell
class TestNotifications:
    def test_each_user_sees_only_their_own_and_can_mark_read(self, team):
        Notification.objects.create(user=team['sm'], type='task', text='for sm')
        n = Notification.objects.create(user=team['sm2'], type='task', text='for sm2')
        sm = client_for(team['sm'])
        assert [x['text'] for x in call(sm, 'get', '/360/api/notifications/').json()['results']] == ['for sm']
        assert call(sm, 'patch', f'/360/api/notifications/{n.id}/', {'read': True}).status_code == 404
        assert call(sm, 'get', '/360/api/notifications/?unread=1').json()['count'] == 1
        assert call(sm, 'post', '/360/api/notifications/read-all/').json() == {'marked': 1}
        assert call(sm, 'get', '/360/api/notifications/?unread=1').json()['count'] == 0
        n.refresh_from_db()
        assert n.read is False                                      # someone else's stays unread

    def test_notifications_cannot_be_created_through_the_api(self, team):
        assert call(client_for(team['sm']), 'post', '/360/api/notifications/', {'text': 'x'}).status_code == 405
