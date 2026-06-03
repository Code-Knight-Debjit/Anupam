import math
import datetime
from django.http import HttpResponse, Http404
from django.conf import settings
from .models import Product, Category


SITEMAP_PAGE_LIMIT = 50000


def _product_url(host, product):
    return f"{host}/products/{product.slug}/"


def sitemap_index(request):
    host = getattr(settings, 'SITE_URL', f"{request.scheme}://{request.get_host()}")
    total = Product.objects.count()
    pages = max(1, math.ceil(total / SITEMAP_PAGE_LIMIT))

    parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    # static sitemap
    parts.append('  <sitemap>')
    parts.append(f'    <loc>{host}/sitemap-static.xml</loc>')
    parts.append(f'    <lastmod>{datetime.date.today().isoformat()}</lastmod>')
    parts.append('  </sitemap>')

    for i in range(1, pages + 1):
        parts.append('  <sitemap>')
        parts.append(f'    <loc>{host}/sitemap-products-{i}.xml</loc>')
        parts.append(f'    <lastmod>{datetime.date.today().isoformat()}</lastmod>')
        parts.append('  </sitemap>')

    parts.append('</sitemapindex>')
    return HttpResponse('\n'.join(parts), content_type='application/xml')


def sitemap_products_page(request, page=1):
    try:
        page = int(page)
    except (TypeError, ValueError):
        raise Http404()

    total = Product.objects.count()
    pages = max(1, math.ceil(total / SITEMAP_PAGE_LIMIT))
    if page < 1 or page > pages:
        raise Http404()

    start = (page - 1) * SITEMAP_PAGE_LIMIT
    end = start + SITEMAP_PAGE_LIMIT
    products = Product.objects.all()[start:end]

    host = getattr(settings, 'SITE_URL', f"{request.scheme}://{request.get_host()}")
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in products:
        lastmod = p.created_at.date().isoformat() if getattr(p, 'created_at', None) else ''
        parts.append('  <url>')
        parts.append(f'    <loc>{_product_url(host, p)}</loc>')
        if lastmod:
            parts.append(f'    <lastmod>{lastmod}</lastmod>')
        parts.append('  </url>')

    parts.append('</urlset>')
    return HttpResponse('\n'.join(parts), content_type='application/xml')


def sitemap_static(request):
    host = getattr(settings, 'SITE_URL', f"{request.scheme}://{request.get_host()}")
    urls = []
    urls.append({'loc': f"{host}/", 'lastmod': datetime.date.today().isoformat()})
    urls.append({'loc': f"{host}/about/", 'lastmod': ''})
    urls.append({'loc': f"{host}/gallery/", 'lastmod': ''})
    urls.append({'loc': f"{host}/contact/", 'lastmod': ''})
    # categories as filtered product lists
    for cat in Category.objects.all():
        urls.append({'loc': f"{host}/products/?category={cat.slug}", 'lastmod': ''})

    parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        parts.append('  <url>')
        parts.append(f"    <loc>{u['loc']}</loc>")
        if u['lastmod']:
            parts.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        parts.append('  </url>')
    parts.append('</urlset>')
    return HttpResponse('\n'.join(parts), content_type='application/xml')
