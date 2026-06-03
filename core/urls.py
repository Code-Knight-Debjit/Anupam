from django.urls import path
from . import views

app_name = 'core'
urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('gallery/', views.gallery, name='gallery'),
    path('deep-groove-ball-bearings/', views.seo_landing_page, kwargs={'slug': 'deep-groove-ball-bearings'}, name='deep-groove-ball-bearings'),
    path('angular-contact-bearings/', views.seo_landing_page, kwargs={'slug': 'angular-contact-bearings'}, name='angular-contact-bearings'),
    path('spherical-roller-bearings/', views.seo_landing_page, kwargs={'slug': 'spherical-roller-bearings'}, name='spherical-roller-bearings'),
    path('cylindrical-roller-bearings/', views.seo_landing_page, kwargs={'slug': 'cylindrical-roller-bearings'}, name='cylindrical-roller-bearings'),
    path('timken-bearings/', views.seo_landing_page, kwargs={'slug': 'timken-bearings'}, name='timken-bearings'),
    path('skf-bearings/', views.seo_landing_page, kwargs={'slug': 'skf-bearings'}, name='skf-bearings'),
    path('fag-bearings/', views.seo_landing_page, kwargs={'slug': 'fag-bearings'}, name='fag-bearings'),
    path('bearing-supplier-bangalore/', views.seo_landing_page, kwargs={'slug': 'bearing-supplier-bangalore'}, name='bearing-supplier-bangalore'),
    path('bearing-supplier-chennai/', views.seo_landing_page, kwargs={'slug': 'bearing-supplier-chennai'}, name='bearing-supplier-chennai'),
    path('bearing-distributor-karnataka/', views.seo_landing_page, kwargs={'slug': 'bearing-distributor-karnataka'}, name='bearing-distributor-karnataka'),
    path('bearings-for-automotive/', views.seo_landing_page, kwargs={'slug': 'bearings-for-automotive'}, name='bearings-for-automotive'),
    path('bearings-for-manufacturing/', views.seo_landing_page, kwargs={'slug': 'bearings-for-manufacturing'}, name='bearings-for-manufacturing'),
    path('bearings-for-mining/', views.seo_landing_page, kwargs={'slug': 'bearings-for-mining'}, name='bearings-for-mining'),
]
