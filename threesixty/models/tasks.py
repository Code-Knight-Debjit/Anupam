"""Task Manager, Notifications, Approval queue, and Outreach/Calling list
assignments. Field names from the original object literals — task creation
sites (~L6046-6056, ~L13393-13403), `pushNotification` (~L13555-13561),
`approvals.push` call sites (~L4950/8032/8053/8215/8225), and
`callAssignments.push` (~L5475-5482) — see docs/360/AUDIT.md.
"""
from django.conf import settings
from django.db import models

from .customers import Contact, Customer
from .sales import SalesDocument


class Task(models.Model):
    PRIORITY_LOW = 'Low'
    PRIORITY_MEDIUM = 'Medium'
    PRIORITY_HIGH = 'High'
    PRIORITY_CHOICES = [(PRIORITY_LOW, 'Low'), (PRIORITY_MEDIUM, 'Medium'), (PRIORITY_HIGH, 'High')]

    STATUS_OPEN = 'Open'
    STATUS_COMPLETED = 'Completed'
    STATUS_CHOICES = [(STATUS_OPEN, 'Open'), (STATUS_COMPLETED, 'Completed')]

    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='threesixty_assigned_tasks',
    )
    joint_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='threesixty_joint_tasks', blank=True,
    )
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    task_type = models.CharField(max_length=40, blank=True)  # e.g. Call / Visit / Appointment
    due_date = models.DateField(null=True, blank=True)
    related_customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks',
    )
    related_contact = models.ForeignKey(
        Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks',
    )
    related_document = models.ForeignKey(
        SalesDocument, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks',
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_created_tasks',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['due_date', '-created_at']

    def __str__(self):
        return self.title


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='threesixty_notifications',
    )
    type = models.CharField(max_length=60, blank=True)
    text = models.TextField()
    read = models.BooleanField(default=False)
    related_customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications',
    )
    related_document = models.ForeignKey(
        SalesDocument, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.text[:60]


class ApprovalRequest(models.Model):
    TYPE_EDIT = 'edit'
    TYPE_DELETE = 'delete'
    TYPE_CUSTOMER_ACCESS = 'customer-access'
    TYPE_CHOICES = [
        (TYPE_EDIT, 'Edit'), (TYPE_DELETE, 'Delete'), (TYPE_CUSTOMER_ACCESS, 'Customer Access'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'), (STATUS_APPROVED, 'Approved'), (STATUS_REJECTED, 'Rejected'),
    ]

    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    note = models.CharField(max_length=255, blank=True)

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, null=True, blank=True, related_name='approval_requests',
    )
    document = models.ForeignKey(
        SalesDocument, on_delete=models.CASCADE, null=True, blank=True, related_name='approval_requests',
    )
    # Snapshot of the proposed change (full target-object payload), applied
    # verbatim on approval; null for delete/access requests.
    proposed_data = models.JSONField(null=True, blank=True)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_requested_approvals',
    )
    requested_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_reviewed_approvals',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f'{self.get_type_display()} request by {self.requested_by}'


class CallAssignment(models.Model):
    """Weekly outreach/calling-list assignment of a customer contact to staff."""
    STATUS_PENDING = 'Pending'
    STATUS_CALLED = 'Called'
    STATUS_CHOICES = [(STATUS_PENDING, 'Pending'), (STATUS_CALLED, 'Called')]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='call_assignments')
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name='call_assignments')
    week_of = models.DateField()  # Monday of the assigned week
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    remarks = models.TextField(blank=True)
    called_at = models.DateTimeField(null=True, blank=True)
    called_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_calls_made',
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='threesixty_call_assignments',
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_calls_assigned',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['-week_of']
        unique_together = [('customer', 'contact', 'assigned_to', 'week_of')]


class CallAttempt(models.Model):
    """'Not reached' attempt log on a CallAssignment (`a.attempts`)."""
    assignment = models.ForeignKey(CallAssignment, on_delete=models.CASCADE, related_name='attempts')
    reason = models.CharField(max_length=120)
    note = models.TextField(blank=True)
    at = models.DateTimeField(auto_now_add=True)
    by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_call_attempts',
    )
    call_again_date = models.DateField(null=True, blank=True)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['at']
