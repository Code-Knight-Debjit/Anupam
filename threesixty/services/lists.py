"""Removing pick-list values and branches without touching existing records
(REQ-LST-01).

Text-valued fields (industry, source, transport, ...) are plain strings on the
records, so removing the list entry already leaves them untouched. Entries
that records point at through a relation (preferred languages / brands /
products, branches) are *deactivated* instead of deleted when in use — they
disappear from pickers but every record keeps its value.
"""
from django.db import transaction

from ..models import Branch, LookupItem


def lookup_in_use(item: LookupItem) -> bool:
    return (item.customers_preferring_language.exists()
            or item.customers_interested_brand.exists()
            or item.customers_interested_product.exists())


def branch_in_use(branch: Branch) -> bool:
    return (branch.sales_documents.exists() or branch.payment_collections.exists()
            or branch.stock_transactions.exists() or branch.employees.exists())


@transaction.atomic
def remove_lookup(item: LookupItem) -> str:
    """Returns 'deleted' or 'deactivated'."""
    if lookup_in_use(item):
        item.is_active = False
        item.save(update_fields=['is_active'])
        return 'deactivated'
    item.delete()
    return 'deleted'


@transaction.atomic
def remove_branch(branch: Branch) -> str:
    if branch_in_use(branch):
        branch.is_active = False
        branch.save(update_fields=['is_active', 'updated_at'])
        return 'deactivated'
    branch.delete()
    return 'deleted'
