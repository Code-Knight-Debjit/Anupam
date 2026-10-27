"""JSON request/response helpers for the threesixty API.

No view anywhere in this app is ever decorated `@csrf_exempt` — Django's
`CsrfViewMiddleware` (already in `MIDDLEWARE`, see settings.py) protects
every unsafe-method (`POST`/`PATCH`/`PUT`/`DELETE`) request automatically.
The SPA must read the `csrftoken` cookie (set via `@ensure_csrf_cookie` on
`/360/api/me`) and send it back as the `X-CSRFToken` header — this is a
plain, standard Django session+CSRF flow, not a custom auth scheme.
"""
import json
from functools import wraps
from decimal import InvalidOperation

from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError
from django.http import JsonResponse

# Raised when a client sends a value of the wrong type/shape and it's assigned
# straight onto a model field (e.g. a string for a decimal, a missing FK id).
# These are the caller's fault, so they map to 400 rather than a 500.
INPUT_ERRORS = (ValueError, TypeError, InvalidOperation, ValidationError, IntegrityError, DataError)
INPUT_ERROR_MESSAGE = 'One or more values in the request are invalid.'


class ApiError(Exception):
    """Raised by any view/service function to short-circuit to an error
    JSON response. `extra` keys are merged into the top-level response body
    (e.g. `current_version=` on a 409 optimistic-concurrency conflict)."""

    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra


def parse_body(request):
    if not request.body:
        return {}
    try:
        data = json.loads(request.body)
    except ValueError:
        raise ApiError(400, 'Invalid JSON body.')
    if not isinstance(data, dict):
        raise ApiError(400, 'JSON body must be an object.')
    return data


def error_response(exc: ApiError):
    payload = {'error': exc.message}
    payload.update(exc.extra)
    return JsonResponse(payload, status=exc.status)


def input_errors_as_400(view_func):
    """For function views that don't go through `JsonResource.dispatch`."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except INPUT_ERRORS:
            return error_response(ApiError(400, INPUT_ERROR_MESSAGE))
    return _wrapped
