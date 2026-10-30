"""Weekly outreach call lists (REQ-AUT-01, REQ-OUT-01/02, REQ-OUT-GAP)."""
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from ..models import CallAssignment, CallAttempt, Customer, Interaction
from ..permissions import RoleRules
from . import contacts as contact_service
from . import tasks as task_service
from .errors import ServiceError


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def can_assign(user) -> bool:
    return RoleRules.is_admin(user) or RoleRules.is_branch_manager(user)


@transaction.atomic
def assign(assigner, customers, assignee, week_raw):
    """Put the customers' contacts on `assignee`'s call list for the week.

    One entry per contact; DND contacts are skipped; a customer with no
    contacts gets one blank entry; the same (customer, contact, person, week)
    is never added twice; `week_of` is always the Monday.

    REQ-OUT-GAP: the contacts come from the *assignee's* view of the customer
    (their contact-level access), not the assigner's, so a contact hidden from
    a staff member can never land on their list.
    """
    if not can_assign(assigner):
        raise ServiceError(403, 'Only Admin or Branch Manager can assign outreach.')
    week = monday_of(week_raw)
    added = skipped = dnd = 0
    visible = RoleRules.visible_customers(assigner, Customer.objects.all())
    for customer in customers:
        if not visible.filter(pk=customer.pk).exists():
            continue
        contacts = list(contact_service.visible_contacts(assignee, customer))
        targets = [c for c in contacts if not c.dnd] if contacts else [None]
        dnd += len(contacts) - len(targets) if contacts else 0
        for contact in targets:
            _, created = CallAssignment.objects.get_or_create(
                customer=customer, contact=contact, assigned_to=assignee, week_of=week,
                defaults={'assigned_by': assigner},
            )
            if created:
                added += 1
            else:
                skipped += 1
    return {'added': added, 'skipped': skipped, 'dnd_skipped': dnd, 'week_of': week.isoformat()}


def can_update(user, assignment) -> bool:
    return assignment.assigned_to_id == user.pk or can_assign(user)


@transaction.atomic
def mark_called(user, assignment, remarks=''):
    """REQ-OUT-01: the first time a call is marked Called, a Call interaction
    is added to that contact's history."""
    if not can_update(user, assignment):
        raise ServiceError(403, 'You cannot modify this assignment.')
    first_time = assignment.status != CallAssignment.STATUS_CALLED
    assignment.status = CallAssignment.STATUS_CALLED
    assignment.remarks = remarks or assignment.remarks
    if first_time or not assignment.called_at:
        assignment.called_at, assignment.called_by = timezone.now(), user
    assignment.save()
    if first_time and assignment.contact_id:
        Interaction.objects.create(
            contact=assignment.contact, type=Interaction.TYPE_CALL, date=timezone.localdate(),
            notes=remarks or 'Outreach — call completed.', created_by=user,
        )
    return assignment


@transaction.atomic
def log_not_reached(user, assignment, reason, note='', call_again=None):
    """REQ-OUT-02: every attempt is kept; a call-again date makes a Call task
    for the staff member the call is assigned to."""
    if not can_update(user, assignment):
        raise ServiceError(403, 'You cannot log an attempt on this assignment.')
    if not (reason or '').strip():
        raise ServiceError(400, 'reason is required.')
    attempt = CallAttempt.objects.create(
        assignment=assignment, reason=reason.strip(), note=note or '', by=user, call_again_date=call_again,
    )
    if call_again:
        task_service.call_task(
            user, assignment.assigned_to, assignment.contact.name if assignment.contact_id else '',
            assignment.customer.name, call_again, related_customer=assignment.customer,
            related_contact=assignment.contact,
        )
    return attempt
