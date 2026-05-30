from django.shortcuts import render

from products.models import Category, Product
from django.http import HttpResponse
import datetime

from .models import GalleryImage, IndustryCard

def home(request):
    categories = Category.objects.all()[:5]
    featured_products = Product.objects.filter(is_featured=True)[:8]
    industries = IndustryCard.objects.filter(is_active=True).order_by('order', 'title')
    return render(request, 'core/home.html', {
        'categories': categories,
        'featured_products': featured_products,
        'industries': industries,
    })

def about(request):
    industries = IndustryCard.objects.filter(is_active=True).order_by('order', 'title')
    return render(request, 'core/about.html', {
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
    return render(request, 'core/gallery.html', {
        'gallery_images': gallery_images,
        'gallery_categories': gallery_categories,
    })


def sitemap_xml(request):
    """Generate a simple sitemap.xml dynamically for products and categories."""
    host = f"{request.scheme}://{request.get_host()}"
    urls = []
    # Home
    urls.append({'loc': f"{host}/", 'lastmod': datetime.date.today().isoformat()})
    # Categories (as product listing with category param)
    for cat in Category.objects.all():
        urls.append({'loc': f"{host}/products/?category={cat.slug}", 'lastmod': ''})
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
