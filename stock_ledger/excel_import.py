from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.comments import Comment

from products.models import Category, Product, SubCategory
from .models import Branch, BranchStock, OpeningStock
from .services import recompute_branch_stock

FIXED_HEADERS = ['Name/SKU', 'Category', 'SubCategory', 'Branch', 'Opening Quantity', 'Cost Price', 'Low Stock Threshold', 'Visible']
HEADER_FILL = PatternFill(start_color='0E0E11', end_color='0E0E11', fill_type='solid')
HEADER_FONT = Font(color='FFFFFF', bold=True)

TRUE_VALUES = {'true', '1', 'yes', 'y'}
FALSE_VALUES = {'false', '0', 'no', 'n'}


@dataclass
class ImportResult:
    imported: int = 0
    created_products: int = 0
    created_categories: int = 0
    created_subcategories: int = 0
    skipped: int = 0
    errors: list = field(default_factory=list)      # list of (row_number, reason) — bad data, can't proceed
    duplicates: list = field(default_factory=list)   # list of (row_number, reason) — already added previously


def build_products_template_workbook() -> BytesIO:
    """Template for bulk-uploading Products: one row per (Product, Branch)
    pair. Name/SKU, Category and Branch are required; SubCategory is optional
    (auto-created under the row's Category if it's new, same as Category
    itself); Opening Quantity + Cost Price together create that product's
    opening balance at that branch (skipped if it already has one there —
    reported as a duplicate, not double-counted); Low Stock Threshold and
    Visible apply regardless. Anything after Visible is a Technical
    Specification: the header is the spec name, the cell below is this
    product's value — shown on the public product page. Add as many of these
    columns as needed; re-uploading an existing product with new spec columns
    fills them in (existing keys are kept, new values win)."""
    wb = Workbook()

    ws = wb.active
    ws.title = 'Products'
    spec_example_headers = ['Bore Diameter', 'Outer Diameter']
    ws.append(FIXED_HEADERS + spec_example_headers)
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal='center')
    ws['A1'].comment = Comment('Product identity — type the part code and brand together as free text, e.g. "6205-2RS Timken". If this exact name isn\'t in the catalogue yet, it will be created automatically.', 'Anupam Bearings')
    ws['B1'].comment = Comment('Product category, e.g. Bearings. Created automatically if it doesn\'t exist yet.', 'Anupam Bearings')
    ws['C1'].comment = Comment('Optional. Created automatically under the Category above if it\'s new.', 'Anupam Bearings')
    ws['D1'].comment = Comment('Must exactly match an existing Branch name or code (case-insensitive) — see the Reference sheet.', 'Anupam Bearings')
    ws['E1'].comment = Comment('Opening balance at this branch, whole number of units (Pcs). Leave blank to skip creating an opening balance for this row.', 'Anupam Bearings')
    ws['F1'].comment = Comment('Price per unit for the opening balance. Required if Opening Quantity is given.', 'Anupam Bearings')
    ws['G1'].comment = Comment('Optional. Low-stock alert threshold at this branch.', 'Anupam Bearings')
    ws['H1'].comment = Comment('Optional, defaults to TRUE. Set to FALSE to hide this product from the public site.', 'Anupam Bearings')
    ws['I1'].comment = Comment('Anything after Visible is a Technical Specification: the header is the spec name, the cell below is this product\'s value — shown on the public product page. Add as many of these columns as you need.', 'Anupam Bearings')

    ws.append(['6001-ZZ Timken', 'Bearings', 'Ball Bearings', 'Bengaluru', 100, 45.50, 10, 'TRUE', '12mm', '28mm'])
    for cell in ws[2]:
        cell.font = Font(italic=True, color='888888')

    widths = [28, 16, 16, 14, 16, 12, 18, 10, 16, 16]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
    ws.freeze_panes = 'A2'

    ref = wb.create_sheet('Reference')
    ref.append(['Valid Branch Names', 'Branch Code', 'Existing Category Names', 'Existing SubCategory Names'])
    for cell in ref[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    branches = list(Branch.objects.filter(is_active=True).order_by('name').values_list('name', 'code'))
    category_names = list(Category.objects.order_by('name').values_list('name', flat=True))
    subcategory_names = list(SubCategory.objects.order_by('name').values_list('name', flat=True))
    for i in range(max(len(branches), len(category_names), len(subcategory_names))):
        row = [
            branches[i][0] if i < len(branches) else '',
            branches[i][1] if i < len(branches) else '',
            category_names[i] if i < len(category_names) else '',
            subcategory_names[i] if i < len(subcategory_names) else '',
        ]
        ref.append(row)
    for i, width in enumerate([18, 14, 22, 22], start=1):
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
        if n < 0:
            raise ValueError
        return n
    except (TypeError, ValueError):
        errors.append((row_number, f'Invalid {field_name}: {value!r}'))
        return None


def _parse_bool(value, default=True):
    if value in (None, ''):
        return default
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return default


def _unique_slug(model, base):
    slug_base = slugify(base) or 'item'
    slug = slug_base
    i = 1
    while model.objects.filter(slug=slug).exists():
        slug = f'{slug_base}-{i}'
        i += 1
    return slug


def _get_or_create_category(name):
    category = Category.objects.filter(name__iexact=name).first()
    if category:
        return category, False
    category = Category.objects.create(name=name, slug=_unique_slug(Category, name))
    return category, True


def _get_or_create_subcategory(name, category):
    subcategory = SubCategory.objects.filter(name__iexact=name, category=category).first()
    if subcategory:
        return subcategory, False
    subcategory = SubCategory.objects.create(name=name, category=category, slug=_unique_slug(SubCategory, name))
    return subcategory, True


def _get_or_create_product(name, category, subcategory, specifications):
    """Technical Specification columns are merged into the product's existing
    specs (new values win, other existing keys are kept) whether the product
    is new or not, so a re-upload can be used to fill in specs for an
    already-catalogued product."""
    product = Product.objects.filter(name__iexact=name).first()
    created = False
    if product is None:
        product = Product.objects.create(
            name=name, slug=_unique_slug(Product, name), category=category, subcategory=subcategory,
        )
        created = True

    if specifications:
        merged = {**(product.specifications or {}), **specifications}
        if merged != (product.specifications or {}):
            product.specifications = merged
            product.save(update_fields=['specifications'])

    return product, created


@transaction.atomic
def import_products_workbook(uploaded_file, user, filename=''):
    """Parses a Products bulk-upload workbook: Name/SKU | Category |
    SubCategory | Branch | Opening Quantity | Cost Price | Low Stock
    Threshold | Visible, one row per (Product, Branch) pair. Category and
    SubCategory are auto-created if new; Branch must already exist (curated
    centrally, never auto-created). A product that already has an opening
    stock entry at that branch has the stock part of the row skipped as a
    duplicate (not double-counted) — Threshold/Visible still apply."""
    wb = load_workbook(uploaded_file, read_only=True, data_only=True)
    ws = wb.active

    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
    spec_names = [str(h).strip() for h in header_row[len(FIXED_HEADERS):] if h not in (None, '')]

    errors = []
    duplicates = []
    valid_rows = []  # (product, branch, quantity, price, threshold, is_new_product)
    created_categories = 0
    created_subcategories = 0
    created_products_total = 0

    rows = list(ws.iter_rows(min_row=2, values_only=True))
    for idx, row in enumerate(rows, start=2):
        if row is None or all(cell in (None, '') for cell in row):
            continue

        def cell(i):
            return row[i] if len(row) > i else None

        name = str(cell(0)).strip() if cell(0) is not None else ''
        category_name = str(cell(1)).strip() if cell(1) is not None else ''
        subcategory_name = str(cell(2)).strip() if cell(2) is not None else ''
        branch_name = str(cell(3)).strip() if cell(3) is not None else ''

        if not name or not category_name or not branch_name:
            errors.append((idx, 'Missing Name/SKU, Category, or Branch.'))
            continue

        branch = Branch.objects.filter(name__iexact=branch_name, is_active=True).first()
        if branch is None:
            branch = Branch.objects.filter(code__iexact=branch_name, is_active=True).first()
        if branch is None:
            errors.append((idx, f'No active branch found matching "{branch_name}".'))
            continue

        quantity = None
        price = None
        if cell(4) not in (None, ''):
            quantity = _parse_int(cell(4), idx, 'Opening Quantity', errors)
            if quantity is not None and quantity > 0:
                if cell(5) in (None, ''):
                    errors.append((idx, 'Cost Price is required when Opening Quantity is given.'))
                    continue
                price = _parse_decimal(cell(5), idx, 'Cost Price', errors)
                if price is None:
                    continue
            else:
                quantity = None

        threshold = None
        if cell(6) not in (None, ''):
            threshold = _parse_int(cell(6), idx, 'Low Stock Threshold', errors)
            if threshold is None:
                continue

        is_visible = _parse_bool(cell(7), default=True)

        specifications = {}
        for spec_index, spec_name in enumerate(spec_names):
            value = cell(len(FIXED_HEADERS) + spec_index)
            if value not in (None, ''):
                specifications[spec_name] = str(value).strip()

        category, category_created = _get_or_create_category(category_name)
        if category_created:
            created_categories += 1

        subcategory = None
        if subcategory_name:
            subcategory, subcategory_created = _get_or_create_subcategory(subcategory_name, category)
            if subcategory_created:
                created_subcategories += 1

        product, is_new_product = _get_or_create_product(name, category, subcategory, specifications)
        if is_new_product:
            created_products_total += 1
        if product.is_visible != is_visible:
            product.is_visible = is_visible
            product.save(update_fields=['is_visible'])

        if quantity and price is not None:
            if OpeningStock.objects.filter(product=product, branch=branch, is_deleted=False).exists():
                duplicates.append((idx, f'"{name}" at {branch.name} already has an opening stock — skipped to avoid double-counting.'))
                if threshold is not None:
                    BranchStock.objects.update_or_create(
                        product=product, branch=branch, defaults={'low_stock_threshold': threshold},
                    )
                continue
            valid_rows.append((product, branch, quantity, price, threshold))
        elif threshold is not None:
            BranchStock.objects.update_or_create(
                product=product, branch=branch, defaults={'low_stock_threshold': threshold},
            )

    result = ImportResult(
        skipped=len(errors) + len(duplicates), errors=errors, duplicates=duplicates,
        created_categories=created_categories, created_subcategories=created_subcategories,
        created_products=created_products_total,
    )

    affected_pairs = set()
    for product, branch, quantity, price, threshold in valid_rows:
        OpeningStock.objects.create(
            product=product, branch=branch, quantity=quantity, price=price,
            effective_date=timezone.localdate(), created_by=user,
        )
        affected_pairs.add((product.id, branch.id))
        result.imported += 1

    for product_id, branch_id in affected_pairs:
        recompute_branch_stock(product_id, branch_id)

    if valid_rows:
        for product, branch, quantity, price, threshold in valid_rows:
            if threshold is not None:
                BranchStock.objects.filter(product=product, branch=branch).update(low_stock_threshold=threshold)

    return result
