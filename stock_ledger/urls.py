from django.urls import path

from . import views

app_name = 'stock_ledger'

urlpatterns = [
    path('', views.stock_dashboard, name='dashboard'),
    path('overview/', views.overview, name='overview'),

    # Product combobox backend
    path('products/search/', views.product_search, name='product_search'),
    path('products/quick-create/', views.product_quick_create, name='product_quick_create'),

    # History
    path('history/', views.history, name='history'),

    # Purchases
    path('purchases/', views.purchase_list, name='purchase_list'),
    path('purchases/add/', views.purchase_add, name='purchase_add'),
    path('purchases/<int:pk>/edit/', views.purchase_edit, name='purchase_edit'),
    path('purchases/<int:pk>/delete/', views.purchase_delete, name='purchase_delete'),

    # Sales
    path('sales/', views.sale_list, name='sale_list'),
    path('sales/add/', views.sale_add, name='sale_add'),
    path('sales/<int:pk>/edit/', views.sale_edit, name='sale_edit'),
    path('sales/<int:pk>/delete/', views.sale_delete, name='sale_delete'),

    # Transfers
    path('transfers/', views.transfer_list, name='transfer_list'),
    path('transfers/create/', views.transfer_create, name='transfer_create'),
    path('transfers/<int:pk>/cancel/', views.transfer_cancel, name='transfer_cancel'),
    path('transfers/<int:pk>/dispatch/', views.transfer_dispatch, name='transfer_dispatch'),
    path('transfers/<int:pk>/receive/', views.transfer_record_receipt, name='transfer_record_receipt'),
    path('transfers/<int:pk>/not-received/', views.transfer_report_not_received, name='transfer_report_not_received'),
    path('transfers/<int:pk>/resolve-issue/', views.transfer_resolve_issue, name='transfer_resolve_issue'),

    # Branches
    path('branches/', views.branch_list, name='branches'),
    path('branches/add/', views.branch_add, name='branch_add'),
    path('branches/<int:pk>/edit/', views.branch_edit, name='branch_edit'),
    path('branches/<int:pk>/deactivate/', views.branch_deactivate, name='branch_deactivate'),

    # Users
    path('users/', views.user_list, name='users'),
    path('users/add/', views.user_add, name='user_add'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/toggle-active/', views.user_toggle_active, name='user_toggle_active'),
    path('users/<int:pk>/reset-password/', views.user_reset_password, name='user_reset_password'),

    # Threshold / BranchStock row removal
    path('branch-stock/<int:pk>/threshold/', views.branch_stock_set_threshold, name='set_threshold'),
    path('branch-stock/<int:pk>/delete/', views.branch_stock_delete, name='branch_stock_delete'),

    # Exports
    path('export/stock/<str:fmt>/', views.export_stock, name='export_stock'),
    path('export/history/<str:kind>/<str:fmt>/', views.export_history, name='export_history'),
]
