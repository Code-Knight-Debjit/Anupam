from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum

from .models import Branch, BranchStock, OpeningStock, StockPurchase, StockSale, StockTransfer, UserProfile


def visible_branches(profile):
    """Branches a given profile is allowed to see stock for."""
    if profile.role == UserProfile.BRANCH_STAFF:
        return Branch.objects.filter(pk=profile.branch_id)
    return Branch.objects.filter(is_active=True)


def historical_stock_matrix(as_of_date, branch_ids=None):
    """Reconstructs {(product_id, branch_id): quantity} as it stood at the end
    of as_of_date, from ledger entries dated on or before that day — a
    read-only report calculation, distinct from recompute_branch_stock's live
    cache (BranchStock.quantity), which always reflects right now.

    Known limitation: StockTransfer only records a single `received_at`
    timestamp, set once a transfer reaches RECEIVED — a transfer sitting in
    PARTIALLY_RECEIVED doesn't carry a date for each partial increment, so its
    received_quantity only counts here once the transfer is fully RECEIVED
    (undercounting the receiving branch for an in-progress partial receipt as
    of the queried date). Dispatch (leaving the sending branch) is precise —
    dispatched_at is a single, well-defined event."""
    from collections import defaultdict

    totals = defaultdict(int)

    def _add(qs, product_field, branch_field, amount_field, sign):
        qs = qs.exclude(**{f'{product_field}__isnull': True})
        for row in qs.values(product_field, branch_field).annotate(total=Sum(amount_field)):
            totals[(row[product_field], row[branch_field])] += sign * row['total']

    opening_qs = OpeningStock.objects.filter(is_deleted=False, effective_date__lte=as_of_date)
    purchase_qs = StockPurchase.objects.filter(is_deleted=False, purchase_date__lte=as_of_date)
    sale_qs = StockSale.objects.filter(is_deleted=False, sale_date__lte=as_of_date)
    transfer_in_qs = StockTransfer.objects.filter(status=StockTransfer.RECEIVED, received_at__date__lte=as_of_date)
    transfer_out_qs = StockTransfer.objects.filter(
        status__in=[
            StockTransfer.DISPATCHED, StockTransfer.PARTIALLY_RECEIVED,
            StockTransfer.RECEIVED, StockTransfer.ISSUE_REPORTED,
        ],
        dispatched_at__date__lte=as_of_date,
    )

    if branch_ids is not None:
        opening_qs = opening_qs.filter(branch_id__in=branch_ids)
        purchase_qs = purchase_qs.filter(branch_id__in=branch_ids)
        sale_qs = sale_qs.filter(branch_id__in=branch_ids)
        transfer_in_qs = transfer_in_qs.filter(to_branch_id__in=branch_ids)
        transfer_out_qs = transfer_out_qs.filter(from_branch_id__in=branch_ids)

    _add(opening_qs, 'product_id', 'branch_id', 'quantity', 1)
    _add(purchase_qs, 'product_id', 'branch_id', 'quantity', 1)
    _add(sale_qs, 'product_id', 'branch_id', 'quantity', -1)
    _add(transfer_in_qs, 'product_id', 'to_branch_id', 'received_quantity', 1)
    _add(transfer_out_qs, 'product_id', 'from_branch_id', 'quantity', -1)

    return totals


@transaction.atomic
def recompute_branch_stock(product_id, branch_id):
    """Recomputes BranchStock.quantity for (product, branch) from scratch, from
    the ledger + transfer statuses. Idempotent by construction: re-running this
    after any create/edit/soft-delete or transfer status change always yields the
    correct current value, so callers never need to worry about double-applying
    a delta on a retried/duplicated request."""
    opening = OpeningStock.objects.filter(
        product_id=product_id, branch_id=branch_id, is_deleted=False
    ).aggregate(total=Sum('quantity'))['total'] or 0
    purchased = StockPurchase.objects.filter(
        product_id=product_id, branch_id=branch_id, is_deleted=False
    ).aggregate(total=Sum('quantity'))['total'] or 0
    sold = StockSale.objects.filter(
        product_id=product_id, branch_id=branch_id, is_deleted=False
    ).aggregate(total=Sum('quantity'))['total'] or 0
    # received_quantity is 0 for every status except PARTIALLY_RECEIVED/RECEIVED,
    # so summing it (rather than filtering by status) already gives the right total.
    transferred_in = StockTransfer.objects.filter(
        product_id=product_id, to_branch_id=branch_id,
    ).aggregate(total=Sum('received_quantity'))['total'] or 0
    transferred_out = StockTransfer.objects.filter(
        product_id=product_id, from_branch_id=branch_id,
        status__in=[
            StockTransfer.DISPATCHED, StockTransfer.PARTIALLY_RECEIVED,
            StockTransfer.RECEIVED, StockTransfer.ISSUE_REPORTED,
        ],
    ).aggregate(total=Sum('quantity'))['total'] or 0

    quantity = opening + purchased - sold + transferred_in - transferred_out

    row, _ = BranchStock.objects.get_or_create(product_id=product_id, branch_id=branch_id)
    row.quantity = quantity
    row.save(update_fields=['quantity', 'updated_at'])
    return row


def get_available_quantity(product_id, branch_id):
    row = BranchStock.objects.filter(product_id=product_id, branch_id=branch_id).first()
    return row.quantity if row else 0


def latest_unit_price(product_id, branch_id=None):
    """Latest known price_per_unit for a product (optionally scoped to a branch),
    from whichever of OpeningStock/StockPurchase is most recent. Used for the
    'total inventory value' stat (valuation = current qty * latest unit price)."""
    opening_qs = OpeningStock.objects.filter(product_id=product_id, is_deleted=False)
    purchase_qs = StockPurchase.objects.filter(product_id=product_id, is_deleted=False)
    if branch_id:
        opening_qs = opening_qs.filter(branch_id=branch_id)
        purchase_qs = purchase_qs.filter(branch_id=branch_id)

    latest_opening = opening_qs.order_by('-effective_date', '-created_at').first()
    latest_purchase = purchase_qs.order_by('-purchase_date', '-created_at').first()

    candidates = []
    if latest_opening:
        candidates.append((latest_opening.effective_date, latest_opening.created_at, latest_opening.price))
    if latest_purchase:
        candidates.append((latest_purchase.purchase_date, latest_purchase.created_at, latest_purchase.price))
    if not candidates:
        return Decimal('0')
    candidates.sort(key=lambda c: (c[0], c[1]))
    return candidates[-1][2]


def total_inventory_value(branch_ids=None):
    """Sum(quantity * latest unit price) across visible BranchStock rows."""
    qs = BranchStock.objects.select_related('product').filter(quantity__gt=0)
    if branch_ids is not None:
        qs = qs.filter(branch_id__in=branch_ids)
    total = Decimal('0')
    for row in qs:
        price = latest_unit_price(row.product_id, row.branch_id)
        total += price * row.quantity
    return total


def get_low_stock_items(branch_ids=None):
    qs = BranchStock.objects.select_related('product', 'branch').filter(
        low_stock_threshold__gt=0, quantity__lte=F('low_stock_threshold')
    )
    if branch_ids is not None:
        qs = qs.filter(branch_id__in=branch_ids)
    return list(qs)


def profit_summary(branch_ids=None, date_from=None, date_to=None):
    """Gross margin (selling - cost) * qty, summed. Admin-only figure."""
    qs = StockSale.objects.filter(is_deleted=False)
    if branch_ids is not None:
        qs = qs.filter(branch_id__in=branch_ids)
    if date_from:
        qs = qs.filter(sale_date__gte=date_from)
    if date_to:
        qs = qs.filter(sale_date__lte=date_to)
    agg = qs.aggregate(
        profit=Sum('total_profit'),
        revenue=Sum('total_selling_price'),
        cost=Sum('total_price'),
        qty=Sum('quantity'),
    )
    return {
        'profit': agg['profit'] or Decimal('0'),
        'revenue': agg['revenue'] or Decimal('0'),
        'cost': agg['cost'] or Decimal('0'),
        'qty': agg['qty'] or 0,
    }
