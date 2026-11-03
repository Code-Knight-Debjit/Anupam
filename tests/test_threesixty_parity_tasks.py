"""Task parity with the reference app: several assignees, the display-only "Joint with" names, the In Progress
status, and notifications on create / edit (docs/360/PARITY_TESTS.md T-07, T-08)."""
from datetime import date

import pytest
from django.core.cache import cache

from threesixty.models import Branch, Notification, Task
from tests.helpers_360 import ADMIN, BM, BS, SM, call, client_for, make_customer, make_employee

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def team():
    chennai = Branch.objects.create(name='Chennai')
    return {'admin': make_employee('admin', ADMIN, [chennai], full_name='Sanjeev'),
            'bm': make_employee('bm', BM, [chennai], full_name='Bala'),
            'bs': make_employee('bs', BS, [chennai], full_name='Staff'),
            'sm': make_employee('sm', SM, [chennai], full_name='Devdutt')}


def post_task(user, **data):
    return call(client_for(user), 'post', '/360/api/tasks/', data)


class TestMultiAssign:
    def test_first_person_is_primary_and_everyone_is_listed_as_an_assignee(self, team):
        res = post_task(team['admin'], title='Share', assigned_to_ids=[team['bs'].pk, team['sm'].pk, team['bm'].pk])
        assert res.status_code == 201
        body = res.json()
        assert body['assigned_to']['id'] == team['bs'].pk
        assert body['assignees'][0]['id'] == team['bs'].pk and {a['id'] for a in body['assignees']} == {team['bs'].pk, team['sm'].pk, team['bm'].pk}

    def test_each_other_assignee_is_told_with_the_shared_suffix(self, team):
        post_task(team['admin'], title='Share', assigned_to_ids=[team['bs'].pk, team['sm'].pk, team['bm'].pk])
        text = Notification.objects.get(user=team['bs']).text
        assert text == 'Sanjeev assigned you a task: "Share" (shared with 2 others).'
        post_task(team['admin'], title='Pair', assigned_to_ids=[team['bs'].pk, team['sm'].pk])
        assert Notification.objects.filter(user=team['sm']).first().text == 'Sanjeev assigned you a task: "Pair" (shared with 1 other).'
        post_task(team['admin'], title='Solo', assigned_to_ids=[team['bs'].pk])
        assert Notification.objects.filter(user=team['bs']).first().text == 'Sanjeev assigned you a task: "Solo".'

    def test_the_creator_is_not_notified_about_their_own_task(self, team):
        post_task(team['admin'], title='Mine', assigned_to_ids=[team['admin'].pk, team['bs'].pk])
        assert not Notification.objects.filter(user=team['admin']).exists()

    def test_editing_adds_people_and_only_the_new_ones_are_told(self, team):
        task_id = post_task(team['admin'], title='T', assigned_to_ids=[team['bs'].pk]).json()['id']
        Notification.objects.all().delete()
        version = call(client_for(team['admin']), 'get', f'/360/api/tasks/{task_id}/').json()['version']
        res = call(client_for(team['admin']), 'patch', f'/360/api/tasks/{task_id}/',
                   {'assigned_to_ids': [team['bs'].pk, team['sm'].pk], 'version': version})
        assert res.status_code == 200
        assert [a['id'] for a in res.json()['assignees']] == [team['bs'].pk, team['sm'].pk]
        assert list(Notification.objects.values_list('user_id', flat=True)) == [team['sm'].pk]

    def test_editing_needs_at_least_one_person_and_can_move_the_customer(self, team):
        customer, _ = make_customer('Sun Steels', team['admin'])
        task_id = post_task(team['admin'], title='T', assigned_to_ids=[team['bs'].pk]).json()['id']
        v = call(client_for(team['admin']), 'get', f'/360/api/tasks/{task_id}/').json()['version']
        assert call(client_for(team['admin']), 'patch', f'/360/api/tasks/{task_id}/', {'assigned_to_ids': [], 'version': v}).status_code == 400
        res = call(client_for(team['admin']), 'patch', f'/360/api/tasks/{task_id}/', {'related_customer_id': customer.pk, 'version': v})
        assert res.json()['related_customer_name'] == 'Sun Steels'


class TestStatuses:
    def test_in_progress_is_a_status_and_done_still_notifies_the_creator(self, team):
        task_id = post_task(team['admin'], title='T', assigned_to_ids=[team['bs'].pk]).json()['id']
        v = call(client_for(team['bs']), 'get', f'/360/api/tasks/{task_id}/').json()['version']
        res = call(client_for(team['bs']), 'patch', f'/360/api/tasks/{task_id}/', {'status': 'In Progress', 'version': v})
        assert res.status_code == 200 and res.json()['status'] == 'In Progress'
        v = res.json()['version']
        call(client_for(team['bs']), 'patch', f'/360/api/tasks/{task_id}/', {'status': 'Done', 'version': v})
        assert 'verify and mark it complete' in Notification.objects.get(user=team['admin']).text


class TestJointNamesFromVisits:
    def test_joint_visit_tasks_carry_description_joint_names_and_the_linked_document(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        res = call(client_for(team['sm']), 'post', f'/360/api/contacts/{contacts[0].pk}/interactions/',
                   {'type': 'Visit', 'date': '2026-10-20', 'followup_date': '2026-11-02', 'notes': 'Bearing demo',
                    'joint_with_user_ids': [team['bs'].pk, team['bm'].pk]})
        assert res.status_code == 201
        mine = Task.objects.get(assigned_to=team['sm'])
        assert mine.description == 'Bearing demo' and sorted(mine.joint_names) == ['Bala', 'Staff']
        theirs = Task.objects.get(assigned_to=team['bs'])
        assert theirs.joint_names == ['Devdutt', 'Bala'] and theirs.description == 'Bearing demo'
        # joint names are display-only: nobody is made a co-assignee
        assert not mine.joint_with.exists() and not theirs.joint_with.exists()

    def test_default_descriptions_when_there_are_no_notes(self, team):
        customer, contacts = make_customer('Sun Steels', team['sm'])
        call(client_for(team['sm']), 'post', f'/360/api/contacts/{contacts[0].pk}/interactions/',
             {'type': 'Appointment', 'date': '2026-10-20', 'followup_date': '2026-11-02', 'joint_with_user_ids': [team['bs'].pk]})
        assert Task.objects.get(assigned_to=team['sm']).description == 'Appointment requested by the customer on 02/11/2026.'
        assert Task.objects.get(assigned_to=team['bs']).description == 'Joint appointment with Devdutt.'
