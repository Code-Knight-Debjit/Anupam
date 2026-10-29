"""Plain-dict serializers — one explicit function per model rather than a
generic introspecting framework, so every field needing special handling
(Aadhaar/PAN masking, M2M id lists, nested items) is visible at the call
site. Field lists are a deliberate API surface, not "whatever the model
has" — new model fields do not silently leak until added here.
"""
from ..permissions import RoleRules
from ..services.tasks import kind_of as task_kind
from ..services.users import is_account_active


def mask_id_number(value):
    """Aadhaar/PAN: keep only the last 4 characters (AUDIT.md §5.5 — these
    are stored for HR purposes but masked in every response except Admin's)."""
    if not value:
        return ''
    value = str(value)
    if len(value) <= 4:
        return 'X' * len(value)
    return 'X' * (len(value) - 4) + value[-4:]


def serialize_user_ref(user):
    if user is None:
        return None
    return {'id': user.id, 'username': user.username, 'full_name': user.get_full_name() or user.username}


BRANCH_IMAGE_FIELDS = ('logo', 'dealer_logo', 'footer_image', 'payment_qr')
BRANCH_TEXT_FIELDS = (
    'name', 'letterhead_name', 'letterhead_address', 'letterhead_gstin', 'letterhead_phone', 'letterhead_email',
    'letterhead_mobile', 'letterhead_website', 'udyam_number',
    'bank_name', 'bank_branch', 'bank_account_no', 'bank_ifsc',
    'accent_color', 'doc_format', 'watermark_enabled', 'watermark_type', 'watermark_text', 'watermark_size',
    'terms', 'is_active',
)


def serialize_branch(branch):
    data = {'id': branch.id, 'legacy_id': branch.legacy_id}
    for field in BRANCH_TEXT_FIELDS:
        data[field] = getattr(branch, field)
    for field in BRANCH_IMAGE_FIELDS:
        image = getattr(branch, field)
        data[field + '_url'] = image.url if image else ''
    return data


def serialize_branch_numbering(config):
    return {
        'id': config.id,
        'branch_id': config.branch_id,
        'doc_type': config.doc_type,
        'prefix': config.prefix,
        'suffix': config.suffix,
        'start_at': config.start_at,
        'last_issued': config.last_issued,
    }


def serialize_holiday(holiday):
    return {
        'id': holiday.id,
        'date': holiday.date.isoformat(),
        'date_to': holiday.date_to.isoformat(),
        'name': holiday.name,
        'is_all_branches': holiday.is_all_branches,
        'branch_ids': list(holiday.branches.values_list('id', flat=True)),
        'legacy_id': holiday.legacy_id,
    }


def serialize_lookup_item(item):
    return {
        'id': item.id,
        'kind': item.kind,
        'name': item.name,
        'extra': item.extra,
        'is_active': item.is_active,
        'sort_order': item.sort_order,
        'legacy_id': item.legacy_id,
    }


def serialize_sales_person(person):
    return {'id': person.id, 'name': person.name, 'phone': person.phone, 'legacy_id': person.legacy_id}


def serialize_site_setting(setting):
    return {'id': setting.id, 'key': setting.key, 'value': setting.value}


def serialize_employee(profile, viewer):
    """Admin sees everything. A person sees their own record with Aadhaar / PAN masked. Everyone else
    gets only what assignment pickers need — no Aadhaar, PAN, birth date, phone or work schedule."""
    is_admin = viewer is not None and RoleRules.is_admin(viewer)
    is_self = viewer is not None and viewer.pk == profile.user_id
    data = {
        'id': profile.id,
        'user_id': profile.user_id,
        'username': profile.user.username,
        'full_name': profile.user.get_full_name() or profile.user.username,
        'is_active_account': profile.user.is_active,
        'is_active': is_account_active(profile),
        'role': profile.role,
        'branch_ids': [b.id for b in profile.branches.all()],
        'job_title': profile.job_title,
        'legacy_id': profile.legacy_id,
    }
    if is_admin or is_self:
        data.update({
            'phone': profile.phone,
            'emp_code': profile.emp_code,
            'is_active_employee': profile.is_active_employee,
            'aadhaar_number': profile.aadhaar_number if is_admin else mask_id_number(profile.aadhaar_number),
            'pan_number': profile.pan_number if is_admin else mask_id_number(profile.pan_number),
            'date_of_birth': profile.date_of_birth.isoformat() if profile.date_of_birth else None,
            'date_of_joining': profile.date_of_joining.isoformat() if profile.date_of_joining else None,
            'work_start': profile.work_start,
            'work_end': profile.work_end,
            'weekly_off': profile.weekly_off,
        })
    return data


def serialize_customer(customer):
    return {
        'id': customer.id,
        'name': customer.name,
        'plant': customer.plant,
        'address': customer.address,
        'area': customer.area,
        'city': customer.city,
        'state': customer.state,
        'pincode': customer.pincode,
        'website': customer.website,
        'gst_number': customer.gst_number,
        'plant_geo_lat': customer.plant_geo_lat,
        'plant_geo_lng': customer.plant_geo_lng,
        'ho_geo_lat': customer.ho_geo_lat,
        'ho_geo_lng': customer.ho_geo_lng,
        'ho_name': customer.ho_name,
        'ho_address': customer.ho_address,
        'ho_city': customer.ho_city,
        'ho_state': customer.ho_state,
        'ho_pincode': customer.ho_pincode,
        'ho_phone': customer.ho_phone,
        'industry': customer.industry,
        'source': customer.source,
        'potential': customer.potential,
        'transport_preference': customer.transport_preference,
        'courier_preference': customer.courier_preference,
        # .all() (not values_list) so a prefetch on the list view is used.
        'preferred_language_ids': [x.id for x in customer.preferred_languages.all()],
        'interested_brand_ids': [x.id for x in customer.interested_brands.all()],
        'interested_product_ids': [x.id for x in customer.interested_products.all()],
        'assigned_to_ids': [x.id for x in customer.assigned_to.all()],
        'label': customer.select_label,
        'plant_geo_set_by': serialize_user_ref(customer.plant_geo_set_by),
        'plant_geo_set_at': customer.plant_geo_set_at.isoformat() if customer.plant_geo_set_at else None,
        'ho_geo_set_by': serialize_user_ref(customer.ho_geo_set_by),
        'ho_geo_set_at': customer.ho_geo_set_at.isoformat() if customer.ho_geo_set_at else None,
        'created_by_role': customer.created_by_role,
        'created_by': serialize_user_ref(customer.created_by),
        'created_at': customer.created_at.isoformat(),
        'updated_at': customer.updated_at.isoformat(),
        'version': customer.version,
        'legacy_id': customer.legacy_id,
    }


def serialize_contact(contact):
    return {
        'id': contact.id,
        'customer_id': contact.customer_id,
        'name': contact.name,
        'job_title': contact.job_title,
        'phone': contact.phone,
        'phone2': contact.phone2,
        'email': contact.email,
        'dnd': contact.dnd,
        'legacy_id': contact.legacy_id,
    }


def serialize_interaction(interaction):
    from ..services.customers import distance_label
    customer = interaction.contact.customer
    return {
        'id': interaction.id,
        'contact_id': interaction.contact_id,
        'type': interaction.type,
        'date': interaction.date.isoformat(),
        'notes': interaction.notes,
        'location_lat': interaction.location_lat,
        'location_lng': interaction.location_lng,
        'location_accuracy_m': interaction.location_accuracy_m,
        'distance_from_plant': distance_label(customer, interaction.location_lat, interaction.location_lng),
        'created_by': serialize_user_ref(interaction.created_by),
        'created_at': interaction.created_at.isoformat(),
        'followup_date': interaction.followup_date.isoformat() if interaction.followup_date else None,
        'also_met_contact_ids': [c.id for c in interaction.also_met.all()],
        'joint_with_user_ids': [u.id for u in interaction.joint_with.all()],
        'is_copy': interaction.is_copy,
        'met_with_name': interaction.met_with_name,
        'linked_doc_id': interaction.linked_doc_id,
        'legacy_id': interaction.legacy_id,
    }


def serialize_sales_document_item(item):
    from ..services import documents as doc_service
    supply = list(item.supply_log.all())
    invoices = list(item.invoice_log.all())
    return {
        'id': item.id,
        'document_id': item.document_id,
        'position': item.position,
        'item_name': item.item_name,
        'make': item.make,
        'qty': str(item.qty),
        'unit': item.unit,
        'rate': str(item.rate),
        'discount': str(item.discount),
        'tax': str(item.tax),
        'amount': str(item.amount),
        'value': str(item.value),
        'supplied': str(doc_service.item_supplied(item)),
        'pending': str(doc_service.item_pending(item)),
        'invoiced': str(doc_service.item_invoiced(item)),
        'balance': str(doc_service.item_balance(item)),
        'supply_log': [serialize_supply_log_entry(e) for e in supply],
        'invoice_log': [serialize_invoice_log_entry(e) for e in invoices],
        'legacy_id': item.legacy_id,
    }


def serialize_invoice_log_entry(entry):
    return {
        'id': entry.id,
        'item_id': entry.item_id,
        'bill_number': entry.bill_number,
        'bill_date': entry.bill_date.isoformat() if entry.bill_date else None,
        'qty_invoiced': str(entry.qty_invoiced),
        'recorded_by': serialize_user_ref(entry.recorded_by),
        'created_at': entry.created_at.isoformat(),
    }


def serialize_supply_log_entry(entry):
    return {
        'id': entry.id,
        'item_id': entry.item_id,
        'date': entry.date.isoformat(),
        'qty_supplied': str(entry.qty_supplied),
        'remarks': entry.remarks,
        'recorded_by': serialize_user_ref(entry.recorded_by),
        'created_at': entry.created_at.isoformat(),
    }


def serialize_document_call_log_entry(entry):
    return {
        'id': entry.id,
        'document_id': entry.document_id,
        'message': entry.message,
        'user': serialize_user_ref(entry.user),
        'timestamp': entry.timestamp.isoformat(),
        'call_later_date': entry.call_later_date.isoformat() if entry.call_later_date else None,
        'outcome': entry.outcome,
    }


def serialize_sales_document(document, include_items=True):
    data = {
        'id': document.id,
        'type': document.type,
        'doc_number': document.doc_number,
        'branch_id': document.branch_id,
        'customer_id': document.customer_id,
        'contact_id': document.contact_id,
        'date': document.date.isoformat(),
        'remarks': document.remarks,
        'reference_id': document.reference_id,
        'source': document.source,
        'order_status': document.order_status,
        'vehicle': document.vehicle,
        'transport': document.transport,
        'show_discount_in_pdf': document.show_discount_in_pdf,
        'packing_charges': str(document.packing_charges),
        'packing_tax': str(document.packing_tax),
        'freight_charges': str(document.freight_charges),
        'freight_tax': str(document.freight_tax),
        'other_charges': str(document.other_charges),
        'other_charges_tax': str(document.other_charges_tax),
        'round_off': str(document.round_off),
        'sub_total': str(document.sub_total),
        'total_amount': str(document.total_amount),
        'quotation_value': str(document.quotation_value) if document.quotation_value is not None else None,
        'sales_person_id': document.sales_person_id,
        'sales_person_name': document.sales_person_name,
        'valid_till': document.valid_till.isoformat() if document.valid_till else None,
        'ref_no': document.ref_no,
        'ref_date': document.ref_date.isoformat() if document.ref_date else None,
        'payment_terms': document.payment_terms,
        'terms': document.terms,
        'created_by': serialize_user_ref(document.created_by),
        'created_at': document.created_at.isoformat(),
        'updated_at': document.updated_at.isoformat(),
        'version': document.version,
        'legacy_id': document.legacy_id,
    }
    if include_items:
        from ..services import documents as doc_service
        data['items'] = [serialize_sales_document_item(i) for i in document.items.all()]
        data['order_value'] = str(document.order_value) if document.order_value is not None else None
        data['lost_reason'] = document.lost_reason
        data['customer_label'] = document.customer.select_label
        data['contact_name'] = document.contact.name if document.contact_id else ''
        data['branch_name'] = document.branch.name
        data['reference_number'] = document.reference.doc_number if document.reference_id else ''
        last = doc_service.last_contact_on(document)
        data['last_contact_on'] = last.isoformat() if last else None
        later = doc_service.next_call_later_date(document)
        data['call_later_date'] = later.isoformat() if later else None
        data['call_later_bucket'] = doc_service.call_later_bucket(document)
        if document.type == 'dc':
            data['invoice_pending'] = doc_service.dc_is_pending(document)
        data['call_log'] = [serialize_document_call_log_entry(e) for e in document.call_log.all()]
    return data


def serialize_payment_receipt(receipt):
    return {
        'id': receipt.id,
        'payment_id': receipt.payment_id,
        'amount': str(receipt.amount),
        'date': receipt.date.isoformat(),
        'mode': receipt.mode,
        'remarks': receipt.remarks,
        'recorded_by': serialize_user_ref(receipt.recorded_by),
        'created_at': receipt.created_at.isoformat(),
        'legacy_id': receipt.legacy_id,
    }


def serialize_payment_contact_log(entry):
    return {
        'id': entry.id,
        'payment_id': entry.payment_id,
        'message': entry.message,
        'user': serialize_user_ref(entry.user),
        'timestamp': entry.timestamp.isoformat(),
        'call_later_date': entry.call_later_date.isoformat() if entry.call_later_date else None,
    }


def serialize_payment_collection(payment, include_receipts=True):
    from ..services import payments as payment_service
    received = payment.received()
    data = {
        'id': payment.id,
        'branch_id': payment.branch_id,
        'customer_id': payment.customer_id,
        'customer_label': payment.customer.select_label,
        'contact_id': payment.contact_id,
        'contact_name': payment.contact.name if payment.contact_id else '',
        'amount': str(payment.amount),
        'received': str(received),
        'balance': str(payment.balance()),
        'date': payment.date.isoformat(),
        'remarks': payment.remarks,
        'age_days': payment_service.age_days(payment),
        'age_bucket': payment_service.age_bucket(payment),
        'created_by': serialize_user_ref(payment.created_by),
        'created_at': payment.created_at.isoformat(),
        'version': payment.version,
        'legacy_id': payment.legacy_id,
    }
    if include_receipts:
        data['receipts'] = [serialize_payment_receipt(r) for r in payment.receipts.all()]
        last = payment_service.last_contact_on(payment)
        data['last_contact_on'] = last.isoformat() if last else None
        later = payment_service.call_later_date(payment)
        data['call_later_date'] = later.isoformat() if later else None
        data['call_later_bucket'] = payment_service.call_later_bucket(payment)
        data['contact_log'] = [serialize_payment_contact_log(l) for l in payment.contact_log.all()]
    return data


def serialize_task(task):
    return {
        'id': task.id,
        'title': task.title,
        'description': task.description,
        'assigned_to': serialize_user_ref(task.assigned_to),
        'joint_with_user_ids': [u.id for u in task.joint_with.all()],
        'kind': task_kind(task),
        'auto_closed_by_visit': task.auto_closed_by_visit,
        'priority': task.priority,
        'status': task.status,
        'task_type': task.task_type,
        'due_date': task.due_date.isoformat() if task.due_date else None,
        'related_customer_id': task.related_customer_id,
        'related_contact_id': task.related_contact_id,
        'related_document_id': task.related_document_id,
        'created_by': serialize_user_ref(task.created_by),
        'created_at': task.created_at.isoformat(),
        'completed_at': task.completed_at.isoformat() if task.completed_at else None,
        'version': task.version,
        'legacy_id': task.legacy_id,
    }


def serialize_notification(notification):
    return {
        'id': notification.id,
        'type': notification.type,
        'text': notification.text,
        'read': notification.read,
        'related_customer_id': notification.related_customer_id,
        'related_document_id': notification.related_document_id,
        'created_at': notification.created_at.isoformat(),
    }


def serialize_approval_request(request_obj):
    return {
        'id': request_obj.id,
        'type': request_obj.type,
        'note': request_obj.note,
        'customer_id': request_obj.customer_id,
        'contact_id': request_obj.contact_id,
        'document_id': request_obj.document_id,
        'target_label': request_obj.target_label,
        'proposed_data': request_obj.proposed_data,
        'requested_by': serialize_user_ref(request_obj.requested_by),
        'requested_at': request_obj.requested_at.isoformat(),
        'status': request_obj.status,
        'reviewed_by': serialize_user_ref(request_obj.reviewed_by),
        'reviewed_at': request_obj.reviewed_at.isoformat() if request_obj.reviewed_at else None,
    }


def serialize_call_attempt(attempt):
    return {
        'id': attempt.id,
        'assignment_id': attempt.assignment_id,
        'reason': attempt.reason,
        'note': attempt.note,
        'at': attempt.at.isoformat(),
        'by': serialize_user_ref(attempt.by),
        'call_again_date': attempt.call_again_date.isoformat() if attempt.call_again_date else None,
    }


def serialize_call_assignment(assignment, include_attempts=True):
    data = {
        'id': assignment.id,
        'customer_id': assignment.customer_id,
        'contact_id': assignment.contact_id,
        'week_of': assignment.week_of.isoformat(),
        'status': assignment.status,
        'remarks': assignment.remarks,
        'called_at': assignment.called_at.isoformat() if assignment.called_at else None,
        'called_by': serialize_user_ref(assignment.called_by),
        'assigned_to': serialize_user_ref(assignment.assigned_to),
        'assigned_by': serialize_user_ref(assignment.assigned_by),
        'assigned_at': assignment.assigned_at.isoformat(),
    }
    if include_attempts:
        data['attempts'] = [serialize_call_attempt(a) for a in assignment.attempts.all()]
    return data


def serialize_attendance_record(record, viewer=None):
    """Locations are shown to Admin and to the person themselves, nobody else (REQ-ATT-04)."""
    data = {
        'id': record.id,
        'user': serialize_user_ref(record.user),
        'date': record.date.isoformat(),
        'check_in': record.check_in.isoformat() if record.check_in else None,
        'check_out': record.check_out.isoformat() if record.check_out else None,
        'status': record.status,
        'note': record.note,
        'marked_by': serialize_user_ref(record.marked_by),
    }
    if viewer is not None and (RoleRules.is_admin(viewer) or record.user_id == viewer.pk):
        data.update(
            in_loc_lat=record.in_loc_lat, in_loc_lng=record.in_loc_lng, in_loc_accuracy_m=record.in_loc_accuracy_m,
            out_loc_lat=record.out_loc_lat, out_loc_lng=record.out_loc_lng, out_loc_accuracy_m=record.out_loc_accuracy_m)
    return data


def serialize_leave_request(leave):
    return {
        'id': leave.id,
        'user': serialize_user_ref(leave.user),
        'date_from': leave.date_from.isoformat(),
        'date_to': leave.date_to.isoformat(),
        'days': leave.days(),
        'reason': leave.reason,
        'status': leave.status,
        'requested_at': leave.requested_at.isoformat(),
        'decided_by': serialize_user_ref(leave.decided_by),
        'decided_at': leave.decided_at.isoformat() if leave.decided_at else None,
        'decision_note': leave.decision_note,
    }
