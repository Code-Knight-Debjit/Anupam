"""Payment Collection, receipts and the payment contact log — thin views over
`services.payments`. Admin / Branch Manager / Branch Staff manage all; anyone
else only the records they created (REQ-PAY-02)."""
from django.http import JsonResponse

from ..models import PaymentCollection, PaymentContactLog, PaymentReceipt
from ..services import payments as payment_service
from .concurrency import check_version
from .http import ApiError
from .pagination import paginate
from .resources import JsonResource
from .serializers import serialize_payment_collection, serialize_payment_receipt, serialize_payment_contact_log


def payment_queryset(user):
    return payment_service.visible_payments(user).select_related('customer', 'branch', 'contact', 'created_by').prefetch_related(
        'receipts', 'contact_log')


class PaymentCollectionResource(JsonResource):
    model = PaymentCollection

    def list_queryset(self, request, **kwargs):
        qs = payment_service.filter_payments(payment_queryset(request.user), request.GET)
        return qs.order_by('-date', '-id')

    def get(self, request, pk=None, **kwargs):
        if pk is None and (request.GET.get('status') or request.GET.get('call_later')):
            rows = payment_service.split_by_status(self.list_queryset(request), request.GET.get('status'))
            if request.GET.get('call_later'):
                rows = [p for p in rows if payment_service.call_later_bucket(p) == request.GET['call_later']]
            return JsonResponse(paginate(request, rows, lambda o: self.serialize(request, o)))
        return super().get(request, pk=pk, **kwargs)

    def serialize(self, request, instance):
        return serialize_payment_collection(instance)

    def apply_create(self, request, data, **kwargs):
        return payment_service.create_payment(request.user, data)

    def apply_update(self, request, instance, data, **kwargs):
        if not payment_service.can_edit(request.user, instance):
            raise ApiError(403, 'You cannot edit this payment collection.')
        check_version(data, instance)
        payment_service.update_payment(request.user, instance, data)
        return payment_queryset(request.user).get(pk=instance.pk)

    def apply_delete(self, request, instance, **kwargs):
        if not payment_service.can_edit(request.user, instance):
            raise ApiError(403, 'You cannot delete this payment collection.')
        instance.delete()


def _payment_or_404(request, payment_id):
    try:
        return payment_queryset(request.user).get(pk=payment_id)
    except (PaymentCollection.DoesNotExist, ValueError, TypeError):
        raise ApiError(404, 'Payment collection not found.')


class PaymentReceiptResource(JsonResource):
    """Append-only: a correction is a new entry, never an edit."""
    model = PaymentReceipt

    def list_queryset(self, request, payment_id=None, **kwargs):
        qs = PaymentReceipt.objects.filter(payment__in=payment_service.visible_payments(request.user))
        if payment_id is not None:
            qs = qs.filter(payment_id=payment_id)
        return qs.select_related('recorded_by').order_by('-date', '-id')

    def serialize(self, request, instance):
        return serialize_payment_receipt(instance)

    def apply_create(self, request, data, payment_id=None, **kwargs):
        payment = _payment_or_404(request, payment_id or data.get('payment_id'))
        if data.get('amount') is None:
            raise ApiError(400, 'amount is required.')
        return payment_service.receive(request.user, payment, data['amount'], data.get('date'), data.get('mode', ''),
                                       data.get('remarks', ''), bool(data.get('confirm_over')))

    def apply_update(self, request, instance, data, **kwargs):
        raise ApiError(405, 'Receipts cannot be edited — log an adjusting entry instead.')

    def apply_delete(self, request, instance, **kwargs):
        raise ApiError(405, 'Receipts cannot be deleted — log an adjusting entry instead.')


class PaymentContactLogResource(JsonResource):
    model = PaymentContactLog

    def list_queryset(self, request, payment_id=None, **kwargs):
        qs = PaymentContactLog.objects.filter(payment__in=payment_service.visible_payments(request.user)).select_related('user')
        if payment_id is not None:
            qs = qs.filter(payment_id=payment_id)
        return qs.order_by('timestamp', 'id')

    def serialize(self, request, instance):
        return serialize_payment_contact_log(instance)

    def apply_create(self, request, data, payment_id=None, **kwargs):
        payment = _payment_or_404(request, payment_id or data.get('payment_id'))
        return payment_service.add_contact_log(request.user, payment, data.get('message'), data.get('call_later_date'))

    def apply_update(self, request, instance, data, **kwargs):
        raise ApiError(405, 'Log entries cannot be edited.')

    def apply_delete(self, request, instance, **kwargs):
        raise ApiError(405, 'Log entries cannot be deleted.')
