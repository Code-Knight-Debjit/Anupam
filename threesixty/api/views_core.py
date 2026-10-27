"""Core/admin-config resources: current-user identity, SPA bootstrap data,
branches, branch numbering config, holidays, manage-lists (LookupItem),
sales persons, site settings, and employee (Users) administration.
"""
from django.contrib.auth.models import User
from django.db import transaction
from django.http import JsonResponse

from ..models import (
    Branch, BranchNumbering, EmployeeProfile, Holiday, LookupItem, SalesPerson, SiteSetting,
)
from ..permissions import RoleRules, role_360_required, staff_360_required
from ..services.accounts import limit_stock_access, revoke_login
from .fields import parse_date_input
from .http import ApiError, error_response, input_errors_as_400, parse_body
from .resources import JsonResource
from .serializers import (
    serialize_branch, serialize_branch_numbering, serialize_employee, serialize_holiday,
    serialize_lookup_item, serialize_sales_person, serialize_site_setting,
)


@staff_360_required
def me(request):
    """Current user's identity + role flags + branch scope. Also the
    endpoint the SPA hits right after login to bootstrap its session —
    Django's CSRF middleware sets the `csrftoken` cookie on any response
    once a view has touched `request.META['CSRF_COOKIE_USED']` or used
    `{% csrf_token %}`; the existing `/dashboard/login/` page template
    already does this, so no `@ensure_csrf_cookie` is needed here."""
    profile = request.user.threesixty_profile
    return JsonResponse({
        'user': serialize_employee(profile, request.user),
        'flags': {
            'is_admin': RoleRules.is_admin(request.user),
            'is_branch_manager': RoleRules.is_branch_manager(request.user),
            'is_branch_staff': RoleRules.is_branch_staff(request.user),
            'is_sales_manager': RoleRules.is_sales_manager(request.user),
            'can_see_dashboard': RoleRules.can_see_dashboard(request.user),
            'uses_personal_dashboard': RoleRules.uses_personal_dashboard(request.user),
            'can_edit_customer_direct': RoleRules.can_edit_customer_direct(request.user),
            'can_delete_customer_direct': RoleRules.can_delete_customer_direct(request.user),
            'can_direct_edit_delete_sales_doc': RoleRules.can_direct_edit_delete_sales_doc(request.user),
        },
    })


@staff_360_required
def bootstrap(request):
    """Read-only reference data needed to render the SPA shell on load —
    branches, lookup lists (grouped by kind), sales persons, site settings,
    holidays. Deliberately unpaginated: these are small, whole-collection
    lookups by design, unlike the record-heavy resources below."""
    lookups = {}
    for item in LookupItem.objects.filter(is_active=True):
        lookups.setdefault(item.kind, []).append(serialize_lookup_item(item))
    return JsonResponse({
        'branches': [serialize_branch(b) for b in Branch.objects.filter(is_active=True)],
        'lookups': lookups,
        'sales_persons': [serialize_sales_person(p) for p in SalesPerson.objects.all()],
        'site_settings': {s.key: s.value for s in SiteSetting.objects.all()},
        'holidays': [serialize_holiday(h) for h in Holiday.objects.all()],
    })


class AdminWriteMixin:
    """`_require_admin` must be called explicitly as the first line of any
    `apply_create`/`apply_update`/`apply_delete` override — company-wide
    config (branches, numbering, manage-lists, sales persons, site
    settings, employees) is Admin-only per AUDIT.md §3. Manage Lists/Sales
    Persons/Site Settings aren't individually enumerated in the verified
    matrix; restricting them to Admin too is a documented assumption based
    on the same "company-wide config" reasoning, not a verified line-item."""

    def _require_admin(self, request):
        if not RoleRules.is_admin(request.user):
            raise ApiError(403, 'Only Admin can modify this resource.')


class BranchResource(AdminWriteMixin, JsonResource):
    model = Branch

    def serialize(self, request, instance):
        return serialize_branch(instance)

    def apply_create(self, request, data):
        self._require_admin(request)
        name = (data.get('name') or '').strip()
        if not name:
            raise ApiError(400, 'name is required.')
        return Branch.objects.create(
            name=name,
            letterhead_name=data.get('letterhead_name', ''),
            letterhead_address=data.get('letterhead_address', ''),
            letterhead_gstin=data.get('letterhead_gstin', ''),
            letterhead_phone=data.get('letterhead_phone', ''),
            letterhead_email=data.get('letterhead_email', ''),
            is_active=data.get('is_active', True),
        )

    def apply_update(self, request, instance, data):
        self._require_admin(request)
        for field in ('name', 'letterhead_name', 'letterhead_address', 'letterhead_gstin',
                      'letterhead_phone', 'letterhead_email', 'is_active'):
            if field in data:
                setattr(instance, field, data[field])
        instance.save()
        return instance

    def apply_delete(self, request, instance):
        self._require_admin(request)
        instance.delete()


@role_360_required(EmployeeProfile.ADMIN)
@input_errors_as_400
def branch_numbering_detail(request, branch_id, doc_type):
    """GET/PATCH the (branch, doc_type) numbering config — Admin only. A
    dedicated endpoint rather than a generic resource because it's keyed by
    a composite (branch, doc_type), not a single pk, and editing it never
    creates/deletes rows (`get_or_create` on first touch)."""
    try:
        branch = Branch.objects.get(pk=branch_id)
    except Branch.DoesNotExist:
        return error_response(ApiError(404, 'Branch not found.'))
    if doc_type not in dict(BranchNumbering.DOC_TYPES):
        return error_response(ApiError(400, 'Unknown doc_type.'))

    config, _ = BranchNumbering.objects.get_or_create(branch=branch, doc_type=doc_type)
    if request.method == 'GET':
        return JsonResponse(serialize_branch_numbering(config))
    if request.method == 'PATCH':
        data = parse_body(request)
        for field in ('prefix', 'suffix', 'start_at'):
            if field in data:
                setattr(config, field, data[field])
        config.save()
        return JsonResponse(serialize_branch_numbering(config))
    return error_response(ApiError(405, 'GET or PATCH only.'))


class HolidayResource(AdminWriteMixin, JsonResource):
    model = Holiday

    def serialize(self, request, instance):
        return serialize_holiday(instance)

    def apply_create(self, request, data):
        self._require_admin(request)
        if not data.get('date') or not data.get('name'):
            raise ApiError(400, 'date and name are required.')
        date = parse_date_input(data['date'], 'date')
        date_to = parse_date_input(data['date_to'], 'date_to') if data.get('date_to') else date
        if date_to < date:
            raise ApiError(400, 'date_to cannot be before date.')
        holiday = Holiday.objects.create(
            date=date, date_to=date_to, name=data['name'], is_all_branches=bool(data.get('is_all_branches')),
        )
        if 'branch_ids' in data:
            holiday.branches.set(data['branch_ids'])
        return holiday

    def apply_update(self, request, instance, data):
        self._require_admin(request)
        for field in ('date', 'date_to'):
            if field in data:
                setattr(instance, field, parse_date_input(data[field], field))
        for field in ('name', 'is_all_branches'):
            if field in data:
                setattr(instance, field, data[field])
        if instance.date_to < instance.date:
            raise ApiError(400, 'date_to cannot be before date.')
        instance.save()
        if 'branch_ids' in data:
            instance.branches.set(data['branch_ids'])
        return instance

    def apply_delete(self, request, instance):
        self._require_admin(request)
        instance.delete()


class LookupItemResource(AdminWriteMixin, JsonResource):
    model = LookupItem

    def list_queryset(self, request):
        qs = LookupItem.objects.all()
        kind = request.GET.get('kind')
        if kind:
            qs = qs.filter(kind=kind)
        return qs

    def serialize(self, request, instance):
        return serialize_lookup_item(instance)

    def apply_create(self, request, data):
        self._require_admin(request)
        kind, name = data.get('kind'), (data.get('name') or '').strip()
        if kind not in dict(LookupItem.KIND_CHOICES) or not name:
            raise ApiError(400, 'A valid kind and non-empty name are required.')
        return LookupItem.objects.create(
            kind=kind, name=name, extra=data.get('extra', ''),
            is_active=data.get('is_active', True), sort_order=data.get('sort_order', 0),
        )

    def apply_update(self, request, instance, data):
        self._require_admin(request)
        for field in ('name', 'extra', 'is_active', 'sort_order'):
            if field in data:
                setattr(instance, field, data[field])
        instance.save()
        return instance

    def apply_delete(self, request, instance):
        self._require_admin(request)
        instance.delete()


class SalesPersonResource(AdminWriteMixin, JsonResource):
    model = SalesPerson

    def serialize(self, request, instance):
        return serialize_sales_person(instance)

    def apply_create(self, request, data):
        self._require_admin(request)
        name = (data.get('name') or '').strip()
        if not name:
            raise ApiError(400, 'name is required.')
        return SalesPerson.objects.create(name=name, phone=data.get('phone', ''))

    def apply_update(self, request, instance, data):
        self._require_admin(request)
        for field in ('name', 'phone'):
            if field in data:
                setattr(instance, field, data[field])
        instance.save()
        return instance

    def apply_delete(self, request, instance):
        self._require_admin(request)
        instance.delete()


class SiteSettingResource(AdminWriteMixin, JsonResource):
    model = SiteSetting

    def serialize(self, request, instance):
        return serialize_site_setting(instance)

    def apply_create(self, request, data):
        self._require_admin(request)
        key = (data.get('key') or '').strip()
        if not key:
            raise ApiError(400, 'key is required.')
        return SiteSetting.objects.create(key=key, value=data.get('value', {}))

    def apply_update(self, request, instance, data):
        self._require_admin(request)
        if 'value' in data:
            instance.value = data['value']
            instance.save()
        return instance

    def apply_delete(self, request, instance):
        self._require_admin(request)
        instance.delete()


class EmployeeResource(AdminWriteMixin, JsonResource):
    """Users/Employees administration — list/detail visible to any staff
    member (needed for assignment pickers etc.), but create/update/delete
    is Admin-only (AUDIT.md §3: "Users CRUD / status / removal — Admin
    only"). Passwords are never read or stored in plaintext: creation uses
    `User.objects.create_user` and a reset uses `set_password`, both of
    which hash before saving."""
    model = EmployeeProfile

    def list_queryset(self, request):
        return EmployeeProfile.objects.select_related('user').all()

    def serialize(self, request, instance):
        return serialize_employee(instance, request.user)

    def apply_create(self, request, data):
        self._require_admin(request)
        username = (data.get('username') or '').strip()
        password = data.get('password')
        role = data.get('role')
        if not username or not password or role not in dict(EmployeeProfile.ROLE_CHOICES):
            raise ApiError(400, 'username, password and a valid role are required.')
        if User.objects.filter(username=username).exists():
            raise ApiError(400, 'That username is already taken.')
        emp_code = (data.get('emp_code') or '').strip() or None
        if emp_code and EmployeeProfile.objects.filter(emp_code__iexact=emp_code).exists():
            raise ApiError(400, 'That employee code is already used by another user.')
        work_start, work_end = data.get('work_start') or '09:30', data.get('work_end') or '18:30'
        if work_end <= work_start:
            raise ApiError(400, 'Work end time must be after the start time.')
        with transaction.atomic():
            user = User.objects.create_user(
                username=username, password=password, is_staff=True,
                first_name=data.get('full_name', ''),
            )
            limit_stock_access(user)
            profile = EmployeeProfile.objects.create(
                user=user, role=role,
                job_title=data.get('job_title', ''), phone=data.get('phone', ''),
                emp_code=emp_code,
                aadhaar_number=data.get('aadhaar_number', ''), pan_number=data.get('pan_number', ''),
                date_of_birth=parse_date_input(data['date_of_birth'], 'date_of_birth') if data.get('date_of_birth') else None,
                date_of_joining=parse_date_input(data['date_of_joining'], 'date_of_joining') if data.get('date_of_joining') else None,
                work_start=work_start, work_end=work_end, weekly_off=data.get('weekly_off', '0'),
            )
            if 'branch_ids' in data:
                profile.branches.set(data['branch_ids'])
        return profile

    def apply_update(self, request, instance, data):
        self._require_admin(request)
        if 'role' in data:
            if data['role'] not in dict(EmployeeProfile.ROLE_CHOICES):
                raise ApiError(400, 'Invalid role.')
            instance.role = data['role']
        if 'emp_code' in data:
            emp_code = (data['emp_code'] or '').strip() or None
            if emp_code and EmployeeProfile.objects.exclude(pk=instance.pk).filter(emp_code__iexact=emp_code).exists():
                raise ApiError(400, 'That employee code is already used by another user.')
            instance.emp_code = emp_code
        for field in ('date_of_birth', 'date_of_joining'):
            if field in data:
                setattr(instance, field, parse_date_input(data[field], field) if data[field] else None)
        work_start = data.get('work_start', instance.work_start)
        work_end = data.get('work_end', instance.work_end)
        if ('work_start' in data or 'work_end' in data) and work_end <= work_start:
            raise ApiError(400, 'Work end time must be after the start time.')
        for field in ('job_title', 'phone', 'aadhaar_number', 'pan_number', 'is_active_employee', 'work_start', 'work_end', 'weekly_off'):
            if field in data:
                setattr(instance, field, data[field])
        instance.save()
        if 'branch_ids' in data:
            instance.branches.set(data['branch_ids'])
        if 'full_name' in data:
            instance.user.first_name = data['full_name']
            instance.user.save(update_fields=['first_name'])
        if data.get('is_active_account') is not None:
            instance.user.is_active = bool(data['is_active_account'])
            instance.user.save(update_fields=['is_active'])
        if data.get('new_password'):
            instance.user.set_password(data['new_password'])
            instance.user.save(update_fields=['password'])
        return instance

    def apply_delete(self, request, instance):
        self._require_admin(request)
        if instance.user_id == request.user.id:
            raise ApiError(400, "You cannot remove your own account.")
        user = instance.user
        instance.delete()
        revoke_login(user)
