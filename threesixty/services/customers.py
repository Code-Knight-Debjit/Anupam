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
POTENTIALS = ('High', 'Medium', 'Low', 'WhatsApp/Email Only')


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
        raise ServiceError(400, 'Potential must be High, Medium, Low or WhatsApp/Email Only.')
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


CONTACT_KEYS = ('name', 'job_title', 'phone', 'phone2', 'email')


def contact_rows(customer, user=None):
    """The contacts of a customer as plain dicts (only those `user` may see when given)."""
    from . import contacts as contact_service
    qs = contact_service.visible_contacts(user, customer) if user is not None else customer.contacts.all()
    return [{'id': c.pk, **{k: getattr(c, k) for k in CONTACT_KEYS}} for c in qs.order_by('id')]


def apply_contacts(customer, rows, actor):
    """Make the customer's contacts (the ones `actor` may see) equal to `rows` — the reference saves the contact list with
    the customer: a row with an id updates that contact, a row without one is new, a visible contact that is no longer in the
    list is removed. Fully blank rows are ignored. Contacts hidden from `actor` are never touched."""
    from ..models import Contact
    from . import contacts as contact_service
    visible = {c.pk: c for c in contact_service.visible_contacts(actor, customer)}
    kept = set()
    for row in rows or []:
        values = {k: (row.get(k) or '').strip() for k in CONTACT_KEYS}
        if not any(values[k] for k in ('name', 'phone', 'phone2', 'email')):
            continue
        cid = row.get('id')
        contact = visible.get(int(cid)) if cid not in (None, '') else None
        if contact is None:
            contact = Contact(customer=customer)
        for k, v in values.items():
            setattr(contact, k, v)
        contact.save()
        kept.add(contact.pk)
    for pk, contact in visible.items():
        if pk not in kept:
            contact_service.delete_contact(contact)


def snapshot(customer):
    """JSON-safe description of a customer, for approval before/after views."""
    data = {f: getattr(customer, f) for f in SCALAR_FIELDS}
    data['plant_geo'] = (f'{customer.plant_geo_lat}, {customer.plant_geo_lng}'
                         if customer.plant_geo_lat is not None else '')
    data['ho_geo'] = (f'{customer.ho_geo_lat}, {customer.ho_geo_lng}'
                      if customer.ho_geo_lat is not None else '')
    for key, attname in M2M_FIELDS.items():
        data[key] = sorted(getattr(customer, attname).values_list('id', flat=True))
    data['contacts'] = contact_rows(customer)
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


# --------------------------------------------------------------------------- person profile
DOC_LABELS = {'enquiry': 'Enquiry', 'quotation': 'Quotation', 'proforma': 'Proforma', 'po': 'Sales Order', 'dc': 'Delivery Challan'}


def _name(user):
    return (user.get_full_name() or user.username) if user else ''


def contact_profile(viewer, contact):
    """Everything the person-profile page shows besides the contact itself: the merged interaction history (logged
    interactions, calls recorded on this contact's sales documents, and not-reached outreach attempts), the contact's sales
    documents, and the open documents an interaction can be linked to ("Regarding")."""
    from ..models import CallAttempt, DocumentCallLog, SalesDocument
    from ..permissions import RoleRules
    from .printing import quotation_value_of
    docs_qs = RoleRules.visible_sales_documents(viewer, SalesDocument.objects.filter(customer=contact.customer)).select_related('contact').prefetch_related('items')
    mine = [d for d in docs_qs if d.contact_id == contact.pk]
    history = []
    for i in contact.interactions.select_related('created_by', 'linked_doc').prefetch_related('also_met', 'joint_with'):
        doc = i.linked_doc
        history.append({
            'id': f'i{i.pk}', 'type': i.type, 'date': i.date.isoformat(), 'notes': i.notes, 'user_name': _name(i.created_by),
            'followup_date': i.followup_date.isoformat() if i.followup_date else None,
            'also_met': [{'id': c.pk, 'name': c.name} for c in i.also_met.all()],
            'joint_with': [{'id': u.pk, 'name': _name(u)} for u in i.joint_with.all()],
            'doc': {'type': doc.type, 'label': DOC_LABELS.get(doc.type, 'document'), 'number': doc.doc_number} if doc else None,
            'is_copy': i.is_copy, 'met_with_name': i.met_with_name,
            'location': {'lat': i.location_lat, 'lng': i.location_lng} if i.location_lat is not None else None,
            'distance': distance_label(contact.customer, i.location_lat, i.location_lng) if i.location_lat is not None else '',
            'at': i.created_at.isoformat(),
        })
    for log in DocumentCallLog.objects.filter(document__in=[d.pk for d in docs_qs if d.contact_id == contact.pk]).select_related('document', 'user'):
        history.append({
            'id': f'l{log.pk}', 'type': 'Call', 'date': log.timestamp.date().isoformat(), 'notes': log.message, 'user_name': _name(log.user),
            'followup_date': log.call_later_date.isoformat() if log.call_later_date else None, 'also_met': [], 'joint_with': [],
            'doc': {'type': log.document.type, 'label': DOC_LABELS.get(log.document.type, 'document'), 'number': log.document.doc_number},
            'via': 'Sales panel contact log', 'at': log.timestamp.isoformat()})
    for att in CallAttempt.objects.filter(assignment__contact=contact).select_related('by'):
        history.append({
            'id': f'a{att.pk}', 'type': 'Call', 'date': att.at.date().isoformat(), 'notes': f'Not answered ({att.reason or "—"})' + (f' — {att.note}' if att.note else ''),
            'user_name': _name(att.by), 'followup_date': att.call_again_date.isoformat() if att.call_again_date else None,
            'also_met': [], 'joint_with': [], 'doc': None, 'via': 'Outreach call log', 'at': att.at.isoformat()})
    history.sort(key=lambda h: (h['date'], h['at']), reverse=True)

    def value(d):
        return str(quotation_value_of(d) if d.type == 'quotation' else d.total_amount or 0)
    documents = sorted(mine, key=lambda d: (d.date or d.created_at.date()), reverse=True)
    open_statuses = {'Win', 'Lose', 'Completed', 'Regretted'}
    linkable = [d for d in docs_qs if d.type in ('enquiry', 'quotation', 'proforma', 'po') and (d.contact_id in (None, contact.pk))
                and d.order_status not in open_statuses]
    linkable.sort(key=lambda d: (d.date or d.created_at.date()), reverse=True)
    return {
        'history': history,
        'documents': [{'id': d.pk, 'type': d.type, 'label': DOC_LABELS.get(d.type, d.type), 'number': d.doc_number, 'date': d.date.isoformat() if d.date else None,
                       'status': d.order_status, 'value': value(d)} for d in documents],
        'linkable': [{'id': d.pk, 'type': d.type, 'label': DOC_LABELS.get(d.type, d.type), 'number': d.doc_number, 'date': d.date.isoformat() if d.date else None,
                      'value': value(d) if d.type == 'quotation' else None} for d in linkable[:25]],
    }


def company_transactions(viewer, customer):
    """"Check Transactions": every enquiry / quotation / proforma and payment recorded for a customer."""
    from ..models import PaymentCollection, SalesDocument
    from ..permissions import RoleRules
    from .printing import quotation_value_of
    docs = RoleRules.visible_sales_documents(viewer, SalesDocument.objects.filter(customer=customer)).select_related('contact').prefetch_related('items')
    out = {}
    for t in ('enquiry', 'quotation', 'proforma'):
        rows = sorted([d for d in docs if d.type == t], key=lambda d: (d.date or d.created_at.date()), reverse=True)
        out[t] = [{'number': d.doc_number, 'date': d.date.isoformat() if d.date else None, 'contact': d.contact.name if d.contact_id else '',
                   'status': d.order_status, 'value': str(quotation_value_of(d) if t == 'quotation' else d.total_amount or 0)} for d in rows]
    pays = PaymentCollection.objects.filter(customer=customer).select_related('contact').prefetch_related('receipts').order_by('-date')
    out['payments'] = [{'date': p.date.isoformat() if p.date else None, 'contact': p.contact.name if p.contact_id else '', 'amount': str(p.amount),
                        'received': str(sum(r.amount for r in p.receipts.all())), 'balance': str(p.balance())} for p in pays]
    return out
