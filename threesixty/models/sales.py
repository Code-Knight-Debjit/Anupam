"""Sales documents: enquiry / quotation / po (sales order) / dc (delivery
challan) / proforma — one table per SALES_DOC_CONFIG type, discriminated by
`type`, matching the original's single `salesDocs` array. Field names are
taken verbatim from the original save-handler object literals (~L11370-11508)
and totals math (`computeQuotationDocData`, ~L8805-8850) — see
docs/360/AUDIT.md §1/§5.
"""
from django.conf import settings
from django.db import models

from .core import Branch, SalesPerson
from .customers import Contact, Customer


class SalesDocument(models.Model):
    TYPE_ENQUIRY = 'enquiry'
    TYPE_QUOTATION = 'quotation'
    TYPE_PO = 'po'
    TYPE_DC = 'dc'
    TYPE_PROFORMA = 'proforma'
    TYPE_CHOICES = [
        (TYPE_ENQUIRY, 'Enquiry'), (TYPE_QUOTATION, 'Quotation'), (TYPE_PO, 'Sales Order'),
        (TYPE_DC, 'Delivery Challan'), (TYPE_PROFORMA, 'Proforma Invoice'),
    ]
    # Reference chain enforced per SALES_DOC_CONFIG.refType: quotation->enquiry,
    # dc->po, proforma->quotation. enquiry/po have no refType.
    REF_TYPE_OF = {
        TYPE_QUOTATION: TYPE_ENQUIRY,
        TYPE_DC: TYPE_PO,
        TYPE_PROFORMA: TYPE_QUOTATION,
    }

    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    doc_number = models.CharField(max_length=64, db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='sales_documents')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='sales_documents')
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales_documents')
    date = models.DateField()
    remarks = models.TextField(blank=True)

    reference = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='derived_documents',
    )

    # enquiry only
    source = models.CharField(max_length=120, blank=True)

    # quotation/dc/proforma order status (enquiry/po have their own option sets too)
    order_status = models.CharField(max_length=40, blank=True)

    # dc only
    vehicle = models.CharField(max_length=120, blank=True)
    transport = models.CharField(max_length=120, blank=True)

    # quotation/dc/proforma charges + totals (computeQuotationDocData)
    show_discount_in_pdf = models.BooleanField(default=False)
    packing_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    packing_tax = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    freight_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    freight_tax = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    other_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_charges_tax = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    round_off = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sub_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quotation_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # quotation/dc/proforma quote metadata
    sales_person = models.ForeignKey(SalesPerson, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales_documents')
    # Text copy of the sales person's name: removing a sales person from the list
    # must not change documents that already used them (REQ-LST-01).
    sales_person_name = models.CharField(max_length=150, blank=True)
    valid_till = models.DateField(null=True, blank=True)
    ref_no = models.CharField(max_length=120, blank=True)
    ref_date = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(max_length=255, blank=True)
    terms = models.JSONField(default=list, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_created_sales_documents',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [models.Index(fields=['type', 'branch', 'doc_number'])]

    def __str__(self):
        return f'{self.get_type_display()} {self.doc_number}'

    def save(self, *args, **kwargs):
        if self.sales_person_id and self.sales_person:
            self.sales_person_name = self.sales_person.name
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = {*kwargs['update_fields'], 'sales_person_name'}
        super().save(*args, **kwargs)


class SalesDocumentItem(models.Model):
    document = models.ForeignKey(SalesDocument, on_delete=models.CASCADE, related_name='items')
    position = models.PositiveIntegerField(default=0)
    item_name = models.CharField(max_length=500, blank=True)
    make = models.CharField(max_length=120, blank=True)
    qty = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit = models.CharField(max_length=40, blank=True)
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # per-line display amount (post discount/tax-fold, pre line-tax) and value
    # (qty * unitFinal) as computed by the original save handler.
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    value = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['position']


class SupplyLogEntry(models.Model):
    """DC/PO fulfilment tracking against a sales-order item's pending qty."""
    item = models.ForeignKey(SalesDocumentItem, on_delete=models.CASCADE, related_name='supply_log')
    date = models.DateField()
    qty_supplied = models.DecimalField(max_digits=12, decimal_places=2)
    remarks = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_supply_log_entries',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['date']


class DocumentCallLog(models.Model):
    """Call log entries on quotation/dc/proforma docs (`cfg.hasCallLog`)."""
    document = models.ForeignKey(SalesDocument, on_delete=models.CASCADE, related_name='call_log')
    message = models.TextField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_call_log_entries',
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['timestamp']
