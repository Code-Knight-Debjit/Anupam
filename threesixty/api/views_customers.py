"""Customer / Contact / Interaction resources.

Customer edit/delete permission follows AUDIT.md §3 exactly: Admin and
Branch Manager always act directly; Branch Staff edits directly but its
deletes route to the approval queue; Sales Manager can never edit or
delete directly — both actions route to the approval queue instead. This
mirrors `canEditCustomerDirect`/`canDeleteCustomerDirect` and the original
`requestSalesDocDelete`/`customer-access` approval flow (~L8449-8530),
generalised to customer edit/delete.
"""
from django.db.models import Q
from django.http import JsonResponse

from ..models import ApprovalRequest, Contact, Customer, Interaction
from ..permissions import RoleRules, staff_360_required
from .fields import parse_date_input
from .concurrency import check_version
from .http import ApiError, parse_body
from .resources import JsonResource
from .serializers import serialize_approval_request, serialize_contact, serialize_customer, serialize_interaction

CUSTOMER_SCALAR_FIELDS = (
    'name', 'plant', 'address', 'area', 'city', 'state', 'pincode', 'website', 'gst_number',
    'plant_geo_lat', 'plant_geo_lng', 'ho_geo_lat', 'ho_geo_lng', 'ho_name', 'ho_address',
    'ho_city', 'ho_state', 'ho_pincode', 'ho_phone', 'industry', 'source', 'potential',
    'transport_preference', 'courier_preference',
)
CUSTOMER_M2M_FIELDS = {
    'preferred_language_ids': 'preferred_languages',
    'interested_brand_ids': 'interested_brands',
    'interested_product_ids': 'interested_products',
    'assigned_to_ids': 'assigned_to',
}


def _apply_customer_scalars(instance, data):
    for field in CUSTOMER_SCALAR_FIELDS:
        if field in data:
            setattr(instance, field, data[field])


def _apply_customer_m2m(instance, data):
    for key, attname in CUSTOMER_M2M_FIELDS.items():
        if key in data:
            getattr(instance, attname).set(data[key])


class CustomerResource(JsonResource):
    model = Customer

    def list_queryset(self, request, **kwargs):
        qs = Customer.objects.all()
        search = request.GET.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(plant__icontains=search) | Q(city__icontains=search))
        return RoleRules.visible_customers(request.user, qs)

    def serialize(self, request, instance):
        return serialize_customer(instance)

    def apply_create(self, request, data, **kwargs):
        name = (data.get('name') or '').strip()
        if not name:
            raise ApiError(400, 'name is required.')
        customer = Customer(name=name, created_by=request.user)
        _apply_customer_scalars(customer, data)
        customer.save()
        _apply_customer_m2m(customer, data)
        return customer

    def apply_update(self, request, instance, data, **kwargs):
        if RoleRules.can_edit_customer_direct(request.user):
            check_version(data, instance)
            _apply_customer_scalars(instance, data)
            instance.version += 1
            instance.save()
            _apply_customer_m2m(instance, data)
            return instance
        if RoleRules.is_sales_manager(request.user):
            approval = ApprovalRequest.objects.create(
                type=ApprovalRequest.TYPE_EDIT, customer=instance, proposed_data=data,
                requested_by=request.user,
            )
            return JsonResponse(
                {'approval_requested': True, 'approval': serialize_approval_request(approval)}, status=202
            )
        raise ApiError(403, 'You cannot edit this customer.')

    def apply_delete(self, request, instance, **kwargs):
        if RoleRules.can_delete_customer_direct(request.user):
            instance.delete()
            return None
        if RoleRules.can_edit_customer_direct(request.user) or RoleRules.is_sales_manager(request.user):
            approval = ApprovalRequest.objects.create(
                type=ApprovalRequest.TYPE_DELETE, customer=instance, requested_by=request.user,
            )
            return JsonResponse(
                {'approval_requested': True, 'approval': serialize_approval_request(approval)}, status=202
            )
        raise ApiError(403, 'You cannot delete this customer.')


class ContactResource(JsonResource):
    """Listed/created either nested (`/customers/<customer_id>/contacts`) or
    flat (`/contacts/<pk>`); a contact inherits its parent customer's
    visibility scope and edit permission — the original has no separate
    contact-level permission model, only the `customer-access` approval
    type which concerns *granting visibility*, not contact CRUD itself."""
    model = Contact

    def list_queryset(self, request, customer_id=None, **kwargs):
        visible_customers = RoleRules.visible_customers(request.user, Customer.objects.all())
        qs = Contact.objects.filter(customer__in=visible_customers)
        if customer_id is not None:
            qs = qs.filter(customer_id=customer_id)
        return qs

    def serialize(self, request, instance):
        return serialize_contact(instance)

    def _require_customer(self, request, customer_id):
        try:
            return RoleRules.visible_customers(request.user, Customer.objects.all()).get(pk=customer_id)
        except Customer.DoesNotExist:
            raise ApiError(404, 'Customer not found.')

    def _require_editable(self, request, customer):
        if not (RoleRules.can_edit_customer_direct(request.user) or RoleRules.is_sales_manager(request.user)):
            raise ApiError(403, 'You cannot modify contacts on this customer.')

    def apply_create(self, request, data, customer_id=None, **kwargs):
        customer_id = customer_id or data.get('customer_id')
        if not customer_id:
            raise ApiError(400, 'customer_id is required.')
        customer = self._require_customer(request, customer_id)
        self._require_editable(request, customer)
        name = (data.get('name') or '').strip()
        if not name:
            raise ApiError(400, 'name is required.')
        return Contact.objects.create(
            customer=customer, name=name, job_title=data.get('job_title', ''),
            phone=data.get('phone', ''), phone2=data.get('phone2', ''), email=data.get('email', ''),
            dnd=data.get('dnd', False),
        )

    def apply_update(self, request, instance, data, **kwargs):
        self._require_editable(request, instance.customer)
        for field in ('name', 'job_title', 'phone', 'phone2', 'email', 'dnd'):
            if field in data:
                setattr(instance, field, data[field])
        instance.save()
        return instance

    def apply_delete(self, request, instance, **kwargs):
        self._require_editable(request, instance.customer)
        instance.delete()


class InteractionResource(JsonResource):
    """Any staff who can see the parent customer may log an interaction;
    only the original logger, Admin, or Branch Manager may edit/delete it
    (the original has no documented edit/delete for interactions at all —
    this is an additive, conservative assumption, not a verified rule)."""
    model = Interaction

    def list_queryset(self, request, contact_id=None, **kwargs):
        visible_customers = RoleRules.visible_customers(request.user, Customer.objects.all())
        qs = Interaction.objects.filter(contact__customer__in=visible_customers)
        if contact_id is not None:
            qs = qs.filter(contact_id=contact_id)
        return qs

    def serialize(self, request, instance):
        return serialize_interaction(instance)

    def apply_create(self, request, data, contact_id=None, **kwargs):
        contact_id = contact_id or data.get('contact_id')
        if not contact_id:
            raise ApiError(400, 'contact_id is required.')
        visible_customers = RoleRules.visible_customers(request.user, Customer.objects.all())
        try:
            contact = Contact.objects.filter(customer__in=visible_customers).get(pk=contact_id)
        except Contact.DoesNotExist:
            raise ApiError(404, 'Contact not found.')
        if not data.get('type') or not data.get('date'):
            raise ApiError(400, 'type and date are required.')
        interaction = Interaction.objects.create(
            contact=contact, type=data['type'], date=parse_date_input(data['date'], 'date'),
            notes=data.get('notes', ''),
            location_lat=data.get('location_lat'), location_lng=data.get('location_lng'),
            created_by=request.user, followup_date=parse_date_input(data.get('followup_date'), 'followup_date'),
            met_with_name=data.get('met_with_name', ''), linked_doc_id=data.get('linked_doc_id'),
        )
        if 'also_met_contact_ids' in data:
            interaction.also_met.set(data['also_met_contact_ids'])
        if 'joint_with_user_ids' in data:
            interaction.joint_with.set(data['joint_with_user_ids'])
        return interaction

    def _require_owner_or_manager(self, request, instance):
        if (instance.created_by_id == request.user.id or RoleRules.is_admin(request.user)
                or RoleRules.is_branch_manager(request.user)):
            return
        raise ApiError(403, 'You cannot modify this interaction.')

    def apply_update(self, request, instance, data, **kwargs):
        self._require_owner_or_manager(request, instance)
        for field in ('type', 'date', 'notes', 'location_lat', 'location_lng', 'followup_date', 'met_with_name'):
            if field in data:
                value = data[field]
                if field in ('date', 'followup_date'):
                    value = parse_date_input(value, field)
                setattr(instance, field, value)
        instance.save()
        if 'also_met_contact_ids' in data:
            instance.also_met.set(data['also_met_contact_ids'])
        if 'joint_with_user_ids' in data:
            instance.joint_with.set(data['joint_with_user_ids'])
        return instance

    def apply_delete(self, request, instance, **kwargs):
        self._require_owner_or_manager(request, instance)
        instance.delete()
