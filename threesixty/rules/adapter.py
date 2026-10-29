"""Lets the 90 spec tests (anupam360_spec/tests/test_requirements.py) run
against the Django implementation.

`from .anupam_rules import *` supplies every rule the spec defines. Functions
for which the Django build has its own implementation are then *replaced* by a
thin wrapper that turns the spec's plain dicts into ORM objects (unsaved where
possible) and calls the real code, so a failing spec test points at a broken
REQ-ID in the Django build, not only in the pure rules.

Rules not overridden here are called directly by the services (see
docs/anupam360.md, traceability table) and are guarded by
tests/test_spec_sync.py, which fails if the copy under threesixty/rules ever
drifts from the spec pack.

Each phase adds its overrides to this file; `DJANGO_BACKED` lists them.
"""
from django.contrib.auth.models import User

from ..models import BranchNumbering, EmployeeProfile
from ..permissions import RoleRules
from ..services import nav as nav_service
from .anupam_rules import *  # noqa: F401,F403
from .anupam_rules import ROLES as _SPEC_ROLES

DJANGO_BACKED = set()


def _backed(fn):
    DJANGO_BACKED.add(fn.__name__)
    return fn


# --------------------------------------------------------------------------- roles & permissions
ROLES = tuple(label for _code, label in EmployeeProfile.ROLE_CHOICES)
DJANGO_BACKED.add('ROLES')
_CODE_BY_LABEL = {label: code for code, label in EmployeeProfile.ROLE_CHOICES}


def _user(u):
    """Spec user dict -> unsaved Django user carrying an EmployeeProfile."""
    user = User(username=str(u['id']), first_name=u.get('name', ''))
    EmployeeProfile(user=user, role=_CODE_BY_LABEL[u['role']])
    return user


@_backed
def is_admin(u): return RoleRules.is_admin(_user(u))
@_backed
def is_bm(u): return RoleRules.is_branch_manager(_user(u))
@_backed
def is_bs(u): return RoleRules.is_branch_staff(_user(u))
@_backed
def is_sm(u): return RoleRules.is_sales_manager(_user(u))
@_backed
def can_direct_edit_delete(u): return RoleRules.can_direct_edit_delete(_user(u))
@_backed
def can_edit_customer_direct(u): return RoleRules.can_edit_customer_direct(_user(u))
@_backed
def can_delete_customer_direct(u): return RoleRules.can_delete_customer_direct(_user(u))
@_backed
def can_direct_edit_delete_sales_doc(u): return RoleRules.can_direct_edit_delete_sales_doc(_user(u))
@_backed
def can_see_all_users_reports(u): return RoleRules.can_see_all_users_reports(_user(u))
@_backed
def uses_personal_dashboard(u): return RoleRules.uses_personal_dashboard(_user(u))
@_backed
def is_approver(u): return RoleRules.is_approver(_user(u))
@_backed
def needs_approval(u, action): return RoleRules.needs_approval(_user(u), action)
@_backed
def nav_visible(u): return nav_service.visible_nav(_user(u))
@_backed
def report_tabs_visible(u): return nav_service.visible_report_tabs(_user(u))


# --------------------------------------------------------------------------- numbering
@_backed
def numbering_cfg(doc_type, branch_cfg=None):
    c = (branch_cfg or {}).get(doc_type) or {}
    start = c.get('start')
    row = BranchNumbering(
        doc_type=doc_type, prefix=c.get('prefix') or '', suffix=c.get('suffix') or '',
        start_at=int(start) if start not in (None, '') else 1,
    )
    return row.effective_config()


# --------------------------------------------------------------------------- customers (phase 2)
import re as _re

from ..models import Contact, Customer, Task
from ..services import customers as _customer_service
from ..services import outreach as _outreach_service
from ..services import tasks as _task_service
from ..services.errors import ServiceError as _ServiceError


def _uid(value):
    """Spec ids are strings like 'u3'; the Django build uses integer pks."""
    return int(_re.sub(r'\D', '', str(value)) or 0)


@_backed
def search_customers(options, query):
    return _customer_service.rank_by_query(options, query, label=str)


@_backed
def company_select_label(c):
    return Customer(name=c.get('name') or '', plant=c.get('plant') or '', area=c.get('area') or '').select_label


@_backed
def geo_parse(text):
    try:
        return _customer_service.parse_pin(text)
    except _ServiceError:
        return None


def _contact(c):
    customer = Customer(name=c.get('companyName') or '')
    return Contact(customer=customer, name=c.get('name') or '', email=c.get('email') or '',
                   phone=c.get('phone') or '', job_title=c.get('jobTitle') or '')


@_backed
def selected_emails(contacts):
    return _customer_service.selected_emails([_contact(c) for c in contacts])


@_backed
def vcard(contacts):
    return _customer_service.vcard([_contact(c) for c in contacts])


# --------------------------------------------------------------------------- activity (phase 3)
@_backed
def monday_of(d):
    from datetime import date
    return _outreach_service.monday_of(date.fromisoformat(d)).isoformat()


def _task(t):
    return Task(title=t.get('title') or '', task_type=t.get('taskType') or '', created_by_id=_uid(t['createdById']) if t.get('createdById') else None)


def _acting(u):
    user = _user(u)
    user.pk = _uid(u['id'])
    return user


@_backed
def task_kind(t): return _task_service.kind_of(_task(t))
@_backed
def can_manage_task(u, t): return _task_service.can_manage(_acting(u), _task(t))
@_backed
def can_edit_task(u, t): return _task_service.can_edit(_acting(u), _task(t))
@_backed
def can_remove_task(u, t): return _task_service.can_remove(_acting(u), _task(t))


# --------------------------------------------------------------------------- sales documents (phase 4)
from decimal import Decimal as _Decimal

from ..services import totals as _totals


@_backed
def doc_total(items, packing=0, packing_tax=0, freight=0, freight_tax=0, other=0, other_tax=0, round_off=0,
              has_discount=True, has_tax=True):
    """Entry-form totals through the Decimal implementation the app saves with."""
    if not (has_discount and has_tax):
        from . import anupam_rules as _rules
        return _rules.doc_total(items, packing, packing_tax, freight, freight_tax, other, other_tax, round_off, has_discount, has_tax)
    rows = [{'qty': i.get('qty'), 'rate': i.get('rate'), 'discount': i.get('discount'), 'tax': i.get('tax')} for i in items]
    sub, total = _totals.compute_document_totals('quotation', rows, packing, packing_tax, freight, freight_tax, other, other_tax, round_off)
    return {'subTotal': float(sub), 'totalAmount': float(total)}


# --------------------------------------------------------------------------- printing (phase 5)
from ..models import SalesDocument as _SalesDocument
from ..models import SalesDocumentItem as _SalesDocumentItem
from ..services import printing as _printing


def _unsaved_document(doc):
    document = _SalesDocument(
        show_discount_in_pdf=bool(doc.get('showDiscountInPdf')), packing_charges=_Decimal(str(doc.get('packingCharges') or 0)),
        packing_tax=_Decimal(str(doc.get('packingTax') or 0)), freight_charges=_Decimal(str(doc.get('freightCharges') or 0)),
        freight_tax=_Decimal(str(doc.get('freightTax') or 0)), other_charges=_Decimal(str(doc.get('otherCharges') or 0)),
        other_charges_tax=_Decimal(str(doc.get('otherChargesTax') or 0)), round_off=_Decimal(str(doc.get('roundOff') or 0)),
        total_amount=None if doc.get('totalAmount') is None else _Decimal(str(doc['totalAmount'])),
        quotation_value=_Decimal(str(doc.get('quotationValue') or 0)))
    items = [_SalesDocumentItem(
        item_name=i.get('itemName') or '', make=i.get('make') or '', qty=_Decimal(str(i.get('qty') or 0)),
        rate=_Decimal(str(i.get('rate') or 0)), discount=_Decimal(str(i.get('discount') or 0)),
        tax=_Decimal(str(i.get('tax') or 0)), value=None if i.get('value') is None else _Decimal(str(i['value'])))
        for i in doc.get('items') or []]
    return document, items


@_backed
def quotation_print_totals(doc):
    document, items = _unsaved_document(doc)
    t = _printing.print_totals(document, items)
    return {'lines': [{'sr': l['sr'], 'name': l['name'], 'qty': float(l['qty']), 'rate': float(l['rate']),
                       'amount': float(l['amount']), 'tax': float(l['tax'])} for l in t['lines']],
            'subTotal': float(t['sub_total']), 'taxTotal': float(t['tax_total']), 'total': float(t['total'])}


@_backed
def amount_in_words(amount):
    return _printing.amount_in_words(_Decimal(str(amount or 0)))


@_backed
def quotation_value_of(doc):
    document, items = _unsaved_document(doc)
    if doc.get('totalAmount') is None:
        document.total_amount = _Decimal('0')
    for item in items:
        if item.value is None:
            item.value = item.qty * item.rate * (1 - item.discount / 100) * (1 + item.tax / 100)
    return float(_printing.quotation_value_of(document, items))
