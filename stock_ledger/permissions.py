from functools import wraps

from django.core.exceptions import PermissionDenied

from .models import UserProfile


def get_profile(user):
    """Every is_staff user is guaranteed a profile (signal + data migration backfill)."""
    return user.stock_profile


def role_required(*roles):
    """Raises PermissionDenied (HTTP 403) if the logged-in user's stock_profile role
    isn't in `roles`. Must be stacked after login_required/staff_required."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            profile = getattr(request.user, 'stock_profile', None)
            if profile is None or profile.role not in roles:
                raise PermissionDenied('You do not have access to this section.')
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def require_branch_match(profile, branch_id):
    """For BRANCH_STAFF, ensures the object being touched belongs to their own branch.
    ADMIN bypasses this check entirely."""
    if profile.role == UserProfile.ADMIN:
        return
    if profile.branch_id != branch_id:
        raise PermissionDenied("You cannot access another branch's records.")
