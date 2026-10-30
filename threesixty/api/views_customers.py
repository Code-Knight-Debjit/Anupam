"""Customer / Contact / Interaction resources and the customer-side endpoints
(assignment, access requests, duplicate check, map, exports, Excel import).

Edit / delete permission (REQ-ROLE-02, AUDIT §3): Admin and Branch Manager act
directly; Branch Staff edits directly but its deletes route to the approval
queue; a Sales Manager's edits *and* deletes of customers and contacts route to
the queue. Contacts always come through `services.contacts` so contact-level
access (REQ-CUS-02..06) is applied on every list, detail and export.
"""
import json

from django.contrib.auth import get_user_model
from django.db.models import Prefetch
from django.views.decorators.http import require_GET
from django.http import HttpResponse, JsonResponse

from ..models import ApprovalRequest, Contact, Customer, Interaction
from ..permissions import RoleRules, role_360_required, staff_360_required
from ..rules import anupam_rules as rules
from ..services import approvals as approval_service
from ..services import contacts as contact_service
from ..services import customers as customer_service
from ..services import audit, excel_import, interactions as interaction_service
from ..services import outreach as outreach_service
from ..services.errors import ServiceError
from .concurrency import check_version
from .fields import parse_date_input
from .http import ApiError, error_response, input_errors_as_400, parse_body
from .resources import JsonResource
from .serializers import serialize_approval_request, serialize_contact, serialize_customer, serialize_interaction

User = get_user_model()


def visible_customers(request):
    return RoleRules.visible_customers(request.user, Customer.objects.all())


def _approval_response(approval):
    return JsonResponse({'approval_requested': True, 'approval': serialize_approval_request(approval)}, status=202)


def _assignment_change(request, customer, data):
    """Who is assigned may only be changed by Admin / Branch Manager (the customer form sends the whole
    list). Returns (to_add, to_remove) user-id sets, or raises 403 if someone else tries to change it."""
    if 'assigned_to_ids' not in data:
        return set(), set()
    try:
        wanted = {int(x) for x in data['assigned_to_ids'] or []}
    except (TypeError, ValueError):
        raise ApiError(400, 'assigned_to_ids must be a list of user ids.')
    current = set(customer.assigned_to.values_list('id', flat=True)) if customer is not None and customer.pk else set()
    if wanted == current:
        return set(), set()
    if not outreach_service.can_assign(request.user):
        raise ApiError(403, 'Only Admin or Branch Manager can assign customers.')
    return wanted - current, current - wanted


def _apply_assignment(request, customer, to_add, to_remove):
    for uid in to_add:
        contact_service.assign_customer(customer, _assignable_user(request, uid), None)
    for uid in to_remove:
        contact_service.deassign_customer(customer, _assignable_user(request, uid))


class CustomerResource(JsonResource):
    model = Customer

    def base_queryset(self, request):
        return visible_customers(request).select_related('created_by', 'plant_geo_set_by', 'ho_geo_set_by').prefetch_related(
            'preferred_languages', 'interested_brands', 'interested_products', 'assigned_to')

    def list_queryset(self, request, **kwargs):
        qs = customer_service.apply_filters(self.base_queryset(request), request.GET)
        search = request.GET.get('search')
        if search:
            return customer_service.search(qs, search)
        return qs.order_by('name', 'plant')

    def get_object(self, request, pk, **kwargs):
        try:
            return self.base_queryset(request).get(pk=pk)
        except Customer.DoesNotExist:
            raise ApiError(404, 'Not found.')

    def serialize(self, request, instance):
        return serialize_customer(instance)

    def apply_create(self, request, data, **kwargs):
        profile = request.user.threesixty_profile
        customer = Customer(created_by=request.user, created_by_role=profile.role)
        to_add, to_remove = _assignment_change(request, None, data)
        customer_service.apply_customer_data(customer, data, request.user)
        customer.save()
        customer_service.apply_customer_m2m(customer, data)
        _apply_assignment(request, customer, to_add, to_remove)
        return Customer.objects.prefetch_related('assigned_to').get(pk=customer.pk)

    def apply_update(self, request, instance, data, **kwargs):
        to_add, to_remove = _assignment_change(request, instance, data)
        if RoleRules.needs_approval(request.user, 'customer.edit'):
            if not RoleRules.is_sales_manager(request.user):
                raise ApiError(403, 'You cannot edit this customer.')
            return _approval_response(approval_service.request_change(
                request.user, ApprovalRequest.TYPE_EDIT, instance, proposed=data))
        check_version(data, instance)
        customer_service.apply_customer_data(instance, data, request.user)
        instance.version += 1
        instance.save()
        customer_service.apply_customer_m2m(instance, data)
        _apply_assignment(request, instance, to_add, to_remove)
        return self.get_object(request, instance.pk)

    def apply_delete(self, request, instance, **kwargs):
        if not RoleRules.needs_approval(request.user, 'customer.delete'):
            audit.record(request.user, 'customer.delete', instance, instance.select_label, request)
            instance.delete()
            return None
        return _approval_response(approval_service.request_change(request.user, ApprovalRequest.TYPE_DELETE, instance))


class ContactResource(JsonResource):
    """Listed/created nested (`/customers/<id>/contacts`) or flat
    (`/contacts/<pk>`). The queryset is the shared contact-access helper's, so
    a contact hidden from the caller is a 404, never a 403."""
    model = Contact

    def list_queryset(self, request, customer_id=None, **kwargs):
        qs = contact_service.visible_contacts_qs(request.user, Contact.objects.select_related('customer'))
        if customer_id is not None:
            qs = qs.filter(customer_id=customer_id)
        return qs.order_by('name')

    def serialize(self, request, instance):
        return serialize_contact(instance)

    def apply_create(self, request, data, customer_id=None, **kwargs):
        customer_id = customer_id or data.get('customer_id')
        if not customer_id:
            raise ApiError(400, 'customer_id is required.')
        try:
            customer = visible_customers(request).get(pk=customer_id)
        except Customer.DoesNotExist:
            raise ApiError(404, 'Customer not found.')
        name = (data.get('name') or '').strip()
        if not name:
            raise ApiError(400, 'name is required.')
        return Contact.objects.create(
            customer=customer, name=rules.title_case_words(name), job_title=data.get('job_title', ''),
            phone=data.get('phone', ''), phone2=data.get('phone2', ''), email=data.get('email', ''),
            dnd=bool(data.get('dnd', False)),
        )

    def apply_update(self, request, instance, data, **kwargs):
        if RoleRules.needs_approval(request.user, 'contact.edit'):
            if not RoleRules.is_sales_manager(request.user):
                raise ApiError(403, 'You cannot edit this contact.')
            return _approval_response(approval_service.request_change(
                request.user, ApprovalRequest.TYPE_EDIT, instance, proposed=data))
        for field in approval_service.CONTACT_FIELDS:
            if field in data:
                value = data[field]
                if field == 'name':
                    value = rules.title_case_words((value or '').strip())
                    if not value:
                        raise ApiError(400, 'name is required.')
                setattr(instance, field, value)
        instance.save()
        return instance

    def apply_delete(self, request, instance, **kwargs):
        if RoleRules.needs_approval(request.user, 'contact.edit'):
            if not RoleRules.is_sales_manager(request.user):
                raise ApiError(403, 'You cannot delete this contact.')
            return _approval_response(approval_service.request_change(request.user, ApprovalRequest.TYPE_DELETE, instance))
        contact_service.delete_contact(instance)
        return None


class InteractionResource(JsonResource):
    """Anyone who can see the contact may log an interaction on it; only the
    logger, Admin or Branch Manager may edit/delete one."""
    model = Interaction

    def list_queryset(self, request, contact_id=None, **kwargs):
        contacts = contact_service.visible_contacts_qs(request.user)
        qs = Interaction.objects.filter(contact__in=contacts).select_related(
            'contact__customer', 'created_by').prefetch_related('also_met', 'joint_with')
        if contact_id is not None:
            qs = qs.filter(contact_id=contact_id)
        return qs.order_by('-date', '-id')

    def serialize(self, request, instance):
        return serialize_interaction(instance)

    def apply_create(self, request, data, contact_id=None, **kwargs):
        contact_id = contact_id or data.get('contact_id')
        if not contact_id:
            raise ApiError(400, 'contact_id is required.')
        contact = interaction_service.require_logging_contact(request.user, contact_id)
        if not data.get('type') or not data.get('date'):
            raise ApiError(400, 'type and date are required.')
        also_met = list(contact_service.visible_contacts_qs(request.user).filter(pk__in=data.get('also_met_contact_ids') or []))
        joint = list(User.objects.filter(pk__in=data.get('joint_with_user_ids') or [], is_active=True,
                                         threesixty_profile__isnull=False))
        return interaction_service.log_interaction(
            request.user, contact, data['type'], parse_date_input(data['date'], 'date'), notes=data.get('notes', ''),
            followup_date=parse_date_input(data.get('followup_date'), 'followup_date'),
            also_met_contacts=also_met, joint_users=joint,
            lat=data.get('location_lat'), lng=data.get('location_lng'), accuracy_m=data.get('location_accuracy_m'),
            linked_doc=_linked_document(request, data.get('linked_doc_id')),
        )

    def _require_owner_or_manager(self, request, instance):
        if (instance.created_by_id == request.user.id or RoleRules.is_admin(request.user)
                or RoleRules.is_branch_manager(request.user)):
            return
        raise ApiError(403, 'You cannot modify this interaction.')

    def apply_update(self, request, instance, data, **kwargs):
        self._require_owner_or_manager(request, instance)
        for field in ('notes', 'date', 'followup_date'):
            if field in data:
                value = parse_date_input(data[field], field) if field != 'notes' else data[field]
                setattr(instance, field, value)
        instance.save()
        return instance

    def apply_delete(self, request, instance, **kwargs):
        self._require_owner_or_manager(request, instance)
        instance.delete()


def _linked_document(request, doc_id):
    if not doc_id:
        return None
    from ..models import SalesDocument
    docs = RoleRules.visible_sales_documents(request.user, SalesDocument.objects.all())
    try:
        return docs.get(pk=doc_id)
    except SalesDocument.DoesNotExist:
        raise ApiError(404, 'Linked document not found.')


# --------------------------------------------------------------------------- assignment (Admin / Branch Manager)
def _assignable_user(request, user_id):
    """An active 360 employee; a Branch Manager may only assign within their own team."""
    try:
        user = User.objects.get(pk=user_id, is_active=True, threesixty_profile__is_active_employee=True)
    except (User.DoesNotExist, ValueError, TypeError):
        raise ApiError(400, 'That person does not exist or is inactive.')
    if RoleRules.is_branch_manager(request.user) and user.pk not in RoleRules.user_ids_in_manager_scope(request.user):
        raise ApiError(403, 'That person is outside your branch scope.')
    return user


@role_360_required('ADMIN', 'BRANCH_MANAGER')
@input_errors_as_400
def customer_assign(request, pk):
    """POST {user_id, contact_ids?} assigns one person (optionally sharing only some contacts);
    DELETE ?user_id= removes them and their contact restriction."""
    try:
        customer = visible_customers(request).get(pk=pk)
    except Customer.DoesNotExist:
        return error_response(ApiError(404, 'Customer not found.'))
    if request.method == 'POST':
        data = parse_body(request)
        user = _assignable_user(request, data.get('user_id'))
        contact_service.assign_customer(customer, user, data.get('contact_ids'))
        return JsonResponse(serialize_customer(Customer.objects.get(pk=pk)))
    if request.method == 'DELETE':
        user = _assignable_user(request, request.GET.get('user_id'))
        contact_service.deassign_customer(customer, user)
        return JsonResponse(serialize_customer(Customer.objects.get(pk=pk)))
    return error_response(ApiError(405, 'POST or DELETE only.'))


@role_360_required('ADMIN', 'BRANCH_MANAGER')
@input_errors_as_400
def customers_bulk_assign(request):
    """POST {customer_ids, user_ids} — whole customers to several people at once."""
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    data = parse_body(request)
    customers = list(visible_customers(request).filter(pk__in=data.get('customer_ids') or []))
    users = [_assignable_user(request, uid) for uid in data.get('user_ids') or []]
    if not customers or not users:
        return error_response(ApiError(400, 'Pick at least one customer and one person.'))
    for customer in customers:
        for user in users:
            contact_service.assign_customer(customer, user, None)
    return JsonResponse({'assigned': len(customers) * len(users)})


@require_GET
@staff_360_required
@input_errors_as_400
def customer_contact_access(request, pk):
    """Who may see which contacts of a customer (Admin / Branch Manager)."""
    if not RoleRules.is_approver(request.user):
        return error_response(ApiError(403, 'Only Admin or Branch Manager can view contact access.'))
    try:
        customer = visible_customers(request).get(pk=pk)
    except Customer.DoesNotExist:
        return error_response(ApiError(404, 'Customer not found.'))
    rows = {}
    for row in customer.contact_access.all():
        rows.setdefault(row.user_id, []).append(row.contact_id)
    return JsonResponse({'customer_id': customer.pk, 'access': [
        {'user_id': u.pk, 'contact_ids': rows.get(u.pk)} for u in customer.assigned_to.all()]})


# --------------------------------------------------------------------------- helpers for the UI
@require_GET
@staff_360_required
@input_errors_as_400
def duplicate_check(request):
    """Similar customer names, across ALL customers (so a Sales Manager is
    warned about a customer they can't see — and can request access)."""
    from ..models import ApprovalRequest as AR
    matches = customer_service.find_duplicates(request.GET.get('name', ''))
    visible = set(visible_customers(request).filter(pk__in=[c.pk for c in matches]).values_list('pk', flat=True))
    pending = set(AR.objects.filter(
        status=AR.STATUS_PENDING, type=AR.TYPE_CUSTOMER_ACCESS, requested_by=request.user,
        customer__in=[c.pk for c in matches]).values_list('customer_id', flat=True))
    return JsonResponse({'matches': [
        {'id': c.pk, 'label': c.select_label, 'has_access': c.pk in visible, 'access_request_pending': c.pk in pending}
        for c in matches]})


@require_GET
@staff_360_required
@input_errors_as_400
def geo_parse(request):
    """Validate a map-pin text/link (REQ-GEO-01)."""
    try:
        pin = customer_service.parse_pin(request.GET.get('text', ''))
    except ApiError as exc:
        return error_response(exc)
    except ServiceError as exc:
        return error_response(exc)
    return JsonResponse(pin)


@require_GET
@staff_360_required
@input_errors_as_400
def nearby(request):
    """Map & Nearby: visible customers with a plant pin within `radius_km` of a point."""
    try:
        lat, lng = float(request.GET['lat']), float(request.GET['lng'])
        radius = float(request.GET.get('radius_km', 25))
    except (KeyError, ValueError):
        return error_response(ApiError(400, 'lat, lng and radius_km are required numbers.'))
    here = {'lat': lat, 'lng': lng}
    found = []
    for c in visible_customers(request).filter(plant_geo_lat__isnull=False, plant_geo_lng__isnull=False):
        metres = rules.geo_dist_m(here, {'lat': c.plant_geo_lat, 'lng': c.plant_geo_lng})
        if metres <= radius * 1000:
            found.append({'id': c.pk, 'label': c.select_label, 'lat': c.plant_geo_lat, 'lng': c.plant_geo_lng,
                          'distance_m': round(metres), 'distance': rules.geo_fmt_dist(metres)})
    found.sort(key=lambda r: r['distance_m'])
    return JsonResponse({'results': found})


@require_GET
@role_360_required('ADMIN', 'BRANCH_MANAGER')
@input_errors_as_400
def contacts_export(request):
    """Copy e-mails / .vcf phonebook for the selected contacts (REQ-CUS-10).
    Only contacts the caller may see are exported; an empty selection is refused."""
    ids = [int(x) for x in request.GET.get('contact_ids', '').split(',') if x.strip().isdigit()]
    customer_ids = [int(x) for x in request.GET.get('customer_ids', '').split(',') if x.strip().isdigit()]
    qs = contact_service.visible_contacts_qs(request.user, Contact.objects.select_related('customer'))
    selection = qs.filter(pk__in=ids) | qs.filter(customer_id__in=customer_ids)
    contacts = list(selection.distinct().order_by('customer__name', 'name'))
    if not contacts:
        return error_response(ApiError(400, 'Select at least one contact first.'))
    if request.GET.get('format') == 'vcf':
        response = HttpResponse(customer_service.vcard(contacts), content_type='text/vcard; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="anupam360-contacts.vcf"'
        return response
    return JsonResponse({'emails': customer_service.selected_emails(contacts), 'count': len(contacts)})


@require_GET
@role_360_required('ADMIN')
@input_errors_as_400
def import_template(request):
    response = HttpResponse(
        excel_import.template_workbook_bytes(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="anupam360-customer-import-template.xlsx"'
    return response


@role_360_required('ADMIN')
@input_errors_as_400
def import_customers(request):
    """POST an .xlsx (multipart `file`) or JSON `{rows: [...]}` — Admin only."""
    if request.method != 'POST':
        return error_response(ApiError(405, 'POST only.'))
    if request.FILES.get('file'):
        rows = excel_import.rows_from_workbook(request.FILES['file'])
    else:
        rows = parse_body(request).get('rows')
        if not isinstance(rows, list):
            return error_response(ApiError(400, 'Upload an .xlsx file or send {"rows": [...]}.'))
        rows = [{k: ('' if v is None else str(v)) for k, v in r.items()} for r in rows if isinstance(r, dict)]
    summary = excel_import.import_rows(rows, request.user)
    audit.record(request.user, 'customers.import', summary=f'{summary["new"]} new, {summary["updated"]} updated, {summary["contacts"]} contacts', request=request)
    return JsonResponse(summary)


@require_GET
@role_360_required('ADMIN', 'BRANCH_MANAGER')
@input_errors_as_400
def customers_export(request):
    """The filtered customer list as Excel or PDF (`?format=xlsx|pdf`) — Admin / Branch Manager."""
    from ..services import exports
    from django.db.models import Count
    qs = customer_service.apply_filters(visible_customers(request), request.GET)
    if request.GET.get('search'):
        customers = customer_service.search(qs, request.GET['search'])
    else:
        customers = list(qs.order_by('name', 'plant'))
    counts = dict(Contact.objects.filter(customer__in=[c.pk for c in customers]).values_list('customer_id').annotate(n=Count('id')))
    headers = ['Customer', 'Plant', 'Area', 'City', 'State', 'Pincode', 'GST Number', 'Industry', 'Source', 'Potential', 'Contacts']
    rows = [[c.name, c.plant, c.area, c.city, c.state, c.pincode, c.gst_number, c.industry, c.source, c.potential,
             counts.get(c.pk, 0)] for c in customers]
    if request.GET.get('format') == 'pdf':
        body, ctype, ext = exports.table_pdf('Customers', headers, rows), 'application/pdf', 'pdf'
    else:
        body, ctype, ext = exports.table_xlsx('Customers', headers, rows), \
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx'
    response = HttpResponse(body, content_type=ctype)
    response['Content-Disposition'] = f'attachment; filename="customers.{ext}"'
    return response
