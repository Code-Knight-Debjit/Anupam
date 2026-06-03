from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Product


class ProductSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return Product.objects.filter()

    def lastmod(self, obj):
        return getattr(obj, 'created_at', None)


class StaticViewSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.5

    def items(self):
        # URL names for core static pages and contact
        return ['core:home', 'core:about', 'core:gallery', 'contact:contact']

    def location(self, item):
        return reverse(item)
