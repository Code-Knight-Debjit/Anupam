from django import template

register = template.Library()


@register.filter
def product_label(product):
    """'{sku} — {name} ({brand})' — the standard way a Product is identified
    throughout the Stock Ledger (code-first, name/brand as context)."""
    if not product:
        return ''
    brand = product.brand.name if product.brand_id else 'No Brand'
    sku = product.sku or '—'
    return f'{sku} — {product.name} ({brand})'
