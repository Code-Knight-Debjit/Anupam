from django.contrib import admin

from . import models as m


@admin.register(m.Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'legacy_id')
    search_fields = ('name',)


@admin.register(m.BranchNumbering)
class BranchNumberingAdmin(admin.ModelAdmin):
    list_display = ('branch', 'doc_type', 'prefix', 'suffix', 'start_at', 'last_issued')
    list_filter = ('branch', 'doc_type')


@admin.register(m.EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'job_title', 'is_active_employee', 'legacy_id')
    list_filter = ('role', 'branches', 'is_active_employee')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'job_title')
    autocomplete_fields = ('user',)


@admin.register(m.Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ('date', 'name')
    list_filter = ('branches',)


@admin.register(m.LookupItem)
class LookupItemAdmin(admin.ModelAdmin):
    list_display = ('kind', 'name', 'extra', 'is_active', 'sort_order')
    list_filter = ('kind', 'is_active')
    search_fields = ('name',)


@admin.register(m.SalesPerson)
class SalesPersonAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone')
    search_fields = ('name',)


@admin.register(m.SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    list_display = ('key',)


class ContactInline(admin.TabularInline):
    model = m.Contact
    extra = 0


@admin.register(m.Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'plant', 'city', 'state', 'industry', 'created_by', 'created_at')
    list_filter = ('state', 'industry', 'source', 'potential')
    search_fields = ('name', 'plant', 'gst_number')
    inlines = [ContactInline]
    autocomplete_fields = ('created_by',)


@admin.register(m.Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'customer', 'job_title', 'phone', 'dnd')
    list_filter = ('dnd',)
    search_fields = ('name', 'phone', 'email')
    autocomplete_fields = ('customer',)


@admin.register(m.Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ('contact', 'type', 'date', 'created_by', 'is_copy')
    list_filter = ('type', 'is_copy')
    autocomplete_fields = ('contact', 'linked_doc')


class SalesDocumentItemInline(admin.TabularInline):
    model = m.SalesDocumentItem
    extra = 0


@admin.register(m.SalesDocument)
class SalesDocumentAdmin(admin.ModelAdmin):
    list_display = ('doc_number', 'type', 'branch', 'customer', 'date', 'order_status', 'total_amount')
    list_filter = ('type', 'branch', 'order_status')
    search_fields = ('doc_number', 'customer__name')
    inlines = [SalesDocumentItemInline]
    autocomplete_fields = ('customer', 'contact', 'reference', 'created_by', 'sales_person')


@admin.register(m.SalesDocumentItem)
class SalesDocumentItemAdmin(admin.ModelAdmin):
    list_display = ('document', 'item_name', 'qty', 'rate', 'value')
    search_fields = ('item_name', 'document__doc_number')
    autocomplete_fields = ('document',)


@admin.register(m.SupplyLogEntry)
class SupplyLogEntryAdmin(admin.ModelAdmin):
    list_display = ('item', 'date', 'qty_supplied', 'recorded_by')
    autocomplete_fields = ('item', 'recorded_by')


@admin.register(m.DocumentCallLog)
class DocumentCallLogAdmin(admin.ModelAdmin):
    list_display = ('document', 'user', 'timestamp')
    autocomplete_fields = ('document', 'user')


@admin.register(m.PaymentCollection)
class PaymentCollectionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'branch', 'amount', 'date', 'created_by')
    list_filter = ('branch',)
    search_fields = ('customer__name',)
    autocomplete_fields = ('customer', 'contact', 'created_by')


@admin.register(m.PaymentReceipt)
class PaymentReceiptAdmin(admin.ModelAdmin):
    list_display = ('payment', 'amount', 'date', 'mode', 'recorded_by')
    list_filter = ('mode',)
    autocomplete_fields = ('payment', 'recorded_by')


@admin.register(m.Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'assigned_to', 'status', 'priority', 'due_date')
    list_filter = ('status', 'priority', 'task_type')
    search_fields = ('title',)
    autocomplete_fields = ('assigned_to', 'related_customer', 'related_contact', 'related_document', 'created_by')


@admin.register(m.Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'type', 'read', 'created_at')
    list_filter = ('type', 'read')
    autocomplete_fields = ('user',)


@admin.register(m.ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ('type', 'status', 'requested_by', 'requested_at', 'reviewed_by', 'reviewed_at')
    list_filter = ('type', 'status')
    autocomplete_fields = ('customer', 'document', 'requested_by', 'reviewed_by')


@admin.register(m.CallAssignment)
class CallAssignmentAdmin(admin.ModelAdmin):
    list_display = ('customer', 'contact', 'week_of', 'status', 'assigned_to')
    list_filter = ('status', 'week_of')
    search_fields = ('customer__name',)
    autocomplete_fields = ('customer', 'contact', 'assigned_to', 'assigned_by', 'called_by')


@admin.register(m.CallAttempt)
class CallAttemptAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'reason', 'at', 'by')
    autocomplete_fields = ('assignment', 'by')


@admin.register(m.AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'check_in', 'check_out')
    list_filter = ('date',)
    autocomplete_fields = ('user',)


@admin.register(m.LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'date_from', 'date_to', 'status', 'decided_by')
    list_filter = ('status',)
    autocomplete_fields = ('user', 'decided_by')


@admin.register(m.StockProduct)
class StockProductAdmin(admin.ModelAdmin):
    list_display = ('item_name', 'make', 'unit', 'opening_qty')
    search_fields = ('item_name',)


@admin.register(m.Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'gstin')
    search_fields = ('name',)


@admin.register(m.StockBill)
class StockBillAdmin(admin.ModelAdmin):
    list_display = ('bill_number', 'supplier', 'date', 'amount')
    autocomplete_fields = ('supplier',)


@admin.register(m.StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ('item_name', 'branch', 'type', 'qty', 'date', 'source')
    list_filter = ('type', 'branch', 'source')
    autocomplete_fields = ('branch', 'ref_document', 'recorded_by')
