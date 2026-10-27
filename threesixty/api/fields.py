"""Small input-coercion helpers for JSON request bodies. Django only
auto-parses date/time strings when a `ModelForm`/DRF serializer is in the
loop; our hand-rolled resources assign request data straight onto model
fields via `setattr`, so a `DateField` holding the raw string `"2026-01-01"`
would still be a `str` (not a `date`) the moment we call `.isoformat()` on
it again in the same request/response cycle, right after `.save()`."""
from django.utils.dateparse import parse_date, parse_time

from .http import ApiError


def parse_date_input(value, field_name='date'):
    if value is None or not isinstance(value, str):
        return value
    parsed = parse_date(value)
    if parsed is None:
        raise ApiError(400, f'Invalid date for {field_name}: {value!r}')
    return parsed


def parse_time_input(value, field_name='time'):
    if value is None or not isinstance(value, str):
        return value
    parsed = parse_time(value)
    if parsed is None:
        raise ApiError(400, f'Invalid time for {field_name}: {value!r}')
    return parsed


def coerce_dates(data, *field_names):
    """Returns a shallow copy of `data` with each named key date-parsed (if
    present and still a string) — call before passing to setattr/create."""
    coerced = dict(data)
    for field_name in field_names:
        if field_name in coerced:
            coerced[field_name] = parse_date_input(coerced[field_name], field_name)
    return coerced
