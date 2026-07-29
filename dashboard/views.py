from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.db import transaction
from django.db.models import Count, Q, Max
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta
import json

from products.excel_table import ExcelTableError, clear_excel_table_file, parse_excel_table_file, store_excel_table_file
from products.models import Category, Product, ProductImage, SubCategory, Enquiry
from contact.models import ContactMessage, ChatMessage
from core.models import GalleryImage, IndustryCard
from stock_ledger.excel_import import build_products_template_workbook, import_products_workbook
from stock_ledger.models import Branch, BranchStock, OpeningStock, StockTransfer, UserProfile
from stock_ledger.permissions import role_required
from stock_ledger.services import recompute_branch_stock

staff_required = user_passes_test(lambda u: u.is_staff, login_url='/dashboard/login/')


def _post_login_redirect(user, next_url=None):
    profile = getattr(user, 'stock_profile', None)
    if profile and profile.role != UserProfile.ADMIN:
        return redirect('dashboard:stock_ledger:overview')
    return redirect(next_url or '/dashboard/')


def dashboard_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return _post_login_redirect(request.user)
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user and user.is_staff:
            login(request, user)
            return _post_login_redirect(user, request.GET.get('next'))
        error = 'Invalid credentials or insufficient permissions.'
    return render(request, 'dashboard/login.html', {'error': error})


def dashboard_logout(request):
    logout(request)
    return redirect('dashboard:login')


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def dashboard_home(request):
    now = timezone.now()
    week_ago = now - timedelta(days=7)

    from django.db.models import Sum
    from stock_ledger.models import BranchStock
    from stock_ledger.services import total_inventory_value

    stats = {
        'total_products':    Product.objects.count(),
        'total_categories':  Category.objects.count(),
        'total_industries':  IndustryCard.objects.filter(is_active=True).count(),
        'total_gallery':     GalleryImage.objects.filter(is_active=True).count(),
        'new_enquiries':     Enquiry.objects.filter(status='new').count(),
        'total_enquiries':   Enquiry.objects.count(),
        'unread_messages':   ContactMessage.objects.filter(is_read=False).count(),
        'total_messages':    ContactMessage.objects.count(),
        'total_chats':       ChatMessage.objects.filter(role='user').count(),
        'chats_this_week':   ChatMessage.objects.filter(role='user', created_at__gte=week_ago).count(),
        'total_stock_qty':      BranchStock.objects.aggregate(total=Sum('quantity'))['total'] or 0,
        'total_inventory_value': total_inventory_value(),
    }

    recent_enquiries = Enquiry.objects.select_related('product').order_by('-created_at')[:6]
    recent_messages  = ContactMessage.objects.order_by('-created_at')[:6]
    recent_chats     = ChatMessage.objects.filter(role='user').order_by('-created_at')[:6]

    # Chart data: enquiries per day last 7 days
    chart_labels = []
    chart_enquiries = []
    chart_messages = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        label = day.strftime('%a')
        chart_labels.append(label)
        chart_enquiries.append(
            Enquiry.objects.filter(created_at__date=day.date()).count()
        )
        chart_messages.append(
            ContactMessage.objects.filter(created_at__date=day.date()).count()
        )

    return render(request, 'dashboard/home.html', {
        'stats': stats,
        'recent_enquiries': recent_enquiries,
        'recent_messages': recent_messages,
        'recent_chats': recent_chats,
        'chart_labels': json.dumps(chart_labels),
        'chart_enquiries': json.dumps(chart_enquiries),
        'chart_messages': json.dumps(chart_messages),
    })


# ── PRODUCTS ──────────────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def product_list(request):
    q = request.GET.get('q', '')
    cat_filter = request.GET.get('category', '')
    subcat_filter = request.GET.get('subcategory', '')
    products = Product.objects.select_related('category', 'subcategory').order_by('-created_at')
    if q:
        products = products.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if cat_filter:
        products = products.filter(category__slug=cat_filter)
    if subcat_filter:
        products = products.filter(subcategory__slug=subcat_filter)
    categories = Category.objects.all()
    subcategories = SubCategory.objects.select_related('category').all()
    page_size = getattr(__import__("django.conf", fromlist=["settings"]).settings, "DASHBOARD_PAGE_SIZE", 20)
    from django.core.paginator import Paginator
    paginator = Paginator(products, page_size)
    page_obj  = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/products.html", {
        "products":       page_obj.object_list,
        "page_obj":       page_obj,
        "categories":     categories,
        "subcategories":  subcategories,
        "q":              q,
        "cat_filter":     cat_filter,
        "subcat_filter":  subcat_filter,
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def product_add(request):
    categories = Category.objects.all()
    subcategories = SubCategory.objects.select_related('category').all()
    branches = Branch.objects.filter(is_active=True).order_by('name')
    excel_error = None
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        slug = slugify(name)
        # ensure unique slug
        base = slug
        i = 1
        while Product.objects.filter(slug=slug).exists():
            slug = f"{base}-{i}"; i += 1

        uploaded_excel = request.FILES.get('excel_table_file')
        parsed_excel = None
        wants_excel_table = request.POST.get('needs_excel_table') == 'on' or bool(uploaded_excel)

        if uploaded_excel:
            try:
                parsed_excel = parse_excel_table_file(uploaded_excel)
            except ExcelTableError as exc:
                excel_error = str(exc)
            finally:
                uploaded_excel.seek(0)

        product = Product(
            name=name,
            slug=slug,
            category_id=request.POST.get('category'),
            subcategory_id=request.POST.get('subcategory') or None,
            description=request.POST.get('description', ''),
            is_featured=request.POST.get('is_featured') == 'on',
            is_visible=request.POST.get('is_visible') == 'on',
            needs_excel_table=wants_excel_table,
        )

        if wants_excel_table and not uploaded_excel:
            excel_error = 'Upload an .xlsx file when Needs Excel Table is enabled.'

        if excel_error:
            return render(request, 'dashboard/product_form.html', {
                'categories': categories,
                'subcategories': subcategories,
                'branches': branches,
                'product': product,
                'excel_error': excel_error,
            })

        if request.FILES.get('image'):
            product.image = request.FILES['image']
        product.save()

        # Parse specs
        spec_keys   = request.POST.getlist('spec_key')
        spec_values = request.POST.getlist('spec_value')
        specs = {k: v for k, v in zip(spec_keys, spec_values) if k.strip()}
        if specs:
            product.specifications = specs

        if uploaded_excel and parsed_excel:
            store_excel_table_file(product, uploaded_excel, parsed_data=parsed_excel)

        gallery_uploads = [upload for upload in request.FILES.getlist('gallery_images') if upload]
        if gallery_uploads:
            existing_max = ProductImage.objects.filter(product=product).aggregate(max_order=Max('order'))['max_order'] or 0
            for offset, upload in enumerate(gallery_uploads, start=1):
                ProductImage.objects.create(
                    product=product,
                    image=upload,
                    order=existing_max + offset,
                )

        product.save()

        # Opening stock: one optional qty/cost/threshold trio per active branch.
        for branch in branches:
            qty_raw = request.POST.get(f'opening_qty_{branch.pk}', '').strip()
            price_raw = request.POST.get(f'opening_price_{branch.pk}', '').strip()
            threshold_raw = request.POST.get(f'threshold_{branch.pk}', '').strip()

            if qty_raw and price_raw:
                try:
                    qty = int(qty_raw)
                except ValueError:
                    qty = 0
                if qty > 0:
                    OpeningStock.objects.create(
                        product=product, branch=branch, quantity=qty, price=price_raw, created_by=request.user,
                    )
                    recompute_branch_stock(product.id, branch.id)

            if threshold_raw:
                try:
                    threshold = max(0, int(threshold_raw))
                except ValueError:
                    threshold = 0
                BranchStock.objects.update_or_create(
                    product=product, branch=branch, defaults={'low_stock_threshold': threshold},
                )

        return redirect('dashboard:products')
    return render(request, 'dashboard/product_form.html', {
        'categories': categories,
        'subcategories': subcategories,
        'branches': branches,
        'product': None,
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    categories = Category.objects.all()
    subcategories = SubCategory.objects.select_related('category').all()
    branches = Branch.objects.filter(is_active=True).order_by('name')
    excel_error = None
    if request.method == 'POST':
        product.name = request.POST.get('name', product.name).strip()
        product.category_id = request.POST.get('category', product.category_id)
        product.subcategory_id = request.POST.get('subcategory') or None
        product.description = request.POST.get('description', '')
        product.is_featured = request.POST.get('is_featured') == 'on'
        product.is_visible = request.POST.get('is_visible') == 'on'

        uploaded_excel = request.FILES.get('excel_table_file')
        parsed_excel = None
        product.needs_excel_table = request.POST.get('needs_excel_table') == 'on'
        if uploaded_excel:
            try:
                parsed_excel = parse_excel_table_file(uploaded_excel)
            except ExcelTableError as exc:
                excel_error = str(exc)
            finally:
                uploaded_excel.seek(0)

        if request.FILES.get('image'):
            product.image = request.FILES['image']

        gallery_uploads = [upload for upload in request.FILES.getlist('gallery_images') if upload]

        if product.needs_excel_table and not uploaded_excel and not product.excel_table_file:
            excel_error = 'Upload an .xlsx file when Needs Excel Table is enabled.'

        if excel_error:
            stock_by_branch = {bs.branch_id: bs for bs in BranchStock.objects.filter(product=product)}
            return render(request, 'dashboard/product_form.html', {
                'categories': categories,
                'subcategories': subcategories,
                'branches': branches,
                'branch_rows': [(b, stock_by_branch.get(b.id)) for b in branches],
                'product': product,
                'excel_error': excel_error,
            })

        spec_keys   = request.POST.getlist('spec_key')
        spec_values = request.POST.getlist('spec_value')
        product.specifications = {k: v for k, v in zip(spec_keys, spec_values) if k.strip()}

        if uploaded_excel and parsed_excel:
            store_excel_table_file(product, uploaded_excel, parsed_data=parsed_excel)
        elif not product.needs_excel_table:
            clear_excel_table_file(product)

        product.save()

        if gallery_uploads:
            existing_max = ProductImage.objects.filter(product=product).aggregate(max_order=Max('order'))['max_order'] or 0
            for offset, upload in enumerate(gallery_uploads, start=1):
                ProductImage.objects.create(
                    product=product,
                    image=upload,
                    order=existing_max + offset,
                )

        for branch in branches:
            threshold_raw = request.POST.get(f'threshold_{branch.pk}', '').strip()
            if threshold_raw:
                try:
                    threshold = max(0, int(threshold_raw))
                except ValueError:
                    continue
                BranchStock.objects.filter(product=product, branch=branch).update(low_stock_threshold=threshold)

        return redirect('dashboard:products')
    stock_by_branch = {bs.branch_id: bs for bs in BranchStock.objects.filter(product=product)}
    return render(request, 'dashboard/product_form.html', {
        'categories': categories,
        'subcategories': subcategories,
        'branches': branches,
        'branch_rows': [(b, stock_by_branch.get(b.id)) for b in branches],
        'product': product,
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def product_delete(request, pk):
    """Deletion is only allowed once the product is a clean slate: zero stock
    everywhere and no in-progress transfer referencing it. Historical
    Opening/Purchase/Sale/Transfer rows are kept (product FK just goes null —
    on_delete=SET_NULL — with the name preserved via product_name_snapshot),
    only the now-empty BranchStock rows for this product are removed."""
    product = get_object_or_404(Product, pk=pk)

    nonzero = BranchStock.objects.filter(product=product).exclude(quantity=0).select_related('branch')
    if nonzero.exists():
        parts = ', '.join(f'{row.quantity} units at {row.branch.name}' for row in nonzero)
        return JsonResponse({'success': False, 'message': f'Still has stock — {parts}. Clear it out first.'})

    if StockTransfer.objects.filter(
        product=product, status__in=[StockTransfer.PENDING, StockTransfer.DISPATCHED, StockTransfer.PARTIALLY_RECEIVED]
    ).exists():
        return JsonResponse({'success': False, 'message': 'Has an in-progress transfer — resolve or cancel it first.'})

    with transaction.atomic():
        BranchStock.objects.filter(product=product).delete()
        product.delete()
    return JsonResponse({'success': True})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def product_toggle_featured(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.is_featured = not product.is_featured
    product.save()
    return JsonResponse({'success': True, 'is_featured': product.is_featured})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def product_image_delete(request, pk):
    image = get_object_or_404(ProductImage, pk=pk)
    image.delete()
    return JsonResponse({'success': True})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_GET
def product_image_library(request):
    q = request.GET.get('q', '').strip()
    qs = ProductImage.objects.select_related('product').order_by('-created_at')
    if q:
        qs = qs.filter(product__name__icontains=q)
    images = qs[:60]
    return JsonResponse({'results': [
        {'id': img.pk, 'url': img.image.url, 'product_name': img.product.name} for img in images
    ]})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def product_image_attach_existing(request, pk):
    """Reuses an already-uploaded ProductImage's stored file for a different
    product, instead of re-uploading the same picture — the picker only
    needs a pointer to the existing file, not a new copy on disk."""
    product = get_object_or_404(Product, pk=pk)
    source = get_object_or_404(ProductImage, pk=request.POST.get('source_image_id'))
    existing_max = ProductImage.objects.filter(product=product).aggregate(max_order=Max('order'))['max_order'] or 0
    new_image = ProductImage.objects.create(
        product=product, image=source.image.name, caption=source.caption, order=existing_max + 1,
    )
    return JsonResponse({'success': True, 'image': {'id': new_image.pk, 'url': new_image.image.url}})


# ── SUB CATEGORIES ────────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def subcategory_list(request):
    subcategories = SubCategory.objects.select_related('category').annotate(product_count=Count('products')).order_by('category__name', 'order', 'name')
    return render(request, 'dashboard/subcategories.html', {'subcategories': subcategories})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def subcategory_add(request):
    categories = Category.objects.all()
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        slug = slugify(name)
        base = slug; i = 1
        while SubCategory.objects.filter(slug=slug).exists():
            slug = f"{base}-{i}"; i += 1
        subcategory = SubCategory.objects.create(
            name=name, slug=slug,
            category_id=request.POST.get('category'),
            order=int(request.POST.get('order', 0) or 0),
        )
        return redirect('dashboard:subcategories')
    return render(request, 'dashboard/subcategory_form.html', {'subcategory': None, 'categories': categories})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def subcategory_edit(request, pk):
    subcategory = get_object_or_404(SubCategory, pk=pk)
    categories = Category.objects.all()
    if request.method == 'POST':
        subcategory.name = request.POST.get('name', subcategory.name).strip()
        subcategory.category_id = request.POST.get('category', subcategory.category_id)
        subcategory.order = int(request.POST.get('order', 0) or 0)
        subcategory.save()
        return redirect('dashboard:subcategories')
    return render(request, 'dashboard/subcategory_form.html', {'subcategory': subcategory, 'categories': categories})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def subcategory_delete(request, pk):
    get_object_or_404(SubCategory, pk=pk).delete()
    return JsonResponse({'success': True})


# ── PRODUCTS BULK UPLOAD ──────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def product_import(request):
    result = None
    error = None
    if request.method == 'POST':
        uploaded = request.FILES.get('workbook')
        if not uploaded:
            error = 'Choose an .xlsx file to upload.'
        else:
            result = import_products_workbook(uploaded, request.user, filename=uploaded.name)
    return render(request, 'dashboard/product_import.html', {'result': result, 'error': error})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def product_import_template(request):
    buf = build_products_template_workbook()
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="products_bulk_upload_template.xlsx"'
    return response


# ── CATEGORIES ────────────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def category_list(request):
    categories = Category.objects.annotate(product_count=Count('products')).order_by('order', 'name')
    return render(request, 'dashboard/categories.html', {'categories': categories})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def category_add(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        slug = slugify(name)
        base = slug; i = 1
        while Category.objects.filter(slug=slug).exists():
            slug = f"{base}-{i}"; i += 1
        cat = Category(
            name=name, slug=slug,
            description=request.POST.get('description', ''),
            icon=request.POST.get('icon', ''),
            order=int(request.POST.get('order', 0) or 0),
        )
        if request.FILES.get('image'):
            cat.image = request.FILES['image']
        cat.save()
        return redirect('dashboard:categories')
    return render(request, 'dashboard/category_form.html', {'category': None})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        category.name = request.POST.get('name', category.name).strip()
        category.description = request.POST.get('description', '')
        category.icon = request.POST.get('icon', '')
        category.order = int(request.POST.get('order', 0) or 0)
        if request.FILES.get('image'):
            category.image = request.FILES['image']
        category.save()
        return redirect('dashboard:categories')
    return render(request, 'dashboard/category_form.html', {'category': category})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def category_delete(request, pk):
    get_object_or_404(Category, pk=pk).delete()
    return JsonResponse({'success': True})


# ── INDUSTRIES ────────────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def industry_list(request):
    industries = IndustryCard.objects.all().order_by('order', 'title')
    return render(request, 'dashboard/industries.html', {'industries': industries})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def industry_add(request):
    if request.method == 'POST':
        industry = IndustryCard(
            title=request.POST.get('title', '').strip(),
            description=request.POST.get('description', '').strip(),
            cta_label=request.POST.get('cta_label', '').strip() or 'Learn More',
            order=int(request.POST.get('order', 0) or 0),
            is_active=request.POST.get('is_active') == 'on',
        )
        if request.FILES.get('image'):
            industry.image = request.FILES['image']
        industry.save()
        return redirect('dashboard:industries')
    return render(request, 'dashboard/industry_form.html', {'industry': None})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def industry_edit(request, pk):
    industry = get_object_or_404(IndustryCard, pk=pk)
    if request.method == 'POST':
        industry.title = request.POST.get('title', industry.title).strip()
        industry.description = request.POST.get('description', industry.description).strip()
        industry.cta_label = request.POST.get('cta_label', industry.cta_label).strip() or 'Learn More'
        industry.order = int(request.POST.get('order', industry.order) or 0)
        industry.is_active = request.POST.get('is_active') == 'on'
        if request.FILES.get('image'):
            industry.image = request.FILES['image']
        industry.save()
        return redirect('dashboard:industries')
    return render(request, 'dashboard/industry_form.html', {'industry': industry})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def industry_delete(request, pk):
    get_object_or_404(IndustryCard, pk=pk).delete()
    return JsonResponse({'success': True})


# ── GALLERY ───────────────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def gallery_list(request):
    gallery_images = GalleryImage.objects.all().order_by('order', '-created_at')
    return render(request, 'dashboard/gallery.html', {'gallery_images': gallery_images})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def gallery_add(request):
    # existing categories for select dropdown
    raw_categories = (
        GalleryImage.objects.all().order_by('category').values_list('category', flat=True).distinct()
    )
    gallery_categories = [c for c in raw_categories if c]

    if request.method == 'POST':
        # prefer a new category input over selecting existing
        category_value = (request.POST.get('new_category', '') or request.POST.get('category_select', '') or request.POST.get('category', '')).strip()
        gallery_image = GalleryImage(
            title=request.POST.get('title', '').strip(),
            category=category_value,
            caption=request.POST.get('caption', '').strip(),
            order=int(request.POST.get('order', 0) or 0),
            is_active=request.POST.get('is_active') == 'on',
        )
        if request.FILES.get('image'):
            gallery_image.image = request.FILES['image']
        gallery_image.save()
        return redirect('dashboard:gallery_items')
    return render(request, 'dashboard/gallery_form.html', {'gallery_image': None, 'gallery_categories': gallery_categories})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def gallery_edit(request, pk):
    gallery_image = get_object_or_404(GalleryImage, pk=pk)
    raw_categories = (
        GalleryImage.objects.all().order_by('category').values_list('category', flat=True).distinct()
    )
    gallery_categories = [c for c in raw_categories if c]

    if request.method == 'POST':
        gallery_image.title = request.POST.get('title', gallery_image.title).strip()
        category_value = (request.POST.get('new_category', '') or request.POST.get('category_select', '') or request.POST.get('category', gallery_image.category)).strip()
        gallery_image.category = category_value
        gallery_image.caption = request.POST.get('caption', gallery_image.caption).strip()
        gallery_image.order = int(request.POST.get('order', gallery_image.order) or 0)
        gallery_image.is_active = request.POST.get('is_active') == 'on'
        if request.FILES.get('image'):
            gallery_image.image = request.FILES['image']
        gallery_image.save()
        return redirect('dashboard:gallery_items')
    return render(request, 'dashboard/gallery_form.html', {'gallery_image': gallery_image, 'gallery_categories': gallery_categories})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def gallery_delete(request, pk):
    get_object_or_404(GalleryImage, pk=pk).delete()
    return JsonResponse({'success': True})


# ── ENQUIRIES ─────────────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def enquiry_list(request):
    status_filter = request.GET.get('status', '')
    enquiries = Enquiry.objects.select_related('product__category').order_by('-created_at')
    if status_filter:
        enquiries = enquiries.filter(status=status_filter)
    from django.core.paginator import Paginator
    from django.conf import settings as _s
    paginator = Paginator(enquiries, getattr(_s, "DASHBOARD_PAGE_SIZE", 20))
    page_obj  = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/enquiries.html", {
        "enquiries":     page_obj.object_list,
        "page_obj":      page_obj,
        "status_filter": status_filter,
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def enquiry_update_status(request, pk):
    enquiry = get_object_or_404(Enquiry, pk=pk)
    data = json.loads(request.body)
    enquiry.status = data.get('status', enquiry.status)
    enquiry.save()
    return JsonResponse({'success': True})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def enquiry_delete(request, pk):
    get_object_or_404(Enquiry, pk=pk).delete()
    return JsonResponse({'success': True})


# ── CONTACT MESSAGES ──────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def message_list(request):
    read_filter = request.GET.get('read', '')
    messages = ContactMessage.objects.order_by('-created_at')
    if read_filter == 'unread':
        messages = messages.filter(is_read=False)
    elif read_filter == 'read':
        messages = messages.filter(is_read=True)
    from django.core.paginator import Paginator
    from django.conf import settings as _s
    paginator = Paginator(messages, getattr(_s, "DASHBOARD_PAGE_SIZE", 20))
    page_obj  = paginator.get_page(request.GET.get("page", 1))
    return render(request, "dashboard/messages.html", {
        "messages":    page_obj.object_list,
        "page_obj":    page_obj,
        "read_filter": read_filter,
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def message_mark_read(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    msg.is_read = True
    msg.save()
    return JsonResponse({'success': True})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def message_delete(request, pk):
    get_object_or_404(ContactMessage, pk=pk).delete()
    return JsonResponse({'success': True})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def message_mark_all_read(request):
    ContactMessage.objects.filter(is_read=False).update(is_read=True)
    return JsonResponse({'success': True})


# ── CHAT MESSAGES ─────────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def chat_list(request):
    sessions = (
        ChatMessage.objects
        .values('session_id')
        .annotate(
            msg_count=Count('id'),
            last_msg=Count('created_at'),
        )
        .order_by('-session_id')
    )
    # get last message per session for display
    from django.db.models import Max
    session_data = (
        ChatMessage.objects
        .values('session_id')
        .annotate(count=Count('id'), latest=Max('created_at'))
        .order_by('-latest')[:50]
    )
    return render(request, 'dashboard/chats.html', {'sessions': session_data})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def chat_detail(request, session_id):
    messages = ChatMessage.objects.filter(session_id=session_id).order_by('created_at')
    return render(request, 'dashboard/chat_detail.html', {
        'messages': messages,
        'session_id': session_id,
    })


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def chat_delete_session(request, session_id):
    ChatMessage.objects.filter(session_id=session_id).delete()
    return JsonResponse({'success': True})


# ── NOTIFICATIONS API ─────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@require_GET
def notifications_api(request):
    profile = getattr(request.user, 'stock_profile', None)
    is_admin = bool(profile and profile.role == UserProfile.ADMIN)
    is_branch_staff = bool(profile and profile.role == UserProfile.BRANCH_STAFF)

    new_enquiries = Enquiry.objects.filter(status='new').count() if is_admin else 0
    unread_messages = ContactMessage.objects.filter(is_read=False).count() if is_admin else 0

    awaiting_receipt = [StockTransfer.DISPATCHED, StockTransfer.PARTIALLY_RECEIVED]
    pending_dispatches = 0
    pending_receipts = 0
    pending_issues = 0
    if is_admin:
        pending_dispatches = StockTransfer.objects.filter(status=StockTransfer.PENDING).count()
        pending_receipts = StockTransfer.objects.filter(status__in=awaiting_receipt).count()
        pending_issues = StockTransfer.objects.filter(status=StockTransfer.ISSUE_REPORTED).count()
    elif is_branch_staff:
        pending_dispatches = StockTransfer.objects.filter(
            status=StockTransfer.PENDING, from_branch_id=profile.branch_id
        ).count()
        pending_receipts = StockTransfer.objects.filter(
            status__in=awaiting_receipt, to_branch_id=profile.branch_id
        ).count()

    return JsonResponse({
        'new_enquiries':      new_enquiries,
        'unread_messages':    unread_messages,
        'pending_dispatches': pending_dispatches,
        'pending_receipts':   pending_receipts,
        'pending_issues':     pending_issues,
        'total_unread':       new_enquiries + unread_messages + pending_dispatches + pending_receipts + pending_issues,
    })


# ── RAG MANAGEMENT ────────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
def rag_status(request):
    """RAG system status and management page."""
    from rag.retriever import get_index_stats
    from rag.llm_client import check_ollama_health

    index_stats   = get_index_stats()
    ollama_health = check_ollama_health()

    # Check Redis
    redis_ok = False
    try:
        from django.core.cache import cache
        cache.set('rag_ping', '1', 5)
        redis_ok = cache.get('rag_ping') == '1'
    except Exception:
        pass

    llm_models = [
        {'name': 'llama3',    'badge': 'default', 'badge_class': 'badge-ok'},
        {'name': 'mistral',   'badge': 'fast',    'badge_class': 'pill-in-progress'},
        {'name': 'llama3.2',  'badge': None, 'badge_class': ''},
        {'name': 'gemma2',    'badge': 'lightweight', 'badge_class': 'pill-assistant'},
        {'name': 'phi3',      'badge': None, 'badge_class': ''},
        {'name': 'qwen2.5',   'badge': None, 'badge_class': ''},
    ]
    cli_commands = [
        {'label': 'Build index (first run)',       'cmd': 'python manage.py ingest_rag_data'},
        {'label': 'Rebuild + include DB products', 'cmd': 'python manage.py ingest_rag_data --rebuild --also-seed-products'},
        {'label': 'Add single file',               'cmd': 'python manage.py ingest_rag_data --file data/knowledge_base/new.json'},
        {'label': 'Check index stats',             'cmd': 'python manage.py ingest_rag_data --stats'},
        {'label': 'Start Celery worker',           'cmd': 'celery -A anupam_bearings worker --loglevel=info'},
        {'label': 'Start Ollama',                  'cmd': 'ollama serve'},
    ]
    return render(request, 'dashboard/rag_status.html', {
        'index_stats':   index_stats,
        'ollama_health': ollama_health,
        'redis_ok':      redis_ok,
        'llm_models':    llm_models,
        'cli_commands':  cli_commands,
    })


# ── RAG ADMIN ACTIONS ─────────────────────────────────────
@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def rag_reindex(request):
    """
    POST /dashboard/rag/reindex/
    Trigger a background RAG reindex from the dashboard UI.
    Calls the ingest management command via Celery or subprocess.
    """
    mode = request.POST.get('mode', 'append')  # 'append' | 'rebuild'
    rebuild = (mode == 'rebuild')

    try:
        from chatbot.tasks import ingest_documents_task
        from rag.chunker import file_to_chunks, texts_to_chunks
        from django.conf import settings as _s
        from pathlib import Path

        kb_dir = Path(getattr(_s, 'RAG_KNOWLEDGE_DIR', 'data/knowledge_base'))
        all_chunks, all_metas = [], []

        if kb_dir.exists():
            for f in sorted(kb_dir.glob('**/*.json')) + sorted(kb_dir.glob('**/*.txt')):
                try:
                    c, m = file_to_chunks(str(f))
                    all_chunks.extend(c)
                    all_metas.extend(m)
                except Exception:
                    pass

        # Also ingest products from DB
        if request.POST.get('include_products') == '1':
            from products.models import Product, Category
            texts, metas = [], []
            for p in Product.objects.select_related('category').all():
                spec_str = ' | '.join(f'{k}: {v}' for k, v in (p.specifications or {}).items())
                texts.append(f'Product: {p.name}\nCategory: {p.category.name}\nDescription: {p.description}\n{spec_str}'.strip())
                metas.append({'source': 'product_database', 'title': p.name, 'category': p.category.name})
            if texts:
                extra_c, extra_m = texts_to_chunks(texts, metas)
                all_chunks.extend(extra_c)
                all_metas.extend(extra_m)

        if not all_chunks:
            return JsonResponse({'success': False, 'message': 'No documents found to index.'})

        # Run as background task
        task = ingest_documents_task.delay(all_chunks, all_metas, rebuild=rebuild)
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'message': f'Reindex started — {len(all_chunks)} chunks queued (mode: {"rebuild" if rebuild else "append"}).',
            'chunks':  len(all_chunks),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})


@login_required(login_url='/dashboard/login/')
@staff_required
@role_required(UserProfile.ADMIN)
@require_POST
def rag_upload_document(request):
    """
    POST /dashboard/rag/upload/
    Upload a .json, .txt, or .pdf file and immediately add it to the RAG index.
    """
    import tempfile, os
    from pathlib import Path
    from django.conf import settings as _s

    uploaded_file = request.FILES.get('document')
    if not uploaded_file:
        return JsonResponse({'success': False, 'message': 'No file uploaded.'})

    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in ('.json', '.txt', '.pdf'):
        return JsonResponse({'success': False, 'message': 'Only .json, .txt, and .pdf files are supported.'})

    if uploaded_file.size > 5 * 1024 * 1024:  # 5MB limit
        return JsonResponse({'success': False, 'message': 'File too large. Maximum 5MB.'})

    try:
        from rag.chunker import file_to_chunks
        from rag.retriever import add_documents
        from django.conf import settings as _s

        # Save to knowledge_base directory
        kb_dir = Path(getattr(_s, 'RAG_KNOWLEDGE_DIR', 'data/knowledge_base'))
        kb_dir.mkdir(parents=True, exist_ok=True)
        save_path = kb_dir / uploaded_file.name

        with open(save_path, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        # Chunk and index immediately
        chunks, metas = file_to_chunks(str(save_path))
        if not chunks:
            return JsonResponse({'success': False, 'message': 'No text could be extracted from the file.'})

        total = add_documents(chunks, metas, rebuild=False)
        return JsonResponse({
            'success': True,
            'message': f'"{uploaded_file.name}" uploaded and indexed. {len(chunks)} chunks added. Total vectors: {total}.',
            'chunks':  len(chunks),
            'total':   total,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error processing file: {str(e)}'})
