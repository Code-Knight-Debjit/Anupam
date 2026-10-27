"""Branch, numbering config, employee profile, lookups, site settings."""
from django.conf import settings
from django.db import models


class Branch(models.Model):
    """Anupam 360 branch (Chennai / Bengaluru). Independent of stock_ledger.Branch."""
    name = models.CharField(max_length=120, unique=True)
    letterhead_name = models.CharField(max_length=200, blank=True)
    letterhead_address = models.TextField(blank=True)
    letterhead_gstin = models.CharField(max_length=20, blank=True)
    letterhead_phone = models.CharField(max_length=40, blank=True)
    letterhead_email = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class BranchNumbering(models.Model):
    """Per-branch, per-document-type numbering config (prefix/start/padding) +
    the monotonic counter itself. One row per (branch, doc_type)."""

    DOC_TYPES = [
        ('enquiry', 'Enquiry'),
        ('quotation', 'Quotation'),
        ('po', 'Purchase Order'),
        ('dc', 'Delivery Challan'),
        ('proforma', 'Proforma Invoice'),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='numbering_configs')
    doc_type = models.CharField(max_length=20, choices=DOC_TYPES)
    prefix = models.CharField(max_length=20, blank=True)
    suffix = models.CharField(max_length=20, blank=True)
    start_at = models.PositiveIntegerField(default=1)
    # last sequence number actually issued (0 = none issued yet). Original
    # JS (`nextDocNumber`/`bumpDocCounter`) only ever moves this forward,
    # even if a user hand-types a higher doc number; see services/numbering.py.
    last_issued = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [('branch', 'doc_type')]

    def __str__(self):
        return f'{self.branch.name} / {self.get_doc_type_display()}'

    def format_number(self, seq: int) -> str:
        # Mirrors the original `formatDocNumber()` exactly: fixed 4-digit
        # padding, hyphen only inserted when prefix/suffix are present.
        padded = str(seq).zfill(4)
        out = f'{self.prefix}{"-" if self.prefix else ""}{padded}'
        if self.suffix:
            out += f'-{self.suffix}'
        return out


class EmployeeProfile(models.Model):
    """Anupam 360 role/branch profile for a staff User. Independent of
    stock_ledger.UserProfile — related_name is namespaced to avoid confusion."""

    ADMIN = 'ADMIN'
    BRANCH_MANAGER = 'BRANCH_MANAGER'
    BRANCH_STAFF = 'BRANCH_STAFF'
    SALES_MANAGER = 'SALES_MANAGER'
    ROLE_CHOICES = [
        (ADMIN, 'Admin'),
        (BRANCH_MANAGER, 'Branch Manager'),
        (BRANCH_STAFF, 'Branch Staff'),
        (SALES_MANAGER, 'Sales Manager'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='threesixty_profile',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    branches = models.ManyToManyField(Branch, related_name='employees', blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    emp_code = models.CharField(max_length=40, blank=True, null=True)
    # Sensitive — masked in every API response except to Admin (never exported/logged).
    aadhaar_number = models.CharField(max_length=20, blank=True)
    pan_number = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    # Attendance scheduling — mirrors the original's `emp.workStart`/`workEnd`/
    # `weeklyOff`/`doj` (contact_management.html attDayStatus, L12201-12220).
    work_start = models.CharField(max_length=5, default='09:30')
    work_end = models.CharField(max_length=5, default='18:30')
    # Comma-separated day-of-week ints (0=Sunday..6=Saturday), '' = none. Default '0'.
    weekly_off = models.CharField(max_length=20, default='0', blank=True)
    date_of_joining = models.DateField(null=True, blank=True)
    is_active_employee = models.BooleanField(default=True)
    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} ({self.get_role_display()})'


class Holiday(models.Model):
    # `date`/`date_to` mirror the original's `h.from`/`h.to` range (single-day
    # holidays have date_to == date). `is_all_branches` mirrors `h.all`.
    date = models.DateField()
    date_to = models.DateField()
    name = models.CharField(max_length=200)
    is_all_branches = models.BooleanField(default=False)
    branches = models.ManyToManyField(Branch, related_name='holidays', blank=True)
    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f'{self.date} — {self.name}'


class LookupItem(models.Model):
    """Generic lookup/list entry (job title, source, industry, language,
    brand, product, category, unit, tax rate, payment term, transport, ...)."""

    KIND_JOB_TITLE = 'job_title'
    KIND_SOURCE = 'source'
    KIND_INDUSTRY = 'industry'
    KIND_LANGUAGE = 'language'
    KIND_BRAND = 'brand'
    KIND_PRODUCT = 'product'
    KIND_CATEGORY = 'category'
    KIND_UNIT = 'unit'
    KIND_TAX_RATE = 'tax_rate'
    KIND_PAYMENT_TERM = 'payment_term'
    KIND_TRANSPORT = 'transport'
    KIND_COURIER = 'courier'
    KIND_CHOICES = [
        (KIND_JOB_TITLE, 'Job Title'),
        (KIND_SOURCE, 'Source'),
        (KIND_INDUSTRY, 'Industry'),
        (KIND_LANGUAGE, 'Language'),
        (KIND_BRAND, 'Brand'),
        (KIND_PRODUCT, 'Product'),
        (KIND_CATEGORY, 'Category'),
        (KIND_UNIT, 'Unit'),
        (KIND_TAX_RATE, 'Tax Rate'),
        (KIND_PAYMENT_TERM, 'Payment Term'),
        (KIND_TRANSPORT, 'Transport'),
        (KIND_COURIER, 'Courier'),
    ]

    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    name = models.CharField(max_length=200)
    # Free-form extra data (e.g. tax rate % as a string, category->brand link).
    extra = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['kind', 'sort_order', 'name']
        unique_together = [('kind', 'name')]

    def __str__(self):
        return f'[{self.kind}] {self.name}'


class SalesPerson(models.Model):
    """Standalone sales-rep lookup (name + phone) used on quotation/proforma
    docs — distinct from EmployeeProfile; original KEY_SALES_PERSONS list."""
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=40, blank=True)
    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class SiteSetting(models.Model):
    """Singleton-ish key/value store for app-wide settings (e.g. doc theme)."""
    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.key
