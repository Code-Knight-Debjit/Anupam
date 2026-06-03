import datetime
import json
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render

from products.models import Category, Product

from .models import GalleryImage, IndustryCard
from .seo import (
    PRIMARY_LOCATIONS,
    SITE_DESCRIPTION,
    SITE_NAME,
    breadcrumb_schema,
    build_canonical_url,
    build_seo_context,
    faq_schema,
    local_business_schema,
)
from .seo_pages import SEO_KEYWORD_MAP, SEO_LANDING_PAGES

def home(request):
    categories = Category.objects.all()[:5]
    featured_products = Product.objects.filter(is_featured=True)[:8]
    industries = IndustryCard.objects.filter(is_active=True).order_by('order', 'title')
    context = build_seo_context(
        request,
        title='Anupam Bearings | Industrial Bearings, Housings, and Motion Products',
        description='Anupam Bearings supplies industrial bearings, bearing housings, linear motion products, and power transmission components from Bengaluru and Chennai.',
        json_ld=[local_business_schema(PRIMARY_LOCATIONS[0])],
    )
    context.update({
        'categories': categories,
        'featured_products': featured_products,
        'industries': industries,
        'keyword_clusters': SEO_KEYWORD_MAP,
    })
    return render(request, 'core/home.html', context)

def about(request):
    industries = IndustryCard.objects.filter(is_active=True).order_by('order', 'title')
    return render(request, 'core/about.html', build_seo_context(
        request,
        title='About Anupam Bearings | Certified Industrial Bearing Supplier',
        description='Learn how Anupam Bearings supports industrial procurement, OEM supply, and maintenance teams with genuine bearings and technical sourcing support.',
    ) | {
        'industries': industries,
    })

def gallery(request):
    gallery_images = GalleryImage.objects.filter(is_active=True).order_by('order', '-created_at')
    gallery_categories = [
        category for category in GalleryImage.objects.filter(is_active=True)
        .order_by('category')
        .values_list('category', flat=True)
        .distinct()
        if category
    ]
    return render(request, 'core/gallery.html', build_seo_context(
        request,
        title='Gallery | Anupam Bearings Industrial Projects',
        description='View industrial product installations, application imagery, and customer project visuals from Anupam Bearings.',
    ) | {
        'gallery_images': gallery_images,
        'gallery_categories': gallery_categories,
    })


def seo_landing_page(request, slug):
    landing_page = SEO_LANDING_PAGES.get(slug)
    if not landing_page:
        raise Http404()

    breadcrumb_items = [
        {'name': 'Home', 'item': '/'},
        {'name': landing_page['headline'], 'item': f'/{slug}/'},
    ]
    local_schema = None
    if 'bangalore' in slug or 'karnataka' in slug:
        local_schema = local_business_schema(PRIMARY_LOCATIONS[0])
    elif 'chennai' in slug or 'tamil' in slug:
        local_schema = local_business_schema(PRIMARY_LOCATIONS[1])

    context = build_seo_context(
        request,
        title=landing_page['title'],
        description=landing_page['description'],
        canonical_url=f"{settings.SITE_URL.rstrip('/')}/{slug}/",
        json_ld=[
            breadcrumb_schema(breadcrumb_items),
            faq_schema(landing_page['faq']) if landing_page.get('faq') else None,
            local_schema,
        ],
    )
    context.update({
        'landing_page': landing_page,
        'keyword_targets': SEO_KEYWORD_MAP['commercial'] + SEO_KEYWORD_MAP['product'] + SEO_KEYWORD_MAP['brand'] + SEO_KEYWORD_MAP['local'],
        'related_links': [
            {'label': 'Products', 'url': '/products/'},
            {'label': 'Contact', 'url': '/contact/'},
        ],
        'breadcrumb_schema_json': json.dumps(breadcrumb_schema(breadcrumb_items), ensure_ascii=False, separators=(',', ':')),
        'faq_schema_json': json.dumps(faq_schema(landing_page['faq']), ensure_ascii=False, separators=(',', ':')) if landing_page.get('faq') else '',
        'local_business_schema_json': json.dumps(local_schema, ensure_ascii=False, separators=(',', ':')) if local_schema else '',
    })
    return render(request, 'core/seo_landing_page.html', context)


def favicon(request):
    favicon_path = Path(settings.BASE_DIR) / 'static' / 'images' / 'favicon.ico'
    if not favicon_path.exists():
        raise Http404()
    return FileResponse(favicon_path.open('rb'), content_type='image/x-icon')


def sitemap_xml(request):
    """Generate a simple sitemap.xml dynamically for products and categories."""
    from django.conf import settings as _settings
    host = getattr(_settings, 'SITE_URL', f"{request.scheme}://{request.get_host()}").rstrip('/')
    urls = []
    # Home
    urls.append({'loc': f"{host}/", 'lastmod': datetime.date.today().isoformat()})
    # Categories (as product listing with category param)
    for cat in Category.objects.all():
        urls.append({'loc': f"{host}/products/?category={cat.slug}", 'lastmod': ''})
    for slug in SEO_LANDING_PAGES:
        urls.append({'loc': f"{host}/{slug}/", 'lastmod': ''})
    # Products
    for p in Product.objects.all():
        lastmod = p.created_at.date().isoformat() if getattr(p, 'created_at', None) else ''
        urls.append({'loc': f"{host}/products/{p.slug}/", 'lastmod': lastmod})

    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        xml_parts.append('  <url>')
        xml_parts.append(f"    <loc>{u['loc']}</loc>")
        if u['lastmod']:
            xml_parts.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        xml_parts.append('  </url>')
    xml_parts.append('</urlset>')

    return HttpResponse('\n'.join(xml_parts), content_type='application/xml')
