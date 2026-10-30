"""Payment collection (REQ-PAY-01/02, REQ-LOG-01, §21).

A payment is an amount to collect from a customer; receipts are added over
time. The balance is amount - received and never negative; receiving more than
the balance needs an explicit confirmation.
"""
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from ..models import Branch, Contact, Customer, PaymentCollection, PaymentContactLog, PaymentReceipt
from ..permissions import RoleRules
from ..rules import anupam_rules as rules
from . import contacts as contact_service
from . import tasks as task_service
from .documents import D, _parse_date
from .errors import ServiceError

AGE_BUCKETS = ('0-30 days', '31-60 days', '61-90 days', '90+ days')


def visible_payments(user):
    """Admin / Branch Manager / Branch Staff see all; anyone else only their own (REQ-PAY-02)."""
    return RoleRules.sales_manager_scope_filter(user, PaymentCollection.objects.all(), owner_field='created_by')


def can_edit(user, payment) -> bool:
    if RoleRules.is_admin(user) or RoleRules.is_branch_manager(user) or RoleRules.is_branch_staff(user):
        return True
    return payment.created_by_id == user.pk


def default_branch(user):
    profile = getattr(user, 'threesixty_profile', None)
    return profile.branches.order_by('id').first() if profile else None


@transaction.atomic
def create_payment(user, data):
    """Branch = the form's branch, else the creator's first branch (§21)."""
    try:
        customer = RoleRules.visible_customers(user, Customer.objects.all()).get(pk=data.get('customer_id'))
    except (Customer.DoesNotExist, ValueError, TypeError):
        raise ServiceError(400, 'customer_id is required and must be a customer you can access.')
    if data.get('branch_id'):
        try:
            branch = Branch.objects.get(pk=data['branch_id'], is_active=True)
        except (Branch.DoesNotExist, ValueError, TypeError):
            raise ServiceError(400, 'branch_id must be an active branch.')
    else:
        branch = default_branch(user)
        if branch is None:
            raise ServiceError(400, 'Select a branch first.')
    amount = D(data.get('amount'), 'amount')
    if amount <= 0:
        raise ServiceError(400, 'Amount must be greater than zero.')
    contact = None
    if data.get('contact_id'):
        try:
            contact = contact_service.visible_contacts(user, customer).get(pk=data['contact_id'])
        except (Contact.DoesNotExist, ValueError, TypeError):
            raise ServiceError(400, 'That contact does not belong to this customer (or is not available to you).')
    return PaymentCollection.objects.create(
        branch=branch, customer=customer, contact=contact, amount=amount, created_by=user,
        date=_parse_date(data.get('date'), 'date') or timezone.localdate(), remarks=data.get('remarks', '') or '')


@transaction.atomic
def update_payment(user, payment, data):
    if not can_edit(user, payment):
        raise ServiceError(403, 'You cannot edit this payment collection.')
    if 'amount' in data:
        amount = D(data['amount'], 'amount')
        if amount <= 0:
            raise ServiceError(400, 'Amount must be greater than zero.')
        payment.amount = amount
    if 'date' in data:
        payment.date = _parse_date(data['date'], 'date') or payment.date
    if 'remarks' in data:
        payment.remarks = data['remarks'] or ''
    if data.get('contact_id') is not None:
        payment.contact = contact_service.visible_contacts(user, payment.customer).filter(pk=data['contact_id']).first() \
            if data['contact_id'] else None
    payment.version += 1
    payment.save()
    return payment


@transaction.atomic
def receive(user, payment, amount, date_, mode='', remarks='', confirm_over=False):
    if not can_edit(user, payment):
        raise ServiceError(403, 'You cannot record a receipt on this payment collection.')
    amount = D(amount, 'amount')
    if amount <= 0:
        raise ServiceError(400, 'Amount must be greater than zero.')
    balance = payment.balance()
    if rules.payment_overpay_needs_confirm({'amount': float(payment.amount), 'receivedLog': [{'amount': float(r.amount)} for r in payment.receipts.all()]},
                                           float(amount)) and not confirm_over:
        raise ServiceError(409, f'This is more than the balance ({balance}). Confirm to continue.',
                           needs_confirmation=True, balance=str(balance))
    mode = mode or PaymentReceipt.MODE_CASH
    if mode not in dict(PaymentReceipt.MODE_CHOICES):
        raise ServiceError(400, 'Unknown payment mode.')
    return PaymentReceipt.objects.create(payment=payment, amount=amount, date=_parse_date(date_, 'date') or timezone.localdate(),
                                         mode=mode, remarks=remarks or '', recorded_by=user)


def age_days(payment, today=None) -> int:
    return ((today or timezone.localdate()) - payment.date).days


def age_bucket(payment, today=None) -> str:
    """Days since the payment date (§20): 0-30, 31-60, 61-90, 90+."""
    return rules.payment_age_bucket(age_days(payment, today))


@transaction.atomic
def add_contact_log(user, payment, message, call_later_date=None):
    message = (message or '').strip()
    if not message:
        raise ServiceError(400, 'message is required.')
    call_later = _parse_date(call_later_date, 'call_later_date')
    entry = PaymentContactLog.objects.create(payment=payment, message=message, user=user, call_later_date=call_later)
    if call_later:                                           # REQ-LOG-01
        task_service.call_task(user, user, payment.contact.name if payment.contact_id else '', payment.customer.name, call_later,
                               related_customer=payment.customer, related_contact=payment.contact)
    return entry


def last_contact_on(payment):
    return max((l.timestamp for l in payment.contact_log.all()), default=None)


def call_later_date(payment):
    dated = [l for l in payment.contact_log.all() if l.call_later_date]
    return max(dated, key=lambda l: l.timestamp).call_later_date if dated else None


def call_later_bucket(payment, today=None) -> str:
    cl = call_later_date(payment)
    today = today or timezone.localdate()
    return 'none' if not cl else 'overdue' if cl < today else 'today' if cl == today else 'upcoming'


def filter_payments(queryset, params):
    get = params.get
    if get('customer_id'):
        queryset = queryset.filter(customer_id=get('customer_id'))
    if get('branch_id'):
        queryset = queryset.filter(branch_id=get('branch_id'))
    if get('date_from'):
        queryset = queryset.filter(date__gte=_parse_date(get('date_from'), 'date_from'))
    if get('date_to'):
        queryset = queryset.filter(date__lte=_parse_date(get('date_to'), 'date_to'))
    return queryset


def split_by_status(payments, status):
    """`pending` = balance > 0, `completed` = fully paid (history)."""
    if status == 'pending':
        return [p for p in payments if p.balance() > 0]
    if status in ('completed', 'history'):
        return [p for p in payments if p.amount > 0 and p.balance() == 0]
    return list(payments)
