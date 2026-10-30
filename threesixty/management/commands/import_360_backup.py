"""One-time importer for the original Anupam 360 app's localStorage backup
export (`BACKUP_ITEMS`, contact_management.html ~L6553-6673) into this
Django app's relational models.

Usage:
    python manage.py import_360_backup path/to/backup.json [--dry-run]

The backup file is the JSON produced by the original app's "Download
Backup" button: `{app: 'Anupam 360', version: 2, exportedAt, exportedBy,
...all BACKUP_ITEMS keys}`.

Deliberately out of scope (see docs/360/AUDIT.md and the master prompt):
`stockProducts`/`suppliers`/`stockBills`/`stockTransactions` (the unrelated
`stock_ledger` app) and `printWatermark`/`docTheme`/`appLogo`/
`appLogoAspect`/`sidebarLogo` (printed-document branding, excluded from this
migration).

Idempotent by `legacy_id`: re-running after a partial/failed run will skip
every row already imported and only create what's missing. It will NOT
update rows that were already imported — this is a one-time migration tool
intended to be run, inspected, and (if something looks wrong) re-run against
a corrected backup file after truncating the affected tables by hand, not a
continuous sync.

Every field mapping below was verified against the original source lines
cited in each `_import_*` method and in the model docstrings — nothing here
is guessed. The two spots requiring a deliberate, documented judgement call
are flagged inline with `NOTE:`.
"""
import json

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime

from threesixty.services import contacts as contact_service
from threesixty.services.accounts import limit_stock_access
from threesixty.models import (
    ApprovalRequest, AttendanceRecord, Branch, BranchNumbering, Contact, CallAssignment,
    CallAttempt, Customer, DocumentCallLog, EmployeeProfile, Holiday, Interaction, LeaveRequest,
    LookupItem, Notification, PaymentCollection, PaymentReceipt, SalesDocument, SalesDocumentItem,
    SalesPerson, SiteSetting, SupplyLogEntry, Task,
)

ROLE_MAP = {
    'Admin': EmployeeProfile.ADMIN,
    'Branch Manager': EmployeeProfile.BRANCH_MANAGER,
    'Branch Staff': EmployeeProfile.BRANCH_STAFF,
    'Sales Manager': EmployeeProfile.SALES_MANAGER,
}

LOOKUP_KIND_MAP = {
    'jobTitles': LookupItem.KIND_JOB_TITLE,
    'sources': LookupItem.KIND_SOURCE,
    'industries': LookupItem.KIND_INDUSTRY,
    'languages': LookupItem.KIND_LANGUAGE,
    'brands': LookupItem.KIND_BRAND,
    'products': LookupItem.KIND_PRODUCT,
    'categories': LookupItem.KIND_CATEGORY,
    'units': LookupItem.KIND_UNIT,
    'taxRates': LookupItem.KIND_TAX_RATE,
    'paymentTerms': LookupItem.KIND_PAYMENT_TERM,
    'transportList': LookupItem.KIND_TRANSPORT,
    'courierList': LookupItem.KIND_COURIER,
}

# NUMBERING_TYPES the original Branch page lets you configure (contact_management.html
# ~L3586-3593) vs. the 5 doc types Django's BranchNumbering actually tracks — 'po' never had
# its own legacy numbering config (it fell through to a hardcoded 'PO' prefix in the sales-doc
# type config instead), and the legacy 'sales'/'purchase' numbering slots belong to the
# unrelated stock_ledger app, so they're intentionally dropped here.
BRANCH_NUMBERING_LEGACY_KEYS = ('enquiry', 'quotation', 'dc', 'proforma')


class DryRunRollback(Exception):
    pass


def _date(value):
    if not value:
        return None
    return parse_date(value) if isinstance(value, str) else value


def _datetime(value):
    if not value:
        return None
    return parse_datetime(value) if isinstance(value, str) else value


class Command(BaseCommand):
    help = "Import a one-time JSON backup export from the original Anupam 360 app."

    def add_arguments(self, parser):
        parser.add_argument('backup_path')
        parser.add_argument('--dry-run', action='store_true', help='Roll back everything at the end; report what would happen.')

    def handle(self, *args, **options):
        path = options['backup_path']
        try:
            with open(path, encoding='utf-8') as fh:
                self.data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f'Could not read backup file: {exc}')
        if self.data.get('app') != 'Anupam 360':
            self.stdout.write(self.style.WARNING(
                f"File doesn't look like an Anupam 360 backup (app={self.data.get('app')!r}) — continuing anyway."
            ))

        self.counts = {}
        self.unresolved = []  # human-readable notes about anything we couldn't resolve

        # legacy id/name -> Django instance maps, built up as each section imports
        self.branch_by_legacy = {}
        self.branch_by_name = {}
        self.user_by_emp_legacy = {}
        self.user_by_name = {}
        self.lookup_by_kind_name = {}
        self.salesperson_by_legacy = {}
        self.customer_by_legacy = {}
        self.contact_by_legacy = {}
        self.salesdoc_by_legacy = {}
        # (interaction, legacy docId) pairs — interactions import before sales documents exist
        self.pending_interaction_docs = []

        try:
            with transaction.atomic():
                self._import_branches()
                self._import_employees()
                self._import_lookups()
                self._import_sales_persons()
                self._import_branch_numbering()
                self._import_customers()
                self._import_sales_documents()
                self._import_payments()
                self._import_tasks()
                self._import_notifications()
                self._import_approvals()
                self._import_call_assignments()
                self._import_attendance()
                self._import_leave_requests()
                self._import_holidays()
                self._import_attendance_start()
                if options['dry_run']:
                    raise DryRunRollback()
        except DryRunRollback:
            self.stdout.write(self.style.WARNING('--dry-run: all changes rolled back.'))

        self.stdout.write(self.style.SUCCESS('Import summary:'))
        for key, (created, skipped) in sorted(self.counts.items()):
            self.stdout.write(f'  {key}: {created} created, {skipped} already present')
        if self.unresolved:
            self.stdout.write(self.style.WARNING(f'{len(self.unresolved)} unresolved reference(s):'))
            for note in self.unresolved[:200]:
                self.stdout.write(f'  - {note}')
            if len(self.unresolved) > 200:
                self.stdout.write(f'  ... and {len(self.unresolved) - 200} more')

    def _bump(self, key, created):
        c, s = self.counts.get(key, (0, 0))
        self.counts[key] = (c + int(created), s + int(not created))

    # ---------- Branches (+ numbering) ----------
    # Branches are created bare (`{id, name}`, ~L7687) and letterhead details are a separate,
    # later save (`branchDetailSaveBtn` handler, ~L7902-7931) — `companyName`/`address`/
    # `phone`/`email`/`gstNumber` map onto the Django letterhead_* fields; `mobile`,
    # `udyamNumber`, bank details, logos, watermark, accentColor, docFormat are all
    # PDF/print-branding-only (excluded phase) and dropped. Branches also have no
    # active/inactive flag in the original (hard-deleted only) — `is_active` is left at its
    # Django default of True.
    def _import_branches(self):
        for b in self.data.get('branches', []):
            existing = Branch.objects.filter(legacy_id=b['id']).first()
            if existing:
                self.branch_by_legacy[b['id']] = existing
                self.branch_by_name[existing.name] = existing
                self._bump('branches', False)
                continue
            # Branch names are unique: adopt a same-named branch (e.g. one made by
            # `seed_threesixty`) rather than crash, filling in only blank letterhead fields.
            same_name = Branch.objects.filter(name=b.get('name', ''), legacy_id__isnull=True).first()
            if same_name:
                for attr, key in (('letterhead_name', 'companyName'), ('letterhead_address', 'address'),
                                  ('letterhead_gstin', 'gstNumber'), ('letterhead_phone', 'phone'),
                                  ('letterhead_email', 'email')):
                    if not getattr(same_name, attr):
                        setattr(same_name, attr, b.get(key, ''))
                same_name.legacy_id = b['id']
                same_name.save()
                self.branch_by_legacy[b['id']] = same_name
                self.branch_by_name[same_name.name] = same_name
                self._bump('branches', False)
                continue
            branch = Branch.objects.create(
                name=b.get('name', ''),
                letterhead_name=b.get('companyName', ''),
                letterhead_address=b.get('address', ''),
                letterhead_gstin=b.get('gstNumber', ''),
                letterhead_phone=b.get('phone', ''),
                letterhead_email=b.get('email', ''),
                legacy_id=b['id'],
            )
            self.branch_by_legacy[b['id']] = branch
            self.branch_by_name[branch.name] = branch
            self._bump('branches', True)

    def _import_branch_numbering(self):
        branches = self.data.get('branches', [])
        doc_counters = self.data.get('docCounters', {})
        for b in branches:
            branch = self.branch_by_legacy.get(b['id'])
            if not branch:
                continue
            numbering = b.get('numbering') or {}
            for doc_type in BRANCH_NUMBERING_LEGACY_KEYS:
                cfg = numbering.get(doc_type) or {}
                counter_key = f'{doc_type}::{branch.name}'
                last_issued = doc_counters.get(counter_key, 0)
                _, created = BranchNumbering.objects.get_or_create(
                    branch=branch, doc_type=doc_type,
                    defaults={
                        'prefix': cfg.get('prefix', ''), 'suffix': cfg.get('suffix', ''),
                        'start_at': cfg.get('start', 1) or 1, 'last_issued': last_issued,
                    },
                )
                self._bump('branch_numbering', created)
            # 'po' never had a legacy prefix/suffix/start config, but a counter may exist.
            po_last_issued = doc_counters.get(f'po::{branch.name}', 0)
            if po_last_issued:
                _, created = BranchNumbering.objects.get_or_create(
                    branch=branch, doc_type='po', defaults={'last_issued': po_last_issued},
                )
                self._bump('branch_numbering', created)

    # ---------- Employees -> User + EmployeeProfile ----------
    # Shape confirmed at the Users-page save handler (~L7440-7531): plaintext `password`
    # is hashed via `User.objects.create_user`, never stored as-is.
    def _import_employees(self):
        for e in self.data.get('employees', []):
            existing = EmployeeProfile.objects.filter(legacy_id=e['id']).first()
            if existing:
                self.user_by_emp_legacy[e['id']] = existing.user
                self.user_by_name[e.get('name', '')] = existing.user
                self._bump('employees', False)
                continue
            username = e.get('userId') or f"legacy-{e['id']}"
            if User.objects.filter(username=username).exists():
                username = f"{username}-{e['id'][:8]}"
            role = ROLE_MAP.get(e.get('role'))
            if role is None:
                self.unresolved.append(f"employee {e.get('name')!r}: unknown role {e.get('role')!r}, defaulted to Branch Staff")
                role = EmployeeProfile.BRANCH_STAFF
            is_active = e.get('active', True) is not False
            # No password in the backup → create_user(password=None) stores an
            # unusable one; an Admin sets a real one afterwards via the Users page.
            user = User.objects.create_user(
                username=username, password=e.get('password') or None,
                first_name=e.get('name', ''), email=e.get('email', ''), is_staff=True, is_active=is_active,
            )
            limit_stock_access(user)
            profile = EmployeeProfile.objects.create(
                user=user, role=role,
                phone=e.get('phone', ''), emp_code=e.get('empCode') or None,
                aadhaar_number=e.get('aadhaar', ''), pan_number=e.get('pan', ''),
                date_of_birth=_date(e.get('dob')), date_of_joining=_date(e.get('doj')),
                work_start=e.get('workStart') or '09:30', work_end=e.get('workEnd') or '18:30',
                weekly_off=e.get('weeklyOff', '0'), is_active_employee=is_active,
                legacy_id=e['id'],
            )
            branch_ids = [self.branch_by_legacy[bid].id for bid in e.get('branches', []) if bid in self.branch_by_legacy]
            if branch_ids:
                profile.branches.set(branch_ids)
            self.user_by_emp_legacy[e['id']] = user
            self.user_by_name[e.get('name', '')] = user
            self._bump('employees', True)

    # ---------- Lookup lists ----------
    # All 12 kinds share the {id, name} shape confirmed at the default-seed lines (~L4307-4366);
    # `extra`/`sort_order` have no legacy equivalent and are left at their model defaults.
    def _import_lookups(self):
        for legacy_key, kind in LOOKUP_KIND_MAP.items():
            for order, item in enumerate(self.data.get(legacy_key, [])):
                existing = LookupItem.objects.filter(legacy_id=item['id']).first()
                if existing:
                    self.lookup_by_kind_name[(kind, existing.name)] = existing
                    self._bump('lookups', False)
                    continue
                name = item.get('name', '')
                by_name = LookupItem.objects.filter(kind=kind, name=name).first()
                if by_name:
                    # Name already seeded (e.g. by seed_threesixty) without a legacy_id — adopt it.
                    if not by_name.legacy_id:
                        by_name.legacy_id = item['id']
                        by_name.save(update_fields=['legacy_id'])
                    self.lookup_by_kind_name[(kind, name)] = by_name
                    self._bump('lookups', False)
                    continue
                obj = LookupItem.objects.create(kind=kind, name=name, sort_order=order, legacy_id=item['id'])
                self.lookup_by_kind_name[(kind, name)] = obj
                self._bump('lookups', True)

    def _lookup_ids(self, kind, names, context=''):
        ids = []
        for name in names or []:
            obj = self.lookup_by_kind_name.get((kind, name))
            if obj:
                ids.append(obj.id)
            else:
                self.unresolved.append(f'{context}: no {kind} lookup named {name!r}')
        return ids

    # ---------- Sales persons ----------
    def _import_sales_persons(self):
        for sp in self.data.get('salesPersons', []):
            existing = SalesPerson.objects.filter(legacy_id=sp['id']).first()
            if existing:
                self.salesperson_by_legacy[sp['id']] = existing
                self._bump('sales_persons', False)
                continue
            obj = SalesPerson.objects.create(name=sp.get('name', ''), phone=sp.get('phone', ''), legacy_id=sp['id'])
            self.salesperson_by_legacy[sp['id']] = obj
            self._bump('sales_persons', True)

    # ---------- Customers + Contacts + Interactions ----------
    # Shape confirmed at the customer-save handler (~L6270-6329): `preferredLanguages`/
    # `interestedBrands`/`interestedProducts`/`assignedTo` all store **names**, not ids
    # (confirmed via the `.brand-check`/`.language-check`/`.assigned-check` checkbox `value`
    # attributes at ~L5014-5035, which are built from `l.name`/`e.name`, not `l.id`/`e.id`).
    # `plantGeo`/`hoGeo` are `{lat, lng, by, at, acc?}` objects (`geoFormRead`, ~L4694-4702);
    # `by`/`at`/`acc` have no Django column and are dropped (lat/lng only).
    def _import_customers(self):
        for c in self.data.get('companies', []):
            existing = Customer.objects.filter(legacy_id=c['id']).first()
            if existing:
                self.customer_by_legacy[c['id']] = existing
                for ct in existing.contacts.all():
                    if ct.legacy_id:
                        self.contact_by_legacy[ct.legacy_id] = ct
                self._bump('customers', False)
                continue
            plant_geo, ho_geo = c.get('plantGeo') or {}, c.get('hoGeo') or {}
            customer = Customer.objects.create(
                name=c.get('name', ''), plant=c.get('plant', ''), address=c.get('address', ''),
                area=c.get('area', ''), city=c.get('city', ''), state=c.get('state', ''),
                pincode=c.get('pincode', ''), website=c.get('website', ''), gst_number=c.get('gstNumber', ''),
                plant_geo_lat=plant_geo.get('lat'), plant_geo_lng=plant_geo.get('lng'),
                ho_geo_lat=ho_geo.get('lat'), ho_geo_lng=ho_geo.get('lng'),
                ho_name=c.get('hoName', ''), ho_address=c.get('hoAddress', ''), ho_city=c.get('hoCity', ''),
                ho_state=c.get('hoState', ''), ho_pincode=c.get('hoPincode', ''), ho_phone=c.get('hoPhone', ''),
                industry=c.get('industry', ''), source=c.get('source', ''), potential=c.get('potential', ''),
                transport_preference=c.get('transportPreference', ''), courier_preference=c.get('courierPreference', ''),
                created_by=self.user_by_emp_legacy.get(c.get('createdById')),
                legacy_id=c['id'],
            )
            if c.get('createdAt'):
                customer.created_at = _datetime(c['createdAt']) or customer.created_at
                customer.save(update_fields=['created_at'])
            ctx = f"customer {c.get('name')!r}"
            customer.preferred_languages.set(self._lookup_ids(LookupItem.KIND_LANGUAGE, c.get('preferredLanguages'), ctx))
            customer.interested_brands.set(self._lookup_ids(LookupItem.KIND_BRAND, c.get('interestedBrands'), ctx))
            customer.interested_products.set(self._lookup_ids(LookupItem.KIND_PRODUCT, c.get('interestedProducts'), ctx))
            assigned_ids = []
            for name in c.get('assignedTo') or []:
                user = self.user_by_name.get(name)
                if user:
                    assigned_ids.append(user.id)
                else:
                    self.unresolved.append(f'{ctx}: assignedTo references unknown employee name {name!r}')
            customer.assigned_to.set(assigned_ids)
            self.customer_by_legacy[c['id']] = customer

            for ct in c.get('contacts', []):
                contact = Contact.objects.create(
                    customer=customer, name=ct.get('name', ''), job_title=ct.get('jobTitle', ''),
                    phone=ct.get('phone', ''), phone2=ct.get('phone2', ''), email=ct.get('email', ''),
                    dnd=bool(ct.get('dnd')), legacy_id=ct['id'],
                )
                self.contact_by_legacy[ct['id']] = contact
                for i in ct.get('interactions', []):
                    self._import_interaction(contact, i)
            # Contact-level access ({person name: [contact ids]}, REQ-CUS-02): no entry = all contacts.
            for name, legacy_contact_ids in (c.get('contactAccess') or {}).items():
                user = self.user_by_name.get(name)
                chosen = [self.contact_by_legacy[x].pk for x in legacy_contact_ids or [] if x in self.contact_by_legacy]
                if user and chosen:
                    contact_service.assign_customer(customer, user, chosen)
            self._bump('customers', True)

    def _import_interaction(self, contact, i):
        if Interaction.objects.filter(legacy_id=i['id']).exists():
            self._bump('interactions', False)
            return
        loc = i.get('location') or {}
        interaction = Interaction.objects.create(
            contact=contact, type=i.get('type', 'Call'), date=_date(i.get('date')) or _date(i.get('createdAt')),
            notes=i.get('notes', ''), location_lat=loc.get('lat'), location_lng=loc.get('lng'),
            created_by=self.user_by_emp_legacy.get(i.get('userId')),
            followup_date=_date(i.get('followupDate')), visit_group=i.get('visitGroup', ''),
            is_copy=bool(i.get('isCopy')), met_with_name=i.get('metWithName', ''),
            legacy_id=i['id'],
        )
        if i.get('docId'):
            self.pending_interaction_docs.append((interaction, i['docId']))
        if i.get('createdAt'):
            interaction.created_at = _datetime(i['createdAt']) or interaction.created_at
            interaction.save(update_fields=['created_at'])
        also_met_ids = [self.contact_by_legacy[o['id']].id for o in i.get('alsoMet', []) if o.get('id') in self.contact_by_legacy]
        interaction.also_met.set(also_met_ids)
        joint_ids = [self.user_by_name[j['name']].id for j in i.get('jointWith', []) if j.get('name') in self.user_by_name]
        interaction.joint_with.set(joint_ids)
        self._bump('interactions', True)

    # ---------- Sales documents + items + supply log + call log ----------
    # Base shape confirmed at the sales-doc save handler (~L11380-11508); item shape at
    # COLUMN_META/itemCols (~L3639-3710); `branch`/`salesPersonId` resolve to Branch-by-name /
    # SalesPerson-by-legacy-id exactly as the original's own selects do.
    def _import_sales_documents(self):
        pending_refs = []  # (document, legacy_ref_id) — resolved in a second pass
        for d in self.data.get('salesDocs', []):
            existing = SalesDocument.objects.filter(legacy_id=d['id']).first()
            if existing:
                self.salesdoc_by_legacy[d['id']] = existing
                self._bump('sales_documents', False)
                continue
            branch = self.branch_by_name.get(d.get('branch'))
            customer = self.customer_by_legacy.get(d.get('customerId'))
            if not customer:
                self.unresolved.append(f"sales document {d.get('docNumber')!r}: unknown customerId {d.get('customerId')!r} — skipped")
                continue
            if not branch:
                self.unresolved.append(f"sales document {d.get('docNumber')!r}: unknown branch {d.get('branch')!r} — skipped")
                continue
            doc = SalesDocument.objects.create(
                type=d.get('type'), doc_number=d.get('docNumber', ''), branch=branch, customer=customer,
                contact=self.contact_by_legacy.get(d.get('contactId')),
                date=_date(d.get('date')), remarks=d.get('remarks', ''),
                source=d.get('source', ''), order_status=d.get('orderStatus', ''),
                vehicle=d.get('vehicle', ''), transport=d.get('transport', ''),
                show_discount_in_pdf=bool(d.get('showDiscountInPdf')),
                packing_charges=d.get('packingCharges', 0) or 0, packing_tax=d.get('packingTax', 0) or 0,
                freight_charges=d.get('freightCharges', 0) or 0, freight_tax=d.get('freightTax', 0) or 0,
                other_charges=d.get('otherCharges', 0) or 0, other_charges_tax=d.get('otherChargesTax', 0) or 0,
                round_off=d.get('roundOff', 0) or 0, sub_total=d.get('subTotal', 0) or 0,
                total_amount=d.get('totalAmount', 0) or 0, quotation_value=d.get('quotationValue'),
                sales_person=self.salesperson_by_legacy.get(d.get('salesPersonId')),
                valid_till=_date(d.get('validTill')), ref_no=d.get('refNo', ''), ref_date=_date(d.get('refDate')),
                payment_terms=d.get('paymentTerms', ''), terms=d.get('terms') or [],
                created_by=self.user_by_emp_legacy.get(d.get('createdById')),
                legacy_id=d['id'],
            )
            if d.get('createdAt'):
                doc.created_at = _datetime(d['createdAt']) or doc.created_at
                doc.save(update_fields=['created_at'])
            for position, item in enumerate(d.get('items', [])):
                si = SalesDocumentItem.objects.create(
                    document=doc, position=position, item_name=item.get('itemName', ''), make=item.get('make', ''),
                    qty=item.get('qty', 0) or 0, unit=item.get('unit', ''), rate=item.get('rate', 0) or 0,
                    discount=item.get('discount', 0) or 0, tax=item.get('tax', 0) or 0,
                    amount=item.get('amount', 0) or 0, value=item.get('value', 0) or 0,
                )
                for log in item.get('supplyLog', []):
                    if SupplyLogEntry.objects.filter(legacy_id=log['id']).exists():
                        continue
                    SupplyLogEntry.objects.create(
                        item=si, date=_date(log.get('date')), qty_supplied=log.get('qtySupplied', 0) or 0,
                        remarks=log.get('remarks', ''), recorded_by=self.user_by_emp_legacy.get(log.get('recordedById')),
                        legacy_id=log['id'],
                    )
            for log in d.get('callLog', []):
                if DocumentCallLog.objects.filter(legacy_id=log['id']).exists():
                    continue
                entry = DocumentCallLog.objects.create(
                    document=doc, message=log.get('message', ''), user=self.user_by_emp_legacy.get(log.get('userId')),
                    legacy_id=log['id'],
                )
                if log.get('timestamp'):
                    entry.timestamp = _datetime(log['timestamp']) or entry.timestamp
                    entry.save(update_fields=['timestamp'])
            self.salesdoc_by_legacy[d['id']] = doc
            if d.get('refId'):
                pending_refs.append((doc, d['refId']))
            self._bump('sales_documents', True)
        for doc, ref_legacy_id in pending_refs:
            ref_doc = self.salesdoc_by_legacy.get(ref_legacy_id)
            if ref_doc:
                doc.reference = ref_doc
                doc.save(update_fields=['reference'])
            else:
                self.unresolved.append(f'sales document {doc.doc_number!r}: reference document {ref_legacy_id!r} not found')
        for interaction, doc_legacy_id in self.pending_interaction_docs:
            linked = self.salesdoc_by_legacy.get(doc_legacy_id)
            if linked:
                interaction.linked_doc = linked
                interaction.save(update_fields=['linked_doc'])
            else:
                self.unresolved.append(f'interaction {interaction.legacy_id!r}: linked document {doc_legacy_id!r} not found')

    # ---------- Payments + receipts ----------
    def _import_payments(self):
        for p in self.data.get('payments', []):
            existing = PaymentCollection.objects.filter(legacy_id=p['id']).first()
            if existing:
                self._bump('payments', False)
                continue
            branch = self.branch_by_name.get(p.get('branch'))
            customer = self.customer_by_legacy.get(p.get('customerId'))
            if not customer or not branch:
                self.unresolved.append(f"payment for {p.get('customerName')!r}: unknown customer/branch — skipped")
                continue
            payment = PaymentCollection.objects.create(
                branch=branch, customer=customer, contact=self.contact_by_legacy.get(p.get('contactId')),
                amount=p.get('amount', 0) or 0, date=_date(p.get('date')), remarks=p.get('remarks', ''),
                created_by=self.user_by_emp_legacy.get(p.get('createdById')), legacy_id=p['id'],
            )
            if p.get('createdAt'):
                payment.created_at = _datetime(p['createdAt']) or payment.created_at
                payment.save(update_fields=['created_at'])
            for r in p.get('receivedLog', []):
                if PaymentReceipt.objects.filter(legacy_id=r['id']).exists():
                    continue
                receipt = PaymentReceipt.objects.create(
                    payment=payment, amount=r.get('amount', 0) or 0, date=_date(r.get('date')),
                    mode=r.get('mode') or PaymentReceipt.MODE_CASH, remarks=r.get('remarks', ''),
                    recorded_by=self.user_by_emp_legacy.get(r.get('recordedById')), legacy_id=r['id'],
                )
                if r.get('createdAt'):
                    receipt.created_at = _datetime(r['createdAt']) or receipt.created_at
                    receipt.save(update_fields=['created_at'])
            self._bump('payments', True)

    # ---------- Tasks ----------
    # NOTE: the original uses the literal status string 'Done' for a completed task
    # (confirmed throughout, e.g. ~L13507-13510), not 'Completed' as Django's
    # `Task.STATUS_COMPLETED` choice value reads — 'Done' is normalized to 'Completed' here;
    # everything else about the task is imported unchanged.
    def _import_tasks(self):
        for t in self.data.get('tasks', []):
            if Task.objects.filter(legacy_id=t['id']).exists():
                self._bump('tasks', False)
                continue
            assigned_to = self.user_by_emp_legacy.get(t.get('assignedToId'))
            if not assigned_to:
                self.unresolved.append(f"task {t.get('title')!r}: unknown assignedToId {t.get('assignedToId')!r} — skipped")
                continue
            status = Task.STATUS_COMPLETED if t.get('status') == 'Done' else Task.STATUS_OPEN
            task = Task.objects.create(
                title=t.get('title', ''), description=t.get('description', ''), assigned_to=assigned_to,
                priority=t.get('priority') or Task.PRIORITY_MEDIUM, status=status, task_type=t.get('taskType', ''),
                due_date=_date(t.get('dueDate')), related_customer=self.customer_by_legacy.get(t.get('relatedCustomerId')),
                related_contact=self.contact_by_legacy.get(t.get('relatedContactId')),
                related_document=self.salesdoc_by_legacy.get(t.get('relatedDocId')),
                created_by=self.user_by_emp_legacy.get(t.get('createdById')),
                completed_at=_datetime(t.get('completedAt')), legacy_id=t['id'],
            )
            if t.get('createdAt'):
                task.created_at = _datetime(t['createdAt']) or task.created_at
                task.save(update_fields=['created_at'])
            joint_ids = [self.user_by_name[n].id for n in t.get('jointNames', []) if n in self.user_by_name]
            task.joint_with.set(joint_ids)
            self._bump('tasks', True)

    # ---------- Notifications ----------
    def _import_notifications(self):
        for n in self.data.get('notifications', []):
            if Notification.objects.filter(legacy_id=n['id']).exists():
                self._bump('notifications', False)
                continue
            user = self.user_by_emp_legacy.get(n.get('userId'))
            if not user:
                self.unresolved.append(f"notification {n.get('text', '')[:40]!r}: unknown userId — skipped")
                continue
            notif = Notification.objects.create(
                user=user, type=n.get('type', ''), text=n.get('text', ''), read=bool(n.get('read')),
                related_customer=self.customer_by_legacy.get(n.get('relatedCustomerId')), legacy_id=n['id'],
            )
            if n.get('createdAt'):
                notif.created_at = _datetime(n['createdAt']) or notif.created_at
                notif.save(update_fields=['created_at'])
            self._bump('notifications', True)

    # ---------- Approvals ----------
    # NOTE: the original deletes an approval request the instant it's approved/rejected
    # (~L8072-8131), so every request still present in a backup is, by construction, still
    # pending — all are imported with status='pending'. `proposed_data` is translated from
    # the legacy camelCase/name-based shape into the Django snake_case/id-based shape the
    # approve-handler (`_apply_approval`, api/views_tasks.py) actually expects — a raw copy
    # of the legacy blob would silently no-op on approval. Only scalar+M2M customer fields and
    # scalar document fields are translated; a pending edit that also changed a customer's
    # contacts will lose that part of the change (contacts have no field in `proposed_data`
    # in the Django model either) — flagged here, not solved, since it's a rare case for a
    # one-time migration.
    def _import_approvals(self):
        for a in self.data.get('approvals', []):
            if ApprovalRequest.objects.filter(legacy_id=a['id']).exists():
                self._bump('approvals', False)
                continue
            customer = self.customer_by_legacy.get(a.get('companyId'))
            document = self.salesdoc_by_legacy.get(a.get('docId'))
            if (a.get('companyId') and not customer) or (a.get('docId') and not document):
                self.unresolved.append(f"approval {a['id']!r}: target company/document not found — skipped")
                continue
            proposed = None
            if a.get('type') == ApprovalRequest.TYPE_EDIT and a.get('proposedData'):
                proposed = (
                    self._translate_customer_proposed(a['proposedData']) if customer
                    else self._translate_document_proposed(a['proposedData'])
                )
            approval = ApprovalRequest.objects.create(
                type=a.get('type'), note=a.get('note', ''), customer=customer, document=document,
                proposed_data=proposed, requested_by=self.user_by_emp_legacy.get(a.get('requestedById')),
                status=ApprovalRequest.STATUS_PENDING, legacy_id=a['id'],
            )
            if a.get('requestedAt'):
                approval.requested_at = _datetime(a['requestedAt']) or approval.requested_at
                approval.save(update_fields=['requested_at'])
            self._bump('approvals', True)

    def _translate_customer_proposed(self, legacy):
        simple = {
            'name': 'name', 'plant': 'plant', 'address': 'address', 'area': 'area', 'website': 'website',
            'gstNumber': 'gst_number', 'city': 'city', 'state': 'state', 'pincode': 'pincode',
            'industry': 'industry', 'source': 'source', 'potential': 'potential',
            'transportPreference': 'transport_preference', 'courierPreference': 'courier_preference',
            'hoName': 'ho_name', 'hoAddress': 'ho_address', 'hoCity': 'ho_city', 'hoState': 'ho_state',
            'hoPincode': 'ho_pincode', 'hoPhone': 'ho_phone',
        }
        out = {dst: legacy[src] for src, dst in simple.items() if src in legacy}
        plant_geo = legacy.get('plantGeo') or {}
        if plant_geo:
            out['plant_geo_lat'], out['plant_geo_lng'] = plant_geo.get('lat'), plant_geo.get('lng')
        ho_geo = legacy.get('hoGeo') or {}
        if ho_geo:
            out['ho_geo_lat'], out['ho_geo_lng'] = ho_geo.get('lat'), ho_geo.get('lng')
        if 'preferredLanguages' in legacy:
            out['preferred_language_ids'] = self._lookup_ids(LookupItem.KIND_LANGUAGE, legacy['preferredLanguages'], 'pending approval')
        if 'interestedBrands' in legacy:
            out['interested_brand_ids'] = self._lookup_ids(LookupItem.KIND_BRAND, legacy['interestedBrands'], 'pending approval')
        if 'interestedProducts' in legacy:
            out['interested_product_ids'] = self._lookup_ids(LookupItem.KIND_PRODUCT, legacy['interestedProducts'], 'pending approval')
        if 'assignedTo' in legacy:
            out['assigned_to_ids'] = [self.user_by_name[n].id for n in legacy['assignedTo'] if n in self.user_by_name]
        return out

    def _translate_document_proposed(self, legacy):
        simple = {
            'contactId': 'contact_id', 'date': 'date', 'remarks': 'remarks', 'source': 'source',
            'orderStatus': 'order_status', 'vehicle': 'vehicle', 'transport': 'transport',
            'showDiscountInPdf': 'show_discount_in_pdf', 'packingCharges': 'packing_charges',
            'packingTax': 'packing_tax', 'freightCharges': 'freight_charges', 'freightTax': 'freight_tax',
            'otherCharges': 'other_charges', 'otherChargesTax': 'other_charges_tax', 'roundOff': 'round_off',
            'quotationValue': 'quotation_value', 'validTill': 'valid_till', 'refNo': 'ref_no',
            'refDate': 'ref_date', 'paymentTerms': 'payment_terms', 'terms': 'terms',
        }
        out = {dst: legacy[src] for src, dst in simple.items() if src in legacy}
        if 'salesPersonId' in legacy:
            sp = self.salesperson_by_legacy.get(legacy['salesPersonId'])
            out['sales_person_id'] = sp.id if sp else None
        if 'contactId' in legacy:
            contact = self.contact_by_legacy.get(legacy['contactId'])
            out['contact_id'] = contact.id if contact else None
        if 'items' in legacy:
            out['items'] = [
                {
                    'item_name': it.get('itemName', ''), 'make': it.get('make', ''), 'qty': it.get('qty', 0),
                    'unit': it.get('unit', ''), 'rate': it.get('rate', 0), 'discount': it.get('discount', 0),
                    'tax': it.get('tax', 0),
                }
                for it in legacy['items']
            ]
        return out

    # ---------- Call assignments + attempts ----------
    def _import_call_assignments(self):
        for a in self.data.get('callAssignments', []):
            if CallAssignment.objects.filter(legacy_id=a['id']).exists():
                self._bump('call_assignments', False)
                continue
            customer = self.customer_by_legacy.get(a.get('customerId'))
            assigned_to = self.user_by_emp_legacy.get(a.get('assignedToId'))
            if not customer or not assigned_to:
                self.unresolved.append(f"call assignment {a['id']!r}: unknown customer/assignedTo — skipped")
                continue
            assignment = CallAssignment.objects.create(
                customer=customer, contact=self.contact_by_legacy.get(a.get('contactId')),
                week_of=_date(a.get('weekOf')), status=a.get('status') or CallAssignment.STATUS_PENDING,
                remarks=a.get('remarks', ''), called_at=_datetime(a.get('calledAt')),
                called_by=self.user_by_emp_legacy.get(a.get('calledById')), assigned_to=assigned_to,
                assigned_by=self.user_by_emp_legacy.get(a.get('assignedById')), legacy_id=a['id'],
            )
            if a.get('assignedAt'):
                assignment.assigned_at = _datetime(a['assignedAt']) or assignment.assigned_at
                assignment.save(update_fields=['assigned_at'])
            for attempt in a.get('attempts', []):
                if CallAttempt.objects.filter(legacy_id=attempt['id']).exists():
                    continue
                ca = CallAttempt.objects.create(
                    assignment=assignment, reason=attempt.get('reason', ''), note=attempt.get('note', ''),
                    by=self.user_by_emp_legacy.get(attempt.get('byId')), call_again_date=_date(attempt.get('callAgainDate')),
                    legacy_id=attempt['id'],
                )
                if attempt.get('at'):
                    ca.at = _datetime(attempt['at']) or ca.at
                    ca.save(update_fields=['at'])
            self._bump('call_assignments', True)

    # ---------- Attendance ----------
    def _import_attendance(self):
        for rec in self.data.get('attendance', []):
            if AttendanceRecord.objects.filter(legacy_id=rec['id']).exists():
                self._bump('attendance', False)
                continue
            user = self.user_by_emp_legacy.get(rec.get('userId'))
            if not user:
                self.unresolved.append(f"attendance record {rec['id']!r}: unknown userId — skipped")
                continue
            in_loc, out_loc = rec.get('inLoc') or {}, rec.get('outLoc') or {}
            AttendanceRecord.objects.create(
                user=user, date=_date(rec.get('date')),
                check_in=rec.get('checkIn') or None, check_out=rec.get('checkOut') or None,
                in_loc_lat=in_loc.get('lat'), in_loc_lng=in_loc.get('lng'), in_loc_accuracy_m=in_loc.get('acc'),
                out_loc_lat=out_loc.get('lat'), out_loc_lng=out_loc.get('lng'), out_loc_accuracy_m=out_loc.get('acc'),
                status=rec.get('status', ''), note=rec.get('note', ''),
                marked_by=self.user_by_emp_legacy.get(rec.get('markedById')), legacy_id=rec['id'],
            )
            self._bump('attendance', True)

    # ---------- Leave requests ----------
    def _import_leave_requests(self):
        for l in self.data.get('leaveRequests', []):
            if LeaveRequest.objects.filter(legacy_id=l['id']).exists():
                self._bump('leave_requests', False)
                continue
            user = self.user_by_emp_legacy.get(l.get('userId'))
            if not user:
                self.unresolved.append(f"leave request {l['id']!r}: unknown userId — skipped")
                continue
            leave = LeaveRequest.objects.create(
                user=user, date_from=_date(l.get('from')), date_to=_date(l.get('to')), reason=l.get('reason', ''),
                status=l.get('status') or LeaveRequest.STATUS_PENDING,
                decided_by=self.user_by_emp_legacy.get(l.get('decidedById')), decided_at=_datetime(l.get('decidedAt')),
                decision_note=l.get('decisionNote', ''), legacy_id=l['id'],
            )
            if l.get('requestedAt'):
                leave.requested_at = _datetime(l['requestedAt']) or leave.requested_at
                leave.save(update_fields=['requested_at'])
            self._bump('leave_requests', True)

    # ---------- Holidays ----------
    def _import_holidays(self):
        for h in self.data.get('holidays', []):
            if Holiday.objects.filter(legacy_id=h['id']).exists():
                self._bump('holidays', False)
                continue
            holiday = Holiday.objects.create(
                date=_date(h.get('from')), date_to=_date(h.get('to')) or _date(h.get('from')),
                name=h.get('name', ''), is_all_branches=bool(h.get('all')), legacy_id=h['id'],
            )
            branch_ids = [self.branch_by_name[n].id for n in h.get('branches', []) if n in self.branch_by_name]
            holiday.branches.set(branch_ids)
            self._bump('holidays', True)

    # ---------- Misc singleton setting ----------
    def _import_attendance_start(self):
        value = self.data.get('attendanceStart')
        if not value:
            return
        SiteSetting.objects.get_or_create(key='attendance_start', defaults={'value': {'date': value}})
