"""Pagination for every list endpoint — the original has none at all (it
reads/writes a whole-array localStorage key per model, see AUDIT.md §4),
so this is a new, additive behaviour the master prompt requires rather
than a ported one."""
from django.conf import settings
from django.core.paginator import Paginator


def paginate(request, queryset, serialize, default_page_size=None):
    default_page_size = default_page_size or getattr(settings, 'DASHBOARD_PAGE_SIZE', 20)
    try:
        page_number = max(int(request.GET.get('page', 1)), 1)
    except (TypeError, ValueError):
        page_number = 1
    try:
        page_size = min(max(int(request.GET.get('page_size', default_page_size)), 1), 200)
    except (TypeError, ValueError):
        page_size = default_page_size

    paginator = Paginator(queryset, page_size)
    page = paginator.get_page(page_number)
    return {
        'results': [serialize(obj) for obj in page.object_list],
        'count': paginator.count,
        'page': page.number,
        'num_pages': paginator.num_pages,
        'page_size': page_size,
    }
