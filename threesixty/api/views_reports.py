"""Reports and dashboards — thin views over `services.reports`.

`GET /reports/<name>/?from=&to=&branch_id=&user_id=` (+ per-report filters);
`format=xlsx|pdf` exports the report's main table. Admin and Branch Manager see
everything and may pick a user; everyone else gets their own data, and a Sales
Manager has no Sales Performance or Customer Activity report (403)."""
from django.http import HttpResponse, JsonResponse

from ..permissions import staff_360_required
from ..services import exports
from ..services import reports as report_service
from ..services.nav import visible_report_tabs
from .http import ApiError, error_response, input_errors_as_400


@staff_360_required
@input_errors_as_400
def report_index(request):
    tabs = visible_report_tabs(request.user)
    return JsonResponse({'reports': [{'key': k, 'title': t} for k, t in report_service.REPORTS.items() if t in tabs],
                         'can_pick_user': report_service.sees_everyone(request.user)})


@staff_360_required
@input_errors_as_400
def report_view(request, name):
    result = report_service.run(name, request.user, request.GET)
    fmt = request.GET.get('format')
    if fmt in ('xlsx', 'pdf'):
        title, headers, rows = report_service.export_table(name, result)
        if fmt == 'pdf':
            body, ctype = exports.table_pdf(title, headers, rows), 'application/pdf'
        else:
            body, ctype = exports.table_xlsx(title, headers, rows), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response = HttpResponse(body, content_type=ctype)
        response['Content-Disposition'] = f'attachment; filename="{name}.{fmt}"'
        return response
    return JsonResponse(result)


@staff_360_required
@input_errors_as_400
def dashboard_admin(request):
    f = report_service.parse_filters(request.user, request.GET)
    try:
        limit = max(1, min(100, int(request.GET.get('activity_limit', 10))))
    except ValueError:
        return error_response(ApiError(400, 'activity_limit must be a number.'))
    return JsonResponse(report_service.admin_dashboard(request.user, f, limit))


@staff_360_required
@input_errors_as_400
def dashboard_admin_drill(request):
    f = report_service.parse_filters(request.user, request.GET)
    items = report_service.employee_drill(request.user, f, request.GET.get('user_id'), request.GET.get('what'))
    return JsonResponse({'count': len(items), 'items': items[:report_service.ITEM_CAP]})


@staff_360_required
@input_errors_as_400
def dashboard_personal(request):
    # Always the viewer's own numbers, whatever the role (the Admin's company view is /dashboard/admin/).
    params = {k: v for k, v in request.GET.items() if k in ('from', 'to')}
    f = report_service.parse_filters(request.user, params)
    return JsonResponse(report_service.personal_dashboard(request.user, f))
