# Generated manually to add Excel-backed specification table support.

from django.db import migrations, models

from products.models import product_excel_upload_to


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='needs_excel_table',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='product',
            name='excel_table_file',
            field=models.FileField(blank=True, null=True, upload_to=product_excel_upload_to),
        ),
        migrations.AddField(
            model_name='product',
            name='excel_table_data',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]