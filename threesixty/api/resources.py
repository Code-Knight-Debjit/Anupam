"""Generic per-record JSON resource base class — list (paginated) / detail /
create / update / delete, built on Django's plain `View` (CSRF-protected by
the existing `CsrfViewMiddleware`, never exempted). Subclasses override the
hooks below; nothing here guesses business rules — permission/scope logic
lives in `threesixty.permissions.RoleRules` and is only *called* from here.
"""
from django.db import transaction
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View

from ..permissions import staff_360_required
from .http import INPUT_ERROR_MESSAGE, INPUT_ERRORS, ApiError, error_response, parse_body
from .pagination import paginate


@method_decorator(staff_360_required, name='dispatch')
class JsonResource(View):
    model = None

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except ApiError as exc:
            return error_response(exc)
        except INPUT_ERRORS:
            # Writes run inside transaction.atomic(), so nothing was persisted.
            return error_response(ApiError(400, INPUT_ERROR_MESSAGE))

    # ---- hooks for subclasses ----
    # All hooks accept **kwargs so nested routes (e.g. /customers/<customer_id>/contacts)
    # can thread the parent id through from the URLconf without changing this base class.
    def serialize(self, request, instance):
        raise NotImplementedError

    def list_queryset(self, request, **kwargs):
        """Already scoped (RoleRules) + ordered; may also apply query-param
        filters. Default: everything, unordered beyond the model's Meta."""
        return self.model.objects.all()

    def get_object(self, request, pk, **kwargs):
        """404s (not 403s) for records outside the caller's visible scope —
        this intentionally does not leak existence of out-of-scope records."""
        try:
            return self.list_queryset(request, **kwargs).get(pk=pk)
        except self.model.DoesNotExist:
            raise ApiError(404, 'Not found.')

    def apply_create(self, request, data, **kwargs):
        raise ApiError(405, 'Create not supported on this resource.')

    def apply_update(self, request, instance, data, **kwargs):
        raise ApiError(405, 'Update not supported on this resource.')

    def apply_delete(self, request, instance, **kwargs):
        instance.delete()
        return None

    # ---- HTTP verbs ----
    def get(self, request, pk=None, **kwargs):
        if pk is None:
            return JsonResponse(
                paginate(request, self.list_queryset(request, **kwargs), lambda o: self.serialize(request, o))
            )
        instance = self.get_object(request, pk, **kwargs)
        return JsonResponse(self.serialize(request, instance))

    def post(self, request, pk=None, **kwargs):
        if pk is not None:
            raise ApiError(405, 'Use PATCH on the record URL to update.')
        data = parse_body(request)
        with transaction.atomic():
            instance = self.apply_create(request, data, **kwargs)
        return JsonResponse(self.serialize(request, instance), status=201)

    def patch(self, request, pk=None, **kwargs):
        if pk is None:
            raise ApiError(405, 'A record id is required to update.')
        instance = self.get_object(request, pk, **kwargs)
        data = parse_body(request)
        with transaction.atomic():
            result = self.apply_update(request, instance, data, **kwargs)
        if isinstance(result, JsonResponse):
            return result
        return JsonResponse(self.serialize(request, result))

    put = patch

    def delete(self, request, pk=None, **kwargs):
        if pk is None:
            raise ApiError(405, 'A record id is required to delete.')
        instance = self.get_object(request, pk, **kwargs)
        with transaction.atomic():
            result = self.apply_delete(request, instance, **kwargs)
        if isinstance(result, JsonResponse):
            return result
        return JsonResponse({'deleted': True})
