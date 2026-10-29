"""Role/permission rules — a direct, verified port of the role helpers in
contact_management.html (~L4252-4280): `isAdmin`/`isBranchManager`/
`isBranchStaff`/`isSalesManager`, `canSeeDashboard`, `usesPersonalDashboard`,
`canDirectEditDelete`, `canEditCustomerDirect`, `canDeleteCustomerDirect`,
`canDirectEditDeleteSalesDoc`, and `namesInManagerScope`, plus the
quotation-specific Sales Manager hard-block found at ~L10176
(`!(isSalesManager() && d.type === 'quotation')`).

This is the single source of truth for `threesixty` authorization — do not
duplicate these checks ad hoc in views/serializers; call into `RoleRules`.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .models import EmployeeProfile


def _profile(user):
    """Returns the user's EmployeeProfile, or None if they don't have one
    (e.g. a stock_ledger-only or Django-admin-only account)."""
    try:
        return user.threesixty_profile
    except EmployeeProfile.DoesNotExist:
        return None


class RoleRules:
    """Stateless permission checks, each taking the acting `user` (and,
    where relevant, the target object) — mirrors the original's reliance on
    a single `currentUser` global, made explicit here instead."""

    @staticmethod
    def role(user):
        profile = _profile(user)
        return profile.role if profile else None

    @staticmethod
    def is_admin(user):
        return RoleRules.role(user) == EmployeeProfile.ADMIN

    @staticmethod
    def is_branch_manager(user):
        return RoleRules.role(user) == EmployeeProfile.BRANCH_MANAGER

    @staticmethod
    def is_branch_staff(user):
        return RoleRules.role(user) == EmployeeProfile.BRANCH_STAFF

    @staticmethod
    def is_sales_manager(user):
        return RoleRules.role(user) == EmployeeProfile.SALES_MANAGER

    @staticmethod
    def can_see_dashboard(user):
        return RoleRules.role(user) in (
            EmployeeProfile.ADMIN, EmployeeProfile.BRANCH_MANAGER,
            EmployeeProfile.BRANCH_STAFF, EmployeeProfile.SALES_MANAGER,
        )

    @staticmethod
    def uses_personal_dashboard(user):
        return RoleRules.role(user) in (
            EmployeeProfile.BRANCH_MANAGER, EmployeeProfile.BRANCH_STAFF, EmployeeProfile.SALES_MANAGER,
        )

    @staticmethod
    def can_direct_edit_delete(user):
        return RoleRules.is_admin(user) or RoleRules.is_branch_manager(user)

    @staticmethod
    def can_edit_customer_direct(user):
        return RoleRules.is_admin(user) or RoleRules.is_branch_manager(user) or RoleRules.is_branch_staff(user)

    @staticmethod
    def can_delete_customer_direct(user):
        return RoleRules.is_admin(user) or RoleRules.is_branch_manager(user)

    @staticmethod
    def can_direct_edit_delete_sales_doc(user):
        return RoleRules.is_admin(user) or RoleRules.is_branch_manager(user) or RoleRules.is_branch_staff(user)

    @staticmethod
    def can_edit_delete_sales_document(user, document):
        """Per-document override: a Sales Manager can never edit or delete a
        Quotation — not even via the approval queue (original ~L10176)."""
        if RoleRules.is_sales_manager(user) and document.type == document.TYPE_QUOTATION:
            return False
        return True

    @staticmethod
    def can_see_all_users_reports(user):
        return RoleRules.is_admin(user) or RoleRules.is_branch_manager(user)

    @staticmethod
    def is_approver(user):
        return RoleRules.is_admin(user) or RoleRules.is_branch_manager(user)

    @staticmethod
    def needs_approval(user, action):
        """Whether `user`'s edit/delete goes to the approval queue instead of
        applying directly (REQ-ROLE-02). Actions: customer.edit, contact.edit,
        customer.delete, salesdoc.edit, salesdoc.delete."""
        if action in ('customer.edit', 'contact.edit'):
            return not RoleRules.can_edit_customer_direct(user)
        if action == 'customer.delete':
            return not RoleRules.can_delete_customer_direct(user)
        if action in ('salesdoc.edit', 'salesdoc.delete'):
            return not RoleRules.can_direct_edit_delete_sales_doc(user)
        raise ValueError(action)

    @staticmethod
    def user_ids_in_manager_scope(user):
        """User ids whose branch(es) overlap the Branch Manager's own
        branches, plus the manager themself — the Django-native equivalent
        of the original's name-set (`namesInManagerScope`, ~L4271-4280);
        original matched by display name since its records only stored
        employee names, but matching by user id is unambiguous here."""
        profile = _profile(user)
        if not profile:
            return {user.pk}
        my_branch_ids = set(profile.branches.values_list('id', flat=True))
        ids = {user.pk}
        scoped = EmployeeProfile.objects.filter(branches__id__in=my_branch_ids).values_list('user_id', flat=True)
        ids.update(scoped)
        return ids

    @staticmethod
    def visible_approval_requests(user, queryset):
        """Admin sees all; Branch Manager sees only requests raised by staff
        in their own branch scope (`namesInManagerScope`, original ~L8201).
        Addition beyond the original: a requester who is neither (Branch
        Staff/Sales Manager) can see the status of their own requests — the
        original has no equivalent "my requests" view to verify against, so
        this is a documented, additive assumption, not a ported behaviour."""
        if RoleRules.is_admin(user):
            return queryset
        if RoleRules.is_branch_manager(user):
            # Requests from people in the manager's branches, plus people who
            # belong to no branch at all (nobody else could see those).
            return queryset.filter(
                Q(requested_by_id__in=RoleRules.user_ids_in_manager_scope(user))
                | Q(requested_by__threesixty_profile__branches__isnull=True)
            ).distinct()
        return queryset.filter(requested_by=user)

    @staticmethod
    def visible_customers(user, queryset):
        """Sales Manager only sees customers they created or are assigned to
        (original `visibleCompanies()`, ~L5055-5073); every other role sees
        all customers (matches the verified permission matrix, AUDIT.md §3)."""
        if RoleRules.is_sales_manager(user):
            return queryset.filter(Q(created_by=user) | Q(assigned_to=user)).distinct()
        return queryset

    @staticmethod
    def sales_manager_scope_filter(user, queryset, owner_field='created_by'):
        """Generic "own records only" restriction applied for a Sales
        Manager on resources that have no bespoke visibility rule of their
        own (payment collections, tasks) — not a verified original
        behaviour (the original has no payments/tasks visibility split by
        role at all), but a conservative, documented default consistent
        with the rest of the Sales Manager scoping rules."""
        if RoleRules.is_sales_manager(user):
            return queryset.filter(**{owner_field: user})
        return queryset

    @staticmethod
    def visible_sales_documents(user, queryset):
        """Sales Manager sees documents they created themselves, plus any
        Enquiry/Quotation on a customer assigned to them — Sales Order/DC/
        Proforma on an assigned-but-not-self-created customer stay hidden
        (original `visibleSalesDocs(type)`, ~L8306-8321). Every other role
        sees all documents."""
        if RoleRules.is_sales_manager(user):
            from .models import Customer, SalesDocument
            assigned_ids = Customer.objects.filter(assigned_to=user).values_list('id', flat=True)
            return queryset.filter(
                Q(created_by=user)
                | (Q(type__in=[SalesDocument.TYPE_ENQUIRY, SalesDocument.TYPE_QUOTATION])
                   & Q(customer_id__in=assigned_ids))
            ).distinct()
        return queryset


LOGIN_URL = '/360/login/'


def staff_360_required(view_func):
    """Signed in, staff, and an active Anupam 360 employee. Uses Django's
    session auth; unauthenticated visitors are sent to the 360 login page
    (`/dashboard/login/` still works and redirects 360 users back here)."""
    @wraps(view_func)
    @login_required(login_url=LOGIN_URL)
    @user_passes_test(lambda u: u.is_staff, login_url=LOGIN_URL)
    def _wrapped(request, *args, **kwargs):
        profile = _profile(request.user)
        if profile is None:
            raise PermissionDenied('No Anupam 360 employee profile for this account.')
        if not profile.is_active_employee:
            raise PermissionDenied('This account is inactive.')
        return view_func(request, *args, **kwargs)
    return _wrapped


def role_360_required(*roles):
    """Restrict to one or more EmployeeProfile roles, e.g.
    @role_360_required(EmployeeProfile.ADMIN)."""
    def decorator(view_func):
        @wraps(view_func)
        @staff_360_required
        def _wrapped(request, *args, **kwargs):
            if RoleRules.role(request.user) not in roles:
                raise PermissionDenied('Your role cannot perform this action.')
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
