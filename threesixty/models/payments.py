"""Payment collection (amount due) + receipts (partial collections against
it) — original `payments` array (KEY_PAYMENTS='paymentCollections') with
nested `receivedLog`. Field names from the add/edit handlers (~L13859-13868,
~L13935-13938) — see docs/360/AUDIT.md."""
from decimal import Decimal

from django.conf import settings
from django.db import models

from .core import Branch
from .customers import Contact, Customer


class PaymentCollection(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='payment_collections')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='payment_collections')
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name='payment_collections')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    remarks = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_created_payments',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['-date']
        indexes = [models.Index(fields=['date']), models.Index(fields=['created_by', 'date'])]


    def received(self):
        return sum((r.amount for r in self.receipts.all()), Decimal('0.00'))

    def balance(self):
        """Amount still to collect; never negative (REQ-PAY-01)."""
        return max(Decimal('0.00'), self.amount - self.received())

    def __str__(self):
        return f'{self.customer.name} — {self.amount}'


class PaymentReceipt(models.Model):
    MODE_CASH = 'Cash'
    MODE_CHEQUE = 'Cheque'
    MODE_BANK_TRANSFER = 'Bank Transfer'
    MODE_UPI = 'UPI'
    MODE_CHOICES = [
        (MODE_CASH, 'Cash'), (MODE_CHEQUE, 'Cheque'),
        (MODE_BANK_TRANSFER, 'Bank Transfer'), (MODE_UPI, 'UPI'),
    ]

    payment = models.ForeignKey(PaymentCollection, on_delete=models.CASCADE, related_name='receipts')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_CASH)
    remarks = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_recorded_receipts',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['-date']


class PaymentContactLog(models.Model):
    """Contact log on a payment collection (chat-style notes, optional "call me
    later" date that also creates a Call task for the person logging it)."""
    payment = models.ForeignKey(PaymentCollection, on_delete=models.CASCADE, related_name='contact_log')
    message = models.TextField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    timestamp = models.DateTimeField(auto_now_add=True)
    call_later_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['timestamp']
