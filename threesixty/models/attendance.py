"""Attendance (check-in/out with geolocation) and Leave requests. Field
names from `attCheckIn`/`attCheckOut` (~L12357-12388) and the leave submit
handler (~L12391-12430) — see docs/360/AUDIT.md."""
from django.conf import settings
from django.db import models


class AttendanceRecord(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='threesixty_attendance_records',
    )
    date = models.DateField()
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    in_loc_lat = models.FloatField(null=True, blank=True)
    in_loc_lng = models.FloatField(null=True, blank=True)
    in_loc_accuracy_m = models.PositiveIntegerField(null=True, blank=True)
    out_loc_lat = models.FloatField(null=True, blank=True)
    out_loc_lng = models.FloatField(null=True, blank=True)
    out_loc_accuracy_m = models.PositiveIntegerField(null=True, blank=True)
    # Manual Admin/Branch-Manager correction (`attOpenDay`/`attDaySave`,
    # ~L12543-12570) — overrides the computed day status outright.
    STATUS_PRESENT = 'Present'
    STATUS_HALF_DAY = 'Half day'
    STATUS_ABSENT = 'Absent'
    STATUS_LEAVE = 'Leave'
    STATUS_OFF_HOLIDAY = 'Off / Holiday'
    STATUS_CHOICES = [
        (STATUS_PRESENT, 'Present'), (STATUS_HALF_DAY, 'Half day'), (STATUS_ABSENT, 'Absent'),
        (STATUS_LEAVE, 'Leave'), (STATUS_OFF_HOLIDAY, 'Off / Holiday'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, blank=True)
    note = models.CharField(max_length=255, blank=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_attendance_corrections',
    )

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['-date']
        unique_together = [('user', 'date')]

    def __str__(self):
        return f'{self.user} — {self.date}'


class LeaveRequest(models.Model):
    STATUS_PENDING = 'Pending'
    STATUS_APPROVED = 'Approved'
    STATUS_REJECTED = 'Rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'), (STATUS_APPROVED, 'Approved'), (STATUS_REJECTED, 'Rejected'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='threesixty_leave_requests',
    )
    date_from = models.DateField()
    date_to = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)

    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='threesixty_leave_decisions',
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True)

    legacy_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)

    class Meta:
        ordering = ['-requested_at']

    def days(self):
        return (self.date_to - self.date_from).days + 1
