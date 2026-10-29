"""Tasks (REQ-TSK-01..06) and the task automations REQ-AUT-05..08.

Task assignees are the primary `assigned_to` plus everyone in `joint_with`.
The model's "Completed" status is the spec's "Done".
"""
import re

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..models import Task
from ..permissions import RoleRules
from .errors import ServiceError
from .notifications import notify

KINDS = ('Call', 'Visit', 'Appointment', 'Task')
DONE = Task.STATUS_COMPLETED
OPEN = Task.STATUS_OPEN
_STATUS_ALIASES = {'Done': DONE, 'Completed': DONE, 'Open': OPEN}


def normalize_status(value):
    try:
        return _STATUS_ALIASES[value]
    except KeyError:
        raise ServiceError(400, 'Status must be Open or Done.')


def kind_of(task) -> str:
    """Call / Visit / Appointment / Task from `task_type`, else from the title prefix."""
    if task.task_type in KINDS:
        return task.task_type
    title = (task.title or '').strip()
    for kind in ('Call', 'Visit', 'Appointment'):
        if re.match(rf'^{kind}\b', title, re.I):
            return kind
    return 'Task'


def assignee_ids(task) -> set:
    return {task.assigned_to_id} | {u.pk for u in task.joint_with.all()}


def is_assignee(user, task) -> bool:
    return user.pk in assignee_ids(task)


# --------------------------------------------------------------------------- permissions
def can_manage(user, task) -> bool:
    return RoleRules.is_admin(user) or RoleRules.is_branch_manager(user) or task.created_by_id == user.pk


def can_edit(user, task) -> bool:                      # REQ-TSK-06
    return can_manage(user, task)


def can_update_status(user, task) -> bool:             # REQ-TSK-04
    return can_manage(user, task) or is_assignee(user, task)


def can_remove(user, task) -> bool:
    """Only the creator removes a task (REQ-TSK-03); a task with no creator
    (older data) may be removed by an Admin."""
    if task.created_by_id is None:
        return RoleRules.is_admin(user)
    return task.created_by_id == user.pk


# --------------------------------------------------------------------------- visibility
def _involving(user):
    return Q(assigned_to=user) | Q(joint_with=user) | Q(created_by=user)


def visible_tasks(user, queryset=None):
    qs = queryset if queryset is not None else Task.objects.all()
    if RoleRules.is_admin(user) or RoleRules.is_branch_manager(user):
        return qs
    cond = _involving(user)
    if RoleRules.is_branch_staff(user):
        scope = RoleRules.user_ids_in_manager_scope(user)
        cond |= Q(assigned_to_id__in=scope) | Q(joint_with__in=scope) | Q(created_by_id__in=scope)
    return qs.filter(cond).distinct()


def main_list(user, queryset=None, scope='mine'):
    """The task page's main list is the viewer's OWN tasks; Admin and Branch
    Manager may switch to everyone (REQ-TSK-01)."""
    vis = visible_tasks(user, queryset)
    if scope == 'all' and (RoleRules.is_admin(user) or RoleRules.is_branch_manager(user)):
        return vis
    return vis.filter(Q(assigned_to=user) | Q(joint_with=user)).distinct()


def assigned_by_me(user, queryset=None):
    """Tasks I created that are assigned to others — the panel under the calendar (REQ-TSK-02)."""
    qs = queryset if queryset is not None else Task.objects.all()
    return qs.filter(created_by=user).exclude(Q(assigned_to=user) | Q(joint_with=user)).distinct()


# --------------------------------------------------------------------------- actions
def _name(user):
    return user.get_full_name() or user.username


@transaction.atomic
def create_task(creator, *, title, assignee_user_ids=None, due_date=None, description='', priority=None,
                task_type='', customer=None, contact=None, document=None, notify_assignees=True):
    """Create a task for one or more people. Each assignee except the creator
    is notified (REQ-AUT-07)."""
    title = (title or '').strip()
    if not title:
        raise ServiceError(400, 'title is required.')
    ids = list(dict.fromkeys(assignee_user_ids or [creator.pk]))
    task = Task.objects.create(
        title=title, description=description, assigned_to_id=ids[0], due_date=due_date,
        priority=priority or Task.PRIORITY_MEDIUM, task_type=task_type if task_type in KINDS else '',
        related_customer=customer, related_contact=contact, related_document=document, created_by=creator,
    )
    if len(ids) > 1:
        task.joint_with.set(ids[1:])
    if notify_assignees:
        for uid in ids:
            if uid != creator.pk:
                notify(uid, 'task', f'{_name(creator)} assigned you a task: "{title}"', document=document)
    return task


@transaction.atomic
def set_status(user, task, status):
    """Assignee (or manager) marks Open/Done. A fresh completion tells the
    creator to verify it — unless the creator did it themself (REQ-AUT-05)."""
    status = normalize_status(status)
    if not can_update_status(user, task):
        raise ServiceError(403, 'You cannot change this task.')
    was_done = task.status == DONE
    task.status = status
    if status == DONE:
        if not was_done:
            task.completed_at, task.completed_by = timezone.now(), user
    else:
        task.completed_at, task.completed_by = None, None
    task.save()
    if status == DONE and not was_done and task.created_by_id and task.created_by_id != user.pk:
        notify(task.created_by_id, 'task_done',
               f'{_name(user)} completed the task "{task.title}" — verify and mark it complete.')
    return task


@transaction.atomic
def delete_task(user, task):
    """Creator-only removal (REQ-AUT-06). If the task was Done and the remover
    manages it, the assignees are told it was verified; otherwise the creator
    (if someone else) is told it was removed."""
    if not can_remove(user, task):
        raise ServiceError(403, 'Only the person who created a task can remove it.')
    acknowledging = task.status == DONE and can_manage(user, task)
    title, creator_id, assignees = task.title, task.created_by_id, assignee_ids(task)
    task.delete()
    if creator_id and creator_id != user.pk and not acknowledging:
        notify(creator_id, 'task_removed', f'{_name(user)} removed the task "{title}"')
    if acknowledging:
        for uid in assignees:
            if uid != user.pk:
                notify(uid, 'task_verified', f'{_name(user)} verified and marked "{title}" as complete.')


@transaction.atomic
def schedule_from_document(user, document, kind, due_date, assignee):
    """"Schedule follow-up" on a sales document: a Call / Visit / Appointment
    task linked to the document; the assignee is notified (REQ-AUT-08)."""
    if kind not in ('Call', 'Visit', 'Appointment'):
        raise ServiceError(400, 'Kind must be Call, Visit or Appointment.')
    who = document.contact.name if document.contact_id else 'contact'
    cust = document.customer.name
    title = f'Appointment with {who} — {cust}' if kind == 'Appointment' else f'{kind} {who} — {cust}'
    task = Task.objects.create(
        title=title, assigned_to=assignee, task_type=kind, due_date=due_date, related_document=document,
        related_customer=document.customer, related_contact=document.contact, created_by=user,
    )
    if assignee.pk != user.pk:
        notify(assignee, 'task', f'{_name(user)} scheduled a {kind.lower()} for you: "{title}"', document=document)
    return task


def call_task(creator, assignee, contact_name, customer_name, due_date, **links):
    """A Call task ("call me later", outreach call-again)."""
    return Task.objects.create(
        title=f'Call {contact_name or "contact"} — {customer_name or ""}'.rstrip(' —'), task_type='Call',
        assigned_to=assignee, due_date=due_date, created_by=creator, **links,
    )
