from django.db import migrations


def backfill_profiles(apps, schema_editor):
    """Every existing is_staff account (all of which currently have full,
    unrestricted dashboard access) gets an ADMIN profile, so the new role-based
    gating doesn't lock anyone out of sections they could already reach."""
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('stock_ledger', 'UserProfile')
    for user in User.objects.filter(is_staff=True):
        UserProfile.objects.get_or_create(user=user, defaults={'role': 'ADMIN'})


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stock_ledger', '0002_seed_branches'),
    ]

    operations = [
        migrations.RunPython(backfill_profiles, noop),
    ]
