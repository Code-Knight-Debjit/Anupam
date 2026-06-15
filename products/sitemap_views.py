"""
products/sitemap_views.py

Changes:
  - sitemap_static now includes all SEO landing pages from core.seo_pages
  - Added <changefreq> and <priority> hints for Google
  - Category filtered URLs (?category=slug) removed from sitemap (they are noindex)
  - Added <lastmod> based on today's date for static pages
"""

import math
import datetime
from django.http import HttpResponse, Http404
from django.conf import settings
from .models import Product, Category


SITEMAP_PAGE_LIMIT = 50_000


def _product_url(host, product):
    return f"{host}/products/{product.slug}/"


def sitemap_index(request):
    host = getattr(settings, 'SITE_URL', f"{request.scheme}://{request.get_host()}")
    total = Product.objects.count()
    pages = max(1, math.ceil(total / SITEMAP_PAGE_LIMIT))

    today = datetime.date.today().isoformat()
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    # Static pages sitemap
    parts += [
        '  <sitemap>',
        f'    <loc>{host}/sitemap-static.xml</loc>',
        f'    <lastmod>{today}</lastmod>',
        '  </sitemap>',
    ]
    # Product sitemaps
    for i in range(1, pages + 1):
        parts += [
            '  <sitemap>',
            f'    <loc>{host}/sitemap-products-{i}.xml</loc>',
            f'    <lastmod>{today}</lastmod>',
            '  </sitemap>',
        ]
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
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for p in products:
        lastmod = p.created_at.date().isoformat() if getattr(p, 'created_at', None) else ''
        parts.append('  <url>')
        parts.append(f'    <loc>{_product_url(host, p)}</loc>')
        if lastmod:
            parts.append(f'    <lastmod>{lastmod}</lastmod>')
        parts.append('    <changefreq>monthly</changefreq>')
        parts.append('    <priority>0.7</priority>')
        parts.append('  </url>')

    parts.append('</urlset>')
    return HttpResponse('\n'.join(parts), content_type='application/xml')


def sitemap_static(request):
    """
    Sitemap for all non-product pages including SEO landing pages.
    NOTE: Category-filtered URLs (/products/?category=X) are intentionally
    excluded — they are marked noindex in the view layer.
    """
    from core.seo_pages import SEO_LANDING_PAGES

    host = getattr(settings, 'SITE_URL', f"{request.scheme}://{request.get_host()}")
    today = datetime.date.today().isoformat()

    # Static core pages
    urls = [
        {'loc': f"{host}/",         'lastmod': today,  'changefreq': 'weekly',  'priority': '1.0'},
        {'loc': f"{host}/about/",   'lastmod': today,  'changefreq': 'monthly', 'priority': '0.6'},
        {'loc': f"{host}/gallery/", 'lastmod': '',     'changefreq': 'monthly', 'priority': '0.5'},
        {'loc': f"{host}/contact/", 'lastmod': '',     'changefreq': 'yearly',  'priority': '0.7'},
        {'loc': f"{host}/products/",'lastmod': today,  'changefreq': 'weekly',  'priority': '0.9'},
    ]

    # SEO landing pages — all 13 of them
    for slug in SEO_LANDING_PAGES:
        urls.append({
            'loc': f"{host}/{slug}/",
            'lastmod': today,
            'changefreq': 'monthly',
            'priority': '0.8',
        })

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for u in urls:
        parts.append('  <url>')
        parts.append(f"    <loc>{u['loc']}</loc>")
        if u.get('lastmod'):
            parts.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        parts.append(f"    <changefreq>{u['changefreq']}</changefreq>")
        parts.append(f"    <priority>{u['priority']}</priority>")
        parts.append('  </url>')
    parts.append('</urlset>')
    return HttpResponse('\n'.join(parts), content_type='application/xml')