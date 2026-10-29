"""Contact-level access (REQ-CUS-02..06, REQ-OUT-GAP).

`ContactAccess(customer, user, contact)`: rows restrict a user to the listed
contacts of a customer; **no rows for that user+customer means all contacts**.
Admin, Branch Manager, Branch Staff and the customer's creator always see all.

Every place that lists contacts — customer page, task / interaction pickers,
outreach, labels, exports, reports — must come through `visible_contacts` /
`visible_contacts_qs`, never filter `Contact` directly.
"""
from django.db import transaction
from django.db.models import Q

from ..models import Contact, ContactAccess, Customer
from ..permissions import RoleRules


def sees_all_contacts(user, customer) -> bool:
    if RoleRules.is_admin(user) or RoleRules.is_branch_manager(user) or RoleRules.is_branch_staff(user):
        return True
    return customer.created_by_id == user.pk


def restricted_contact_ids(user, customer):
    """None if `user` is unrestricted on `customer`, else the set of allowed contact ids."""
    if sees_all_contacts(user, customer):
        return None
    ids = set(ContactAccess.objects.filter(customer=customer, user=user).values_list('contact_id', flat=True))
    return ids or None


def visible_contacts(user, customer):
    """Contacts of one customer that `user` may see (a queryset)."""
    qs = Contact.objects.filter(customer=customer)
    allowed = restricted_contact_ids(user, customer)
    return qs if allowed is None else qs.filter(pk__in=allowed)


def visible_contacts_qs(user, queryset=None):
    """Same rule across many customers at once, for flat contact lists."""
    qs = queryset if queryset is not None else Contact.objects.all()
    qs = qs.filter(customer__in=RoleRules.visible_customers(user, Customer.objects.all()))
    if RoleRules.is_admin(user) or RoleRules.is_branch_manager(user) or RoleRules.is_branch_staff(user):
        return qs
    rows = ContactAccess.objects.filter(user=user)
    return qs.filter(
        Q(customer__created_by=user) | ~Q(customer_id__in=rows.values('customer_id')) | Q(pk__in=rows.values('contact_id'))
    )


def can_see_contact(user, contact) -> bool:
    return visible_contacts_qs(user, Contact.objects.filter(pk=contact.pk)).exists()


@transaction.atomic
def assign_customer(customer, user, contact_ids=None):
    """Assign (add) `user` to the customer, optionally sharing only some
    contacts. Selecting every contact — or giving none — leaves no restriction
    row (REQ-CUS-03); assigning again replaces the earlier selection."""
    customer.assigned_to.add(user)
    ContactAccess.objects.filter(customer=customer, user=user).delete()
    if contact_ids is None:
        return customer
    own = set(customer.contacts.values_list('pk', flat=True))
    chosen = {int(c) for c in contact_ids} & own
    if chosen and len(chosen) < len(own):
        ContactAccess.objects.bulk_create(
            [ContactAccess(customer=customer, user=user, contact_id=c) for c in chosen]
        )
    return customer


@transaction.atomic
def deassign_customer(customer, user):
    """Removing a person also removes their contact restriction (REQ-CUS-04)."""
    customer.assigned_to.remove(user)
    ContactAccess.objects.filter(customer=customer, user=user).delete()


@transaction.atomic
def delete_contact(contact):
    """Deleting a contact must never widen anyone's access: a person whose only
    shared contact disappears would silently fall back to "all contacts", so
    such a person is un-assigned instead."""
    customer = contact.customer
    affected = list(ContactAccess.objects.filter(customer=customer, contact=contact).values_list('user_id', flat=True))
    contact.delete()
    for user_id in affected:
        if not ContactAccess.objects.filter(customer=customer, user_id=user_id).exists():
            customer.assigned_to.remove(user_id)
