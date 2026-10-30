"""Encrypt Aadhaar / PAN values that were stored in plain text before the
fields became encrypted. Safe to re-run (already-encrypted values are skipped).
Reading never needs this: plain-text rows are still readable and are encrypted
the next time they are saved."""
from django.core.management.base import BaseCommand
from django.db import connection

from threesixty.fields import PREFIX
from threesixty.models import EmployeeProfile


class Command(BaseCommand):
    help = 'Encrypt plain-text Aadhaar / PAN values in the 360 employee profiles.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only report how many rows would change.')

    def handle(self, *args, **options):
        table = EmployeeProfile._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(f'select id, aadhaar_number, pan_number from {table}')
            plain = [r[0] for r in cursor.fetchall() if any(v and not v.startswith(PREFIX) for v in r[1:])]
        if options['dry_run']:
            self.stdout.write(f'{len(plain)} profile(s) have plain-text values.')
            return
        for profile in EmployeeProfile.objects.filter(pk__in=plain):
            profile.save(update_fields=['aadhaar_number', 'pan_number'])
        self.stdout.write(self.style.SUCCESS(f'Encrypted {len(plain)} profile(s).'))
