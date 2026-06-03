"""
products/views.py — product list, detail, search, and enquiry with full validation
"""
import json, logging, resend
from django.shortcuts  import render, get_object_or_404
from django.http       import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.db.models  import Q
from django.core.paginator import Paginator
from django.conf        import settings

from .excel_table import build_excel_table_payload, ExcelTableError
from .models            import Category, Product, Enquiry
from core.validators    import validate_enquiry
from core.seo import breadcrumb_schema, build_seo_context, product_schema

logger = logging.getLogger(__name__)


def product_list(request):
    """Public product catalogue with search + category filter + pagination."""
    categories     = Category.objects.prefetch_related('products').all()
    active_category = request.GET.get('category', '')
    q               = request.GET.get('q', '').strip()

    products = Product.objects.select_related('category').order_by('category__order', 'name')
    if active_category:
        products = products.filter(category__slug=active_category)
    if q:
        products = products.filter(
            Q(name__icontains=q)
            | Q(description__icontains=q)
            | Q(category__name__icontains=q)
        )

    page_size  = getattr(settings, 'PUBLIC_PRODUCTS_PAGE_SIZE', 12)
    paginator  = Paginator(products, page_size)
    page_num   = request.GET.get('page', 1)
    page_obj   = paginator.get_page(page_num)

    filtered = bool(q or active_category)
    seo_context = build_seo_context(
        request,
        title='Industrial Bearings and Motion Products | Anupam Bearings',
        description='Browse industrial bearings, bearing housings, linear motion products, and power transmission products from Anupam Bearings.',
        canonical_url=f"{settings.SITE_URL.rstrip('/')}/products/",
        robots='noindex,follow' if filtered else None,
    )

    return render(request, 'products/product_list.html', seo_context | {
        'categories':     categories,
        'page_obj':       page_obj,
        'products':       page_obj.object_list,
        'active_category': active_category,
        'q':              q,
        'total_count':    paginator.count,
    })


def product_detail(request, slug):
    """Public product detail page with specs and related products."""
    product  = get_object_or_404(Product.objects.prefetch_related('images'), slug=slug)
    related  = (
        Product.objects
        .filter(category=product.category)
        .exclude(pk=product.pk)
        .order_by('?')[:4]
    )
    excel_table_initial = None
    if product.needs_excel_table and product.excel_table_file and product.excel_table_data:
        try:
            excel_table_initial = build_excel_table_payload(product, request.GET)
        except ExcelTableError:
            excel_table_initial = None

    canonical_url = f"{settings.SITE_URL.rstrip('/')}/products/{product.slug}/"
    image_urls = []
    for image in list(product.images.all()):
        if getattr(image.image, 'url', None):
            image_urls.append(f"{settings.SITE_URL.rstrip('/')}{image.image.url}")
    if product.image and getattr(product.image, 'url', None):
        image_urls.append(f"{settings.SITE_URL.rstrip('/')}{product.image.url}")

    seo_context = build_seo_context(
        request,
        title=f'{product.name} | Anupam Bearings',
        description=(product.description or '')[:300] or f'{product.name} from Anupam Bearings.',
        canonical_url=canonical_url,
        og_type='product',
        json_ld=[
            breadcrumb_schema([
                {'name': 'Home', 'item': '/'},
                {'name': 'Products', 'item': '/products/'},
                {'name': product.category.name, 'item': f"/products/?category={product.category.slug}"},
                {'name': product.name, 'item': f"/products/{product.slug}/"},
            ]),
            product_schema(product, image_urls, canonical_url),
        ],
    )

    return render(request, 'products/product_detail.html', seo_context | {
        'product': product,
        'related': related,
        'product_images': list(product.images.all()),
        'excel_table_enabled': bool(product.needs_excel_table and product.excel_table_file and product.excel_table_data),
        'excel_table_initial': excel_table_initial,
    })


@require_GET
def product_excel_table_data(request, slug):
    product = get_object_or_404(Product, slug=slug)
    if not (product.needs_excel_table and product.excel_table_file and product.excel_table_data):
        return JsonResponse({'success': False, 'message': 'No Excel table is available for this product.'}, status=404)

    try:
        payload = build_excel_table_payload(product, request.GET)
    except ExcelTableError as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=400)

    return JsonResponse({'success': True, 'table': payload})


@require_POST
def enquire(request):
    """
    POST /products/enquire/
    Validated enquiry submission with spam protection.
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Invalid request format.'}, status=400)

    cleaned, errors = validate_enquiry(data)
    if errors:
        return JsonResponse({'success': False, 'message': next(iter(errors.values())), 'errors': errors}, status=400)

    # Resolve product
    product = None
    if cleaned['product_id']:
        try:
            product = Product.objects.get(id=cleaned['product_id'])
        except Product.DoesNotExist:
            pass

    enquiry = Enquiry.objects.create(
        product=product,
        name=cleaned['name'],
        email=cleaned['email'],
        phone=cleaned['phone'],
        company=cleaned['company'],
        message=cleaned['message'],
    )

    # Email notification via Resend
    if getattr(settings, 'RESEND_API_KEY', ''):
        try:
            resend.api_key = settings.RESEND_API_KEY
            product_name   = product.name if product else 'General'
            resend.Emails.send({
                'from':    settings.DEFAULT_FROM_EMAIL,
                'to':      [settings.COMPANY_EMAIL],
                'subject': f'[Anupam Bearings] New Enquiry: {product_name}',
                'html': (
                    f'<h2>New Product Enquiry</h2>'
                    f'<p><b>Product:</b> {product_name}</p>'
                    f'<p><b>Name:</b> {enquiry.name}</p>'
                    f'<p><b>Email:</b> {enquiry.email}</p>'
                    f'<p><b>Phone:</b> {enquiry.phone or "—"}</p>'
                    f'<p><b>Company:</b> {enquiry.company or "—"}</p>'
                    f'<p><b>Message:</b><br>{enquiry.message}</p>'
                ),
            })
        except Exception as e:
            logger.warning(f'Resend email failed: {e}')

    return JsonResponse({'success': True, 'message': 'Enquiry submitted! We will contact you within 24 hours.'})


def product_search_api(request):
    """
    GET /products/search/?q=bearing
    JSON search API for frontend live-search.
    Returns top 8 matching products.
    """
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    products = (
        Product.objects
        .filter(
            Q(name__icontains=q)
            | Q(description__icontains=q)
            | Q(category__name__icontains=q)
        )
        .select_related('category')
        .order_by('name')[:8]
    )

    results = [
        {
            'id':       p.pk,
            'name':     p.name,
            'category': p.category.name,
            'slug':     p.slug,
            'icon':     p.category.icon,
            'url':      f'/products/{p.slug}/',
        }
        for p in products
    ]
    return JsonResponse({'results': results, 'query': q})
