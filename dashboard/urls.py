from django.urls import path
from . import views

app_name = 'dashboard'
urlpatterns = [
    path('',               views.dashboard_home,          name='home'),
    path('login/',         views.dashboard_login,          name='login'),
    path('logout/',        views.dashboard_logout,         name='logout'),

    # Products
    path('products/',              views.product_list,            name='products'),
    path('products/add/',          views.product_add,             name='product_add'),
    path('products/<int:pk>/edit/',          views.product_edit,            name='product_edit'),
    path('products/<int:pk>/delete/',        views.product_delete,          name='product_delete'),
    path('products/<int:pk>/toggle-featured/', views.product_toggle_featured, name='product_toggle_featured'),

    # Categories
    path('categories/',            views.category_list,           name='categories'),
    path('categories/add/',        views.category_add,            name='category_add'),
    path('categories/<int:pk>/edit/',        views.category_edit,           name='category_edit'),
    path('categories/<int:pk>/delete/',      views.category_delete,         name='category_delete'),

    # Content
    path('industries/',              views.industry_list,          name='industries'),
    path('industries/add/',          views.industry_add,           name='industry_add'),
    path('industries/<int:pk>/edit/', views.industry_edit,          name='industry_edit'),
    path('industries/<int:pk>/delete/', views.industry_delete,      name='industry_delete'),
    path('gallery/',                 views.gallery_list,           name='gallery_items'),
    path('gallery/add/',             views.gallery_add,            name='gallery_add'),
    path('gallery/<int:pk>/edit/',    views.gallery_edit,           name='gallery_edit'),
    path('gallery/<int:pk>/delete/',  views.gallery_delete,         name='gallery_delete'),
    path('products/images/<int:pk>/delete/', views.product_image_delete, name='product_image_delete'),

    # Enquiries
    path('enquiries/',             views.enquiry_list,            name='enquiries'),
    path('enquiries/<int:pk>/status/',       views.enquiry_update_status,   name='enquiry_status'),
    path('enquiries/<int:pk>/delete/',       views.enquiry_delete,          name='enquiry_delete'),

    # Contact Messages
    path('messages/',              views.message_list,            name='messages'),
    path('messages/<int:pk>/read/',          views.message_mark_read,       name='message_read'),
    path('messages/<int:pk>/delete/',        views.message_delete,          name='message_delete'),
    path('messages/mark-all-read/',          views.message_mark_all_read,   name='message_mark_all_read'),

    # Chat Sessions
    path('chats/',                 views.chat_list,               name='chats'),
    path('chats/<str:session_id>/', views.chat_detail,            name='chat_detail'),
    path('chats/<str:session_id>/delete/', views.chat_delete_session, name='chat_delete'),

    # RAG
    path('rag/',          views.rag_status,          name='rag_status'),
    path('rag/reindex/', views.rag_reindex,          name='rag_reindex'),
    path('rag/upload/',  views.rag_upload_document,  name='rag_upload'),

    # API
    path('api/notifications/',     views.notifications_api,       name='notifications_api'),
]
