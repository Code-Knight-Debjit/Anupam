"""Branch, numbering config, employee profile, lookups, site settings."""
import re

from django.conf import settings
from django.db import models

from ..fields import EncryptedCharField


class Branch(models.Model):
    """Anupam 360 branch (Chennai / Bengaluru). Independent of stock_ledger.Branch."""
    name = models.CharField(max_length=120, unique=True)
    letterhead_name = models.CharField(max_length=200, blank=True)
    letterhead_address = models.TextField(blank=True)
    letterhead_gstin = models.CharField(max_length=20, blank=True)
    letterhead_phone = models.CharField(max_length=40, blank=True)
    letterhead_email = models.CharField(max_length=120, blank=True)
    letterhead_mobile = models.CharField(max_length=40, blank=True)
    letterhead_website = models.CharField(max_length=200, blank=True)
    udyam_number = models.CharField(max_length=40, blank=True)

    # Bank details printed on quotation / proforma (not on challans).
    bank_name = models.CharField(max_length=120, blank=True)
    bank_branch = models.CharField(max_length=120, blank=True)
    bank_account_no = models.CharField(max_length=40, blank=True)
    bank_ifsc = models.CharField(max_length=20, blank=True)

    # Branding images — uploaded through api/views_core.branch_image (type + size checked).
    logo = models.ImageField(upload_to='threesixty/branding/', blank=True, null=True)
    dealer_logo = models.ImageField(upload_to='threesixty/branding/', blank=True, null=True)
    footer_image = models.ImageField(upload_to='threesixty/branding/', blank=True, null=True)
    payment_qr = models.ImageField(upload_to='threesixty/branding/', blank=True, null=True)

    accent_color = models.CharField(max_length=7, blank=True, help_text='#rrggbb')
    # Print/PDF layout: format 1 or 2 (REQ §18). Header and footer are shared.
    doc_format = models.PositiveSmallIntegerField(default=1, choices=[(1, 'Format 1'), (2, 'Format 2')])

    WATERMARK_LOGO = 'logo'
    WATERMARK_TEXT = 'text'
    watermark_enabled = models.BooleanField(default=False)
    watermark_type = models.CharField(
        max_length=4, default=WATERMARK_LOGO, choices=[(WATERMARK_LOGO, 'Logo'), (WATERMARK_TEXT, 'Text')],
    )
    watermark_text = models.CharField(max_length=80, blank=True)
    watermark_size = models.PositiveSmallIntegerField(default=50, help_text='Percent of the page width')

    terms = models.TextField(blank=True, help_text='Default terms & conditions for this branch')
    is_active = models.BooleanField(default=True)
    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.watermark_enabled and self.watermark_type == self.WATERMARK_TEXT and not self.watermark_text.strip():
            raise ValidationError({'watermark_text': 'Watermark text is required when the watermark type is text.'})
        if self.accent_color and not re.fullmatch(r'#[0-9a-fA-F]{6}', self.accent_color):
            raise ValidationError({'accent_color': 'Use a colour like #a14000.'})
        if not 10 <= self.watermark_size <= 100:
            raise ValidationError({'watermark_size': 'Watermark size must be between 10 and 100 percent.'})


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

    def effective_config(self) -> dict:
        """prefix/suffix/start with the spec fallbacks applied: a blank prefix
        falls back to the type's default, a blank suffix means none (REQ-DOC-02)."""
        from ..rules import anupam_rules as rules
        return rules.numbering_cfg(self.doc_type, {
            self.doc_type: {'prefix': self.prefix, 'suffix': self.suffix, 'start': self.start_at},
        })

    def format_number(self, seq: int) -> str:
        from ..rules import anupam_rules as rules
        return rules.format_doc_number(self.effective_config(), seq)


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
    # Sensitive — encrypted at rest; shown only to Admin (and masked to the person themselves); never exported/logged.
    aadhaar_number = EncryptedCharField(blank=True)
    pan_number = EncryptedCharField(blank=True)
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
