import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Branch(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    ADMIN = 'ADMIN'
    BRANCH_STAFF = 'BRANCH_STAFF'
    VIEWER = 'VIEWER'
    ROLE_CHOICES = [
        (ADMIN, 'Admin'),
        (BRANCH_STAFF, 'Branch Staff'),
        (VIEWER, 'Viewer'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stock_profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ADMIN)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, null=True, blank=True, related_name='staff_profiles')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username} ({self.get_role_display()})'


class AuditModel(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self, user):
        self.is_deleted = True
        self.deleted_by = user
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_by', 'deleted_at'])


class OpeningStock(AuditModel):
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='opening_stock_entries')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='opening_stock_entries')
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=14, decimal_places=2)
    effective_date = models.DateField(default=timezone.localdate)
    import_batch = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        ordering = ['-effective_date', '-created_at']
        verbose_name_plural = 'Opening stock entries'

    def save(self, *args, **kwargs):
        self.total_price = Decimal(str(self.price)) * int(self.quantity)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Opening: {self.product} @ {self.branch} ({self.quantity})'


class StockPurchase(AuditModel):
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='purchase_entries')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='purchase_entries')
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=14, decimal_places=2)
    purchase_date = models.DateField(default=timezone.localdate)
    supplier = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-purchase_date', '-created_at']

    def save(self, *args, **kwargs):
        self.total_price = Decimal(str(self.price)) * int(self.quantity)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Purchase: {self.product} @ {self.branch} ({self.quantity})'


class StockSale(AuditModel):
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='sale_entries')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='sale_entries')
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=2, help_text='Cost price per unit')
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=14, decimal_places=2)
    total_selling_price = models.DecimalField(max_digits=14, decimal_places=2)
    total_profit = models.DecimalField(max_digits=14, decimal_places=2)
    sale_date = models.DateField(default=timezone.localdate)
    customer = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-sale_date', '-created_at']

    def save(self, *args, **kwargs):
        price = Decimal(str(self.price))
        selling_price = Decimal(str(self.selling_price))
        quantity = int(self.quantity)
        self.total_price = price * quantity
        self.total_selling_price = selling_price * quantity
        self.total_profit = (selling_price - price) * quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Sale: {self.product} @ {self.branch} ({self.quantity})'


class StockTransfer(models.Model):
    PENDING = 'PENDING'
    DISPATCHED = 'DISPATCHED'
    PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED'
    RECEIVED = 'RECEIVED'
    ISSUE_REPORTED = 'ISSUE_REPORTED'
    CANCELLED = 'CANCELLED'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (DISPATCHED, 'Dispatched'),
        (PARTIALLY_RECEIVED, 'Partially Received'),
        (RECEIVED, 'Received'),
        (ISSUE_REPORTED, 'Issue Reported'),
        (CANCELLED, 'Cancelled'),
    ]

    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='transfers')
    from_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='transfers_out')
    to_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='transfers_in')
    quantity = models.PositiveIntegerField()
    received_quantity = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    dispatched_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    issue_reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    issue_reported_at = models.DateTimeField(null=True, blank=True)
    issue_resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    issue_resolved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def remaining_quantity(self):
        return self.quantity - self.received_quantity

    def __str__(self):
        return f'Transfer #{self.pk}: {self.product} {self.from_branch}→{self.to_branch} ({self.quantity}) [{self.status}]'


class BranchStock(models.Model):
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='branch_stocks')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='stock_rows')
    quantity = models.IntegerField(default=0)
    low_stock_threshold = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('product', 'branch')]
        ordering = ['product__name', 'branch__name']

    def __str__(self):
        return f'{self.product} @ {self.branch}: {self.quantity}'


def new_import_batch_id():
    return uuid.uuid4().hex[:16]


class OpeningStockImportBatch(models.Model):
    batch_id = models.CharField(max_length=64, unique=True, default=new_import_batch_id)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    row_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    filename = models.CharField(max_length=255, blank=True)
    is_deleted = models.BooleanField(default=False)
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'Import {self.batch_id} ({self.row_count} rows)'
