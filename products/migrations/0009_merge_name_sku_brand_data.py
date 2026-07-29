from django.db import migrations


def compose_merged_name(apps, schema_editor):
    """Fold sku+brand into the single Name/SKU field before the columns
    holding them are dropped in a later migration. Reuses the exact
    composition the `product_label` template filter already displayed, so
    nothing existing becomes unreadable: since (sku, brand) was already
    unique_together and both are embedded below, the result can't collide."""
    Product = apps.get_model('products', 'Product')
    for product in Product.objects.select_related('brand').all():
        sku = (product.sku or '').strip()
        brand_name = product.brand.name if product.brand_id else ''
        name = (product.name or '').strip()

        if not sku and not brand_name:
            continue  # nothing to compose in — name stays as-is

        if name.lower() == sku.lower():
            merged = f'{sku} {brand_name}'.strip()
        else:
            merged = f'{sku} — {name} ({brand_name})' if brand_name else f'{sku} — {name}'

        if merged and merged != product.name:
            product.name = merged
            product.save(update_fields=['name'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0008_alter_product_sku_alter_product_unique_together'),
    ]

    operations = [
        migrations.RunPython(compose_merged_name, noop_reverse),
    ]
