"""`/360/api/` routes. Every resource below is reached through
`staff_360_required` (applied on `JsonResource.dispatch` / each function
view) — there is no endpoint here that bypasses session auth or CSRF."""
from django.urls import path

from . import views_labels, views_attendance, views_core, views_customers, views_outreach, views_payments, views_sales, views_tasks

app_name = 'threesixty_api'

urlpatterns = [
    path('me/', views_core.me, name='me'),
    path('bootstrap/', views_core.bootstrap, name='bootstrap'),

    path('branches/', views_core.BranchResource.as_view(), name='branches'),
    path('branches/<int:pk>/', views_core.BranchResource.as_view(), name='branch-detail'),
    path('branches/<int:branch_id>/images/<str:kind>/', views_core.branch_image, name='branch-image'),
    path('branches/<int:branch_id>/numbering/<str:doc_type>/', views_core.branch_numbering_detail,
         name='branch-numbering'),

    path('holidays/', views_core.HolidayResource.as_view(), name='holidays'),
    path('holidays/<int:pk>/', views_core.HolidayResource.as_view(), name='holiday-detail'),

    path('lookups/', views_core.LookupItemResource.as_view(), name='lookups'),
    path('lookups/<int:pk>/', views_core.LookupItemResource.as_view(), name='lookup-detail'),

    path('sales-persons/', views_core.SalesPersonResource.as_view(), name='sales-persons'),
    path('sales-persons/<int:pk>/', views_core.SalesPersonResource.as_view(), name='sales-person-detail'),

    path('site-settings/', views_core.SiteSettingResource.as_view(), name='site-settings'),
    path('site-settings/<int:pk>/', views_core.SiteSettingResource.as_view(), name='site-setting-detail'),

    path('employees/', views_core.EmployeeResource.as_view(), name='employees'),
    path('employees/<int:pk>/', views_core.EmployeeResource.as_view(), name='employee-detail'),

    path('customers/', views_customers.CustomerResource.as_view(), name='customers'),
    path('customers/<int:pk>/', views_customers.CustomerResource.as_view(), name='customer-detail'),
    path('customers/duplicate-check/', views_customers.duplicate_check, name='customer-duplicate-check'),
    path('customers/export/', views_customers.customers_export, name='customers-export'),
    path('customers/nearby/', views_customers.nearby, name='customers-nearby'),
    path('customers/bulk-assign/', views_customers.customers_bulk_assign, name='customers-bulk-assign'),
    path('customers/import/', views_customers.import_customers, name='customers-import'),
    path('customers/import/template/', views_customers.import_template, name='customers-import-template'),
    path('contacts/export/', views_customers.contacts_export, name='contacts-export'),
    path('geo/parse/', views_customers.geo_parse, name='geo-parse'),
    path('customers/<int:pk>/assign/', views_customers.customer_assign, name='customer-assign'),
    path('customers/<int:pk>/contact-access/', views_customers.customer_contact_access, name='customer-contact-access'),
    path('customers/<int:customer_id>/contacts/', views_customers.ContactResource.as_view(),
         name='customer-contacts'),
    path('contacts/', views_customers.ContactResource.as_view(), name='contacts'),
    path('contacts/<int:pk>/', views_customers.ContactResource.as_view(), name='contact-detail'),
    path('contacts/<int:contact_id>/interactions/', views_customers.InteractionResource.as_view(),
         name='contact-interactions'),
    path('interactions/', views_customers.InteractionResource.as_view(), name='interactions'),
    path('interactions/<int:pk>/', views_customers.InteractionResource.as_view(), name='interaction-detail'),

    path('sales-documents/', views_sales.SalesDocumentResource.as_view(), name='sales-documents'),
    path('sales-documents/<int:pk>/', views_sales.SalesDocumentResource.as_view(), name='sales-document-detail'),
    path('sales-documents/export/', views_sales.documents_export, name='sales-documents-export'),
    path('sales-documents/<int:pk>/pdf/', views_sales.document_pdf, name='sales-document-pdf'),
    path('sales-documents/<int:pk>/print/', views_sales.document_pdf, name='sales-document-print'),
    path('sales-documents/<int:pk>/export.xlsx', views_sales.document_xlsx, name='sales-document-xlsx'),
    path('sales-documents/<int:pk>/outcome/', views_sales.document_outcome, name='sales-document-outcome'),
    path('sales-documents/<int:pk>/clone/', views_sales.document_clone, name='sales-document-clone'),
    path('sales-documents/<int:pk>/schedule/', views_sales.document_schedule, name='sales-document-schedule'),
    path('sales-documents/<int:document_id>/calls/', views_sales.DocumentCallLogResource.as_view(),
         name='sales-document-calls'),
    path('supply-log/<int:pk>/', views_sales.SupplyLogEntryResource.as_view(), name='supply-log-detail'),
    path('sales-document-items/<int:item_id>/invoice-log/', views_sales.InvoiceLogEntryResource.as_view(),
         name='sales-document-item-invoice-log'),
    path('sales-document-items/<int:item_id>/supply-log/', views_sales.SupplyLogEntryResource.as_view(),
         name='sales-document-item-supply-log'),

    path('payment-collections/', views_payments.PaymentCollectionResource.as_view(), name='payment-collections'),
    path('payment-collections/<int:pk>/', views_payments.PaymentCollectionResource.as_view(),
         name='payment-collection-detail'),
    path('payment-collections/<int:payment_id>/contact-log/', views_payments.PaymentContactLogResource.as_view(),
         name='payment-collection-contact-log'),
    path('payment-collections/<int:payment_id>/receipts/', views_payments.PaymentReceiptResource.as_view(),
         name='payment-collection-receipts'),

    path('labels/options/', views_labels.label_options, name='label-options'),
    path('labels/autofill/', views_labels.label_autofill, name='label-autofill'),
    path('labels/pdf/', views_labels.label_pdf, name='label-pdf'),

    path('tasks/', views_tasks.TaskResource.as_view(), name='tasks'),
    path('tasks/<int:pk>/', views_tasks.TaskResource.as_view(), name='task-detail'),

    path('notifications/', views_tasks.NotificationResource.as_view(), name='notifications'),
    path('notifications/read-all/', views_tasks.notifications_read_all, name='notifications-read-all'),
    path('notifications/<int:pk>/', views_tasks.NotificationResource.as_view(), name='notification-detail'),

    path('approvals/', views_tasks.ApprovalRequestResource.as_view(), name='approvals'),
    path('approvals/<int:pk>/', views_tasks.ApprovalRequestResource.as_view(), name='approval-detail'),
    path('approvals/<int:pk>/changes/', views_tasks.approval_changes, name='approval-changes'),
    path('approvals/<int:pk>/approve/', views_tasks.approve_request, name='approval-approve'),
    path('approvals/<int:pk>/reject/', views_tasks.reject_request, name='approval-reject'),

    path('call-assignments/assign/', views_outreach.assign_outreach, name='call-assignments-assign'),
    path('call-assignments/', views_outreach.CallAssignmentResource.as_view(), name='call-assignments'),
    path('call-assignments/<int:pk>/', views_outreach.CallAssignmentResource.as_view(),
         name='call-assignment-detail'),
    path('call-assignments/<int:assignment_id>/attempts/', views_outreach.CallAttemptResource.as_view(),
         name='call-assignment-attempts'),

    path('attendance/', views_attendance.AttendanceRecordResource.as_view(), name='attendance'),
    path('attendance/<int:pk>/', views_attendance.AttendanceRecordResource.as_view(), name='attendance-detail'),
    path('attendance/check-in/', views_attendance.check_in, name='attendance-check-in'),
    path('attendance/check-out/', views_attendance.check_out, name='attendance-check-out'),
    path('attendance/correct/', views_attendance.correct_day, name='attendance-correct'),

    path('leave-requests/', views_attendance.LeaveRequestResource.as_view(), name='leave-requests'),
    path('leave-requests/<int:pk>/', views_attendance.LeaveRequestResource.as_view(), name='leave-request-detail'),
    path('leave-requests/<int:pk>/approve/', views_attendance.approve_leave_request,
         name='leave-request-approve'),
    path('leave-requests/<int:pk>/reject/', views_attendance.reject_leave_request,
         name='leave-request-reject'),
]
