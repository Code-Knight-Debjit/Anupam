from django.apps import AppConfig


class StockLedgerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stock_ledger'
    verbose_name = 'Stock Ledger'

    def ready(self):
        import stock_ledger.signals  # noqa: F401
