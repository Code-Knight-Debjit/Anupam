"""Approval queue (REQ-ROLE-02, REQUIREMENTS §11, REQ-AUT-02..04).

A Sales Manager's edit/delete of a customer, contact, enquiry or sales
document does not change anything: it creates an `ApprovalRequest` holding the
target's state *before* and the proposed state *after*. Nothing is applied
until an Admin / Branch Manager approves. One pending request per person,
target and kind.
"""
from django.db import transaction
from django.utils import timezone

from ..models import ApprovalRequest, Contact, Customer, SalesDocument
from ..permissions import RoleRules
from . import customers as customer_service
from .errors import ServiceError
from .notifications import notify, notify_approvers

TYPE_LABELS = {
    ApprovalRequest.TYPE_EDIT: 'edit', ApprovalRequest.TYPE_DELETE: 'delete',
    ApprovalRequest.TYPE_CUSTOMER_ACCESS: 'access',
}

CONTACT_FIELDS = ('name', 'job_title', 'phone', 'phone2', 'email', 'dnd')


def _target_kwargs(target):
    if isinstance(target, Customer):
        return {'customer': target}
    if isinstance(target, Contact):
        return {'contact': target}
    if isinstance(target, SalesDocument):
        return {'document': target}
    raise TypeError(target)


def _label(target):
    if isinstance(target, Customer):
        return f'Customer {target.select_label}'
    if isinstance(target, Contact):
        return f'Contact {target.name} ({target.customer.name})'
    return f'{target.get_type_display()} {target.doc_number}'


def snapshot(target):
    if isinstance(target, Customer):
        return customer_service.snapshot(target)
    if isinstance(target, Contact):
        return {f: getattr(target, f) for f in CONTACT_FIELDS}
    from . import documents
    return documents.snapshot(target)


def _pending(user, type_, target):
    return ApprovalRequest.objects.filter(
        status=ApprovalRequest.STATUS_PENDING, requested_by=user, type=type_, **_target_kwargs(target),
    )


@transaction.atomic
def request_change(user, type_, target, proposed=None):
    """Queue an edit or delete for approval (one pending request per person,
    target and kind). Returns the new request."""
    if type_ not in (ApprovalRequest.TYPE_EDIT, ApprovalRequest.TYPE_DELETE):
        raise ValueError(type_)
    if _pending(user, type_, target).exists():
        raise ServiceError(409, f'You already have a pending {TYPE_LABELS[type_]} request for this record.')
    approval = ApprovalRequest.objects.create(
        type=type_, requested_by=user, proposed_data=proposed if type_ == ApprovalRequest.TYPE_EDIT else None,
        before_data=snapshot(target), target_label=_label(target)[:300], **_target_kwargs(target),
    )
    who = user.get_full_name() or user.username
    notify_approvers(user, 'approval-request', f'{who} requested to {TYPE_LABELS[type_]} {approval.target_label}.',
                     customer=target if isinstance(target, Customer) else None,
                     document=target if isinstance(target, SalesDocument) else None)
    return approval


@transaction.atomic
def request_customer_access(user, customer):
    """REQ-AUT-02: one pending request only; every Admin and Branch Manager is told."""
    if RoleRules.visible_customers(user, Customer.objects.filter(pk=customer.pk)).exists():
        raise ServiceError(400, 'You already have access to this customer.')
    if _pending(user, ApprovalRequest.TYPE_CUSTOMER_ACCESS, customer).exists():
        raise ServiceError(409, 'You already have a pending access request for this customer.')
    approval = ApprovalRequest.objects.create(
        type=ApprovalRequest.TYPE_CUSTOMER_ACCESS, customer=customer, requested_by=user,
        target_label=_label(customer)[:300],
    )
    who = user.get_full_name() or user.username
    notify_approvers(user, 'customer-access-request', f'{who} requested access to customer "{customer.name}".',
                     customer=customer)
    return approval


# --------------------------------------------------------------------------- deciding
def _apply(approval):
    if approval.type == ApprovalRequest.TYPE_CUSTOMER_ACCESS:
        approval.customer.assigned_to.add(approval.requested_by)
        return
    target = approval.customer or approval.contact or approval.document
    if approval.type == ApprovalRequest.TYPE_DELETE:
        if approval.contact_id:
            from . import contacts
            contacts.delete_contact(approval.contact)
        else:
            target.delete()
        return
    data = dict(approval.proposed_data or {})
    data.pop('version', None)
    if approval.customer_id:
        customer_service.apply_customer_data(approval.customer, data, approval.requested_by)
        approval.customer.version += 1
        approval.customer.save()
        customer_service.apply_customer_m2m(approval.customer, data)
    elif approval.contact_id:
        for field in CONTACT_FIELDS:
            if field in data:
                setattr(approval.contact, field, data[field])
        approval.contact.save()
    else:
        from . import documents
        documents.apply_edit(approval.document, data, approval.requested_by)


def get_pending(user, pk):
    qs = RoleRules.visible_approval_requests(
        user, ApprovalRequest.objects.select_for_update().filter(status=ApprovalRequest.STATUS_PENDING))
    try:
        approval = qs.get(pk=pk)
    except ApprovalRequest.DoesNotExist:
        raise ServiceError(404, 'Pending approval request not found in your scope.')
    return approval


def _require_approver(user):
    if not RoleRules.is_approver(user):
        raise ServiceError(403, 'Only Admin or Branch Manager can approve/reject requests.')


@transaction.atomic
def approve(user, pk):
    """Applies the change in the same transaction; if applying fails the
    request stays pending."""
    _require_approver(user)
    approval = get_pending(user, pk)
    if not (approval.customer_id or approval.contact_id or approval.document_id):
        raise ServiceError(404, 'The record this request was about no longer exists.')
    label = approval.target_label
    approval.status = ApprovalRequest.STATUS_APPROVED
    approval.reviewed_by, approval.reviewed_at = user, timezone.now()
    approval.save()
    _apply(approval)
    if approval.type == ApprovalRequest.TYPE_CUSTOMER_ACCESS:
        notify(approval.requested_by_id, 'customer-access-approved',
               f'Your access request for "{approval.customer.name}" was approved.', customer=approval.customer)
    else:
        notify(approval.requested_by_id, 'approval',
               f'Your {TYPE_LABELS[approval.type]} request for {label} was approved.')
    return approval


@transaction.atomic
def reject(user, pk):
    _require_approver(user)
    approval = get_pending(user, pk)
    approval.status = ApprovalRequest.STATUS_REJECTED
    approval.reviewed_by, approval.reviewed_at = user, timezone.now()
    approval.save()
    if approval.type == ApprovalRequest.TYPE_CUSTOMER_ACCESS:
        notify(approval.requested_by_id, 'customer-access-declined',
               f'Your access request for "{approval.customer.name if approval.customer else approval.target_label}" was declined.')
    else:
        notify(approval.requested_by_id, 'approval',
               f'Your {TYPE_LABELS[approval.type]} request for {approval.target_label} was rejected.')
    return approval


# --------------------------------------------------------------------------- "what changed"
def describe_changes(approval):
    """Rows of {field, before, after} for the "view what changed" screen: only
    the fields the requester actually changes. A delete request lists what
    will be removed; an access request has nothing to compare."""
    before = approval.before_data or {}
    if approval.type == ApprovalRequest.TYPE_EDIT:
        proposed = approval.proposed_data or {}
        rows = []
        for key, new in proposed.items():
            if key == 'version':
                continue
            old = before.get(key)
            if _norm(old) != _norm(new):
                rows.append({'field': key, 'before': old, 'after': new})
        return rows
    if approval.type == ApprovalRequest.TYPE_DELETE:
        return [{'field': key, 'before': value, 'after': None} for key, value in before.items() if value not in ('', None, [])]
    return []


def _norm(value):
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    if isinstance(value, dict):
        return {k: _norm(v) for k, v in value.items()}
    if value is None:
        return ''
    return str(value).strip()
