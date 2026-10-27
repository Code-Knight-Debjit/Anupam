"""Downgrades stock-ledger access for 360 employees who were auto-promoted to
stock ADMIN by `stock_ledger.signals.ensure_stock_profile`.

Usage:
    python manage.py fix_360_stock_access           # dry run, lists who would change
    python manage.py fix_360_stock_access --apply

Only 360 employees whose 360 role is *not* Admin are touched; a 360 Admin
keeps whatever stock role they have, since that is usually the site owner.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from stock_ledger.models import UserProfile
from threesixty.models import EmployeeProfile
from threesixty.services.accounts import LEAST_PRIVILEGED_STOCK_ROLE, limit_stock_access


class Command(BaseCommand):
    help = 'Downgrade stock-ledger ADMIN profiles of non-Admin 360 employees.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Write the changes (default is a dry run).')

    def handle(self, *args, **options):
        affected = (
            EmployeeProfile.objects.exclude(role=EmployeeProfile.ADMIN)
            .filter(user__stock_profile__role=UserProfile.ADMIN)
            .select_related('user')
        )
        for profile in affected:
            self.stdout.write(f'{profile.user.username} ({profile.role}): stock ADMIN -> {LEAST_PRIVILEGED_STOCK_ROLE}')
        if not options['apply']:
            self.stdout.write(f'{affected.count()} account(s) would change. Re-run with --apply.')
            return
        with transaction.atomic():
            for profile in affected:
                limit_stock_access(profile.user)
        self.stdout.write(self.style.SUCCESS('Done.'))
