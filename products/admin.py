from django.contrib import admin
from .excel_table import clear_excel_table_file, store_excel_table_file
from .forms import ProductAdminForm
from .models import Category, Product, ProductImage, Enquiry


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'order']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    inlines = [ProductImageInline]
    list_display = ['name', 'category', 'is_featured', 'needs_excel_table', 'created_at']
    list_filter = ['category', 'is_featured', 'needs_excel_table']
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'category', 'description', 'specifications'),
        }),
        ('Media', {
            'fields': ('image',),
        }),
        ('Table Settings', {
            'fields': ('is_featured', 'needs_excel_table', 'excel_table_file', 'excel_table_summary'),
        }),
    )
    readonly_fields = ('excel_table_summary',)

    def excel_table_summary(self, obj):
        if not obj or not obj.pk:
            return 'Save the product before uploading an Excel table.'
        if not obj.needs_excel_table:
            return 'Excel table disabled.'
        if not obj.excel_table_file:
            return 'Enabled, but no Excel file has been uploaded yet.'
        table_data = obj.excel_table_data or {}
        row_count = len(table_data.get('rows', []))
        column_count = len(table_data.get('columns', []))
        sheet_name = table_data.get('sheet_name', 'Sheet 1')
        source_name = table_data.get('source_name', obj.excel_table_file.name)
        return f'{source_name} • {sheet_name} • {row_count} rows • {column_count} columns'

    def save_model(self, request, obj, form, change):
        uploaded_file = request.FILES.get('excel_table_file')
        parsed_data = form.cleaned_data.get('_excel_table_data')

        super().save_model(request, obj, form, change)

        if not obj.needs_excel_table:
            clear_excel_table_file(obj)
            obj.save(update_fields=['needs_excel_table', 'excel_table_file', 'excel_table_data'])
            return

        if uploaded_file:
            store_excel_table_file(obj, uploaded_file, parsed_data=parsed_data)
            obj.save(update_fields=['needs_excel_table', 'excel_table_file', 'excel_table_data'])

@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'product', 'status', 'created_at']
    list_filter = ['status']
