from .models import UserProfile
from .services import get_low_stock_items, visible_branches


def dashboard_role(request):
    """Exposes the logged-in dashboard user's role/branch to every template,
    used by dashboard/base.html to gate the sidebar sections."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated or not user.is_staff:
        return {}
    profile = getattr(user, 'stock_profile', None)
    if profile is None:
        return {}
    return {
        'dash_role': profile.role,
        'dash_branch': profile.branch,
    }


def low_stock_alert(request):
    """Runs the once-per-session low-stock check for Admin/Branch Staff on every
    dashboard page render, so it fires regardless of which page is opened first
    in a session (per the 'any dashboard page' requirement)."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated or not user.is_staff:
        return {'show_low_stock_modal': False}
    profile = getattr(user, 'stock_profile', None)
    if profile is None or profile.role not in (UserProfile.ADMIN, UserProfile.BRANCH_STAFF):
        return {'show_low_stock_modal': False}
    if request.session.get('low_stock_alert_shown'):
        return {'show_low_stock_modal': False}

    branch_ids = list(visible_branches(profile).values_list('id', flat=True))
    items = get_low_stock_items(branch_ids=branch_ids)
    if not items:
        return {'show_low_stock_modal': False}
    # Flag set only once something is actually shown, so a stock-free session
    # keeps checking on each page until there's something to alert on.
    request.session['low_stock_alert_shown'] = True
    return {'show_low_stock_modal': True, 'low_stock_items': items}
