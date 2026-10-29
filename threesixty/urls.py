from django.urls import include, path

from . import views

app_name = 'threesixty'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.threesixty_login, name='login'),
    path('logout/', views.threesixty_logout, name='logout'),
    path('api/', include('threesixty.api.urls')),
]
