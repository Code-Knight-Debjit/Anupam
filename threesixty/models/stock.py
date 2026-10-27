"""Dormant Stock module — the original app ships `stockProducts`/`suppliers`/
`stockBills`/`stockTransactions` collections and an auto stock-out hook on
Delivery Challan save (`autoStockOutFromDC`, ~L12844-12856), but its UI was
removed (confirmed via grep: no sidebar nav entry references it). Per
assumption §2/§6 of the master prompt, these get models (for data-import
fidelity and the DC auto-log) but no Phase-1-6 UI.
"""
from django.conf import settings
from django.db import models

from .core import Branch
from .sales import SalesDocument


class StockProduct(models.Model):
    item_name = models.CharField(max_length=500)
    make = models.CharField(max_length=120, blank=True)
    unit = models.CharField(max_length=40, blank=True)
    opening_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['item_name']

    def __str__(self):
        return self.item_name


class Supplier(models.Model):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=40, blank=True)
    gstin = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=500, blank=True)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class StockBill(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='bills')
    bill_number = models.CharField(max_length=120, blank=True)
    date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return self.bill_number or f'Bill #{self.pk}'


class StockTransaction(models.Model):
    TYPE_IN = 'IN'
    TYPE_OUT = 'OUT'
    TYPE_CHOICES = [(TYPE_IN, 'In'), (TYPE_OUT, 'Out')]

    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_transactions')
    item_name = models.CharField(max_length=500)
    make = models.CharField(max_length=120, blank=True)
    unit = models.CharField(max_length=40, blank=True)
    type = models.CharField(max_length=5, choices=TYPE_CHOICES)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    source = models.CharField(max_length=120, blank=True)  # e.g. "Delivery Challan"
    ref_document = models.ForeignKey(
        SalesDocument, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_transactions',
    )
    remarks = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_stock_transactions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['-date']
