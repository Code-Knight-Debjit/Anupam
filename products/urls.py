from django.urls import path
from . import views

app_name = 'products'
urlpatterns = [
    path('',                   views.product_list,       name='list'),
    path('enquire/',           views.enquire,            name='enquire'),
    path('search/',            views.product_search_api, name='search'),
    path('<slug:slug>/table-data/', views.product_excel_table_data, name='excel_table_data'),
    path('<slug:slug>/',       views.product_detail,     name='detail'),
]
