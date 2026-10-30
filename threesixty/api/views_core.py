"""Core/admin-config resources: current-user identity, SPA bootstrap data,
branches, branch numbering config, holidays, manage-lists (LookupItem),
sales persons, site settings, and employee (Users) administration.
"""
import re

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse

from ..models import (
    Branch, BranchNumbering, EmployeeProfile, Holiday, LookupItem, SalesPerson, SiteSetting,
)
from ..permissions import RoleRules, role_360_required, staff_360_required
from ..services import attendance as attendance_service
from ..services import audit as audit_service
from ..services import lists as list_service
from ..services import users as user_service
from ..services.accounts import limit_stock_access, revoke_login
from ..services.nav import visible_nav, visible_report_tabs
from ..services.numbering import NOT_GENERATED, peek_next_number
from ..services.uploads import validate_image_upload
from .fields import parse_date_input
from .http import ApiError, error_response, input_errors_as_400, parse_body
from .resources import JsonResource
from .serializers import (
    BRANCH_IMAGE_FIELDS, BRANCH_TEXT_FIELDS, serialize_branch, serialize_branch_numbering, serialize_employee, serialize_holiday,
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
            'is_approver': RoleRules.is_approver(request.user),
        },
        'nav': visible_nav(request.user),
        'report_tabs': visible_report_tabs(request.user),
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


_HHMM = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')


def clean_schedule(work_start, work_end, weekly_off):
    """Work hours as HH:MM (end after start) and weekly-off days as 0=Sun..6=Sat."""
    if not (_HHMM.match(str(work_start)) and _HHMM.match(str(work_end))):
        raise ApiError(400, 'Work hours must be in HH:MM format.')
    if work_end <= work_start:
        raise ApiError(400, 'Work end time must be after the start time.')
    days = [d.strip() for d in str(weekly_off or '').split(',') if d.strip()]
    if any(d not in {'0', '1', '2', '3', '4', '5', '6'} for d in days):
        raise ApiError(400, 'Weekly off must be day numbers 0 (Sun) to 6 (Sat), comma-separated.')
    return ','.join(sorted(set(days)))


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

    def _apply(self, branch, data):
        for field in BRANCH_TEXT_FIELDS:
            if field in data:
                value = data[field]
                if isinstance(value, str):
                    value = value.strip()
                setattr(branch, field, value)
        if not branch.name:
            raise ApiError(400, 'name is required.')
        if Branch.objects.exclude(pk=branch.pk).filter(name__iexact=branch.name).exists():
            raise ApiError(400, 'A branch with that name already exists.')
        try:
            branch.full_clean(exclude=[*BRANCH_IMAGE_FIELDS, 'legacy_id'])
        except ValidationError as exc:
            raise ApiError(400, '; '.join(m for msgs in exc.message_dict.values() for m in msgs))
        branch.save()
        return branch

    def apply_create(self, request, data):
        self._require_admin(request)
        branch = self._apply(Branch(), data)
        audit_service.record(request.user, 'branch.create', branch, branch.name, request)
        return branch

    def apply_update(self, request, instance, data):
        self._require_admin(request)
        branch = self._apply(instance, data)
        audit_service.record(request.user, 'branch.update', branch, ', '.join(sorted(k for k in data if k != 'version')), request)
        return branch

    def apply_delete(self, request, instance):
        """Records that use the branch keep it (REQ-LST-01): a branch in use is
        deactivated instead of deleted."""
        self._require_admin(request)
        outcome = list_service.remove_branch(instance)
        audit_service.record(request.user, f'branch.{outcome}', instance, instance.name, request)
        return JsonResponse({'deleted': outcome == 'deleted', 'deactivated': outcome == 'deactivated'})


@role_360_required(EmployeeProfile.ADMIN)
@input_errors_as_400
def branch_image(request, branch_id, kind):
    """POST (multipart `file`) or DELETE one branding image of a branch —
    Admin only; type, content and size are checked (services/uploads)."""
    if kind not in BRANCH_IMAGE_FIELDS:
        return error_response(ApiError(404, 'Unknown image kind.'))
    try:
        branch = Branch.objects.get(pk=branch_id)
    except Branch.DoesNotExist:
        return error_response(ApiError(404, 'Branch not found.'))
    if request.method == 'POST':
        uploaded = request.FILES.get('file')
        if uploaded is None:
            return error_response(ApiError(400, 'No file uploaded.'))
        try:
            ext = validate_image_upload(uploaded)
        except ValidationError as exc:
            return error_response(ApiError(400, exc.messages[0]))
        uploaded.name = f'branch{branch.pk}_{kind}.{ext}'
        getattr(branch, kind).save(uploaded.name, uploaded, save=True)
        return JsonResponse(serialize_branch(branch))
    if request.method == 'DELETE':
        getattr(branch, kind).delete(save=True)
        return JsonResponse(serialize_branch(branch))
    return error_response(ApiError(405, 'POST or DELETE only.'))


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

    if doc_type in NOT_GENERATED:
        return error_response(ApiError(400, 'Pending PO has no generated number — it uses the customer\'s own PO number.'))

    config, _ = BranchNumbering.objects.get_or_create(branch=branch, doc_type=doc_type)
    if request.method == 'GET':
        return JsonResponse(_numbering_payload(config))
    if request.method == 'PATCH':
        data = parse_body(request)
        if 'prefix' in data:
            config.prefix = str(data['prefix'] or '').strip()[:20]
        if 'suffix' in data:
            config.suffix = str(data['suffix'] or '').strip()[:20]
        if 'start_at' in data:
            try:
                start_at = int(data['start_at'])
            except (TypeError, ValueError):
                return error_response(ApiError(400, 'Start number must be a whole number.'))
            if start_at < 1:
                return error_response(ApiError(400, 'Start number must be at least 1.'))
            config.start_at = start_at
        config.save()
        return JsonResponse(_numbering_payload(config))
    return error_response(ApiError(405, 'GET or PATCH only.'))


def _numbering_payload(config):
    payload = serialize_branch_numbering(config)
    effective = config.effective_config()
    payload.update({'effective_prefix': effective['prefix'], 'next_number': peek_next_number(config.branch, config.doc_type)})
    return payload


class HolidayResource(AdminWriteMixin, JsonResource):
    model = Holiday

    def serialize(self, request, instance):
        return serialize_holiday(instance)

    def apply_create(self, request, data):
        """Adds the holiday and tells everyone (or the chosen branches') — REQ-AUT-09."""
        self._require_admin(request)
        if not data.get('date') or not data.get('name'):
            raise ApiError(400, 'date and name are required.')
        date = parse_date_input(data['date'], 'date')
        date_to = parse_date_input(data['date_to'], 'date_to') if data.get('date_to') else date
        return attendance_service.add_holiday(
            data['name'], date, date_to, data.get('branch_ids'), bool(data.get('is_all_branches')))

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
        # A previously removed (deactivated) value comes back instead of colliding.
        item, created = LookupItem.objects.get_or_create(
            kind=kind, name=name,
            defaults={'extra': data.get('extra', ''), 'is_active': data.get('is_active', True),
                      'sort_order': data.get('sort_order', 0)},
        )
        if not created:
            if item.is_active:
                raise ApiError(400, 'That value already exists in this list.')
            item.is_active = True
            item.extra = data.get('extra', item.extra)
            item.save()
        return item

    def apply_update(self, request, instance, data):
        self._require_admin(request)
        for field in ('name', 'extra', 'is_active', 'sort_order'):
            if field in data:
                setattr(instance, field, data[field])
        instance.save()
        return instance

    def apply_delete(self, request, instance):
        """Records already using the value keep it (REQ-LST-01)."""
        self._require_admin(request)
        outcome = list_service.remove_lookup(instance)
        return JsonResponse({'deleted': outcome == 'deleted', 'deactivated': outcome == 'deactivated'})


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
        return EmployeeProfile.objects.select_related('user').prefetch_related('branches').order_by('user__first_name', 'user__username')

    @staticmethod
    def _check_password(password, user=None):
        try:
            user_service.check_new_password(password, user=user)
        except user_service.AccountError as exc:
            raise ApiError(exc.status, exc.message)

    def serialize(self, request, instance):
        return serialize_employee(instance, request.user)

    def apply_create(self, request, data):
        self._require_admin(request)
        username = (data.get('username') or '').strip()
        password = data.get('password')
        role = data.get('role')
        if not username or not password or role not in dict(EmployeeProfile.ROLE_CHOICES):
            raise ApiError(400, 'username, password and a valid role are required.')
        self._check_password(password, User(username=username, first_name=data.get('full_name', '')))
        if User.objects.filter(username=username).exists():
            raise ApiError(400, 'That username is already taken.')
        emp_code = (data.get('emp_code') or '').strip() or None
        if emp_code and EmployeeProfile.objects.filter(emp_code__iexact=emp_code).exists():
            raise ApiError(400, 'That employee code is already used by another user.')
        work_start, work_end = data.get('work_start') or '09:30', data.get('work_end') or '18:30'
        weekly_off = clean_schedule(work_start, work_end, data.get('weekly_off', '0'))
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
                work_start=work_start, work_end=work_end, weekly_off=weekly_off,
            )
            if 'branch_ids' in data:
                profile.branches.set(data['branch_ids'])
        audit_service.record(request.user, 'user.create', profile, f'{username} ({role})', request)
        return profile

    def apply_update(self, request, instance, data):
        self._require_admin(request)
        try:
            if 'role' in data:
                if data['role'] not in dict(EmployeeProfile.ROLE_CHOICES):
                    raise ApiError(400, 'Invalid role.')
                user_service.check_can_change_role(request.user, instance, data['role'])
                instance.role = data['role']
            # `is_active_account` is the older name of the same switch.
            wants_active = data.get('is_active', data.get('is_active_account'))
            if wants_active is not None and not wants_active and user_service.is_account_active(instance):
                user_service.check_can_deactivate(request.user, instance)
        except user_service.AccountError as exc:
            raise ApiError(exc.status, exc.message)
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
        if {'work_start', 'work_end', 'weekly_off'} & set(data):
            data['weekly_off'] = clean_schedule(work_start, work_end, data.get('weekly_off', instance.weekly_off))
        for field in ('job_title', 'phone', 'aadhaar_number', 'pan_number', 'work_start', 'work_end', 'weekly_off'):
            if field in data:
                setattr(instance, field, data[field])
        instance.save()
        if 'branch_ids' in data:
            instance.branches.set(data['branch_ids'])
        if 'full_name' in data:
            instance.user.first_name = data['full_name']
            instance.user.save(update_fields=['first_name'])
        if wants_active is not None:
            user_service.set_active(instance, bool(wants_active))
        if data.get('new_password'):
            self._check_password(data['new_password'], instance.user)
            instance.user.set_password(data['new_password'])
            instance.user.save(update_fields=['password'])
        changed = sorted(set(data) - {'version', 'new_password'})
        audit_service.record(request.user, 'user.update', instance,
                             ', '.join(changed + (['password'] if data.get('new_password') else [])), request)
        return instance

    def apply_delete(self, request, instance):
        """Remove a person (REQ-USR-02). If they own records, `?transfer_to=<user id>` (or a JSON body
        `{"transfer_to_id": ...}`) names who takes them over — otherwise it is refused."""
        self._require_admin(request)
        try:
            body = parse_body(request)
        except ApiError:
            body = {}
        transfer_to = request.GET.get('transfer_to') or body.get('transfer_to_id')
        try:
            result = user_service.remove_user(request.user, instance, transfer_to)
        except user_service.AccountError as exc:
            raise ApiError(exc.status, exc.message, **({'needs_transfer': True} if 'owns records' in exc.message else {}))
        audit_service.record(request.user, 'user.remove', summary=f'{result["removed"]} removed; records to {result["transferred_to"] or "nobody"}', request=request)
        return JsonResponse({'deleted': True, **result})
