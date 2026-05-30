from django.core.management.base import BaseCommand
from products.models import Category, Product
from django.utils.text import slugify

CATEGORIES = [
    {"name": "Rolling Bearings", "icon": "⚙️", "description": "Tapered roller bearings, ball bearings, cylindrical and spherical roller bearings for all industrial applications.", "order": 1},
    {"name": "Bearing Housings", "icon": "🔩", "description": "Pillow block, SNT Plummer block, Timken split bearing housing and solid block solutions.", "order": 2},
    {"name": "Linear Motion", "icon": "📐", "description": "LM bush bearings, ball screws, cross roller guides, precision lock nuts and lead screws.", "order": 3},
    {"name": "Power Transmission", "icon": "⚡", "description": "Chain & sprocket, V-pulley & belt, timing belts, couplings and specialized industrial chains.", "order": 4},
    {"name": "Lubrication & Maintenance", "icon": "🛢️", "description": "Groeneveld-BEKA lubrication systems, seals, bearing pullers, heaters and maintenance products.", "order": 5},
]

PRODUCTS = {
    "Rolling Bearings": [
        {"name": "Tapered Roller Bearing", "description": "High-precision Timken tapered roller bearings for heavy radial and axial loads. Available in 0-8\" range.", "is_featured": True},
        {"name": "Cylindrical Roller Bearing", "description": "4-row cylindrical roller bearings for high radial load applications in industrial machinery.", "is_featured": True},
        {"name": "Spherical Roller Bearing", "description": "Self-aligning spherical roller bearings for misaligned applications and heavy-duty environments.", "is_featured": True},
        {"name": "Double Row Tapered Bearing", "description": "Double row tapered roller bearings for applications requiring both radial and axial support.", "is_featured": False},
        {"name": "Spherical Plain Bearing", "description": "Maintenance-free spherical plain bearings for oscillating movements and static loads.", "is_featured": False},
        {"name": "Graphite Bush Bearing", "description": "Self-lubricating graphite bush bearings ideal for high-temperature and slow-speed applications.", "is_featured": False},
        {"name": "Ball Transfer Unit", "description": "Omnidirectional ball transfer units for material handling and conveyor systems.", "is_featured": False},
        {"name": "Combined Roller Bearing", "description": "Combined radial and axial load capacity roller bearings for complex force applications.", "is_featured": True},
    ],
    "Bearing Housings": [
        {"name": "Pillow Block Bearing Housing", "description": "Cast iron pillow block bearing housings for standard and heavy-duty applications.", "is_featured": True},
        {"name": "SNT Plummer Block", "description": "Timken SNT series plummer block housings for tapered roller bearings with split design.", "is_featured": True},
        {"name": "Timken Split Bearing Housing", "description": "Two-piece split bearing housing for easy installation and maintenance without shaft removal.", "is_featured": False},
        {"name": "Spherical Roller Solid Block", "description": "Solid block housings for spherical roller bearings in heavy industrial environments.", "is_featured": False},
    ],
    "Linear Motion": [
        {"name": "LM Bush Bearing", "description": "Linear motion bush bearings for precise linear guidance with low friction.", "is_featured": True},
        {"name": "Ball Screw Support", "description": "Precision ball screw support units for CNC machines and linear motion systems.", "is_featured": False},
        {"name": "Cross Roller Guide", "description": "High-rigidity cross roller guides for precision linear motion in machine tools.", "is_featured": False},
        {"name": "Precision Lock Nut", "description": "High-precision lock nuts for accurate bearing positioning and retention.", "is_featured": False},
        {"name": "Lead Screw", "description": "Precision lead screws for linear actuation in industrial and automation applications.", "is_featured": False},
    ],
    "Power Transmission": [
        {"name": "Chain & Sprocket Set", "description": "Heavy-duty roller chain and sprocket sets for reliable power transmission.", "is_featured": True},
        {"name": "V-Pulley & Belt", "description": "Classical and narrow V-belt pulley systems for efficient power transmission.", "is_featured": False},
        {"name": "Timing Belt & Pulley", "description": "Synchronous timing belts and pulleys for precise speed ratio power transmission.", "is_featured": False},
        {"name": "Flexible Coupling", "description": "Jaw, disc, and grid couplings for connecting shafts with misalignment compensation.", "is_featured": False},
        {"name": "Heavy Duty Elevator Chain", "description": "High-strength elevator chains for vertical conveying in mining and construction.", "is_featured": False},
        {"name": "Reclaimer Chain", "description": "Specialized reclaimer chains for bulk material handling in mining and ports.", "is_featured": True},
    ],
    "Lubrication & Maintenance": [
        {"name": "Groeneveld-BEKA Auto Lubrication", "description": "Automatic lubrication systems for transport, construction, mining and industrial applications.", "is_featured": True},
        {"name": "Industrial Seals", "description": "Oil and grease seals for bearing protection against contamination and leakage.", "is_featured": False},
        {"name": "Bearing Pullers", "description": "Mechanical and hydraulic bearing pullers for safe and efficient bearing removal.", "is_featured": False},
        {"name": "Induction Bearing Heater", "description": "Electric induction heaters for safe, fast, and damage-free bearing mounting.", "is_featured": True},
        {"name": "Industrial Grease", "description": "High-performance greases for extreme temperature, load, and speed applications.", "is_featured": False},
    ],
}

class Command(BaseCommand):
    help = 'Seed the database with sample data'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding categories...')
        cat_map = {}
        for cat_data in CATEGORIES:
            cat, _ = Category.objects.get_or_create(
                slug=slugify(cat_data['name']),
                defaults={**cat_data, 'slug': slugify(cat_data['name'])}
            )
            cat_map[cat_data['name']] = cat

        self.stdout.write('Seeding products...')
        for cat_name, products in PRODUCTS.items():
            cat = cat_map.get(cat_name)
            if not cat:
                continue
            for p in products:
                base_slug = slugify(p['name'])
                slug = base_slug
                i = 1
                while Product.objects.filter(slug=slug).exclude(name=p['name']).exists():
                    slug = f"{base_slug}-{i}"
                    i += 1
                Product.objects.get_or_create(
                    name=p['name'],
                    defaults={**p, 'category': cat, 'slug': slug}
                )

        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))
