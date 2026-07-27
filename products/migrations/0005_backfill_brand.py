from django.db import migrations


def backfill_brand(apps, schema_editor):
    Brand = apps.get_model('products', 'Brand')
    Product = apps.get_model('products', 'Product')
    unbranded, _ = Brand.objects.get_or_create(
        slug='unbranded', defaults={'name': 'Unbranded', 'is_active': True, 'order': 0}
    )
    Product.objects.filter(brand__isnull=True).update(brand=unbranded)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0004_brand_product_sku_product_brand'),
    ]

    operations = [
        migrations.RunPython(backfill_brand, noop),
    ]
