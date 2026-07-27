from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.db import transaction
from django.utils import timezone
from openpyxl import Workbook, load_workbook

from products.models import Product
from .models import Branch, OpeningStock, OpeningStockImportBatch, new_import_batch_id
from .services import recompute_branch_stock

TEMPLATE_HEADERS = ['ID', 'Brand', 'Branch', 'Quantity', 'Price']


class ImportError_(ValueError):
    pass


@dataclass
class ImportResult:
    batch: OpeningStockImportBatch | None
    imported: int = 0
    skipped: int = 0
    errors: list = field(default_factory=list)  # list of (row_number, reason)


def build_template_workbook() -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = 'Opening Stock'
    ws.append(TEMPLATE_HEADERS)
    ws.append(['6001-ZZ', 'TIMKEN', 'Bengaluru', 100, 45.50])
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


@transaction.atomic
def import_opening_stock_workbook(uploaded_file, user, filename=''):
    """Parses an Opening Stock Excel workbook (ID | Brand | Branch | Quantity |
    Price). Matches each row's Product by (sku=ID, brand__name=Brand) and Branch
    by name/code. Never auto-creates a missing Branch/Brand/Product — bad rows are
    skipped and reported, valid rows are committed together in one batch tagged
    with a batch id so they can be found and soft-deleted as a group later."""
    wb = load_workbook(uploaded_file, read_only=True, data_only=True)
    ws = wb.active

    errors = []
    valid_rows = []  # (product, branch, quantity, price)

    rows = list(ws.iter_rows(min_row=2, values_only=True))
    for idx, row in enumerate(rows, start=2):
        if row is None or all(cell in (None, '') for cell in row):
            continue
        raw_id = row[0] if len(row) > 0 else None
        raw_brand = row[1] if len(row) > 1 else None
        raw_branch = row[2] if len(row) > 2 else None
        raw_qty = row[3] if len(row) > 3 else None
        raw_price = row[4] if len(row) > 4 else None

        sku = str(raw_id).strip() if raw_id is not None else ''
        brand_name = str(raw_brand).strip() if raw_brand is not None else ''
        branch_name = str(raw_branch).strip() if raw_branch is not None else ''

        if not sku or not brand_name or not branch_name:
            errors.append((idx, 'Missing ID, Brand, or Branch.'))
            continue

        quantity = _parse_int(raw_qty, idx, 'Quantity', errors)
        price = _parse_decimal(raw_price, idx, 'Price', errors)
        if quantity is None or price is None:
            continue

        product = Product.objects.filter(sku__iexact=sku, brand__name__iexact=brand_name).first()
        if product is None:
            errors.append((idx, f'No product found for ID "{sku}" + Brand "{brand_name}".'))
            continue

        branch = Branch.objects.filter(name__iexact=branch_name, is_active=True).first()
        if branch is None:
            branch = Branch.objects.filter(code__iexact=branch_name, is_active=True).first()
        if branch is None:
            errors.append((idx, f'No active branch found matching "{branch_name}".'))
            continue

        valid_rows.append((product, branch, quantity, price))

    result = ImportResult(batch=None, skipped=len(errors), errors=errors)
    if not valid_rows:
        return result

    batch_id = new_import_batch_id()
    batch = OpeningStockImportBatch.objects.create(
        batch_id=batch_id, uploaded_by=user, filename=filename,
        row_count=len(valid_rows), skipped_count=len(errors),
    )

    affected_pairs = set()
    for product, branch, quantity, price in valid_rows:
        OpeningStock.objects.create(
            product=product, branch=branch, quantity=quantity, price=price,
            effective_date=timezone.localdate(),
            created_by=user, import_batch=batch_id,
        )
        affected_pairs.add((product.id, branch.id))

    for product_id, branch_id in affected_pairs:
        recompute_branch_stock(product_id, branch_id)

    result.batch = batch
    result.imported = len(valid_rows)
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
