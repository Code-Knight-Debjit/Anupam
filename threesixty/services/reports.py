"""Reports and dashboards (REQUIREMENTS §12, §19, §20; REQ-RPT-01..03, REQ-ROLE-05).

Filters on every report: date range, branch, and user (the user picker is only
for Admin / Branch Manager). Admin and Branch Manager see all data; Branch Staff
and Sales Managers see only their own, and a Sales Manager has no Sales
Performance or Customer Activity report. Every number comes with the list
behind it (`numbers[key].items`) so the UI can drill down.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from ..models import (
    CallAssignment, CallAttempt, Contact, Customer, DocumentCallLog, EmployeeProfile, Interaction, PaymentContactLog,
    PaymentCollection, SalesDocument, Task,
)
from ..permissions import RoleRules
from ..rules import anupam_rules as rules
from . import attendance as att
from . import documents as doc_service
from . import payments as payment_service
from .errors import ServiceError
from .nav import visible_report_tabs
from .printing import money, quotation_value_of

REPORTS = {
    'sales-performance': 'Sales Performance', 'customer-activity': 'Customer Activity', 'not-contacted': 'Not Contacted',
    'user-performance': 'User Performance', 'sales-reports': 'Sales Reports', 'customer-reports': 'Customer Reports',
    'payment-collection': 'Payment Collection', 'interaction-log': 'Interaction Log',
}
ITEM_CAP = 500
CALL_TYPES = (Interaction.TYPE_CALL, Interaction.TYPE_COLD_CALL)


# --------------------------------------------------------------------------- filters & scope
@dataclass
class Filters:
    start: date
    end: date
    branch_id: int | None
    user_id: int | None            # None = everyone this viewer may see


def sees_everyone(user) -> bool:
    return RoleRules.is_admin(user) or RoleRules.is_branch_manager(user)


def _date(text, name):
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        raise ServiceError(400, f'{name} must be a date like 2026-10-01.')


def parse_filters(user, params) -> Filters:
    today = timezone.localdate()
    start = _date(params['from'], 'from') if params.get('from') else today.replace(day=1)
    end = _date(params['to'], 'to') if params.get('to') else today
    if end < start:
        raise ServiceError(400, 'The end date is before the start date.')
    branch_id = int(params['branch_id']) if str(params.get('branch_id') or '').isdigit() else None
    user_id = int(params['user_id']) if str(params.get('user_id') or '').isdigit() else None
    if not sees_everyone(user):
        if user_id not in (None, user.pk):
            raise ServiceError(403, 'You can only see your own data.')
        user_id = user.pk                      # "own data"
    return Filters(start, end, branch_id, user_id)


def require_report(user, name):
    if name not in REPORTS:
        raise ServiceError(404, 'Unknown report.')
    if REPORTS[name] not in visible_report_tabs(user):
        raise ServiceError(403, 'Your role cannot open this report.')      # REQ-RPT-01


def _branch_user_ids(branch_id):
    return set(EmployeeProfile.objects.filter(branches__id=branch_id).values_list('user_id', flat=True))


def _name(user):
    return (user.get_full_name() or user.username) if user else '—'


def _numbers(buckets):
    """{key: list of items} -> {key: {count, items, truncated}}."""
    out = {}
    for key, items in buckets.items():
        out[key] = {'count': len(items), 'items': items[:ITEM_CAP], 'truncated': len(items) > ITEM_CAP}
    return out


def _doc_item(d):
    return {'kind': 'document', 'id': d.pk, 'label': f'{d.get_type_display()} {d.doc_number}', 'customer': d.customer.select_label,
            'date': d.date.isoformat(), 'status': d.order_status, 'value': str(money(quotation_value_of(d)))}


def _customer_item(c, **extra):
    return {'kind': 'customer', 'id': c.pk, 'label': c.select_label, **extra}


def _interaction_item(i):
    return {'kind': 'interaction', 'id': i.pk, 'label': f'{i.type} — {i.contact.name}', 'customer': i.contact.customer.select_label,
            'date': i.date.isoformat(), 'by': _name(i.created_by), 'notes': i.notes}


# --------------------------------------------------------------------------- data access
def scoped_documents(user, f: Filters, doc_types=None):
    qs = SalesDocument.objects.filter(date__range=(f.start, f.end)).select_related('customer', 'branch', 'created_by') \
        .prefetch_related('items')
    if doc_types:
        qs = qs.filter(type__in=doc_types)
    if f.branch_id:
        qs = qs.filter(branch_id=f.branch_id)
    if f.user_id:
        qs = qs.filter(created_by_id=f.user_id)
    return qs.order_by('-date', '-id')


def scoped_customers(user, f: Filters):
    """Customers the viewer may see; for 'own data' viewers or a chosen user, those they created or are assigned."""
    qs = RoleRules.visible_customers(user, Customer.objects.all())
    if f.user_id:
        qs = qs.filter(Q(created_by_id=f.user_id) | Q(assigned_to__id=f.user_id))
    if f.branch_id:
        ids = _branch_user_ids(f.branch_id)
        qs = qs.filter(Q(created_by_id__in=ids) | Q(assigned_to__id__in=ids))
    return qs.distinct()


def scoped_interactions(f: Filters, include_joint=True):
    qs = Interaction.objects.filter(is_copy=False, date__range=(f.start, f.end)).select_related('contact__customer', 'created_by')
    if f.user_id:
        cond = Q(created_by_id=f.user_id)
        if include_joint:
            cond |= Q(joint_with__id=f.user_id)
        qs = qs.filter(cond)
    elif f.branch_id:
        qs = qs.filter(created_by_id__in=_branch_user_ids(f.branch_id))
    return qs.distinct()


# --------------------------------------------------------------------------- 1. Sales Performance
def sales_performance(user, f: Filters):
    docs = list(scoped_documents(user, f, ['enquiry', 'quotation']))
    enquiries = [d for d in docs if d.type == 'enquiry']
    quotations = [d for d in docs if d.type == 'quotation']
    won = [q for q in quotations if q.order_status == 'Win']
    lost = [q for q in quotations if q.order_status == 'Lose']
    pending = [q for q in quotations if q.order_status in ('Pending', '')]
    value = lambda ds: sum((quotation_value_of(d) for d in ds), Decimal('0'))
    conversion = rules.sales_conversion([None] * len(enquiries), [{'orderStatus': q.order_status, 'totalAmount': float(quotation_value_of(q))} for q in quotations])

    def table(key, label_of):
        groups = defaultdict(lambda: {'enquiries': 0, 'quotations': 0, 'won': 0, 'quotation_value': Decimal('0'), 'won_value': Decimal('0')})
        for d in docs:
            g = groups[label_of(d)]
            if d.type == 'enquiry':
                g['enquiries'] += 1
            else:
                g['quotations'] += 1
                g['quotation_value'] += quotation_value_of(d)
                if d.order_status == 'Win':
                    g['won'] += 1
                    g['won_value'] += quotation_value_of(d)
        return [{key: name, **{k: (str(money(v)) if isinstance(v, Decimal) else v) for k, v in g.items()}} for name, g in sorted(groups.items())]

    customers = lambda ds: _unique_customers(ds)
    return {
        'summary': {
            'enquiries': len(enquiries), 'quotations': len(quotations), 'orders_won': len(won),
            'enquiry_to_quotation_pct': conversion['enq_to_quo_pct'], 'quotation_to_win_pct': conversion['quo_to_win_pct'],
            'quotation_value': str(money(value(quotations))), 'won_value': str(money(value(won))),
            'lost_value': str(money(value(lost))), 'pending_value': str(money(value(pending))),
            'order_value': str(money(sum((q.order_value or Decimal('0') for q in won), Decimal('0')))),
        },
        'by_branch': table('branch', lambda d: d.branch.name),
        'by_person': table('person', lambda d: _name(d.created_by)),
        'numbers': _numbers({'enquiries': customers(enquiries), 'quotations': customers(quotations), 'won': customers(won),
                             'lost': customers(lost), 'pending': customers(pending)}),
    }


def _unique_customers(docs):
    seen, out = {}, []
    for d in docs:
        if d.customer_id not in seen:
            seen[d.customer_id] = {'kind': 'customer', 'id': d.customer_id, 'label': d.customer.select_label, 'documents': []}
            out.append(seen[d.customer_id])
        seen[d.customer_id]['documents'].append(f'{d.get_type_display()} {d.doc_number}')
    return out


# --------------------------------------------------------------------------- 2. Customer Activity
def customer_activity(user, f: Filters):
    won = [d for d in scoped_documents(user, f, ['quotation']) if d.order_status == 'Win']
    totals = defaultdict(lambda: [None, Decimal('0'), 0])
    for d in won:
        row = totals[d.customer_id]
        row[0] = d.customer
        row[1] += d.order_value if d.order_value is not None else quotation_value_of(d)
        row[2] += 1
    top = sorted(totals.values(), key=lambda r: -r[1])[:10]
    new_customers = list(scoped_customers(user, f).filter(created_at__date__range=(f.start, f.end)).order_by('-created_at'))
    return {
        'top_customers': [{'customer_id': c.pk, 'customer': c.select_label, 'won_value': str(money(v)), 'orders': n} for c, v, n in top],
        'new_customers': [_customer_item(c, date=c.created_at.date().isoformat(), by=_name(c.created_by)) for c in new_customers[:ITEM_CAP]],
        'numbers': _numbers({'new_customers': [_customer_item(c) for c in new_customers]}),
    }


# --------------------------------------------------------------------------- 3. Not Contacted
def not_contacted(user, f: Filters, days=30, mode='both', state='', area=''):
    """Customers with no call and/or no visit in the last N days (spec rule); never-contacted count,
    longest gap first. 'Own data' viewers only see customers they created or are assigned to."""
    if mode not in ('both', 'neither', 'call', 'visit', 'either'):
        raise ServiceError(400, 'mode must be neither, call, visit or either.')
    mode = 'both' if mode == 'neither' else mode
    try:
        days = int(days)
    except (TypeError, ValueError):
        raise ServiceError(400, 'days must be a whole number.')
    qs = RoleRules.visible_customers(user, Customer.objects.all())
    if not sees_everyone(user):
        qs = qs.filter(Q(created_by=user) | Q(assigned_to=user))              # "only their related customers"
    if f.user_id:
        qs = qs.filter(Q(created_by_id=f.user_id) | Q(assigned_to__id=f.user_id))
    if f.branch_id:
        ids = _branch_user_ids(f.branch_id)
        qs = qs.filter(Q(created_by_id__in=ids) | Q(assigned_to__id__in=ids))
    if state:
        qs = qs.filter(state__iexact=state)
    if area:
        qs = qs.filter(area__iexact=area)
    qs = qs.distinct().annotate(
        _call=Max('contacts__interactions__date', filter=Q(contacts__interactions__type__in=CALL_TYPES)),
        _visit=Max('contacts__interactions__date', filter=Q(contacts__interactions__type=Interaction.TYPE_VISIT)))
    customers = list(qs)
    today = timezone.localdate()
    hits = rules.not_contacted(
        [{'id': c.pk, 'contacts': [{'interactions': [i for i in ({'type': 'Call', 'date': c._call.isoformat()} if c._call else None,
                                                                {'type': 'Visit', 'date': c._visit.isoformat()} if c._visit else None) if i]}]}
         for c in customers], days, mode, today.isoformat())
    by_id = {c.pk: c for c in customers}
    rows = [{'customer_id': h['id'], 'customer': by_id[h['id']].select_label, 'state': by_id[h['id']].state, 'area': by_id[h['id']].area,
             'days_since_call': h['daysSinceCall'], 'days_since_visit': h['daysSinceVisit'],
             'last_call': by_id[h['id']]._call.isoformat() if by_id[h['id']]._call else None,
             'last_visit': by_id[h['id']]._visit.isoformat() if by_id[h['id']]._visit else None} for h in hits]
    return {'days': days, 'mode': mode, 'results': rows, 'numbers': _numbers({'customers': [_customer_item(by_id[r['customer_id']]) for r in rows]})}


# --------------------------------------------------------------------------- 4. User Performance
def user_performance(user, f: Filters):
    profiles = att.team_profiles(user) if sees_everyone(user) else att.team_profiles(user).filter(user=user)
    if sees_everyone(user):
        profiles = EmployeeProfile.objects.filter(user__is_active=True, is_active_employee=True).select_related('user')
        if f.branch_id:
            profiles = profiles.filter(branches__id=f.branch_id)
    if f.user_id:
        profiles = profiles.filter(user_id=f.user_id)
    profiles = list(profiles.distinct().order_by('user__first_name', 'user__username'))
    interactions = list(Interaction.objects.filter(is_copy=False, date__range=(f.start, f.end)).select_related('contact__customer', 'created_by')
                        .prefetch_related('joint_with'))
    sales_logs = list(DocumentCallLog.objects.filter(timestamp__date__range=(f.start, f.end)).select_related('document__customer'))
    pay_logs = list(PaymentContactLog.objects.filter(timestamp__date__range=(f.start, f.end)).select_related('payment__customer'))
    attendance = att.compute_range(profiles, f.start, min(f.end, timezone.localdate()), timezone.localdate()) if f.start <= timezone.localdate() else {}
    rows = []
    for p in profiles:
        uid = p.user_id
        mine = [i for i in interactions if i.created_by_id == uid or any(j.pk == uid for j in i.joint_with.all())]
        calls = [i for i in mine if i.type in CALL_TYPES]
        visits = [i for i in mine if i.type == Interaction.TYPE_VISIT]
        appts = [i for i in mine if i.type == Interaction.TYPE_APPOINTMENT]
        not_visited = list(interaction_not_visited(uid, f))
        follow_ups = [l for l in sales_logs if l.user_id == uid] + [l for l in pay_logs if l.user_id == uid]
        rows.append({
            'user_id': uid, 'name': _name(p.user), 'role': p.role,
            'calls': len(calls), 'visits': len(visits), 'appointments': len(appts),
            'appointments_visited': len(appts) - len(not_visited), 'appointments_not_visited': len(not_visited),
            'visit_pct': rules.visit_percent_of_appointments(len(appts), len(appts) - len(not_visited)),
            'follow_up_calls': len(follow_ups),
            'customers_called': len({i.contact.customer_id for i in calls}), 'customers_visited': len({i.contact.customer_id for i in visits}),
            'attendance': att.tally(attendance.get(uid, [])),
            'numbers': _numbers({
                'calls': [_interaction_item(i) for i in calls], 'visits': [_interaction_item(i) for i in visits],
                'appointments': [_interaction_item(i) for i in appts], 'appointments_not_visited': [_interaction_item(i) for i in not_visited],
                'follow_up_calls': [{'kind': 'log', 'label': l.message[:80], 'date': l.timestamp.date().isoformat()} for l in follow_ups],
                'customers_called': [{'kind': 'customer', 'id': c.pk, 'label': c.select_label} for c in {i.contact.customer for i in calls}],
                'customers_visited': [{'kind': 'customer', 'id': c.pk, 'label': c.select_label} for c in {i.contact.customer for i in visits}],
            }),
        })
    return {'results': rows}


def interaction_not_visited(uid, f: Filters):
    from . import interactions
    from django.contrib.auth import get_user_model
    return interactions.appointments_not_visited(get_user_model().objects.get(pk=uid), f.start, f.end).select_related('contact__customer', 'created_by')


# --------------------------------------------------------------------------- 5. Sales Reports / Customer Reports
def sales_reports(user, f: Filters, doc_type='', status=''):
    qs = scoped_documents(user, f, [doc_type] if doc_type else None)
    if status:
        qs = qs.filter(order_status=status)
    docs = list(qs)
    rows = [{'id': d.pk, 'number': d.doc_number, 'date': d.date.isoformat(), 'type': d.get_type_display(), 'branch': d.branch.name,
             'customer': d.customer.select_label, 'status': d.order_status, 'value': str(money(quotation_value_of(d))), 'by': _name(d.created_by)}
            for d in docs]
    return {'results': rows, 'total_value': str(money(sum((quotation_value_of(d) for d in docs), Decimal('0')))),
            'numbers': _numbers({'documents': [_doc_item(d) for d in docs]})}


def customer_reports(user, f: Filters, state='', industry='', potential=''):
    qs = scoped_customers(user, f)
    for field, value in (('state', state), ('industry', industry), ('potential', potential)):
        if value:
            qs = qs.filter(**{f'{field}__iexact': value})
    qs = qs.annotate(_contacts=Count('contacts', distinct=True),
                     _call=Max('contacts__interactions__date', filter=Q(contacts__interactions__type__in=CALL_TYPES)),
                     _visit=Max('contacts__interactions__date', filter=Q(contacts__interactions__type=Interaction.TYPE_VISIT))).order_by('name')
    customers = list(qs)
    rows = [{'id': c.pk, 'customer': c.select_label, 'city': c.city, 'state': c.state, 'industry': c.industry, 'potential': c.potential,
             'contacts': c._contacts, 'last_call': c._call.isoformat() if c._call else None,
             'last_visit': c._visit.isoformat() if c._visit else None, 'added': c.created_at.date().isoformat()} for c in customers]
    return {'results': rows, 'numbers': _numbers({'customers': [_customer_item(c) for c in customers]})}


# --------------------------------------------------------------------------- 6. Payment Collection
def payment_collection(user, f: Filters):
    qs = payment_service.visible_payments(user).filter(date__range=(f.start, f.end)).select_related('customer', 'branch', 'created_by') \
        .prefetch_related('receipts')
    if f.branch_id:
        qs = qs.filter(branch_id=f.branch_id)
    if f.user_id:
        qs = qs.filter(created_by_id=f.user_id)
    if not sees_everyone(user):
        qs = qs.filter(created_by=user)                                         # "own data"
    payments = list(qs)
    ageing = {b: {'count': 0, 'balance': Decimal('0')} for b in payment_service.AGE_BUCKETS}
    by_customer = defaultdict(lambda: {'invoiced': Decimal('0'), 'received': Decimal('0'), 'balance': Decimal('0')})
    buckets = defaultdict(list)
    for p in payments:
        row = by_customer[p.customer.select_label]
        row['invoiced'] += p.amount
        row['received'] += p.received()
        row['balance'] += p.balance()
        if p.balance() > 0:
            bucket = payment_service.age_bucket(p)
            ageing[bucket]['count'] += 1
            ageing[bucket]['balance'] += p.balance()
            buckets[bucket].append({'kind': 'payment', 'id': p.pk, 'label': p.customer.select_label, 'date': p.date.isoformat(),
                                    'balance': str(p.balance())})
    return {
        'ageing': [{'bucket': b, 'count': v['count'], 'balance': str(money(v['balance']))} for b, v in ageing.items()],
        'total_outstanding': str(money(sum((v['balance'] for v in ageing.values()), Decimal('0')))),
        'by_customer': [{'customer': name, **{k: str(money(v)) for k, v in row.items()}} for name, row in sorted(by_customer.items())],
        'numbers': _numbers(dict(buckets)),
    }


# --------------------------------------------------------------------------- 7. Interaction Log
def interaction_log(user, f: Filters, kind=''):
    if kind and kind not in rules.INTERACTION_TYPES:
        raise ServiceError(400, 'type must be one of: ' + ', '.join(rules.INTERACTION_TYPES))
    tiles = {}
    items = {}
    inter = list(scoped_interactions(f, include_joint=False))
    for t, types in (('Call', CALL_TYPES), ('Visit', (Interaction.TYPE_VISIT,)), ('Appointment', (Interaction.TYPE_APPOINTMENT,))):
        items[t] = [_interaction_item(i) for i in inter if i.type in types]
    logs = DocumentCallLog.objects.filter(timestamp__date__range=(f.start, f.end)).select_related('document__customer', 'user')
    paylogs = PaymentContactLog.objects.filter(timestamp__date__range=(f.start, f.end)).select_related('payment__customer', 'user')
    outreach = CallAttempt.objects.filter(at__date__range=(f.start, f.end)).select_related('assignment__customer', 'by')
    called = CallAssignment.objects.filter(status='Called', called_at__date__range=(f.start, f.end)).select_related('customer', 'called_by')
    if f.user_id:
        logs, paylogs = logs.filter(user_id=f.user_id), paylogs.filter(user_id=f.user_id)
        outreach, called = outreach.filter(by_id=f.user_id), called.filter(called_by_id=f.user_id)
    elif f.branch_id:
        ids = _branch_user_ids(f.branch_id)
        logs, paylogs = logs.filter(user_id__in=ids), paylogs.filter(user_id__in=ids)
        outreach, called = outreach.filter(by_id__in=ids), called.filter(called_by_id__in=ids)
    visible_docs = doc_service.visible_documents(user)
    logs = logs.filter(document__in=visible_docs)
    paylogs = paylogs.filter(payment__in=payment_service.visible_payments(user))
    items['Sales Log'] = [{'kind': 'log', 'label': f'{l.document.get_type_display()} {l.document.doc_number} — {l.message[:60]}',
                           'customer': l.document.customer.select_label, 'date': l.timestamp.date().isoformat(), 'by': _name(l.user)} for l in logs]
    items['Payment Log'] = [{'kind': 'log', 'label': l.message[:80], 'customer': l.payment.customer.select_label,
                             'date': l.timestamp.date().isoformat(), 'by': _name(l.user)} for l in paylogs]
    items['Outreach'] = [{'kind': 'log', 'label': f'Called — {c.customer.select_label}', 'customer': c.customer.select_label,
                          'date': c.called_at.date().isoformat(), 'by': _name(c.called_by)} for c in called] + \
                        [{'kind': 'log', 'label': f'Not reached ({a.reason}) — {a.assignment.customer.select_label}',
                          'customer': a.assignment.customer.select_label, 'date': a.at.date().isoformat(), 'by': _name(a.by)} for a in outreach]
    for t in rules.INTERACTION_TYPES:
        tiles[t] = len(items[t])
    shown = items[kind] if kind else [i for t in rules.INTERACTION_TYPES for i in items[t]]
    shown = sorted(shown, key=lambda r: r['date'], reverse=True)
    return {'tiles': tiles, 'results': shown[:ITEM_CAP], 'truncated': len(shown) > ITEM_CAP}


# --------------------------------------------------------------------------- dispatch & export tables
def run(name, user, params):
    require_report(user, name)
    f = parse_filters(user, params)
    get = params.get
    if name == 'sales-performance':
        return sales_performance(user, f)
    if name == 'customer-activity':
        return customer_activity(user, f)
    if name == 'not-contacted':
        return not_contacted(user, f, get('days', 30), get('mode', 'both'), get('state', ''), get('area', ''))
    if name == 'user-performance':
        return user_performance(user, f)
    if name == 'sales-reports':
        return sales_reports(user, f, get('type', ''), get('status', ''))
    if name == 'customer-reports':
        return customer_reports(user, f, get('state', ''), get('industry', ''), get('potential', ''))
    if name == 'payment-collection':
        return payment_collection(user, f)
    return interaction_log(user, f, get('interaction_type', ''))


def export_table(name, result):
    """(title, headers, rows) for Excel / PDF export of a report's main table."""
    title = REPORTS[name]
    if name == 'sales-performance':
        s = result['summary']
        rows = [[k.replace('_', ' ').title(), v] for k, v in s.items()]
        rows += [['', '']] + [[f'Branch: {r["branch"]}', f'{r["quotations"]} quotations, {r["won"]} won, {r["won_value"]}'] for r in result['by_branch']]
        rows += [[f'Person: {r["person"]}', f'{r["quotations"]} quotations, {r["won"]} won, {r["won_value"]}'] for r in result['by_person']]
        return title, ['Measure', 'Value'], rows
    if name == 'customer-activity':
        return title, ['Customer', 'Orders won', 'Won value'], [[r['customer'], r['orders'], r['won_value']] for r in result['top_customers']]
    if name == 'not-contacted':
        return title, ['Customer', 'State', 'Area', 'Days since call', 'Days since visit', 'Last call', 'Last visit'], \
            [[r['customer'], r['state'], r['area'], 'never' if r['days_since_call'] is None else r['days_since_call'],
              'never' if r['days_since_visit'] is None else r['days_since_visit'], r['last_call'] or '', r['last_visit'] or ''] for r in result['results']]
    if name == 'user-performance':
        return title, ['Name', 'Calls', 'Visits', 'Appointments', 'Visited %', 'Follow-up calls', 'Customers called', 'Customers visited', 'Present', 'Late', 'Absent'], \
            [[r['name'], r['calls'], r['visits'], r['appointments'], r['visit_pct'], r['follow_up_calls'], r['customers_called'],
              r['customers_visited'], r['attendance']['present'], r['attendance']['late'], r['attendance']['absent']] for r in result['results']]
    if name == 'sales-reports':
        return title, ['Number', 'Date', 'Type', 'Branch', 'Customer', 'Status', 'Value', 'By'], \
            [[r['number'], r['date'], r['type'], r['branch'], r['customer'], r['status'], r['value'], r['by']] for r in result['results']]
    if name == 'customer-reports':
        return title, ['Customer', 'City', 'State', 'Industry', 'Potential', 'Contacts', 'Last call', 'Last visit', 'Added'], \
            [[r['customer'], r['city'], r['state'], r['industry'], r['potential'], r['contacts'], r['last_call'] or '', r['last_visit'] or '', r['added']]
             for r in result['results']]
    if name == 'payment-collection':
        rows = [[f'Ageing {a["bucket"]}', a['count'], a['balance']] for a in result['ageing']] + [['', '', '']]
        rows += [[r['customer'], r['invoiced'], f'received {r["received"]}, balance {r["balance"]}'] for r in result['by_customer']]
        return title, ['Customer / bucket', 'Count / invoiced', 'Balance'], rows
    return title, ['Date', 'Type', 'Customer', 'By', 'Detail'], [[r['date'], r['label'].split(' — ')[0], r.get('customer', ''), r.get('by', ''), r['label']]
                                                                for r in result['results']]


# --------------------------------------------------------------------------- dashboards
def personal_dashboard(user, f: Filters):
    """The numbers of a non-Admin dashboard, for the period (§19)."""
    today = timezone.localdate()
    mine = Interaction.objects.filter(is_copy=False, date__range=(f.start, f.end)).filter(Q(created_by=user) | Q(joint_with=user)).distinct()
    appts = mine.filter(type=Interaction.TYPE_APPOINTMENT).count()
    visits = mine.filter(type=Interaction.TYPE_VISIT).count()
    from . import interactions
    not_visited = interactions.appointments_not_visited(user, f.start, f.end).count()
    tasks = Task.objects.filter(Q(assigned_to=user) | Q(joint_with=user)).distinct().exclude(status='Completed')
    docs = SalesDocument.objects.filter(created_by=user).prefetch_related('items')
    pending = lambda t: [d for d in docs if d.type == t and (d.order_status or 'Pending') == 'Pending']
    my_payments = list(PaymentCollection.objects.filter(created_by=user).prefetch_related('receipts'))
    profile = user.threesixty_profile
    month_start, month_end = att.month_bounds(None)
    days = att.compute_range([profile], month_start, month_end)[user.pk]
    today_record = next((d['record'] for d in days if d['date'] == today), None)
    return {
        'period': {'from': f.start.isoformat(), 'to': f.end.isoformat()},
        'tasks': {'pending': tasks.count(), 'due_today': tasks.filter(due_date=today).count(), 'overdue': tasks.filter(due_date__lt=today).count()},
        'outreach_pending': CallAssignment.objects.filter(assigned_to=user).exclude(status='Called').count(),
        'activity': {'calls_done': mine.filter(type__in=CALL_TYPES).count(), 'appointments_taken': appts, 'visits_made': visits,
                     'appointments_not_visited': not_visited, 'visit_pct': rules.visit_percent_of_appointments(appts, appts - not_visited)},
        'pending': {'enquiries': len(pending('enquiry')), 'quotations': len(pending('quotation')), 'proformas': len(pending('proforma')),
                    'challans': len([d for d in docs if d.type == 'dc' and doc_service.dc_is_pending(d)]),
                    'pos': len([d for d in docs if d.type == 'po' and d.order_status != 'Completed'])},
        'payments': {'pending': len([p for p in my_payments if p.balance() > 0]),
                     'completed': len([p for p in my_payments if p.amount > 0 and p.balance() == 0])},
        'attendance': {'today': {'check_in': att.hm(today_record.check_in) if today_record else '', 'check_out': att.hm(today_record.check_out) if today_record else ''},
                       'month': att.tally(days)},
        'calendar': task_calendar(user, month_start, month_end),
    }


def task_calendar(user, start, end):
    by_day = defaultdict(list)
    for t in Task.objects.filter(Q(assigned_to=user) | Q(joint_with=user), due_date__range=(start, end)).distinct().order_by('due_date'):
        by_day[t.due_date.isoformat()].append({'id': t.pk, 'title': t.title, 'status': t.status, 'kind': t.task_type})
    return dict(by_day)


def admin_dashboard(user, f: Filters, activity_limit=10):
    if not RoleRules.is_admin(user):
        raise ServiceError(403, 'The company dashboard is for the Admin only.')
    from ..models import ApprovalRequest
    today = timezone.localdate()
    docs = list(SalesDocument.objects.exclude(type='dc').exclude(type='po').filter(order_status__in=['Pending', '']).values_list('type', flat=True))
    dcs = [d for d in SalesDocument.objects.filter(type='dc').prefetch_related('items') if doc_service.dc_is_pending(d)]
    pos = SalesDocument.objects.filter(type='po').exclude(order_status='Completed').count()
    payments = [p for p in PaymentCollection.objects.select_related('customer').prefetch_related('receipts') if p.balance() > 0]
    payments.sort(key=lambda p: -p.balance())
    pending = ApprovalRequest.objects.filter(status='pending').filter(Q(customer__isnull=False) | Q(contact__isnull=False) | Q(document__isnull=False))
    profiles = list(EmployeeProfile.objects.filter(user__is_active=True, is_active_employee=True).select_related('user'))
    employees = []
    for p in profiles:
        uid = p.user_id
        last = [d for d in (
            Interaction.objects.filter(created_by_id=uid).aggregate(m=Max('created_at'))['m'],
            SalesDocument.objects.filter(created_by_id=uid).aggregate(m=Max('created_at'))['m'],
            Customer.objects.filter(created_by_id=uid).aggregate(m=Max('created_at'))['m']) if d]
        employees.append({
            'user_id': uid, 'name': _name(p.user), 'role': p.role,
            'customers_added': Customer.objects.filter(created_by_id=uid, created_at__date__range=(f.start, f.end)).count(),
            'contacts_added': Contact.objects.filter(customer__created_by_id=uid, customer__created_at__date__range=(f.start, f.end)).count(),
            'documents_raised': SalesDocument.objects.filter(created_by_id=uid, date__range=(f.start, f.end)).count(),
            'last_activity': max(last).isoformat() if last else None})
    att_today = att.compute_range(profiles, today, today)
    strip = defaultdict(int)
    for p in profiles:
        strip[att_today[p.user_id][0]['code'] or 'not_marked'] += 1
    feed = []
    for d in SalesDocument.objects.select_related('customer', 'created_by').order_by('-created_at')[:activity_limit]:
        feed.append({'at': d.created_at.isoformat(), 'text': f'{_name(d.created_by)} raised {d.get_type_display()} {d.doc_number} for {d.customer.name}'})
    for i in Interaction.objects.filter(is_copy=False).select_related('contact__customer', 'created_by').order_by('-created_at')[:activity_limit]:
        feed.append({'at': i.created_at.isoformat(), 'text': f'{_name(i.created_by)} logged a {i.type.lower()} with {i.contact.name} ({i.contact.customer.name})'})
    feed.sort(key=lambda r: r['at'], reverse=True)
    month_start, month_end = att.month_bounds(None)
    calendar = defaultdict(list)
    for t in Task.objects.filter(due_date__range=(month_start, month_end)).order_by('due_date')[:500]:
        calendar[t.due_date.isoformat()].append({'id': t.pk, 'title': t.title, 'status': t.status})
    return {
        'period': {'from': f.start.isoformat(), 'to': f.end.isoformat()},
        'approvals': {'pending': pending.count(), 'latest': [{'id': a.pk, 'type': a.type, 'label': a.target_label, 'by': _name(a.requested_by)}
                                                             for a in pending.select_related('requested_by')[:5]]},
        'pipeline': {'open_enquiries': docs.count('enquiry'), 'open_quotations': docs.count('quotation'), 'open_proformas': docs.count('proforma'),
                     'pending_pos': pos, 'challans_pending_invoicing': len(dcs)},
        'payments': {'outstanding_total': str(money(sum((p.balance() for p in payments), Decimal('0')))),
                     'top': [{'id': p.pk, 'customer': p.customer.select_label, 'balance': str(p.balance())} for p in payments[:6]]},
        'employees': employees, 'activity': feed[:activity_limit], 'attendance_today': dict(strip), 'calendar': dict(calendar),
    }


def employee_drill(user, f: Filters, user_id, what):
    """The list behind a number in the Admin dashboard's employee table."""
    if not RoleRules.is_admin(user):
        raise ServiceError(403, 'The company dashboard is for the Admin only.')
    if what == 'customers':
        qs = Customer.objects.filter(created_by_id=user_id, created_at__date__range=(f.start, f.end))
        return [_customer_item(c, date=c.created_at.date().isoformat()) for c in qs]
    if what == 'contacts':
        qs = Contact.objects.filter(customer__created_by_id=user_id, customer__created_at__date__range=(f.start, f.end)).select_related('customer')
        return [{'kind': 'contact', 'id': c.pk, 'label': f'{c.name} — {c.customer.select_label}'} for c in qs]
    if what == 'documents':
        return [_doc_item(d) for d in SalesDocument.objects.filter(created_by_id=user_id, date__range=(f.start, f.end)).select_related('customer').prefetch_related('items')]
    raise ServiceError(400, 'what must be customers, contacts or documents.')
