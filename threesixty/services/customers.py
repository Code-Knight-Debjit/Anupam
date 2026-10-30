"""Customer rules: saving, search & labels, duplicate warning, map pins,
smart filters, contact exports (REQ-CUS-*, REQ-GEO-*).

Shared by the API, the approval service (applying an approved edit) and the
Excel importer, so a customer is saved the same way everywhere.
"""
import re
from datetime import timedelta

from django.db.models import Max, Q
from django.utils import timezone

from ..models import Contact, Customer, Interaction, LookupItem
from ..rules import anupam_rules as rules
from .errors import ServiceError

SCALAR_FIELDS = (
    'name', 'plant', 'address', 'area', 'city', 'state', 'pincode', 'website', 'gst_number',
    'ho_name', 'ho_address', 'ho_city', 'ho_state', 'ho_pincode', 'ho_phone',
    'industry', 'source', 'potential', 'transport_preference', 'courier_preference',
)
GEO_FIELDS = {'plant': ('plant_geo_lat', 'plant_geo_lng'), 'ho': ('ho_geo_lat', 'ho_geo_lng')}
M2M_FIELDS = {
    'preferred_language_ids': 'preferred_languages',
    'interested_brand_ids': 'interested_brands',
    'interested_product_ids': 'interested_products',
}
POTENTIALS = ('High', 'Medium', 'Low')


# --------------------------------------------------------------------------- map pins
def parse_pin(text):
    """'lat, lng' or a Google Maps link -> {'lat','lng'}; raises a 400 with a
    message the user can act on (REQ-GEO-01)."""
    pin = rules.geo_parse(text)
    if pin is None:
        raise ServiceError(400, 'That is not a valid location. Use "latitude, longitude" '
                                '(for example 13.0285, 77.5197) or paste a Google Maps link.')
    return pin


def set_pin(customer, which, value, user):
    """`value` is text/link, or empty to remove the pin. Remembers who set it and when."""
    lat_f, lng_f = GEO_FIELDS[which]
    if value in (None, ''):
        lat = lng = None
    else:
        pin = parse_pin(value)
        lat, lng = pin['lat'], pin['lng']
    changed = (getattr(customer, lat_f), getattr(customer, lng_f)) != (lat, lng)
    setattr(customer, lat_f, lat)
    setattr(customer, lng_f, lng)
    if changed:
        setattr(customer, f'{which}_geo_set_by', user if lat is not None else None)
        setattr(customer, f'{which}_geo_set_at', timezone.now() if lat is not None else None)


def distance_label(customer, lat, lng):
    """'450 m' / '1.5 km' / '25 km' between a position and the plant pin (REQ-GEO-02)."""
    if customer.plant_geo_lat is None or lat is None or lng is None:
        return ''
    metres = rules.geo_dist_m({'lat': customer.plant_geo_lat, 'lng': customer.plant_geo_lng},
                              {'lat': float(lat), 'lng': float(lng)})
    return rules.geo_fmt_dist(metres)


# --------------------------------------------------------------------------- saving
def apply_customer_data(customer, data, user=None):
    """Copy the editable fields of `data` onto `customer` (not saved).
    Assignment is deliberately absent: only Admin / Branch Manager assign, via
    `services.contacts`. Many-to-many ids are returned for `apply_customer_m2m`."""
    for field in SCALAR_FIELDS:
        if field in data:
            value = data[field]
            setattr(customer, field, value.strip() if isinstance(value, str) else (value or ''))
    if 'potential' in data and data['potential'] not in ('', None, *POTENTIALS):
        raise ServiceError(400, 'Potential must be High, Medium or Low.')
    if 'gst_number' in data:
        customer.gst_number = (data['gst_number'] or '').strip().upper()
    for which, (lat_f, lng_f) in GEO_FIELDS.items():
        if f'{which}_geo' in data:                 # text / link, or '' to remove
            set_pin(customer, which, data[f'{which}_geo'], user)
        elif lat_f in data or lng_f in data:       # raw numbers (older clients)
            lat, lng = data.get(lat_f, getattr(customer, lat_f)), data.get(lng_f, getattr(customer, lng_f))
            if (lat is None) != (lng is None):
                raise ServiceError(400, 'Give both latitude and longitude, or neither.')
            if lat is not None:
                set_pin(customer, which, f'{lat}, {lng}', user)
            else:
                set_pin(customer, which, '', user)
    if not (customer.name or '').strip():
        raise ServiceError(400, 'name is required.')


def apply_customer_m2m(customer, data):
    for key, attname in M2M_FIELDS.items():
        if key in data:
            getattr(customer, attname).set(data[key])


def snapshot(customer):
    """JSON-safe description of a customer, for approval before/after views."""
    data = {f: getattr(customer, f) for f in SCALAR_FIELDS}
    data['plant_geo'] = (f'{customer.plant_geo_lat}, {customer.plant_geo_lng}'
                         if customer.plant_geo_lat is not None else '')
    data['ho_geo'] = (f'{customer.ho_geo_lat}, {customer.ho_geo_lng}'
                      if customer.ho_geo_lat is not None else '')
    for key, attname in M2M_FIELDS.items():
        data[key] = sorted(getattr(customer, attname).values_list('id', flat=True))
    return data


# --------------------------------------------------------------------------- search & duplicates
_WORD_SPLIT = re.compile(r'[\s,.\-()/&]+')


def rank_by_query(objects, query, label=lambda o: o.select_label):
    """Word-based search order (REQ-CUS-08): labels starting with the text
    first, then labels where a later word starts with it, then anything
    containing it. Objects that don't match are dropped."""
    q = (query or '').strip().lower()
    if not q:
        return list(objects)
    starts, words, contains = [], [], []
    for obj in objects:
        text = label(obj).lower()
        if text.startswith(q):
            starts.append(obj)
        elif any(w.startswith(q) for w in _WORD_SPLIT.split(text)):
            words.append(obj)
        elif q in text:
            contains.append(obj)
    return starts + words + contains


def search(queryset, query):
    q = (query or '').strip()
    if not q:
        return list(queryset)
    narrowed = queryset.filter(Q(name__icontains=q) | Q(plant__icontains=q) | Q(area__icontains=q))
    return rank_by_query(narrowed, q)


def find_duplicates(name, queryset=None):
    """Existing customers whose names are close to `name` (REQ-CUS-09)."""
    name = (name or '').strip()
    if not name:
        return []
    qs = queryset if queryset is not None else Customer.objects.all()
    return [c for c in qs.only('id', 'name', 'plant', 'area', 'created_by') if rules.near_duplicate(name, c.name)]


# --------------------------------------------------------------------------- smart filters
def _days_filter(queryset, annotation, value):
    if not value:
        return queryset
    if value == 'never':
        return queryset.filter(**{f'{annotation}__isnull': True})
    cutoff = timezone.localdate()
    if value == '90plus':
        # "Not called in 90+ days": has a last date, and it is older than 90 days.
        return queryset.filter(**{f'{annotation}__lt': cutoff - timedelta(days=90)})
    try:
        days = int(value)
    except ValueError:
        raise ServiceError(400, 'Invalid day filter.')
    return queryset.filter(**{f'{annotation}__gte': cutoff - timedelta(days=days)})


def apply_filters(queryset, params):
    """The customer list's smart filters (REQUIREMENTS §2)."""
    get = params.get
    if get('designation'):
        queryset = queryset.filter(contacts__job_title__iexact=get('designation'))
    for param, field in (('state', 'state'), ('area', 'area'), ('industry', 'industry'),
                         ('source', 'source'), ('potential', 'potential')):
        if get(param):
            queryset = queryset.filter(**{f'{field}__iexact': get(param)})
    if get('brand'):
        queryset = queryset.filter(interested_brands__name__iexact=get('brand'))
    if get('product'):
        queryset = queryset.filter(interested_products__name__iexact=get('product'))
    if get('language'):
        queryset = queryset.filter(preferred_languages__name__iexact=get('language'))
    if get('assigned_to'):
        queryset = queryset.filter(assigned_to__id=get('assigned_to'))
    if get('added_by'):
        queryset = queryset.filter(created_by_id=get('added_by'))
    if get('last_call') or get('last_visit'):
        call_types = [Interaction.TYPE_CALL, Interaction.TYPE_COLD_CALL]
        queryset = queryset.annotate(
            _last_call=Max('contacts__interactions__date', filter=Q(contacts__interactions__type__in=call_types)),
            _last_visit=Max('contacts__interactions__date', filter=Q(contacts__interactions__type=Interaction.TYPE_VISIT)),
        )
        queryset = _days_filter(queryset, '_last_call', get('last_call'))
        queryset = _days_filter(queryset, '_last_visit', get('last_visit'))
    return queryset.distinct()


# --------------------------------------------------------------------------- contact exports
def selected_emails(contacts):
    return rules.selected_emails([{'email': c.email} for c in contacts])


def vcard(contacts):
    return rules.vcard([
        {'name': c.name, 'companyName': c.customer.name, 'jobTitle': c.job_title,
         'phone': c.phone, 'email': c.email} for c in contacts
    ])


def lookup_names(kind):
    return list(LookupItem.objects.filter(kind=kind, is_active=True).values_list('name', flat=True))
