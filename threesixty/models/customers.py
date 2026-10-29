"""Customer (original `companies`), Contact (nested `contacts`), and
Interaction (nested `contact.interactions`) — normalized out of the
original app's embedded-array shape into real relations.

Field names below are taken verbatim from the original object literals
built in contact_management.html (customer save handler ~L6290-6327,
date-of-interaction handler ~L6024-6041) — see docs/360/AUDIT.md.
"""
from django.conf import settings
from django.db import models

from .core import Branch, LookupItem


class Customer(models.Model):
    name = models.CharField(max_length=255)
    plant = models.CharField(max_length=255, blank=True)  # plant/unit — disambiguates near-duplicate names
    logo = models.ImageField(upload_to='threesixty/customer_logos/', blank=True, null=True)
    address = models.CharField(max_length=500, blank=True)
    area = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    pincode = models.CharField(max_length=20, blank=True)
    website = models.CharField(max_length=255, blank=True)
    gst_number = models.CharField(max_length=20, blank=True)

    # Plant / HO geolocation — "lat, lng" pair or blank.
    plant_geo_lat = models.FloatField(null=True, blank=True)
    plant_geo_lng = models.FloatField(null=True, blank=True)
    ho_geo_lat = models.FloatField(null=True, blank=True)
    ho_geo_lng = models.FloatField(null=True, blank=True)
    ho_name = models.CharField(max_length=255, blank=True)
    ho_address = models.CharField(max_length=500, blank=True)
    ho_city = models.CharField(max_length=120, blank=True)
    ho_state = models.CharField(max_length=120, blank=True)
    ho_pincode = models.CharField(max_length=20, blank=True)
    ho_phone = models.CharField(max_length=40, blank=True)

    industry = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=120, blank=True)
    potential = models.CharField(max_length=40, blank=True)
    transport_preference = models.CharField(max_length=120, blank=True)
    courier_preference = models.CharField(max_length=120, blank=True)

    preferred_languages = models.ManyToManyField(
        LookupItem, related_name='customers_preferring_language', blank=True,
        limit_choices_to={'kind': LookupItem.KIND_LANGUAGE},
    )
    interested_brands = models.ManyToManyField(
        LookupItem, related_name='customers_interested_brand', blank=True,
        limit_choices_to={'kind': LookupItem.KIND_BRAND},
    )
    interested_products = models.ManyToManyField(
        LookupItem, related_name='customers_interested_product', blank=True,
        limit_choices_to={'kind': LookupItem.KIND_PRODUCT},
    )

    # Branch Staff/Sales Manager visibility scope — original `assignedTo` array
    # of employee ids/names. FK'd to the user model (via EmployeeProfile.user).
    assigned_to = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='threesixty_assigned_customers', blank=True,
    )

    # Who pinned the plant / head-office location, and when (REQ-GEO-01).
    plant_geo_set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    plant_geo_set_at = models.DateTimeField(null=True, blank=True)
    ho_geo_set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    ho_geo_set_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_created_customers',
    )
    # Role of the creator at the time (a snapshot: roles can change later).
    created_by_role = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Optimistic concurrency token (incremented on every API write).
    version = models.PositiveIntegerField(default=1)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['name', 'plant']), models.Index(fields=['area']), models.Index(fields=['state'])]

    def __str__(self):
        return f'{self.name} ({self.plant})' if self.plant else self.name

    TITLE_CASED_FIELDS = ('name', 'plant', 'address', 'area', 'city', 'state', 'ho_name', 'ho_address', 'ho_city', 'ho_state')

    def save(self, *args, **kwargs):
        # Names and addresses are title-cased on save (REQUIREMENTS §16).
        from ..rules.anupam_rules import title_case_words
        for field in self.TITLE_CASED_FIELDS:
            setattr(self, field, title_case_words((getattr(self, field) or '').strip()))
        super().save(*args, **kwargs)

    @property
    def select_label(self):
        """'Customer name, Plant, Area' — never the city (REQ-CUS-07)."""
        from ..rules.anupam_rules import company_select_label
        return company_select_label({'name': self.name, 'plant': self.plant, 'area': self.area})


class Contact(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=255)
    job_title = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    phone2 = models.CharField(max_length=40, blank=True)
    email = models.CharField(max_length=255, blank=True)
    dnd = models.BooleanField(default=False, help_text='Do Not Disturb — excluded from outreach/calling lists')

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ContactAccess(models.Model):
    """Contact-level assignment (REQ-CUS-02..06): a row says `user` may see
    `contact` of `customer`. **No rows for a (customer, user) means the user
    sees all of the customer's contacts.** Always read through
    `services.contacts` — never filter contacts ad hoc."""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='contact_access')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='threesixty_contact_access')
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='access_rows')

    class Meta:
        unique_together = [('customer', 'user', 'contact')]
        indexes = [models.Index(fields=['customer', 'user'])]

    def __str__(self):
        return f'{self.user_id} -> {self.contact_id} ({self.customer_id})'


class Interaction(models.Model):
    """Date-of-interaction entry logged against a Contact. `also_met` links
    sibling contacts met in the same visit; `joint_with` links colleague
    users who joined; `is_copy`/`met_with_name` mirror the original app's
    practice of writing a flagged copy into every other attendee's history
    (`visitGroup` ties the copies back to the original)."""

    TYPE_CALL = 'Call'
    TYPE_COLD_CALL = 'Cold Call'  # older data; counted as a call (REQ-INT-07)
    TYPE_VISIT = 'Visit'
    TYPE_EMAIL = 'Email'
    TYPE_APPOINTMENT = 'Appointment'
    TYPE_WHATSAPP = 'WhatsApp'
    TYPE_CHOICES = [
        (TYPE_CALL, 'Call'), (TYPE_COLD_CALL, 'Cold Call'), (TYPE_VISIT, 'Visit'), (TYPE_EMAIL, 'Email'),
        (TYPE_APPOINTMENT, 'Appointment'), (TYPE_WHATSAPP, 'WhatsApp'),
    ]

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='interactions')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    date = models.DateField()
    notes = models.TextField(blank=True)
    location_lat = models.FloatField(null=True, blank=True)
    location_lng = models.FloatField(null=True, blank=True)
    location_accuracy_m = models.PositiveIntegerField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_logged_interactions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    followup_date = models.DateField(null=True, blank=True)
    also_met = models.ManyToManyField(Contact, related_name='interactions_also_met_in', blank=True)
    visit_group = models.CharField(max_length=64, blank=True)
    joint_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='threesixty_joint_interactions', blank=True,
    )
    is_copy = models.BooleanField(default=False)
    met_with_name = models.CharField(max_length=255, blank=True)

    linked_doc = models.ForeignKey(
        'threesixty.SalesDocument', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='interactions',
    )

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.get_type_display()} with {self.contact.name} on {self.date}'
