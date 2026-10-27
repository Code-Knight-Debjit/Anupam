"""Seeds the two default branches and all DEFAULT_* lookup lists from the
original app (contact_management.html ~L3585-3832). Idempotent — safe to
re-run; existing rows (matched by kind+name / branch name) are left alone."""
from django.core.management.base import BaseCommand
from django.db import transaction

from threesixty.models import Branch, LookupItem

DEFAULT_BRANCHES = ["Chennai", "Bengaluru"]

DEFAULT_LOOKUPS = {
    LookupItem.KIND_JOB_TITLE: ["Purchase", "Maintenance", "GM", "Quality", "Stores"],
    LookupItem.KIND_SOURCE: ["Referral", "Cold Call", "LinkedIn", "Website", "Exhibition", "Existing Customer"],
    LookupItem.KIND_INDUSTRY: [
        "Conveyor Manufacturing", "Fan Manufacturing", "Gearbox Manufacturing",
        "Food Processing Machinery", "Agricultural Machinery", "Textile Machinery",
        "Packaging Machinery", "Other",
    ],
    LookupItem.KIND_LANGUAGE: ["Tamil", "English", "Hindi", "Telugu", "Malayalam"],
    LookupItem.KIND_BRAND: ["Timken", "SKF", "FAG", "NSK", "NTN", "Koyo", "NBC"],
    LookupItem.KIND_PRODUCT: [
        "Deep Groove Ball Bearing", "Spherical Roller Bearing", "Tapered Roller Bearing",
        "Cylindrical Roller Bearing", "Thrust Bearing", "Pillow Block / Housing Unit",
    ],
    LookupItem.KIND_CATEGORY: [
        "Deep Groove Ball Bearing", "Tapered Roller Bearing", "Spherical Roller Bearing",
        "Cylindrical Roller Bearing", "Thrust Bearing", "Pillow Block / Housing Unit",
        "Oil Seal", "Other",
    ],
    LookupItem.KIND_UNIT: ["Nos", "Pair", "Kg", "Pack", "Meter", "MM", "CM", "Set", "Box", "Ltr"],
    LookupItem.KIND_TAX_RATE: ["0", "5", "12", "18", "28"],
    LookupItem.KIND_PAYMENT_TERM: [
        "100% Advance", "50% Advance, 50% Before Delivery", "Net 15 Days", "Net 30 Days", "Against Delivery",
    ],
    # No default transport/courier lists in the original — start empty.
}


class Command(BaseCommand):
    help = 'Seed default branches and lookup lists for the Anupam 360 (threesixty) app.'

    @transaction.atomic
    def handle(self, *args, **options):
        created_branches = 0
        for name in DEFAULT_BRANCHES:
            _, created = Branch.objects.get_or_create(name=name)
            created_branches += int(created)

        created_lookups = 0
        for kind, names in DEFAULT_LOOKUPS.items():
            for order, name in enumerate(names):
                _, created = LookupItem.objects.get_or_create(
                    kind=kind, name=name, defaults={'sort_order': order},
                )
                created_lookups += int(created)

        self.stdout.write(self.style.SUCCESS(
            f'Seed complete: {created_branches} branch(es) created, {created_lookups} lookup item(s) created.'
        ))
