"""Login-account lifecycle helpers shared by the employees API and the
backup importer.

`stock_ledger.signals.ensure_stock_profile` gives *every* new `is_staff`
user a stock-ledger ADMIN profile (it was written for `createsuperuser`).
A 360 employee must not inherit stock-ledger admin rights, so any account
created for a 360 employee is downgraded to the least-privileged stock role
straight away. The stock profile can't simply be deleted: the signal would
recreate it as ADMIN on the user's next save (e.g. the `last_login` update).
"""
from stock_ledger.models import UserProfile

LEAST_PRIVILEGED_STOCK_ROLE = UserProfile.VIEWER


def limit_stock_access(user):
    """Pin the user's stock-ledger role to the least-privileged one."""
    UserProfile.objects.update_or_create(
        user=user, defaults={'role': LEAST_PRIVILEGED_STOCK_ROLE, 'branch': None},
    )


def revoke_login(user):
    """Remove every way back in for a departed employee. The `User` row is
    kept (not deleted) because other apps reference it with PROTECT FKs and
    historical records must keep their author."""
    user.is_active = False
    user.is_staff = False
    user.set_unusable_password()
    user.save(update_fields=['is_active', 'is_staff', 'password'])
