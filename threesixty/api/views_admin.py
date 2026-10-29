"""Admin tools: backup & restore, audit log, record counts before removing a user,
customer logo upload. Everything here is Admin only unless stated."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_GET
from django.http import FileResponse, HttpResponse, JsonResponse
from django.utils import timezone

from ..models import AuditLog, Customer, EmployeeProfile
from ..permissions import RoleRules, role_360_required
from ..services import audit, backup as backup_service, exports
from ..services import users as user_service
from ..services.uploads import validate_image_upload
from .http import ApiError, error_response, input_errors_as_400, parse_body
from .pagination import paginate
from .serializers import serialize_customer

User = get_user_model()


def _uploaded_backup(request):
    uploaded = request.FILES.get('file')
    if uploaded is None:
        raise ApiError(400, 'Choose a backup file.')
    return backup_service.parse(uploaded.read(backup_service.MAX_BYTES + 1))


@require_GET
@role_360_required(EmployeeProfile.ADMIN)
@input_errors_as_400
def backup_export(request):
    """Download a full backup (one JSON file)."""
    data = backup_service.build_backup(request.user)
    audit.record(request.user, 'backup.export', summary=f'{sum(data["counts"].values())} records', request=request)
    response = HttpResponse(backup_service.dump(data), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="anupam360-backup-{timezone.localtime():%Y%m%d-%H%M}.json"'
    return response


@role_360_required(EmployeeProfile.ADMIN)
@input_errors_as_400
def backup_describe(request):
    """POST a backup file: what it contains and what an older backup lacks. Changes nothing."""
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    return JsonResponse(backup_service.describe(_uploaded_backup(request)))


@role_360_required(EmployeeProfile.ADMIN)
@input_errors_as_400
def backup_restore(request):
    """POST a backup file with `confirm=yes`. A safety copy of the current data is written first;
    the restore is all-or-nothing."""
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    if request.POST.get('confirm') != 'yes':
        return error_response(ApiError(400, 'Restoring replaces ALL current data. Send confirm=yes to go ahead.'))
    data = _uploaded_backup(request)
    backup_service._check_users(data, request.user)             # refuse before touching anything
    safety = backup_service.write_safety_copy(request.user)
    restored = backup_service.restore(data, request.user)
    audit.record(request.user, 'backup.restore', summary=f'restored {sum(restored.values())} records; safety copy {safety.name}', request=request)
    return JsonResponse({'restored': restored, 'safety_copy': safety.name})


@require_GET
@role_360_required(EmployeeProfile.ADMIN)
@input_errors_as_400
def safety_copies(request, name=None):
    """List the safety copies, or download one by name."""
    folder = backup_service.backup_dir()
    if name is None:
        files = sorted(folder.glob('safety-copy-*.json'), reverse=True)
        return JsonResponse({'results': [{'name': f.name, 'size': f.stat().st_size} for f in files]})
    path = folder / name
    if path.parent != folder or not path.name.startswith('safety-copy-') or not path.is_file():      # no path tricks
        return error_response(ApiError(404, 'Not found.'))
    return FileResponse(open(path, 'rb'), as_attachment=True, filename=path.name, content_type='application/json')


@require_GET
@role_360_required(EmployeeProfile.ADMIN)
@input_errors_as_400
def audit_log(request):
    """The audit trail, newest first. Filters: action, user_id, from, to; `format=xlsx|pdf` exports."""
    qs = AuditLog.objects.all()
    get = request.GET.get
    if get('action'):
        qs = qs.filter(action__startswith=get('action'))
    if get('user_id'):
        qs = qs.filter(user_id=get('user_id'))
    if get('from'):
        qs = qs.filter(at__date__gte=get('from'))
    if get('to'):
        qs = qs.filter(at__date__lte=get('to'))
    if get('format') in ('xlsx', 'pdf'):
        headers = ['When', 'Who', 'Action', 'Object', 'Summary', 'IP']
        rows = [[timezone.localtime(a.at).strftime('%Y-%m-%d %H:%M'), a.username, a.action, f'{a.object_type} {a.object_id}'.strip(), a.summary,
                 a.ip_address or ''] for a in qs[:5000]]
        if get('format') == 'pdf':
            body, ctype = exports.table_pdf('Audit log', headers, rows), 'application/pdf'
        else:
            body, ctype = exports.table_xlsx('Audit log', headers, rows), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response = HttpResponse(body, content_type=ctype)
        response['Content-Disposition'] = f'attachment; filename="audit-log.{get("format")}"'
        return response
    return JsonResponse(paginate(request, qs, lambda a: {
        'id': a.id, 'at': a.at.isoformat(), 'user_id': a.user_id, 'username': a.username, 'action': a.action,
        'object_type': a.object_type, 'object_id': a.object_id, 'summary': a.summary, 'ip_address': a.ip_address}))


@require_GET
@role_360_required(EmployeeProfile.ADMIN)
@input_errors_as_400
def employee_records(request, pk):
    """How many records a person owns — shown before removing them."""
    try:
        profile = EmployeeProfile.objects.select_related('user').get(pk=pk)
    except EmployeeProfile.DoesNotExist:
        return error_response(ApiError(404, 'Not found.'))
    return JsonResponse(user_service.record_counts(profile.user))


@role_360_required(EmployeeProfile.ADMIN, EmployeeProfile.BRANCH_MANAGER, EmployeeProfile.BRANCH_STAFF)
@input_errors_as_400
def customer_logo(request, pk):
    """POST (multipart `file`) / DELETE a customer's logo. Editing is direct only for roles that may edit
    customers directly; a Sales Manager's edits go through approval and cannot carry a file."""
    try:
        customer = RoleRules.visible_customers(request.user, Customer.objects.all()).get(pk=pk)
    except Customer.DoesNotExist:
        return error_response(ApiError(404, 'Not found.'))
    if request.method == 'POST':
        uploaded = request.FILES.get('file')
        if uploaded is None:
            return error_response(ApiError(400, 'No file uploaded.'))
        try:
            ext = validate_image_upload(uploaded)
        except ValidationError as exc:
            return error_response(ApiError(400, exc.messages[0]))
        customer.logo.save(f'customer{customer.pk}.{ext}', uploaded, save=True)
        return JsonResponse(serialize_customer(customer))
    if request.method == 'DELETE':
        customer.logo.delete(save=True)
        return JsonResponse(serialize_customer(customer))
    return error_response(ApiError(405, 'POST or DELETE only.'))
