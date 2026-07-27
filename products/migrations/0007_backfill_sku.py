from django.db import migrations


def backfill_sku(apps, schema_editor):
    Product = apps.get_model('products', 'Product')
    for product in Product.objects.filter(sku=''):
        product.sku = f'LEGACY-{product.id}'
        product.save(update_fields=['sku'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0006_alter_product_brand'),
    ]

    operations = [
        migrations.RunPython(backfill_sku, noop),
    ]
