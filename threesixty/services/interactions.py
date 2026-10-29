"""Logging a Call / Visit / Appointment on a contact (REQUIREMENTS §8, §23).

Automations done in the caller's transaction:
  REQ-INT-01  a follow-up date creates a task for the logger
  REQ-INT-02  an Appointment must have its appointment date
  REQ-INT-03  a Visit closes that contact's open Appointment tasks
  REQ-INT-04  each joint member of a Visit / Appointment gets their own task
  REQ-INT-05  "also met" contacts get a flagged copy of the Visit (not counted twice)
"""
import uuid

from django.db import transaction

from ..models import Contact, Interaction, Task
from . import contacts as contact_service
from . import tasks as task_service
from .errors import ServiceError
from .notifications import notify

CALL_TYPES = (Interaction.TYPE_CALL, Interaction.TYPE_COLD_CALL)    # REQ-INT-07
FORM_TYPES = (Interaction.TYPE_CALL, Interaction.TYPE_VISIT, Interaction.TYPE_APPOINTMENT)
FOLLOWUP_TYPES = (Interaction.TYPE_CALL, Interaction.TYPE_VISIT, Interaction.TYPE_APPOINTMENT)
JOINT_TYPES = (Interaction.TYPE_VISIT, Interaction.TYPE_APPOINTMENT)


@transaction.atomic
def log_interaction(user, contact, type_, date, notes='', followup_date=None, also_met_contacts=(),
                    joint_users=(), lat=None, lng=None, accuracy_m=None, linked_doc=None):
    if type_ not in FORM_TYPES:
        raise ServiceError(400, 'Type must be Call, Visit or Appointment.')
    if not date:
        raise ServiceError(400, 'date is required.')
    if type_ == Interaction.TYPE_APPOINTMENT and not followup_date:
        raise ServiceError(400, 'An appointment needs the appointment date.')            # REQ-INT-02
    customer = contact.customer
    followup = followup_date if type_ in FOLLOWUP_TYPES else None
    if type_ == Interaction.TYPE_VISIT and lat is not None and lng is not None:
        location = (lat, lng, accuracy_m)
    else:
        location = (None, None, None)                           # only Visits capture a position
    group = uuid.uuid4().hex if type_ == Interaction.TYPE_VISIT else ''
    interaction = Interaction.objects.create(
        contact=contact, type=type_, date=date, notes=notes or '', created_by=user, followup_date=followup,
        location_lat=location[0], location_lng=location[1], location_accuracy_m=location[2],
        linked_doc=linked_doc, visit_group=group,
    )
    also_met = [c for c in also_met_contacts if c.pk != contact.pk] if type_ == Interaction.TYPE_VISIT else []
    if also_met:
        interaction.also_met.set(also_met)
        for other in also_met:                                    # REQ-INT-05
            Interaction.objects.create(
                contact=other, type=type_, date=date, notes=notes or '', created_by=user, is_copy=True,
                met_with_name=contact.name, visit_group=group, linked_doc=linked_doc,
            )
    joint = [u for u in joint_users if u.pk != user.pk] if type_ in JOINT_TYPES else []
    if joint:
        interaction.joint_with.set(joint)

    if followup:                                                  # REQ-INT-01
        Task.objects.create(
            title=f'{type_} {contact.name} — {customer.name}', assigned_to=user, task_type=type_,
            due_date=followup, related_contact=contact, related_customer=customer, created_by=user,
        )
    if type_ == Interaction.TYPE_VISIT:                           # REQ-INT-03
        for task in Task.objects.filter(related_contact=contact, status=task_service.OPEN):
            if task_service.kind_of(task) == 'Appointment':
                task.status = task_service.DONE
                task.auto_closed_by_visit = True
                task.save(update_fields=['status', 'auto_closed_by_visit'])
    name = user.get_full_name() or user.username
    for member in joint:                                          # REQ-INT-04
        title = f'Joint {type_.lower()} with {name} — {contact.name}, {customer.name}'
        Task.objects.create(
            title=title, assigned_to=member, task_type=type_, due_date=followup or date,
            related_contact=contact, related_customer=customer, created_by=user,
        )
        notify(member, 'task', f'{name} assigned you a task: "{title}"', customer=customer)
    return interaction


def require_logging_contact(user, contact_id):
    """The contact must be one the logger may see (contact-level access)."""
    try:
        return contact_service.visible_contacts_qs(user, Contact.objects.select_related('customer')).get(pk=contact_id)
    except Contact.DoesNotExist:
        raise ServiceError(404, 'Contact not found.')


def appointments_not_visited(user, since=None, until=None):
    """Appointments `user` took (own or joint, not copies) with no visit to the
    same contact on or after the appointment date (REQ-INT-06)."""
    from django.db.models import Exists, OuterRef, Q
    appts = Interaction.objects.filter(type=Interaction.TYPE_APPOINTMENT, is_copy=False).filter(
        Q(created_by=user) | Q(joint_with=user)).distinct()
    if since:
        appts = appts.filter(date__gte=since)
    if until:
        appts = appts.filter(date__lte=until)
    later_visit = Interaction.objects.filter(contact=OuterRef('contact'), type=Interaction.TYPE_VISIT, date__gte=OuterRef('date'))
    return appts.annotate(_visited=Exists(later_visit)).filter(_visited=False)


def visit_percent(appointments: int, visited: int) -> int:
    from ..rules.anupam_rules import visit_percent_of_appointments
    return visit_percent_of_appointments(appointments, visited)
