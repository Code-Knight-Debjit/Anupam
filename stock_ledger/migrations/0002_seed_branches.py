from django.db import migrations


BRANCHES = [
    {
        'name': 'Bengaluru',
        'slug': 'bengaluru',
        'code': 'BLR',
        'address': 'No. 128, Jigani Link Road, Bommasandra Industrial Area, Bengaluru – 560 099, Karnataka',
    },
    {
        'name': 'Chennai',
        'slug': 'chennai',
        'code': 'MAA',
        'address': 'No. 3 (Old No.2) Katchaleeswarar Pagoda Lane, Parrys, Chennai – 600001, Tamil Nadu',
    },
]


def seed_branches(apps, schema_editor):
    Branch = apps.get_model('stock_ledger', 'Branch')
    for data in BRANCHES:
        Branch.objects.get_or_create(slug=data['slug'], defaults=data)


def remove_branches(apps, schema_editor):
    Branch = apps.get_model('stock_ledger', 'Branch')
    Branch.objects.filter(slug__in=[b['slug'] for b in BRANCHES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('stock_ledger', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_branches, remove_branches),
    ]
