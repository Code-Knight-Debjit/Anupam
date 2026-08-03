from django.core.management.base import BaseCommand
from django.db import transaction

from stock_ledger.models import BranchStock, OpeningStock, StockPurchase, StockSale, StockTransfer


class Command(BaseCommand):
    help = (
        "Wipes Stock Ledger transaction data ONLY: OpeningStock, StockPurchase, "
        "StockSale, StockTransfer, and BranchStock rows. Branches, Users, "
        "Products, and Categories are left untouched — this resets every "
        "quantity to zero/gone so you can start recording real stock from a "
        "clean slate against the existing catalogue. Without --yes this is a "
        "dry run that only prints counts."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes', action='store_true',
            help='Actually delete the data. Omit to preview counts only (dry run).',
        )

    def handle(self, *args, **options):
        counts = {
            'StockSale': StockSale.objects.count(),
            'StockPurchase': StockPurchase.objects.count(),
            'StockTransfer': StockTransfer.objects.count(),
            'OpeningStock': OpeningStock.objects.count(),
            'BranchStock': BranchStock.objects.count(),
        }

        self.stdout.write('Stock Ledger transaction data currently on this server:')
        for name, count in counts.items():
            self.stdout.write(f'  {name}: {count}')

        if not options['yes']:
            self.stdout.write(self.style.WARNING(
                '\nDry run only — nothing was deleted. Re-run with --yes to actually clear this data.'
            ))
            return

        if sum(counts.values()) == 0:
            self.stdout.write(self.style.SUCCESS('\nNothing to delete — already clear.'))
            return

        with transaction.atomic():
            deleted = {
                'StockSale': StockSale.objects.all().delete()[0],
                'StockPurchase': StockPurchase.objects.all().delete()[0],
                'StockTransfer': StockTransfer.objects.all().delete()[0],
                'OpeningStock': OpeningStock.objects.all().delete()[0],
                'BranchStock': BranchStock.objects.all().delete()[0],
            }

        self.stdout.write(self.style.SUCCESS('\nDeleted:'))
        for name, count in deleted.items():
            self.stdout.write(f'  {name}: {count}')
        self.stdout.write(self.style.SUCCESS(
            '\nDone. Branches, Users, Products, and Categories were not touched.'
        ))
