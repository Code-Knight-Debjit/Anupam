import json
from datetime import date, datetime

from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.text import slugify

from products.models import Category, Product
from .exports import export_branch_stock, export_ledger_history
from .models import (
    Branch, BranchStock, OpeningStock, StockPurchase,
    StockSale, StockTransfer, UserProfile,
)
from .permissions import require_branch_match, role_required
from .services import (
    get_available_quantity, historical_stock_matrix, latest_unit_price,
    profit_summary, recompute_branch_stock, visible_branches,
)

staff_required = user_passes_test(lambda u: u.is_staff, login_url='/dashboard/login/')


def _profile(request):
    return request.user.stock_profile


def _is_admin(profile):
    return profile.role == UserProfile.ADMIN


def _branch_choices(profile):
    if _is_admin(profile):
        return Branch.objects.filter(is_active=True)
    return Branch.objects.filter(pk=profile.branch_id)


def _parse_date(value, default=None):
    if not value:
        return default
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return default


# ── PRODUCT SEARCH / QUICK CREATE (combobox backend) ──────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF)
def product_search(request):
    q = request.GET.get('q', '').strip()
    in_stock_branch = request.GET.get('in_stock_branch', '')

    qs = Product.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)
    if in_stock_branch:
        qs = qs.filter(
            branch_stocks__branch_id=in_stock_branch, branch_stocks__quantity__gt=0
        )
    qs = qs.order_by('name')[:20]

    results = [{'id': p.id, 'name': p.name, 'label': p.name} for p in qs]
    return JsonResponse({'results': results})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF)
def product_quick_create(request):
    name = request.POST.get('name', '').strip()

    if not name:
        return JsonResponse({'success': False, 'message': 'Enter a product name/SKU.'})

    existing = Product.objects.filter(name__iexact=name).first()
    if existing:
        return JsonResponse({'success': True, 'product': {'id': existing.id, 'label': existing.name}})

    category, _ = Category.objects.get_or_create(slug='uncategorized', defaults={'name': 'Uncategorized'})
    slug_base = slugify(name) or 'product'
    slug = slug_base
    i = 1
    while Product.objects.filter(slug=slug).exists():
        slug = f'{slug_base}-{i}'
        i += 1

    product = Product.objects.create(name=name, slug=slug, category=category)
    return JsonResponse({'success': True, 'product': {'id': product.id, 'label': product.name}})


# ── DASHBOARD (everybody) ─────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF, UserProfile.VIEWER)
def stock_dashboard(request):
    """Company-wide, point-in-time stock picture — visible to every role,
    unlike Overview (Admin-only). One row per product, one column per active
    branch showing what that branch's stock was at the end of the selected
    date (reconstructed from ledger history), plus a grand-total column."""
    q = request.GET.get('q', '').strip()
    as_of = _parse_date(request.GET.get('date'), timezone.localdate())

    branches = list(Branch.objects.filter(is_active=True).order_by('name'))
    branch_ids = [b.id for b in branches]
    matrix = historical_stock_matrix(as_of, branch_ids=branch_ids)

    products = Product.objects.order_by('name')
    if q:
        products = products.filter(name__icontains=q)

    rows = []
    for product in products:
        qtys = [matrix.get((product.id, b.id), 0) for b in branches]
        rows.append({'product': product, 'qtys': qtys, 'total': sum(qtys)})

    return render(request, 'dashboard/stock_dashboard.html', {
        'rows': rows,
        'branches': branches,
        'q': q,
        'as_of': as_of,
    })


# ── OVERVIEW (Admin only) ─────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def overview(request):
    profile = _profile(request)
    branch_filter = request.GET.get('branch', '')
    product_filter = request.GET.get('product', '')
    q = request.GET.get('q', '').strip()
    show_zero = request.GET.get('show_zero') == '1'

    rows_qs = BranchStock.objects.select_related('product', 'branch')
    rows_qs = rows_qs.filter(branch_id__in=visible_branches(profile).values_list('id', flat=True))

    if profile.role == UserProfile.BRANCH_STAFF:
        branch_filter = str(profile.branch_id)

    if branch_filter:
        rows_qs = rows_qs.filter(branch_id=branch_filter)
    if product_filter:
        rows_qs = rows_qs.filter(product_id=product_filter)
    if q:
        rows_qs = rows_qs.filter(product__name__icontains=q)
    if not show_zero:
        rows_qs = rows_qs.exclude(quantity=0)

    include_money = _is_admin(profile)
    grouped = profile.role == UserProfile.VIEWER and not branch_filter

    display_rows = []
    if grouped:
        totals = {}
        for row in rows_qs:
            key = row.product_id
            if key not in totals:
                totals[key] = {'product': row.product, 'quantity': 0}
            totals[key]['quantity'] += row.quantity
        display_rows = sorted(totals.values(), key=lambda r: r['product'].name)
    else:
        for row in rows_qs.order_by('product__name', 'branch__name'):
            if include_money:
                row.unit_price = latest_unit_price(row.product_id, row.branch_id)
                row.value = row.unit_price * row.quantity
            display_rows.append(row)

    stats = {
        'total_quantity': sum(r.quantity for r in rows_qs),
        'low_stock_count': rows_qs.filter(low_stock_threshold__gt=0, quantity__lte=F('low_stock_threshold')).count(),
    }

    profit_data = None
    if include_money:
        date_from = _parse_date(request.GET.get('date_from'))
        date_to = _parse_date(request.GET.get('date_to'))
        if not date_from and not date_to:
            today = timezone.localdate()
            date_from = today.replace(day=1)
            date_to = today
        branch_ids_for_profit = [int(branch_filter)] if branch_filter else None
        profit_data = profit_summary(branch_ids=branch_ids_for_profit, date_from=date_from, date_to=date_to)
        profit_data['date_from'] = date_from
        profit_data['date_to'] = date_to
        stats['total_inventory_value'] = sum(
            latest_unit_price(r.product_id, r.branch_id) * r.quantity for r in rows_qs
        )

    return render(request, 'dashboard/stock_overview.html', {
        'rows': display_rows,
        'grouped': grouped,
        'include_money': include_money,
        'stats': stats,
        'profit_data': profit_data,
        'branches': _branch_choices(profile),
        'branch_filter': branch_filter,
        'product_filter': product_filter,
        'q': q,
        'show_zero': show_zero,
        'is_admin': _is_admin(profile),
        'is_branch_staff': profile.role == UserProfile.BRANCH_STAFF,
    })


# ── PURCHASES ─────────────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF, UserProfile.VIEWER)
def purchase_list(request):
    profile = _profile(request)
    qs = StockPurchase.objects.select_related('product', 'branch', 'created_by', 'updated_by').filter(is_deleted=False)
    qs = qs.filter(branch_id__in=visible_branches(profile).values_list('id', flat=True))
    branch_filter = request.GET.get('branch', '')
    q = request.GET.get('q', '').strip()
    if profile.role == UserProfile.BRANCH_STAFF:
        branch_filter = str(profile.branch_id)
    if branch_filter:
        qs = qs.filter(branch_id=branch_filter)
    if q:
        qs = qs.filter(Q(product__name__icontains=q) | Q(product_name_snapshot__icontains=q))
    qs = qs.order_by('-purchase_date', '-created_at')

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/stock_purchase_list.html', {
        'entries': page_obj.object_list,
        'page_obj': page_obj,
        'branches': _branch_choices(profile),
        'branch_filter': branch_filter,
        'q': q,
        'include_money': _is_admin(profile),
        'can_mutate': profile.role in (UserProfile.ADMIN, UserProfile.BRANCH_STAFF),
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF)
def purchase_add(request):
    """A single purchase (one supplier, one date, one notes field — e.g. one
    Blinkit order) can cover several different products at once, so this takes
    parallel item_product[]/item_quantity[]/item_price[] arrays and creates one
    StockPurchase row per line item, all sharing the same branch/date/supplier/
    notes, atomically."""
    profile = _profile(request)
    if request.method == 'POST':
        branch_id = int(request.POST.get('branch')) if _is_admin(profile) else profile.branch_id
        require_branch_match(profile, branch_id)

        purchase_date = _parse_date(request.POST.get('purchase_date'), timezone.localdate())
        supplier = request.POST.get('supplier', '').strip()
        notes = request.POST.get('notes', '').strip()

        item_products = request.POST.getlist('item_product')
        item_quantities = request.POST.getlist('item_quantity')
        item_prices = request.POST.getlist('item_price')

        items = []
        item_error = None
        for product_id, quantity_raw, price_raw in zip(item_products, item_quantities, item_prices):
            if not product_id or not quantity_raw or not price_raw:
                continue
            try:
                quantity = int(quantity_raw)
                if quantity <= 0:
                    raise ValueError
            except ValueError:
                item_error = f'Invalid quantity "{quantity_raw}".'
                break
            items.append((product_id, quantity, price_raw))

        if not items and not item_error:
            item_error = 'Add at least one item.'

        if item_error:
            return render(request, 'dashboard/stock_purchase_form.html', {
                'entry': None,
                'branches': _branch_choices(profile),
                'is_admin': _is_admin(profile),
                'stock_error': item_error,
                'posted': {
                    'purchase_date': request.POST.get('purchase_date', ''),
                    'supplier': supplier,
                    'notes': notes,
                },
            })

        with transaction.atomic():
            created_entries = [
                StockPurchase.objects.create(
                    product_id=product_id, branch_id=branch_id, quantity=quantity, price=price_raw,
                    purchase_date=purchase_date, supplier=supplier, notes=notes, created_by=request.user,
                )
                for product_id, quantity, price_raw in items
            ]
            affected_pairs = {(e.product_id, e.branch_id) for e in created_entries}
            for product_id, branch_id in affected_pairs:
                recompute_branch_stock(product_id, branch_id)

        return redirect('dashboard:stock_ledger:purchase_list')
    return render(request, 'dashboard/stock_purchase_form.html', {
        'entry': None,
        'branches': _branch_choices(profile),
        'is_admin': _is_admin(profile),
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF)
def purchase_edit(request, pk):
    profile = _profile(request)
    entry = get_object_or_404(StockPurchase, pk=pk, is_deleted=False)
    require_branch_match(profile, entry.branch_id)
    if request.method == 'POST':
        entry.quantity = int(request.POST.get('quantity', entry.quantity) or entry.quantity)
        entry.price = request.POST.get('price', entry.price)
        entry.purchase_date = _parse_date(request.POST.get('purchase_date'), entry.purchase_date)
        entry.supplier = request.POST.get('supplier', entry.supplier).strip()
        entry.notes = request.POST.get('notes', entry.notes).strip()
        entry.updated_by = request.user
        entry.save()
        recompute_branch_stock(entry.product_id, entry.branch_id)
        return redirect('dashboard:stock_ledger:purchase_list')
    return render(request, 'dashboard/stock_purchase_form.html', {
        'entry': entry,
        'branches': _branch_choices(profile),
        'is_admin': _is_admin(profile),
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF)
def purchase_delete(request, pk):
    profile = _profile(request)
    entry = get_object_or_404(StockPurchase, pk=pk, is_deleted=False)
    require_branch_match(profile, entry.branch_id)
    entry.soft_delete(request.user)
    recompute_branch_stock(entry.product_id, entry.branch_id)
    return JsonResponse({'success': True})


# ── SALES ─────────────────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF, UserProfile.VIEWER)
def sale_list(request):
    profile = _profile(request)
    qs = StockSale.objects.select_related('product', 'branch', 'created_by', 'updated_by').filter(is_deleted=False)
    qs = qs.filter(branch_id__in=visible_branches(profile).values_list('id', flat=True))
    branch_filter = request.GET.get('branch', '')
    q = request.GET.get('q', '').strip()
    if profile.role == UserProfile.BRANCH_STAFF:
        branch_filter = str(profile.branch_id)
    if branch_filter:
        qs = qs.filter(branch_id=branch_filter)
    if q:
        qs = qs.filter(Q(product__name__icontains=q) | Q(product_name_snapshot__icontains=q))
    qs = qs.order_by('-sale_date', '-created_at')

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/stock_sale_list.html', {
        'entries': page_obj.object_list,
        'page_obj': page_obj,
        'branches': _branch_choices(profile),
        'branch_filter': branch_filter,
        'q': q,
        'include_money': _is_admin(profile),
        'can_mutate': profile.role in (UserProfile.ADMIN, UserProfile.BRANCH_STAFF),
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF)
def sale_add(request):
    """One sale (one branch, one date, one customer/notes — e.g. one invoice)
    can cover several different products at once, mirroring purchase_add.
    Unlike purchases, each item is validated against currently-available stock
    — and since two rows in the same submission could both target the same
    product, the running total sold per product within this one request is
    tracked so the sum can't oversell even though each row looks fine alone.
    Cost price is never taken from the form — it's pulled from
    latest_unit_price() at save time, since the system already knows it."""
    profile = _profile(request)
    if request.method == 'POST':
        branch_id = int(request.POST.get('branch')) if _is_admin(profile) else profile.branch_id
        require_branch_match(profile, branch_id)

        sale_date = _parse_date(request.POST.get('sale_date'), timezone.localdate())
        customer = request.POST.get('customer', '').strip()
        notes = request.POST.get('notes', '').strip()

        item_products = request.POST.getlist('item_product')
        item_quantities = request.POST.getlist('item_quantity')
        item_selling_prices = request.POST.getlist('item_selling_price')

        items = []
        item_error = None
        remaining_by_product = {}
        for product_id, quantity_raw, selling_price_raw in zip(
            item_products, item_quantities, item_selling_prices
        ):
            if not product_id or not quantity_raw or not selling_price_raw:
                continue
            try:
                quantity = int(quantity_raw)
                if quantity <= 0:
                    raise ValueError
            except ValueError:
                item_error = f'Invalid quantity "{quantity_raw}".'
                break

            if product_id not in remaining_by_product:
                remaining_by_product[product_id] = get_available_quantity(product_id, branch_id)
            remaining_by_product[product_id] -= quantity
            if remaining_by_product[product_id] < 0:
                name = Product.objects.filter(pk=product_id).values_list('name', flat=True).first()
                item_error = f'Not enough stock for "{name}" to sell {quantity} of it here.'
                break

            items.append((product_id, quantity, selling_price_raw))

        if not items and not item_error:
            item_error = 'Add at least one item.'

        if item_error:
            return render(request, 'dashboard/stock_sale_form.html', {
                'entry': None,
                'branches': _branch_choices(profile),
                'is_admin': _is_admin(profile),
                'stock_error': item_error,
                'posted': {
                    'sale_date': request.POST.get('sale_date', ''),
                    'customer': customer,
                    'notes': notes,
                },
            })

        with transaction.atomic():
            created_entries = [
                StockSale.objects.create(
                    product_id=product_id, branch_id=branch_id, quantity=quantity,
                    price=latest_unit_price(product_id, branch_id), selling_price=selling_price_raw,
                    sale_date=sale_date, customer=customer, notes=notes, created_by=request.user,
                )
                for product_id, quantity, selling_price_raw in items
            ]
            affected_pairs = {(e.product_id, e.branch_id) for e in created_entries}
            for aff_product_id, aff_branch_id in affected_pairs:
                recompute_branch_stock(aff_product_id, aff_branch_id)

        return redirect('dashboard:stock_ledger:sale_list')
    return render(request, 'dashboard/stock_sale_form.html', {
        'entry': None,
        'branches': _branch_choices(profile),
        'is_admin': _is_admin(profile),
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF)
def sale_edit(request, pk):
    profile = _profile(request)
    entry = get_object_or_404(StockSale, pk=pk, is_deleted=False)
    require_branch_match(profile, entry.branch_id)
    if request.method == 'POST':
        new_quantity = int(request.POST.get('quantity', entry.quantity) or entry.quantity)
        available = get_available_quantity(entry.product_id, entry.branch_id) + entry.quantity
        if new_quantity <= 0 or new_quantity > available:
            return render(request, 'dashboard/stock_sale_form.html', {
                'entry': entry,
                'branches': _branch_choices(profile),
                'is_admin': _is_admin(profile),
                'stock_error': f'Only {available} available for this product/branch — cannot set quantity to {new_quantity}.',
            })

        entry.quantity = new_quantity
        entry.selling_price = request.POST.get('selling_price', entry.selling_price)
        entry.sale_date = _parse_date(request.POST.get('sale_date'), entry.sale_date)
        entry.customer = request.POST.get('customer', entry.customer).strip()
        entry.notes = request.POST.get('notes', entry.notes).strip()
        entry.updated_by = request.user
        entry.save()
        recompute_branch_stock(entry.product_id, entry.branch_id)
        return redirect('dashboard:stock_ledger:sale_list')
    return render(request, 'dashboard/stock_sale_form.html', {
        'entry': entry,
        'branches': _branch_choices(profile),
        'is_admin': _is_admin(profile),
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF)
def sale_delete(request, pk):
    profile = _profile(request)
    entry = get_object_or_404(StockSale, pk=pk, is_deleted=False)
    require_branch_match(profile, entry.branch_id)
    entry.soft_delete(request.user)
    recompute_branch_stock(entry.product_id, entry.branch_id)
    return JsonResponse({'success': True})


# ── TRANSFERS ─────────────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF)
def transfer_list(request):
    profile = _profile(request)
    if _is_admin(profile):
        qs = StockTransfer.objects.select_related('product', 'from_branch', 'to_branch').all()
    else:
        qs = StockTransfer.objects.select_related('product', 'from_branch', 'to_branch').filter(
            Q(from_branch_id=profile.branch_id) | Q(to_branch_id=profile.branch_id)
        )
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(product__name__icontains=q) | Q(product_name_snapshot__icontains=q))
    return render(request, 'dashboard/stock_transfers.html', {
        'transfers': qs,
        'q': q,
        'is_admin': _is_admin(profile),
        'my_branch_id': profile.branch_id,
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def transfer_create(request):
    if request.method == 'POST':
        product_id = request.POST.get('product')
        from_branch_id = request.POST.get('from_branch')
        quantity = int(request.POST.get('quantity', 0) or 0)

        available = get_available_quantity(product_id, from_branch_id)
        if quantity <= 0 or quantity > available:
            return render(request, 'dashboard/stock_transfer_form.html', {
                'branches': Branch.objects.filter(is_active=True),
                'stock_error': f'Only {available} in stock at the sending branch — cannot transfer {quantity}.',
            })

        StockTransfer.objects.create(
            product_id=product_id,
            from_branch_id=from_branch_id,
            to_branch_id=request.POST.get('to_branch'),
            quantity=quantity,
            notes=request.POST.get('notes', '').strip(),
            created_by=request.user,
        )
        return redirect('dashboard:stock_ledger:transfer_list')
    return render(request, 'dashboard/stock_transfer_form.html', {
        'branches': Branch.objects.filter(is_active=True),
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def transfer_cancel(request, pk):
    transfer = get_object_or_404(StockTransfer, pk=pk)
    updated = StockTransfer.objects.filter(pk=pk, status=StockTransfer.PENDING).update(
        status=StockTransfer.CANCELLED, cancelled_by=request.user, cancelled_at=timezone.now(),
    )
    if not updated:
        return JsonResponse({'success': False, 'message': 'Transfer is no longer pending.'})
    return JsonResponse({'success': True})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF)
def transfer_dispatch(request, pk):
    profile = _profile(request)
    transfer = get_object_or_404(StockTransfer, pk=pk)
    require_branch_match(profile, transfer.from_branch_id)

    updated = StockTransfer.objects.filter(pk=pk, status=StockTransfer.PENDING).update(
        status=StockTransfer.DISPATCHED, dispatched_by=request.user, dispatched_at=timezone.now(),
    )
    if not updated:
        return JsonResponse({'success': False, 'message': 'Transfer already dispatched or no longer pending.'})
    recompute_branch_stock(transfer.product_id, transfer.from_branch_id)
    return JsonResponse({'success': True})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF)
def transfer_record_receipt(request, pk):
    """Records some or all of the remaining quantity as received. Reaching the
    full dispatched quantity (possibly across several partial calls) closes the
    transfer as RECEIVED; anything short of that leaves it PARTIALLY_RECEIVED so
    the rest can be recorded later. select_for_update serializes concurrent
    submissions (matters once Postgres is in play in prod; sqlite already
    serializes writes at the file level)."""
    profile = _profile(request)
    try:
        quantity = int(json.loads(request.body or '{}').get('quantity', 0))
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'message': 'Invalid quantity.'})

    with transaction.atomic():
        transfer = get_object_or_404(StockTransfer.objects.select_for_update(), pk=pk)
        require_branch_match(profile, transfer.to_branch_id)

        if transfer.status not in (StockTransfer.DISPATCHED, StockTransfer.PARTIALLY_RECEIVED):
            return JsonResponse({'success': False, 'message': 'Transfer is not awaiting receipt.'})

        remaining = transfer.remaining_quantity
        if quantity <= 0 or quantity > remaining:
            return JsonResponse({'success': False, 'message': f'Enter a quantity between 1 and {remaining}.'})

        transfer.received_quantity += quantity
        if transfer.received_quantity >= transfer.quantity:
            transfer.status = StockTransfer.RECEIVED
            transfer.received_by = request.user
            transfer.received_at = timezone.now()
        else:
            transfer.status = StockTransfer.PARTIALLY_RECEIVED
        transfer.save()

    recompute_branch_stock(transfer.product_id, transfer.to_branch_id)
    return JsonResponse({
        'success': True, 'status': transfer.status,
        'received_quantity': transfer.received_quantity, 'remaining_quantity': transfer.remaining_quantity,
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF)
def transfer_report_not_received(request, pk):
    profile = _profile(request)
    transfer = get_object_or_404(StockTransfer, pk=pk)
    require_branch_match(profile, transfer.to_branch_id)

    updated = StockTransfer.objects.filter(
        pk=pk, status__in=[StockTransfer.DISPATCHED, StockTransfer.PARTIALLY_RECEIVED]
    ).update(
        status=StockTransfer.ISSUE_REPORTED, issue_reported_by=request.user, issue_reported_at=timezone.now(),
    )
    if not updated:
        return JsonResponse({'success': False, 'message': 'Transfer is not awaiting receipt.'})
    return JsonResponse({'success': True})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def transfer_resolve_issue(request, pk):
    with transaction.atomic():
        transfer = get_object_or_404(StockTransfer.objects.select_for_update(), pk=pk)
        if transfer.status != StockTransfer.ISSUE_REPORTED:
            return JsonResponse({'success': False, 'message': 'Transfer has no open issue.'})
        transfer.status = StockTransfer.PARTIALLY_RECEIVED if transfer.received_quantity > 0 else StockTransfer.DISPATCHED
        transfer.issue_resolved_by = request.user
        transfer.issue_resolved_at = timezone.now()
        transfer.save()
    return JsonResponse({'success': True, 'status': transfer.status})


# ── BRANCHES (Admin only) ─────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def branch_list(request):
    branches = Branch.objects.all().order_by('name')
    return render(request, 'dashboard/stock_branches.html', {'branches': branches})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def branch_add(request):
    if request.method == 'POST':
        from django.utils.text import slugify
        name = request.POST.get('name', '').strip()
        slug = slugify(name)
        base = slug; i = 1
        while Branch.objects.filter(slug=slug).exists():
            slug = f'{base}-{i}'; i += 1
        Branch.objects.create(
            name=name, slug=slug,
            code=request.POST.get('code', '').strip().upper(),
            address=request.POST.get('address', '').strip(),
            is_active=request.POST.get('is_active') == 'on',
        )
        return redirect('dashboard:stock_ledger:branches')
    return render(request, 'dashboard/stock_branch_form.html', {'branch': None})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def branch_edit(request, pk):
    branch = get_object_or_404(Branch, pk=pk)
    if request.method == 'POST':
        branch.name = request.POST.get('name', branch.name).strip()
        branch.code = request.POST.get('code', branch.code).strip().upper()
        branch.address = request.POST.get('address', branch.address).strip()
        branch.is_active = request.POST.get('is_active') == 'on'
        branch.save()
        return redirect('dashboard:stock_ledger:branches')
    return render(request, 'dashboard/stock_branch_form.html', {'branch': branch})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def branch_deactivate(request, pk):
    branch = get_object_or_404(Branch, pk=pk)
    branch.is_active = not branch.is_active
    branch.save(update_fields=['is_active'])
    return JsonResponse({'success': True, 'is_active': branch.is_active})


# ── USERS (Admin only) ────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def user_list(request):
    profiles = UserProfile.objects.select_related('user', 'branch').order_by('user__username')
    return render(request, 'dashboard/stock_users.html', {'profiles': profiles})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def user_add(request):
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        role = request.POST.get('role')
        branch_id = request.POST.get('branch') or None

        if not username or not password:
            error = 'Username and password are required.'
        elif User.objects.filter(username=username).exists():
            error = 'That username is already taken.'
        elif role == UserProfile.BRANCH_STAFF and not branch_id:
            error = 'Branch is required for Branch Staff.'

        if not error:
            user = User.objects.create_user(
                username=username, password=password,
                email=request.POST.get('email', '').strip(),
                first_name=request.POST.get('first_name', '').strip(),
                is_staff=True,
            )
            UserProfile.objects.filter(user=user).delete()  # remove signal-created default
            UserProfile.objects.create(
                user=user, role=role,
                branch_id=branch_id if role == UserProfile.BRANCH_STAFF else None,
            )
            return redirect('dashboard:stock_ledger:users')

    return render(request, 'dashboard/stock_user_form.html', {
        'profile_obj': None,
        'branches': Branch.objects.filter(is_active=True),
        'error': error,
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def user_edit(request, pk):
    profile_obj = get_object_or_404(UserProfile, pk=pk)
    error = None
    if request.method == 'POST':
        role = request.POST.get('role')
        branch_id = request.POST.get('branch') or None
        if role == UserProfile.BRANCH_STAFF and not branch_id:
            error = 'Branch is required for Branch Staff.'
        else:
            profile_obj.role = role
            profile_obj.branch_id = branch_id if role == UserProfile.BRANCH_STAFF else None
            profile_obj.save()
            profile_obj.user.first_name = request.POST.get('first_name', profile_obj.user.first_name).strip()
            profile_obj.user.email = request.POST.get('email', profile_obj.user.email).strip()
            profile_obj.user.save()
            return redirect('dashboard:stock_ledger:users')
    return render(request, 'dashboard/stock_user_form.html', {
        'profile_obj': profile_obj,
        'branches': Branch.objects.filter(is_active=True),
        'error': error,
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def user_toggle_active(request, pk):
    profile_obj = get_object_or_404(UserProfile, pk=pk)
    profile_obj.user.is_active = not profile_obj.user.is_active
    profile_obj.user.save(update_fields=['is_active'])
    return JsonResponse({'success': True, 'is_active': profile_obj.user.is_active})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def user_reset_password(request, pk):
    profile_obj = get_object_or_404(UserProfile, pk=pk)
    new_password = json.loads(request.body or '{}').get('password', '') if request.body else request.POST.get('password', '')
    if not new_password or len(new_password) < 8:
        return JsonResponse({'success': False, 'message': 'Password must be at least 8 characters.'})
    profile_obj.user.set_password(new_password)
    profile_obj.user.save(update_fields=['password'])
    return JsonResponse({'success': True})


# ── THRESHOLD (Admin only, inline AJAX) ───────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def branch_stock_set_threshold(request, pk):
    row = get_object_or_404(BranchStock, pk=pk)
    try:
        threshold = int(json.loads(request.body).get('threshold', 0))
    except (ValueError, json.JSONDecodeError):
        return HttpResponseBadRequest('Invalid threshold')
    row.low_stock_threshold = max(0, threshold)
    row.save(update_fields=['low_stock_threshold'])
    return JsonResponse({'success': True, 'threshold': row.low_stock_threshold})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def branch_stock_delete(request, pk):
    row = get_object_or_404(BranchStock, pk=pk)
    if row.quantity != 0:
        return JsonResponse({'success': False, 'message': 'Only zero-quantity rows can be removed.'})
    row.delete()
    return JsonResponse({'success': True})


# ── EXPORTS ───────────────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF, UserProfile.VIEWER)
def export_stock(request, fmt):
    profile = _profile(request)
    rows = BranchStock.objects.select_related('product', 'branch').filter(
        branch_id__in=visible_branches(profile).values_list('id', flat=True)
    )
    branch_filter = request.GET.get('branch', '')
    if profile.role == UserProfile.BRANCH_STAFF:
        branch_filter = str(profile.branch_id)
    if branch_filter:
        rows = rows.filter(branch_id=branch_filter)

    include_money = _is_admin(profile)
    rows = list(rows.order_by('product__name', 'branch__name'))
    if include_money:
        for r in rows:
            r.unit_price = latest_unit_price(r.product_id, r.branch_id)
            r.value = r.unit_price * r.quantity
    return export_branch_stock(rows, include_money, fmt)


DATE_FIELD_BY_KIND = {'opening': 'effective_date', 'purchase': 'purchase_date', 'sale': 'sale_date'}


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF, UserProfile.VIEWER)
def export_history(request, kind, fmt):
    profile = _profile(request)
    model = {'opening': OpeningStock, 'purchase': StockPurchase, 'sale': StockSale}.get(kind)
    if model is None:
        return HttpResponseBadRequest('Unknown history kind')

    qs = model.objects.select_related('product', 'branch').filter(is_deleted=False)
    qs = qs.filter(branch_id__in=visible_branches(profile).values_list('id', flat=True))
    branch_filter = request.GET.get('branch', '')
    if profile.role == UserProfile.BRANCH_STAFF:
        branch_filter = str(profile.branch_id)
    if branch_filter:
        qs = qs.filter(branch_id=branch_filter)

    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))
    date_field = DATE_FIELD_BY_KIND[kind]
    if date_from:
        qs = qs.filter(**{f'{date_field}__gte': date_from})
    if date_to:
        qs = qs.filter(**{f'{date_field}__lte': date_to})

    include_money = _is_admin(profile)
    return export_ledger_history(kind, list(qs), include_money, fmt)


# ── HISTORY (Purchases + Sales, date-ranged) ──────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN, UserProfile.BRANCH_STAFF, UserProfile.VIEWER)
def history(request):
    profile = _profile(request)
    branch_filter = request.GET.get('branch', '')
    q = request.GET.get('q', '').strip()
    if profile.role == UserProfile.BRANCH_STAFF:
        branch_filter = str(profile.branch_id)

    today = timezone.localdate()
    date_from = _parse_date(request.GET.get('date_from'), today.replace(day=1))
    date_to = _parse_date(request.GET.get('date_to'), today)

    branch_ids = visible_branches(profile).values_list('id', flat=True)

    purchases = StockPurchase.objects.select_related('product', 'branch').filter(
        is_deleted=False, branch_id__in=branch_ids, purchase_date__gte=date_from, purchase_date__lte=date_to,
    )
    sales = StockSale.objects.select_related('product', 'branch').filter(
        is_deleted=False, branch_id__in=branch_ids, sale_date__gte=date_from, sale_date__lte=date_to,
    )
    if branch_filter:
        purchases = purchases.filter(branch_id=branch_filter)
        sales = sales.filter(branch_id=branch_filter)
    if q:
        purchases = purchases.filter(Q(product__name__icontains=q) | Q(product_name_snapshot__icontains=q))
        sales = sales.filter(Q(product__name__icontains=q) | Q(product_name_snapshot__icontains=q))

    return render(request, 'dashboard/stock_history.html', {
        'purchases': purchases.order_by('-purchase_date', '-created_at'),
        'sales': sales.order_by('-sale_date', '-created_at'),
        'branches': _branch_choices(profile),
        'branch_filter': branch_filter,
        'q': q,
        'date_from': date_from,
        'date_to': date_to,
        'include_money': _is_admin(profile),
    })
