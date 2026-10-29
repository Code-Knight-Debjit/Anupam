"""User lifecycle rules: activation, last-admin protection, password reset
(REQ-USR-01..03). The yes/no decisions come from `rules/anupam_rules.py`; this
module only maps ORM rows onto the dict shapes it expects.
"""
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q

from ..models import EmployeeProfile
from ..rules import anupam_rules as rules
from .nav import ROLE_NAMES

MIN_PASSWORD = rules.MIN_PASSWORD


class AccountError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def is_account_active(profile: EmployeeProfile) -> bool:
    """One notion of 'active': the login account AND the employee record."""
    return profile.user.is_active and profile.is_active_employee


def _employee_dicts():
    return [
        {'id': str(p.user_id), 'role': ROLE_NAMES[p.role], 'active': is_account_active(p)}
        for p in EmployeeProfile.objects.select_related('user')
    ]


def _actor_dict(actor_user, actor_profile):
    return {'id': str(actor_user.pk), 'role': ROLE_NAMES[actor_profile.role]}


def check_can_deactivate(actor_user, target: EmployeeProfile):
    actor_profile = actor_user.threesixty_profile
    ok, message = rules.can_deactivate_user(
        _actor_dict(actor_user, actor_profile),
        {'id': str(target.user_id), 'role': ROLE_NAMES[target.role]},
        _employee_dicts(),
    )
    if not ok:
        raise AccountError(message, 403 if 'Only an admin' in message else 400)


def check_can_change_role(actor_user, target: EmployeeProfile, new_role: str):
    """Demoting the last active Admin is the same hazard as deactivating them."""
    if target.role == EmployeeProfile.ADMIN and new_role != EmployeeProfile.ADMIN and is_account_active(target):
        others = EmployeeProfile.objects.filter(role=EmployeeProfile.ADMIN, user__is_active=True,
                                                is_active_employee=True).exclude(pk=target.pk)
        if not others.exists():
            raise AccountError('At least one active admin is required.')


def set_active(profile: EmployeeProfile, active: bool):
    """Keep `User.is_active` (what Django's login checks) and
    `EmployeeProfile.is_active_employee` (what the Users page shows) in step."""
    profile.is_active_employee = active
    profile.save(update_fields=['is_active_employee', 'updated_at'])
    if profile.user.is_active != active:
        profile.user.is_active = active
        profile.user.save(update_fields=['is_active'])


def check_new_password(new_pw: str, confirm_pw: str | None = None):
    if not new_pw or len(new_pw) < MIN_PASSWORD:
        raise AccountError(f'New password must be at least {MIN_PASSWORD} characters.')
    if confirm_pw is not None and new_pw != confirm_pw:
        raise AccountError("Passwords don't match.")


@transaction.atomic
def reset_password(username: str, new_pw: str, confirm_pw: str, verifier_username: str = '', verifier_pw: str = ''):
    """'Forgot password' on the login screen (REQ-USR-03).

    If another Admin exists, one of them must confirm with their own password
    (REQ-USR-03). A sole Admin can reset without a verifier, as the spec says;
    the sign-in page throttles attempts per account and per client.
    """
    generic = AccountError('Could not reset that password. Check the user ID and the admin details.', 403)
    try:
        target = EmployeeProfile.objects.select_related('user').get(user__username=(username or '').strip())
    except EmployeeProfile.DoesNotExist:
        raise generic
    # "Another Admin exists" counts every other Admin record, but only an
    # *active* one can confirm (an inactive Admin cannot sign in either).
    others = EmployeeProfile.objects.filter(role=EmployeeProfile.ADMIN).exclude(pk=target.pk)
    if others.exists():
        verifier = authenticate(username=(verifier_username or '').strip(), password=verifier_pw or '')
        active_others = others.filter(user__is_active=True, is_active_employee=True)
        if verifier is None or verifier.pk == target.user_id or not active_others.filter(user=verifier).exists():
            raise AccountError("That admin's password is incorrect.", 403)
    check_new_password(new_pw, confirm_pw)
    target.user.set_password(new_pw)
    target.user.save(update_fields=['password'])
    return target


@transaction.atomic
def create_first_admin(username: str, password: str, full_name: str = '') -> EmployeeProfile:
    """First run only: refuses as soon as any 360 Admin exists."""
    username = (username or '').strip()
    if not username:
        raise AccountError('User ID is required.')
    check_new_password(password)
    if EmployeeProfile.objects.filter(role=EmployeeProfile.ADMIN).exists():
        raise AccountError('An admin already exists.', 403)
    if User.objects.filter(username=username).exists():
        raise AccountError('That user ID is already taken.')
    from .accounts import limit_stock_access
    user = User.objects.create_user(username=username, password=password, is_staff=True, first_name=full_name)
    limit_stock_access(user)
    return EmployeeProfile.objects.create(user=user, role=EmployeeProfile.ADMIN)


# --------------------------------------------------------------------------- removal with record transfer (REQ-USR-02)
def record_counts(user) -> dict:
    """What a person owns: customers created / assigned, tasks created / assigned, documents, payments, outreach."""
    from ..models import CallAssignment, Customer, PaymentCollection, SalesDocument, Task
    counts = {
        'customers_created': Customer.objects.filter(created_by=user).count(),
        'customers_assigned': Customer.objects.filter(assigned_to=user).count(),
        'tasks_created': Task.objects.filter(created_by=user).count(),
        'tasks_assigned': Task.objects.filter(Q(assigned_to=user) | Q(joint_with=user)).distinct().count(),
        'documents': SalesDocument.objects.filter(created_by=user).count(),
        'payments': PaymentCollection.objects.filter(created_by=user).count(),
        'outreach_assigned': CallAssignment.objects.filter(assigned_to=user).count(),
        'outreach_given': CallAssignment.objects.filter(assigned_by=user).count(),
    }
    counts['total'] = sum(counts.values())
    return counts


def check_can_remove(actor_user, target: EmployeeProfile, total: int):
    ok, message = rules.can_remove_user(
        {'id': str(actor_user.pk), 'role': ROLE_NAMES[actor_user.threesixty_profile.role]},
        {'id': str(target.user_id), 'role': ROLE_NAMES[target.role]},
        _employee_dicts(), total)
    if not ok:
        raise AccountError(message, 403 if 'Only an admin' in message else 400)
    return message == 'needs_transfer'


@transaction.atomic
def remove_user(actor_user, target: EmployeeProfile, transfer_to_id=None):
    """Remove a person. If they own records those MUST be handed to another active
    user first (customers, tasks, documents, payments, outreach); the login is then
    disabled (the User row stays so history keeps its author)."""
    from ..models import CallAssignment, ContactAccess, Customer, PaymentCollection, SalesDocument, Task
    from .accounts import revoke_login
    counts = record_counts(target.user)
    needs_transfer = check_can_remove(actor_user, target, counts['total'])
    heir = None
    if needs_transfer:
        if not transfer_to_id:
            raise AccountError('This person owns records. Choose who should take them over.')
        heir = User.objects.filter(pk=transfer_to_id, is_active=True, threesixty_profile__is_active_employee=True).exclude(pk=target.user_id).first()
        if heir is None:
            raise AccountError('The person to transfer the records to must be another active user.')
        old = target.user
        Customer.objects.filter(created_by=old).update(created_by=heir)
        for customer in Customer.objects.filter(assigned_to=old):
            customer.assigned_to.remove(old)
            customer.assigned_to.add(heir)
            # the heir inherits the contact restriction the person had (if any), unless they already have their own
            if not ContactAccess.objects.filter(customer=customer, user=heir).exists():
                ContactAccess.objects.filter(customer=customer, user=old).update(user=heir)
            ContactAccess.objects.filter(customer=customer, user=old).delete()
        Task.objects.filter(created_by=old).update(created_by=heir)
        for task in Task.objects.filter(Q(assigned_to=old) | Q(joint_with=old)).distinct():
            if task.assigned_to_id == old.pk:
                task.assigned_to = heir
                task.save(update_fields=['assigned_to'])
            task.joint_with.remove(old)
        SalesDocument.objects.filter(created_by=old).update(created_by=heir)
        PaymentCollection.objects.filter(created_by=old).update(created_by=heir)
        for assignment in CallAssignment.objects.filter(assigned_to=old):
            clash = CallAssignment.objects.filter(customer=assignment.customer, contact=assignment.contact, assigned_to=heir,
                                                  week_of=assignment.week_of).exists()
            if clash:
                assignment.delete()
            else:
                assignment.assigned_to = heir
                assignment.save(update_fields=['assigned_to'])
        CallAssignment.objects.filter(assigned_by=old).update(assigned_by=heir)
    user = target.user
    target.delete()
    revoke_login(user)
    return {'removed': user.username, 'transferred_to': heir.username if heir else None, 'records': counts}
