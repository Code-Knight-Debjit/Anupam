from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.comments import Comment

from products.models import Brand, Category, Product
from .models import Branch, BranchStock, OpeningStock, OpeningStockImportBatch, new_import_batch_id
from .services import recompute_branch_stock

FIXED_HEADERS = ['ID', 'Brand', 'Category', 'Branch', 'Quantity', 'Price', 'Location']
HEADER_FILL = PatternFill(start_color='0E0E11', end_color='0E0E11', fill_type='solid')
HEADER_FONT = Font(color='FFFFFF', bold=True)


class ImportError_(ValueError):
    pass


@dataclass
class ImportResult:
    batch: OpeningStockImportBatch | None
    imported: int = 0
    created_products: int = 0
    created_categories: int = 0
    skipped: int = 0
    errors: list = field(default_factory=list)      # list of (row_number, reason) — bad data, can't proceed
    duplicates: list = field(default_factory=list)   # list of (row_number, reason) — already added previously


def build_template_workbook() -> BytesIO:
    """One-time-setup template for bulk-uploading Opening Stock. Sheet 1 is the
    fill-in-and-upload sheet: the fixed columns (ID, Brand, Category, Branch,
    Quantity, Price, Location) plus any further columns, which are treated as
    Technical Specifications — each extra header becomes a spec name and the
    cell below it becomes that product's value for it (shown on the public
    product page). Sheet 2 is a live reference of Brand/Category/Branch names
    already in the system — Brand and Branch must already exist; Category is
    created automatically if it's new, same as the Product itself."""
    wb = Workbook()

    ws = wb.active
    ws.title = 'Opening Stock'
    spec_example_headers = ['Bore Diameter', 'Outer Diameter']
    ws.append(FIXED_HEADERS + spec_example_headers)
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal='center')
    ws['A1'].comment = Comment('Product SKU / part code, e.g. 6001-ZZ. If this code + Brand isn\'t in the catalogue yet, it will be created automatically.', 'Anupam Bearings')
    ws['B1'].comment = Comment('Must exactly match an existing Brand name (case-insensitive) — see the Reference sheet. Brands are not auto-created.', 'Anupam Bearings')
    ws['C1'].comment = Comment('Product category, e.g. Bearings. Created automatically if it doesn\'t exist yet — only applied when the product itself is new.', 'Anupam Bearings')
    ws['D1'].comment = Comment('Must exactly match an existing Branch name or code (case-insensitive) — see the Reference sheet.', 'Anupam Bearings')
    ws['E1'].comment = Comment('Whole number of units (Pcs), greater than 0.', 'Anupam Bearings')
    ws['F1'].comment = Comment('Price per unit, e.g. 45.50', 'Anupam Bearings')
    ws['G1'].comment = Comment('Physical rack location at this branch, e.g. C1R2. Optional.', 'Anupam Bearings')
    ws['H1'].comment = Comment('Anything after Location is a Technical Specification: the header is the spec name, the cell below is this product\'s value — shown on the public product page. Add as many of these columns as you need.', 'Anupam Bearings')

    ws.append(['6001-ZZ', 'TIMKEN', 'Bearings', 'Bengaluru', 100, 45.50, 'C1R2', '12mm', '28mm'])
    for cell in ws[2]:
        cell.font = Font(italic=True, color='888888')

    widths = [16, 14, 16, 14, 12, 12, 12, 16, 16]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
    ws.freeze_panes = 'A2'

    ref = wb.create_sheet('Reference')
    ref.append(['Valid Brand Names', 'Valid Branch Names', 'Branch Code', 'Existing Category Names'])
    for cell in ref[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    brand_names = list(Brand.objects.filter(is_active=True).order_by('name').values_list('name', flat=True))
    branches = list(Branch.objects.filter(is_active=True).order_by('name').values_list('name', 'code'))
    category_names = list(Category.objects.order_by('name').values_list('name', flat=True))
    for i in range(max(len(brand_names), len(branches), len(category_names))):
        row = [
            brand_names[i] if i < len(brand_names) else '',
            branches[i][0] if i < len(branches) else '',
            branches[i][1] if i < len(branches) else '',
            category_names[i] if i < len(category_names) else '',
        ]
        ref.append(row)
    for i, width in enumerate([22, 18, 14, 22], start=1):
        ref.column_dimensions[ref.cell(row=1, column=i).column_letter].width = width

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _parse_decimal(value, row_number, field_name, errors):
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError):
        errors.append((row_number, f'Invalid {field_name}: {value!r}'))
        return None


def _parse_int(value, row_number, field_name, errors):
    try:
        n = int(value)
        if n <= 0:
            raise ValueError
        return n
    except (TypeError, ValueError):
        errors.append((row_number, f'Invalid {field_name}: {value!r}'))
        return None


def _unique_slug(model, base):
    slug_base = slugify(base) or 'item'
    slug = slug_base
    i = 1
    while model.objects.filter(slug=slug).exists():
        slug = f'{slug_base}-{i}'
        i += 1
    return slug


def _get_or_create_category(name):
    """A Category name given explicitly in the sheet is auto-created if it
    doesn't exist yet — unlike Brand, which is deliberately curated
    centrally, Category is just a label and the dashboard's own quick-create
    flow already establishes 'create it if it's new' as the norm here."""
    category = Category.objects.filter(name__iexact=name).first()
    if category:
        return category, False
    category = Category.objects.create(name=name, slug=_unique_slug(Category, name))
    return category, True


def _get_or_create_product(sku, brand, category, specifications):
    """Opening Stock is how a product's very first balance enters the system,
    so a (SKU, Brand) that doesn't exist yet is the *expected* case, not an
    error — it's auto-created (name defaults to the code) the same way the
    dashboard's inline product-create combobox does. Technical Specification
    columns are merged into the product's existing specs (new values win,
    other existing keys are kept) whether the product is new or not, so a
    re-upload can be used to fill in specs for an already-catalogued product."""
    product = Product.objects.filter(sku__iexact=sku, brand=brand).first()
    created = False
    if product is None:
        product = Product.objects.create(
            name=sku, slug=_unique_slug(Product, sku), sku=sku, brand=brand, category=category,
        )
        created = True

    if specifications:
        merged = {**(product.specifications or {}), **specifications}
        if merged != (product.specifications or {}):
            product.specifications = merged
            product.save(update_fields=['specifications'])

    return product, created


@transaction.atomic
def import_opening_stock_workbook(uploaded_file, user, filename=''):
    """Parses an Opening Stock Excel workbook: ID | Brand | Category | Branch |
    Quantity | Price | Location, followed by any number of Technical
    Specification columns (header = spec name, cell = spec value for that
    product). Brand and Branch must already exist (skipped + reported if not);
    Category and the Product itself (the SKU+Brand pair) are auto-created if
    new, since that's the expected case for a first-time opening balance.
    Location and specs are applied even when the stock itself turns out to be
    a duplicate, so a re-upload can still be used to fill those in. If the
    product already has an opening stock entry at that branch, the stock part
    of the row is treated as a duplicate re-upload — skipped and reported
    separately from actual errors, rather than silently double-counted."""
    wb = load_workbook(uploaded_file, read_only=True, data_only=True)
    ws = wb.active

    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
    spec_names = [str(h).strip() for h in header_row[len(FIXED_HEADERS):] if h not in (None, '')]

    errors = []
    duplicates = []
    valid_rows = []  # (product, branch, quantity, price, is_new_product)
    created_categories = 0

    rows = list(ws.iter_rows(min_row=2, values_only=True))
    for idx, row in enumerate(rows, start=2):
        if row is None or all(cell in (None, '') for cell in row):
            continue

        def cell(i):
            return row[i] if len(row) > i else None

        sku = str(cell(0)).strip() if cell(0) is not None else ''
        brand_name = str(cell(1)).strip() if cell(1) is not None else ''
        category_name = str(cell(2)).strip() if cell(2) is not None else ''
        branch_name = str(cell(3)).strip() if cell(3) is not None else ''
        location = str(cell(6)).strip() if cell(6) is not None else ''

        if not sku or not brand_name or not category_name or not branch_name:
            errors.append((idx, 'Missing ID, Brand, Category, or Branch.'))
            continue

        quantity = _parse_int(cell(4), idx, 'Quantity', errors)
        price = _parse_decimal(cell(5), idx, 'Price', errors)
        if quantity is None or price is None:
            continue

        brand = Brand.objects.filter(name__iexact=brand_name, is_active=True).first()
        if brand is None:
            errors.append((idx, f'No active brand found matching "{brand_name}". Add it under Brands first.'))
            continue

        branch = Branch.objects.filter(name__iexact=branch_name, is_active=True).first()
        if branch is None:
            branch = Branch.objects.filter(code__iexact=branch_name, is_active=True).first()
        if branch is None:
            errors.append((idx, f'No active branch found matching "{branch_name}".'))
            continue

        category, category_created = _get_or_create_category(category_name)
        if category_created:
            created_categories += 1

        specifications = {}
        for spec_index, spec_name in enumerate(spec_names):
            value = cell(len(FIXED_HEADERS) + spec_index)
            if value not in (None, ''):
                specifications[spec_name] = str(value).strip()

        product, is_new_product = _get_or_create_product(sku, brand, category, specifications)

        if location:
            BranchStock.objects.update_or_create(
                product=product, branch=branch, defaults={'location': location},
            )

        if not is_new_product and OpeningStock.objects.filter(
            product=product, branch=branch, is_deleted=False
        ).exists():
            duplicates.append((idx, f'"{sku}" ({brand.name}) at {branch.name} was already given an opening stock — skipped to avoid double-counting.'))
            continue

        valid_rows.append((product, branch, quantity, price, is_new_product))

    result = ImportResult(
        batch=None, skipped=len(errors) + len(duplicates), errors=errors, duplicates=duplicates,
        created_categories=created_categories,
    )
    if not valid_rows:
        return result

    batch_id = new_import_batch_id()
    batch = OpeningStockImportBatch.objects.create(
        batch_id=batch_id, uploaded_by=user, filename=filename,
        row_count=len(valid_rows), skipped_count=len(errors) + len(duplicates),
    )

    affected_pairs = set()
    created_products = 0
    for product, branch, quantity, price, is_new_product in valid_rows:
        OpeningStock.objects.create(
            product=product, branch=branch, quantity=quantity, price=price,
            effective_date=timezone.localdate(),
            created_by=user, import_batch=batch_id,
        )
        affected_pairs.add((product.id, branch.id))
        if is_new_product:
            created_products += 1

    for product_id, branch_id in affected_pairs:
        recompute_branch_stock(product_id, branch_id)

    result.batch = batch
    result.imported = len(valid_rows)
    result.created_products = created_products
    return result


@transaction.atomic
def delete_import_batch(batch: OpeningStockImportBatch, user):
    rows = OpeningStock.objects.filter(import_batch=batch.batch_id, is_deleted=False)
    affected_pairs = set(rows.values_list('product_id', 'branch_id'))
    for row in rows:
        row.soft_delete(user)
    for product_id, branch_id in affected_pairs:
        recompute_branch_stock(product_id, branch_id)
    batch.is_deleted = True
    batch.deleted_by = user
    batch.deleted_at = timezone.now()
    batch.save(update_fields=['is_deleted', 'deleted_by', 'deleted_at'])
