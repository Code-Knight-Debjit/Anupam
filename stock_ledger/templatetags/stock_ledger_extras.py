from django import template

register = template.Library()


@register.filter
def product_label(product):
    """A bare Product's display identity — just the merged Name/SKU field now
    that Brand/SKU no longer exist as separate fields."""
    if not product:
        return ''
    return product.name


@register.filter
def ledger_product_label(entry):
    """Display identity for a ledger row (OpeningStock/StockPurchase/StockSale/
    StockTransfer). `product` can be null after the referenced Product was
    deleted (on_delete=SET_NULL) — falls back to the snapshot captured at row
    creation time so historical rows never go blank."""
    if entry is None:
        return ''
    if entry.product_id:
        return entry.product.name
    return entry.product_name_snapshot or '(deleted product)'
