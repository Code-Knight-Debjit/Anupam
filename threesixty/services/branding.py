"""The app logo (sign-in screen, sidebar, mobile header, and the default letterhead / watermark logo of a branch with none of
its own) and an optional separate sidebar logo — the reference's Branches-page "App logo" and "Sidebar logo" settings. Each is
one image file plus a small site setting that remembers where it is and its shape."""
import time

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage

from ..models import SiteSetting
from .errors import ServiceError
from .uploads import validate_image_upload

KINDS = {'app': 'appLogo', 'sidebar': 'sidebarLogo'}


def _key(kind):
    if kind not in KINDS:
        raise ServiceError(404, 'Unknown logo.')
    return KINDS[kind]


def info(kind):
    """{'url', 'path', 'aspect'} of the chosen logo, or None for the built-in one."""
    row = SiteSetting.objects.filter(key=_key(kind)).first()
    value = (row.value if row else None) or {}
    if not value.get('name') or not default_storage.exists(value['name']):
        return None
    return {'url': value['url'], 'path': default_storage.path(value['name']), 'aspect': value.get('aspect') or 0}


def set_logo(kind, uploaded, aspect=0):
    key = _key(kind)
    try:
        ext = validate_image_upload(uploaded)
    except ValidationError as exc:
        raise ServiceError(400, exc.messages[0])
    clear(kind)
    name = default_storage.save(f'threesixty/branding/{kind}_logo.{ext}', uploaded)
    try:
        aspect = float(aspect or 0)
    except (TypeError, ValueError):
        aspect = 0
    value = {'name': name, 'url': f'{default_storage.url(name)}?v={int(time.time())}', 'aspect': aspect}
    SiteSetting.objects.update_or_create(key=key, defaults={'value': value})
    return value


def clear(kind):
    row = SiteSetting.objects.filter(key=_key(kind)).first()
    if row:
        name = (row.value or {}).get('name')
        if name and default_storage.exists(name):
            default_storage.delete(name)
        row.delete()
