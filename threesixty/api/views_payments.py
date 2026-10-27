"""Payment Collection + Receipt resources.

The verified permission matrix (AUDIT.md §3) has no line item for payment
collections at all. Scope/permission here is a documented, conservative
default consistent with the rest of the Sales Manager restrictions: Admin/
Branch Manager/Branch Staff see and may edit/delete all; a Sales Manager
is restricted to records they created themselves — not a ported rule.
"""
from ..models import Branch, Contact, Customer, PaymentCollection, PaymentReceipt
from ..permissions import RoleRules
from .concurrency import check_version
from .fields import parse_date_input
from .http import ApiError
from .resources import JsonResource
from .serializers import serialize_payment_collection, serialize_payment_receipt


class PaymentCollectionResource(JsonResource):
    model = PaymentCollection

    def list_queryset(self, request, **kwargs):
        qs = PaymentCollection.objects.all()
        customer_id = request.GET.get('customer_id')
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        return RoleRules.sales_manager_scope_filter(request.user, qs)

    def serialize(self, request, instance):
        return serialize_payment_collection(instance)

    def _can_edit(self, request, instance):
        if RoleRules.is_admin(request.user) or RoleRules.is_branch_manager(request.user) \
                or RoleRules.is_branch_staff(request.user):
            return True
        return RoleRules.is_sales_manager(request.user) and instance.created_by_id == request.user.id

    def apply_create(self, request, data, **kwargs):
        try:
            branch = Branch.objects.get(pk=data.get('branch_id'))
        except Branch.DoesNotExist:
            raise ApiError(400, 'branch_id is required and must exist.')
        try:
            customer = Customer.objects.get(pk=data.get('customer_id'))
        except Customer.DoesNotExist:
            raise ApiError(400, 'customer_id is required and must exist.')
        if data.get('amount') is None:
            raise ApiError(400, 'amount is required.')
        contact = None
        if data.get('contact_id'):
            contact = Contact.objects.filter(pk=data['contact_id'], customer=customer).first()
        return PaymentCollection.objects.create(
            branch=branch, customer=customer, contact=contact, amount=data['amount'], created_by=request.user,
        )

    def apply_update(self, request, instance, data, **kwargs):
        if not self._can_edit(request, instance):
            raise ApiError(403, 'You cannot edit this payment collection.')
        check_version(data, instance)
        if 'amount' in data:
            instance.amount = data['amount']
        instance.version += 1
        instance.save()
        return instance

    def apply_delete(self, request, instance, **kwargs):
        if not self._can_edit(request, instance):
            raise ApiError(403, 'You cannot delete this payment collection.')
        instance.delete()


class PaymentReceiptResource(JsonResource):
    """Append-only receipts against a PaymentCollection — the original has
    no edit/delete for a logged receipt (a correction would be a new
    negative/adjusting entry in a real accounting flow), so this resource
    only supports create + list, matching that behaviour."""
    model = PaymentReceipt

    def list_queryset(self, request, payment_id=None, **kwargs):
        qs = RoleRules.sales_manager_scope_filter(
            request.user, PaymentCollection.objects.all(), owner_field='created_by'
        )
        receipts = PaymentReceipt.objects.filter(payment__in=qs)
        if payment_id is not None:
            receipts = receipts.filter(payment_id=payment_id)
        return receipts

    def serialize(self, request, instance):
        return serialize_payment_receipt(instance)

    def apply_create(self, request, data, payment_id=None, **kwargs):
        payment_id = payment_id or data.get('payment_id')
        scoped = RoleRules.sales_manager_scope_filter(
            request.user, PaymentCollection.objects.all(), owner_field='created_by'
        )
        try:
            payment = scoped.get(pk=payment_id)
        except PaymentCollection.DoesNotExist:
            raise ApiError(404, 'Payment collection not found.')
        if data.get('amount') is None or not data.get('date'):
            raise ApiError(400, 'amount and date are required.')
        return PaymentReceipt.objects.create(
            payment=payment, amount=data['amount'], date=parse_date_input(data['date'], 'date'),
            mode=data.get('mode', PaymentReceipt.MODE_CASH), remarks=data.get('remarks', ''),
            recorded_by=request.user,
        )

    def apply_update(self, request, instance, data, **kwargs):
        raise ApiError(405, 'Receipts cannot be edited — log an adjusting entry instead.')

    def apply_delete(self, request, instance, **kwargs):
        raise ApiError(405, 'Receipts cannot be deleted — log an adjusting entry instead.')
