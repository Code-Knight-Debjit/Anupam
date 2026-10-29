import logging

from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django_ratelimit.core import is_ratelimited

from dashboard.views import _login_client_ip_key, _login_throttled, _login_username_key

from .models import EmployeeProfile
from .permissions import staff_360_required
from .services import users as user_service

logger = logging.getLogger(__name__)


@staff_360_required
def index(request):
    """The Anupam 360 single-page app shell."""
    return render(request, 'threesixty/index.html', {
        'profile': request.user.threesixty_profile,
    })


def _reset_throttled(request):
    """Password-reset attempts are throttled per target user and per client,
    separately from sign-in. Best-effort, like the sign-in throttle."""
    try:
        by_account = is_ratelimited(request, group='threesixty_reset_account', key=_login_username_key,
                                    rate='5/15m', method='POST', increment=True)
        by_client = is_ratelimited(request, group='threesixty_reset_client', key=_login_client_ip_key,
                                   rate='15/15m', method='POST', increment=True)
    except Exception:
        logger.warning('Reset rate limiting unavailable; allowing the attempt.', exc_info=True)
        return False
    return by_account or by_client


def _safe_next(request):
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return next_url
    return '/360/'


def _login_context(request, **extra):
    ctx = {'first_run': not EmployeeProfile.objects.filter(role=EmployeeProfile.ADMIN).exists(),
           'next': request.GET.get('next', '')}
    ctx.update(extra)
    return ctx


def threesixty_login(request):
    """User ID + password sign-in, 'Forgot password' (REQ-USR-03) and the
    one-time 'create the first admin' form (REQ §24). Inactive users cannot
    sign in (REQ-USR-01): Django's auth backend rejects `is_active=False`, and
    the profile must be an active 360 employee."""
    if request.user.is_authenticated and getattr(request.user, 'threesixty_profile', None):
        return redirect(_safe_next(request))
    if request.method != 'POST':
        return render(request, 'threesixty/login.html', _login_context(request))

    action = request.POST.get('action', 'login')

    if action == 'reset':
        if _reset_throttled(request):
            return render(request, 'threesixty/login.html',
                          _login_context(request, error='Too many attempts. Please wait a few minutes.', panel='reset'),
                          status=429)
        try:
            user_service.reset_password(
                request.POST.get('username', ''), request.POST.get('new_password', ''),
                request.POST.get('confirm_password', ''),
                request.POST.get('verifier_username', ''), request.POST.get('verifier_password', ''),
            )
        except user_service.AccountError as exc:
            return render(request, 'threesixty/login.html',
                          _login_context(request, error=exc.message, panel='reset'), status=exc.status)
        return render(request, 'threesixty/login.html',
                      _login_context(request, notice='Password changed. You can sign in now.'))

    if action == 'first_admin':
        try:
            with transaction.atomic():
                profile = user_service.create_first_admin(
                    request.POST.get('username', ''), request.POST.get('password', ''),
                    request.POST.get('full_name', ''),
                )
        except user_service.AccountError as exc:
            return render(request, 'threesixty/login.html',
                          _login_context(request, error=exc.message, panel='first'), status=exc.status)
        login(request, profile.user)
        return redirect('/360/')

    if _login_throttled(request):
        return render(request, 'threesixty/login.html',
                      _login_context(request, error='Too many login attempts. Please wait a few minutes and try again.'),
                      status=429)
    user = authenticate(request, username=request.POST.get('username', '').strip(),
                        password=request.POST.get('password', ''))
    profile = getattr(user, 'threesixty_profile', None) if user else None
    if user and user.is_staff and profile and profile.is_active_employee:
        login(request, user)
        return redirect(_safe_next(request))
    return render(request, 'threesixty/login.html',
                  _login_context(request, error='Invalid user ID or password, or the account is inactive.'))


def threesixty_logout(request):
    logout(request)
    return redirect('threesixty:login')
