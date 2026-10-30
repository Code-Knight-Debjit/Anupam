"""Creating notifications (the bell). Every automation in REQUIREMENTS §16
that says "notified" goes through `notify`, in the caller's transaction."""
from ..models import EmployeeProfile, Notification


def notify(user, type_, text, *, customer=None, document=None):
    """`user` may be a User or a user id. Returns the Notification."""
    user_id = getattr(user, 'pk', user)
    return Notification.objects.create(
        user_id=user_id, type=type_, text=text,
        related_customer=customer, related_document=document,
    )


def active_profiles(*roles):
    qs = EmployeeProfile.objects.filter(user__is_active=True, is_active_employee=True)
    return qs.filter(role__in=roles) if roles else qs


def approver_user_ids(requester=None):
    """Every active Admin, plus Branch Managers. A Branch Manager only
    *sees* requests from people in their branch scope, so when the requester
    has branches the notification goes to managers who share one; a requester
    with no branch is visible to (and notified to) every manager."""
    ids = set(active_profiles(EmployeeProfile.ADMIN).values_list('user_id', flat=True))
    managers = active_profiles(EmployeeProfile.BRANCH_MANAGER)
    profile = getattr(requester, 'threesixty_profile', None) if requester is not None else None
    branch_ids = list(profile.branches.values_list('id', flat=True)) if profile else []
    if branch_ids:
        managers = managers.filter(branches__id__in=branch_ids)
    ids |= set(managers.values_list('user_id', flat=True))
    if requester is not None:
        ids.discard(requester.pk)
    return ids


def notify_approvers(requester, type_, text, **kwargs):
    for user_id in approver_user_ids(requester):
        notify(user_id, type_, text, **kwargs)
