from django import forms

from .excel_table import ExcelTableError, parse_excel_table_file
from .models import Product


class ProductAdminForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        needs_excel_table = cleaned.get('needs_excel_table')
        uploaded_file = cleaned.get('excel_table_file')

        if uploaded_file:
            try:
                cleaned['_excel_table_data'] = parse_excel_table_file(uploaded_file)
            except ExcelTableError as exc:
                self.add_error('excel_table_file', str(exc))
            finally:
                uploaded_file.seek(0)

            if not needs_excel_table:
                cleaned['needs_excel_table'] = True

        existing_file = bool(self.instance and self.instance.pk and getattr(self.instance, 'excel_table_file', None))
        if needs_excel_table and not uploaded_file and not existing_file:
            self.add_error('excel_table_file', 'Upload an .xlsx file when Needs Excel Table is enabled.')

        return cleaned