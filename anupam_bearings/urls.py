from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from core import views as core_views
from products import sitemap_views

urlpatterns = [
    # path('admin/', admin.site.urls),
  path('favicon.ico', core_views.favicon, name='favicon'),
    path('dashboard/', include('dashboard.urls')),
    path('', include('core.urls')),
    path('products/', include('products.urls')),
    path('contact/', include('contact.urls')),
    path('api/', include('chatbot.urls')),
  path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),
  path('sitemap.xml', sitemap_views.sitemap_index, name='sitemap_index'),
  path('sitemap-static.xml', sitemap_views.sitemap_static, name='sitemap_static'),
  path('sitemap-products-<int:page>.xml', sitemap_views.sitemap_products_page, name='sitemap_products_page'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) \
  + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
