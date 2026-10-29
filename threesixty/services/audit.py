"""Writing the audit log. Called from the services / views that change something
important; it never raises (an audit failure must not undo or block the action)."""
import logging

from ..models import AuditLog

logger = logging.getLogger(__name__)


def client_ip(request):
    if request is None:
        return None
    return request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR') or None


def record(user, action, obj=None, summary='', request=None, username=''):
    try:
        AuditLog.objects.create(
            user=user if getattr(user, 'pk', None) else None,
            username=(getattr(user, 'username', '') or username)[:150],
            action=action[:60], object_type=(obj.__class__.__name__ if obj is not None else '')[:60],
            object_id=str(getattr(obj, 'pk', '') or '')[:64], summary=(summary or '')[:500], ip_address=client_ip(request))
    except Exception:                                   # pragma: no cover - defensive
        logger.warning('Could not write audit log entry %s', action, exc_info=True)
