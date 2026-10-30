"""Print Label: options, customer auto-fill and the label PDF. The PDF is the
same bytes for Preview, Print (inline) and Download (`download=1`)."""
from django.views.decorators.http import require_GET
from django.http import HttpResponse, JsonResponse

from ..permissions import staff_360_required
from ..services import labels
from .http import ApiError, error_response, input_errors_as_400, parse_body


def _guard(request):
    if not labels.can_print_labels(request.user):
        raise ApiError(403, 'Your role cannot print labels.')


@require_GET
@staff_360_required
@input_errors_as_400
def label_options(request):
    _guard(request)
    return JsonResponse(labels.options())


@require_GET
@staff_360_required
@input_errors_as_400
def label_autofill(request):
    _guard(request)
    return JsonResponse(labels.autofill(request.user, request.GET.get('customer_id'), request.GET.get('contact_id') or None))


@staff_360_required
@input_errors_as_400
def label_pdf(request):
    """POST a JSON body or GET the same fields as a query string."""
    _guard(request)
    data = parse_body(request) if request.method == 'POST' else request.GET.dict()
    req = labels.build_request(request.user, data)
    response = HttpResponse(labels.build_pdf(req), content_type='application/pdf')
    kind = 'attachment' if str(data.get('download', '')).lower() in ('1', 'true') else 'inline'
    response['Content-Disposition'] = f'{kind}; filename="label.pdf"'
    return response
