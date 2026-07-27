from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=User)
def ensure_stock_profile(sender, instance, created, **kwargs):
    """Safety net for is_staff accounts created outside the dashboard's Add User
    flow (e.g. `createsuperuser`) — they default to full ADMIN access, matching
    pre-existing behaviour where any is_staff user could reach everything."""
    if not instance.is_staff:
        return
    UserProfile.objects.get_or_create(user=instance, defaults={'role': UserProfile.ADMIN})
