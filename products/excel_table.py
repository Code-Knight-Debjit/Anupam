from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree as ET

from django.core.paginator import Paginator
from django.utils.text import slugify

XLSX_NS = {
    'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'rel': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'pkgrel': 'http://schemas.openxmlformats.org/package/2006/relationships',
}


class ExcelTableError(ValueError):
    pass


def validate_excel_filename(filename: str) -> None:
    if Path(filename).suffix.lower() != '.xlsx':
        raise ExcelTableError('Only .xlsx files are supported.')


def _stringify_cell(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _build_column_key(label: str, index: int, existing_keys: set[str]) -> str:
    base = slugify(label) or f'column-{index + 1}'
    key = base
    counter = 2
    while key in existing_keys:
        key = f'{base}-{counter}'
        counter += 1
    existing_keys.add(key)
    return key


def _cell_ref_to_index(cell_ref: str | None, fallback_index: int) -> int:
    if not cell_ref:
        return fallback_index

    letters = ''.join(ch for ch in cell_ref if ch.isalpha())
    if not letters:
        return fallback_index

    index = 0
    for character in letters.upper():
        index = index * 26 + (ord(character) - 64)
    return index - 1


def _load_xml(zip_file: ZipFile, member_name: str) -> ET.Element:
    with zip_file.open(member_name) as member:
        return ET.fromstring(member.read())


def _shared_strings(zip_file: ZipFile) -> list[str]:
    if 'xl/sharedStrings.xml' not in zip_file.namelist():
        return []

    root = _load_xml(zip_file, 'xl/sharedStrings.xml')
    strings = []
    for shared_string in root.findall('main:si', XLSX_NS):
        strings.append(''.join(shared_string.itertext()))
    return strings


def _worksheet_path(zip_file: ZipFile) -> tuple[str, str]:
    workbook_root = _load_xml(zip_file, 'xl/workbook.xml')
    sheets_root = workbook_root.find('main:sheets', XLSX_NS)
    if sheets_root is None:
        raise ExcelTableError('The workbook does not contain any sheets.')

    first_sheet = sheets_root.find('main:sheet', XLSX_NS)
    if first_sheet is None:
        raise ExcelTableError('The workbook does not contain any sheets.')

    sheet_name = first_sheet.attrib.get('name', 'Sheet 1')
    rel_id = first_sheet.attrib.get(f'{{{XLSX_NS["rel"]}}}id')
    if not rel_id:
        raise ExcelTableError('The workbook could not resolve the first worksheet.')

    rels_root = _load_xml(zip_file, 'xl/_rels/workbook.xml.rels')
    rel_map = {}
    for rel in rels_root.findall('pkgrel:Relationship', XLSX_NS):
        rel_map[rel.attrib.get('Id', '')] = rel.attrib.get('Target', '')

    target = rel_map.get(rel_id)
    if not target:
        raise ExcelTableError('The workbook could not resolve the first worksheet.')

    if target.startswith('/'):
        target = target.lstrip('/')
    if not target.startswith('xl/'):
        target = f'xl/{target}'

    return sheet_name, target


def _read_sheet_rows(zip_file: ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[str]]:
    sheet_root = _load_xml(zip_file, sheet_path)
    sheet_data = sheet_root.find('main:sheetData', XLSX_NS)
    if sheet_data is None:
        return []

    rows: list[list[str]] = []
    for row_element in sheet_data.findall('main:row', XLSX_NS):
        cells_by_index: dict[int, str] = {}
        max_index = -1

        for fallback_index, cell_element in enumerate(row_element.findall('main:c', XLSX_NS)):
            cell_ref = cell_element.attrib.get('r')
            cell_index = _cell_ref_to_index(cell_ref, fallback_index)
            cell_type = cell_element.attrib.get('t', '')
            value_element = cell_element.find('main:v', XLSX_NS)
            inline_string = cell_element.find('main:is', XLSX_NS)
            value = ''

            if cell_type == 's' and value_element is not None and value_element.text is not None:
                shared_index = int(value_element.text)
                if 0 <= shared_index < len(shared_strings):
                    value = shared_strings[shared_index]
            elif cell_type == 'inlineStr' and inline_string is not None:
                value = ''.join(inline_string.itertext())
            elif cell_type == 'b' and value_element is not None:
                value = 'TRUE' if value_element.text == '1' else 'FALSE'
            elif value_element is not None and value_element.text is not None:
                value = value_element.text

            cells_by_index[cell_index] = _stringify_cell(value)
            max_index = max(max_index, cell_index)

        if max_index >= 0:
            row_values = [''] * (max_index + 1)
            for cell_index, value in cells_by_index.items():
                row_values[cell_index] = value
            rows.append(row_values)

    return rows


def parse_excel_table_file(uploaded_file) -> dict[str, Any]:
    validate_excel_filename(uploaded_file.name)
    uploaded_file.seek(0)

    try:
        with ZipFile(uploaded_file) as zip_file:
            shared_strings = _shared_strings(zip_file)
            sheet_name, sheet_path = _worksheet_path(zip_file)
            raw_rows = _read_sheet_rows(zip_file, sheet_path, shared_strings)
    except BadZipFile as exc:
        raise ExcelTableError('The uploaded file is not a valid .xlsx workbook.') from exc

    uploaded_file.seek(0)

    if not raw_rows:
        raise ExcelTableError('The workbook does not contain any usable table data.')

    header_row = []
    data_start = 0
    for row_index, row in enumerate(raw_rows):
        if any(cell not in (None, '') for cell in row):
            header_row = [_stringify_cell(cell) or f'Column {column_index + 1}' for column_index, cell in enumerate(row)]
            data_start = row_index + 1
            break

    if not header_row:
        raise ExcelTableError('The workbook does not contain any column headers.')

    existing_keys: set[str] = set()
    columns = [
        {
            'key': _build_column_key(label, index, existing_keys),
            'label': label,
            'index': index,
        }
        for index, label in enumerate(header_row)
    ]

    rows = []
    for row_index, row in enumerate(raw_rows[data_start:], start=1):
        if not any(cell not in (None, '') for cell in row):
            continue

        values = {}
        search_parts = []
        for column, cell in zip(columns, row):
            text_value = _stringify_cell(cell)
            values[column['key']] = text_value
            if text_value:
                search_parts.append(text_value.lower())

        rows.append({
            'id': row_index,
            'values': values,
            'search_text': ' '.join(search_parts),
        })

    if not rows:
        raise ExcelTableError('The workbook only contains header rows.')

    return {
        'source_name': Path(uploaded_file.name).name,
        'sheet_name': sheet_name,
        'columns': columns,
        'rows': rows,
    }


def store_excel_table_file(product, uploaded_file, parsed_data: dict[str, Any] | None = None) -> None:
    if parsed_data is None:
        parsed_data = parse_excel_table_file(uploaded_file)

    uploaded_file.seek(0)
    base_name = slugify(product.slug or product.name or 'product') or 'product'
    product.excel_table_file.save(f'{base_name}.xlsx', uploaded_file, save=False)
    product.excel_table_data = parsed_data
    product.needs_excel_table = True


def clear_excel_table_file(product) -> None:
    product.excel_table_file = None
    product.excel_table_data = {}


def _sortable_value(raw_value: Any):
    if raw_value in (None, ''):
        return (1, 1, '')
    if isinstance(raw_value, (int, float)):
        return (0, 0, float(raw_value))
    text = str(raw_value).strip()
    try:
        return (0, 0, float(text.replace(',', '')))
    except ValueError:
        return (0, 1, text.lower())


def _numeric_value(raw_value: Any) -> float | None:
    if raw_value in (None, ''):
        return None
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, (int, float)):
        return float(raw_value)

    text = str(raw_value).strip().replace(',', '')
    try:
        return float(text)
    except ValueError:
        return None


def _format_numeric_value(raw_value: float) -> int | float:
    return int(raw_value) if float(raw_value).is_integer() else raw_value


def _is_numeric_column(rows: list[dict[str, Any]], column_key: str, column_label: str) -> bool:
    label_text = f'{column_key} {column_label}'.lower()
    if 'designation' in label_text:
        return False

    has_values = False
    for row in rows:
        value = (row.get('values', {}).get(column_key) or '').strip()
        if not value:
            continue
        has_values = True
        if _numeric_value(value) is None:
            return False
    return has_values


def build_excel_table_payload(product, params) -> dict[str, Any]:
    table_data = product.excel_table_data or {}
    columns = table_data.get('columns', [])
    rows = table_data.get('rows', [])

    search = (params.get('q') or params.get('search') or '').strip().lower()
    sort_key = params.get('sort') or (columns[0]['key'] if columns else '')
    direction = (params.get('direction') or 'asc').lower()
    page_size = params.get('page_size', 20)
    try:
        page_size = max(5, min(int(page_size), 100))
    except (TypeError, ValueError):
        page_size = 20

    column_types = {
        column['key']: 'range' if _is_numeric_column(rows, column['key'], column['label']) else 'select'
        for column in columns
    }

    active_select_filters: dict[str, str] = {}
    active_range_filters: dict[str, dict[str, str]] = {}
    for column in columns:
        key = column['key']
        if column_types.get(key) == 'range':
            min_value = (params.get(f'f_{key}_min') or '').strip()
            max_value = (params.get(f'f_{key}_max') or '').strip()
            if min_value or max_value:
                active_range_filters[key] = {
                    'min': min_value,
                    'max': max_value,
                }
        else:
            value = (params.get(f'f_{key}') or '').strip()
            if value:
                active_select_filters[key] = value

    search_filtered_rows = []
    for row in rows:
        values = row.get('values', {})
        if search and search not in (row.get('search_text') or '').lower():
            continue

        search_filtered_rows.append(row)

    filtered_rows = []
    for row in search_filtered_rows:
        values = row.get('values', {})

        matched = True
        for column in columns:
            key = column['key']
            if column_types.get(key) == 'range':
                range_filter = active_range_filters.get(key)
                if not range_filter:
                    continue

                numeric_value = _numeric_value(values.get(key))
                if numeric_value is None:
                    matched = False
                    break

                min_value = range_filter.get('min', '')
                max_value = range_filter.get('max', '')

                if min_value:
                    try:
                        if numeric_value < float(min_value):
                            matched = False
                            break
                    except ValueError:
                        matched = False
                        break

                if max_value:
                    try:
                        if numeric_value > float(max_value):
                            matched = False
                            break
                    except ValueError:
                        matched = False
                        break
            else:
                value = active_select_filters.get(key)
                if value and (values.get(key) or '') != value:
                    matched = False
                    break
        if matched:
            filtered_rows.append(row)

    if sort_key and columns:
        valid_keys = {column['key'] for column in columns}
        if sort_key in valid_keys:
            reverse = direction == 'desc'
            filtered_rows.sort(
                key=lambda row: _sortable_value(row.get('values', {}).get(sort_key, '')),
                reverse=reverse,
            )

    paginator = Paginator(filtered_rows, page_size)
    page = params.get('page', 1)
    page_obj = paginator.get_page(page)

    filter_payload = []
    value_rows = search_filtered_rows
    for column in columns:
        key = column['key']
        if column_types.get(key) == 'range':
            numeric_values = [
                numeric_value
                for row in value_rows
                if (numeric_value := _numeric_value(row.get('values', {}).get(key))) is not None
            ]
            filter_payload.append({
                'key': key,
                'label': column['label'],
                'type': 'range',
                'min': _format_numeric_value(min(numeric_values)) if numeric_values else '',
                'max': _format_numeric_value(max(numeric_values)) if numeric_values else '',
                'selected_min': active_range_filters.get(key, {}).get('min', ''),
                'selected_max': active_range_filters.get(key, {}).get('max', ''),
            })
        else:
            counter = Counter()
            for row in value_rows:
                value = (row.get('values', {}).get(key) or '').strip()
                if value:
                    counter[value] += 1
            options = [
                {'value': value, 'label': value, 'count': count}
                for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0].lower()))
            ]
            filter_payload.append({
                'key': key,
                'label': column['label'],
                'type': 'select',
                'options': options,
                'selected': active_select_filters.get(key, ''),
            })

    page_numbers = list(range(1, paginator.num_pages + 1)) if paginator.num_pages else []

    return {
        'source_name': table_data.get('source_name', ''),
        'sheet_name': table_data.get('sheet_name', ''),
        'columns': columns,
        'filters': filter_payload,
        'rows': page_obj.object_list,
        'pagination': {
            'page': page_obj.number,
            'page_size': page_size,
            'total': paginator.count,
            'total_pages': paginator.num_pages,
            'page_numbers': page_numbers,
            'has_previous': page_obj.has_previous(),
            'has_next': page_obj.has_next(),
        },
        'sorting': {
            'key': sort_key,
            'direction': direction,
        },
        'search': params.get('q') or params.get('search') or '',
    }