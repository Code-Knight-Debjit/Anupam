"""
core/views.py

Changes from original:
  - All views pass `keywords` to build_seo_context for meta keywords tag
  - seo_landing_page passes `related_pages` to template sidebar (replaces keyword list)
  - about view passes Organization schema
  - contact view passes LocalBusiness schema
"""

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
    organization_schema,
)
from .seo_pages import SEO_KEYWORD_MAP, SEO_LANDING_PAGES, RELATED_PAGES_MAP


def home(request):
    categories = Category.objects.all()[:5]
    featured_products = Product.objects.filter(is_featured=True)[:8]
    industries = IndustryCard.objects.filter(is_active=True).order_by('order', 'title')
    context = build_seo_context(
        request,
        title='Anupam Bearings | Industrial Bearings, Housings & Motion Products Supplier India',
        description=(
            'Anupam Bearings — certified Timken partner supplying industrial bearings, '
            'bearing housings, linear motion products, and power transmission components '
            'from Bengaluru and Chennai across India.'
        ),
        keywords=(
            'bearing supplier bangalore, industrial bearings india, timken bearings supplier, '
            'bearing distributor chennai, deep groove ball bearings, spherical roller bearings'
        ),
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
    context = build_seo_context(
        request,
        title='About Anupam Bearings | Certified Timken Industrial Bearing Supplier India',
        description=(
            'Anupam Bearings is a certified Timken partner supplying industrial bearings, '
            'bearing housings, and motion products to OEMs, maintenance teams, and distributors '
            'across Bengaluru, Chennai, Karnataka, Tamil Nadu, and India.'
        ),
        keywords=(
            'anupam bearings about, timken certified partner india, industrial bearing company bangalore'
        ),
        json_ld=[organization_schema()],
    )
    context['industries'] = industries
    return render(request, 'core/about.html', context)


def gallery(request):
    gallery_images = GalleryImage.objects.filter(is_active=True).order_by('order', '-created_at')
    gallery_categories = [
        category for category in GalleryImage.objects.filter(is_active=True)
        .order_by('category')
        .values_list('category', flat=True)
        .distinct()
        if category
    ]
    context = build_seo_context(
        request,
        title='Gallery | Anupam Bearings Industrial Products & Projects',
        description='View industrial bearing products, installation projects, and application imagery from Anupam Bearings.',
    )
    context.update({
        'gallery_images': gallery_images,
        'gallery_categories': gallery_categories,
    })
    return render(request, 'core/gallery.html', context)


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
        keywords=landing_page.get('keywords', ''),
        json_ld=[
            breadcrumb_schema(breadcrumb_items),
            faq_schema(landing_page['faq']) if landing_page.get('faq') else None,
            local_schema,
        ],
    )
    context.update({
        'landing_page': landing_page,
        # `related_pages` drives the sidebar — no raw keyword lists exposed to users
        'related_pages': RELATED_PAGES_MAP.get(slug, []),
    })
    return render(request, 'core/seo_landing_page.html', context)


def favicon(request):
    favicon_path = Path(settings.BASE_DIR) / 'static' / 'images' / 'favicon.ico'
    if not favicon_path.exists():
        raise Http404()
    return FileResponse(favicon_path.open('rb'), content_type='image/x-icon')