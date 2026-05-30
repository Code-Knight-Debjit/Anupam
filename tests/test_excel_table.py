import json
from io import BytesIO
from types import SimpleNamespace
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from products.excel_table import build_excel_table_payload, parse_excel_table_file
from products.models import Category, Product


def build_minimal_xlsx(headers, rows, sheet_name='Table'):
    def cell_xml(ref, value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f'<c r="{ref}"><v>{value}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'

    def column_letter(index):
        letters = ''
        index += 1
        while index:
            index, remainder = divmod(index - 1, 26)
            letters = chr(65 + remainder) + letters
        return letters

    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>''')
        archive.writestr('_rels/.rels', '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''')
        archive.writestr('xl/workbook.xml', f'''<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>''')
        archive.writestr('xl/_rels/workbook.xml.rels', '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>''')

        row_nodes = []
        for row_index, values in enumerate([headers, *rows], start=1):
            cell_nodes = []
            for column_index, value in enumerate(values):
                ref = f'{column_letter(column_index)}{row_index}'
                cell_nodes.append(cell_xml(ref, value))
            row_nodes.append(f'<row r="{row_index}">{"".join(cell_nodes)}</row>')

        archive.writestr('xl/worksheets/sheet1.xml', f'''<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{''.join(row_nodes)}</sheetData>
</worksheet>''')

    buffer.seek(0)
    return buffer.getvalue()


@pytest.mark.django_db
def test_parse_excel_table_file_extracts_rows_and_columns():
    xlsx_bytes = build_minimal_xlsx(
        ['Designation', 'Bore', 'OD'],
        [
            ['6204', '20', '47'],
            ['6205', '25', '52'],
        ],
    )
    uploaded = SimpleUploadedFile('bearing-table.xlsx', xlsx_bytes, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    parsed = parse_excel_table_file(uploaded)

    assert parsed['sheet_name'] == 'Table'
    assert [column['label'] for column in parsed['columns']] == ['Designation', 'Bore', 'OD']
    assert parsed['rows'][0]['values']['designation'] == '6204'
    assert parsed['rows'][1]['values']['bore'] == '25'


@pytest.mark.django_db
def test_build_excel_table_payload_filters_and_sorts_rows():
    product_data = {
        'source_name': 'bearing-table.xlsx',
        'sheet_name': 'Table',
        'columns': [
            {'key': 'designation', 'label': 'Designation', 'index': 0},
            {'key': 'bore', 'label': 'Bore', 'index': 1},
            {'key': 'od', 'label': 'OD', 'index': 2},
        ],
        'rows': [
            {'id': 1, 'values': {'designation': '6205', 'bore': '25', 'od': '52'}, 'search_text': '6205 25 52'},
            {'id': 2, 'values': {'designation': '6204', 'bore': '20', 'od': '47'}, 'search_text': '6204 20 47'},
        ],
    }
    product = SimpleNamespace(excel_table_data=product_data)

    payload = build_excel_table_payload(product, {
        'q': '620',
        'sort': 'designation',
        'direction': 'desc',
        'page_size': '10',
        'f_bore_min': '20',
        'f_bore_max': '20',
    })

    assert payload['pagination']['total'] == 1
    assert payload['pagination']['page_numbers'] == [1]
    assert payload['rows'][0]['values']['designation'] == '6204'
    assert payload['filters'][0]['type'] == 'select'
    assert payload['filters'][0]['key'] == 'designation'
    assert payload['filters'][1]['type'] == 'range'
    assert payload['filters'][1]['key'] == 'bore'
    assert payload['filters'][1]['selected_min'] == '20'
    assert payload['filters'][1]['selected_max'] == '20'


@pytest.mark.django_db
def test_build_excel_table_payload_uses_designation_exact_match():
    product_data = {
        'source_name': 'bearing-table.xlsx',
        'sheet_name': 'Table',
        'columns': [
            {'key': 'designation', 'label': 'Designation', 'index': 0},
            {'key': 'bore', 'label': 'Bore', 'index': 1},
        ],
        'rows': [
            {'id': 1, 'values': {'designation': '6205', 'bore': '25'}, 'search_text': '6205 25'},
            {'id': 2, 'values': {'designation': '6204', 'bore': '20'}, 'search_text': '6204 20'},
        ],
    }
    product = SimpleNamespace(excel_table_data=product_data)

    payload = build_excel_table_payload(product, {'f_designation': '6204'})

    assert payload['filters'][0]['type'] == 'select'
    assert payload['rows'][0]['values']['designation'] == '6204'
    assert payload['pagination']['total'] == 1


@pytest.mark.django_db
def test_excel_table_endpoint_returns_json(client):
    user = User.objects.create_superuser('tableadmin', 'admin@example.com', 'pass12345')
    client.force_login(user)

    category = Category.objects.create(name='Rolling Bearings', slug='rolling-bearings', icon='gear')
    parsed_data = {
        'source_name': 'bearing-table.xlsx',
        'sheet_name': 'Table',
        'columns': [
            {'key': 'designation', 'label': 'Designation', 'index': 0},
            {'key': 'bore', 'label': 'Bore', 'index': 1},
        ],
        'rows': [
            {'id': 1, 'values': {'designation': '6204', 'bore': '20'}, 'search_text': '6204 20'},
            {'id': 2, 'values': {'designation': '6205', 'bore': '25'}, 'search_text': '6205 25'},
        ],
    }
    product = Product.objects.create(
        name='Tapered Roller Bearing',
        slug='tapered-roller-bearing',
        category=category,
        description='Test product',
        needs_excel_table=True,
        excel_table_file='product_tables/tapered-roller-bearing.xlsx',
        excel_table_data=parsed_data,
    )

    response = client.get(f'/products/{product.slug}/table-data/?q=6204')

    assert response.status_code == 200
    data = json.loads(response.content)
    assert data['success'] is True
    assert data['table']['pagination']['total'] == 1
    assert data['table']['rows'][0]['values']['designation'] == '6204'