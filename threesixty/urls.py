from django.urls import include, path

from . import views

app_name = 'threesixty'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/', include('threesixty.api.urls')),
]
