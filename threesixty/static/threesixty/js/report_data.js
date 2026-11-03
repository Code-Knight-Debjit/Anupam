// The data every report is built from, in the reference's shape (so each report reads like its original). Everything comes
// from the same scoped list endpoints the rest of the app uses, so a user only ever reports on what they may see.
import { api } from './api.js';
import { state, isAdmin, isBranchManager } from './state.js';

const num = (v) => Number(v) || 0;
export const docValue = (d) => num(d.total_amount) || (d.items || []).reduce((s, i) => s + num(i.value), 0) || num(d.quotation_value);
const userName = (ref) => (ref && ref.full_name) || '';

/** Names of the branches a user belongs to. */
export function branchNamesOf(userId) {
  const e = state.employees.find((x) => x.user_id === userId);
  return e ? (e.branch_ids || []).map((id) => (state.branches.find((b) => b.id === id) || {}).name).filter(Boolean) : [];
}
/** A customer belongs to the branches of whoever added it or is assigned to it (reference: companyBranches). */
export function companyBranches(c) {
  const set = new Set();
  [c.createdById, ...(c.assignedIds || [])].filter((x) => x != null).forEach((id) => branchNamesOf(id).forEach((b) => set.add(b)));
  return [...set];
}

export async function loadReportData({ interactions = false, tasks = false, assignments = false } = {}) {
  const [cards, docs, payments, ints, taskList, calls] = await Promise.all([
    api.get('customers/cards/'),
    api.all('sales-documents/'),
    api.all('payment-collections/'),
    interactions ? api.all('interactions/') : [],
    tasks ? api.all(isAdmin() || isBranchManager() ? 'tasks/?scope=all' : 'tasks/') : [],
    assignments ? api.all('call-assignments/') : [],
  ]);
  const companies = cards.results.map((c) => ({
    id: c.id, name: c.name, plant: c.plant, area: c.area, city: c.city, state: c.state, pincode: c.pincode, industry: c.industry, source: c.source,
    potential: c.potential, gstNumber: c.gst_number, website: c.website, transportPreference: c.transport_preference, courierPreference: c.courier_preference,
    interestedBrands: c.interested_brands, interestedProducts: c.interested_products, preferredLanguages: c.preferred_languages,
    assignedTo: (c.assigned_to || []).map((u) => u.full_name), assignedIds: (c.assigned_to || []).map((u) => u.id),
    createdById: c.created_by ? c.created_by.id : null, createdByName: c.created_by_name || '', createdAt: c.created_at, lastCall: c.last_call, lastVisit: c.last_visit,
    contacts: (c.contacts || []).map((k) => ({ id: k.id, name: k.name, jobTitle: k.job_title, phone: k.phone, phone2: k.phone2, email: k.email, interactions: [] })),
  }));
  const byContact = new Map();
  companies.forEach((c) => c.contacts.forEach((k) => byContact.set(k.id, { company: c, contact: k })));
  const empName = (id) => (state.employees.find((e) => e.user_id === id) || {}).full_name || '';
  ints.forEach((i) => {
    const hit = byContact.get(i.contact_id); if (!hit) return;
    hit.contact.interactions.push({
      id: i.id, type: i.type, date: i.date, createdAt: i.created_at, notes: i.notes, userId: i.created_by ? i.created_by.id : null, userName: userName(i.created_by),
      followupDate: i.followup_date, isCopy: i.is_copy,
      jointWith: (i.joint_with_user_ids || []).map((id) => ({ id, name: empName(id) })),
      alsoMet: (i.also_met_contact_ids || []).map((id) => ({ name: (byContact.get(id) || { contact: {} }).contact.name })),
      location: i.location_lat != null ? { lat: i.location_lat, lng: i.location_lng } : null,
    });
  });
  const salesDocs = docs.map((d) => ({
    id: d.id, type: d.type, docNumber: d.doc_number, date: d.date, branch: d.branch_name, customerId: d.customer_id, customerName: d.customer_name || d.customer_label,
    contactId: d.contact_id, contactName: d.contact_name, contactPhone: d.contact_phone, orderStatus: d.order_status, lostReason: d.lost_reason, source: d.source,
    refId: d.reference_id, createdById: d.created_by ? d.created_by.id : null, createdByName: userName(d.created_by), createdAt: d.created_at, value: docValue(d),
    items: (d.items || []).map((i) => ({ itemName: i.item_name, qty: num(i.qty), value: num(i.value), balance: num(i.balance) })),
    callLog: (d.call_log || []).map((l) => ({ userId: l.user ? l.user.id : null, userName: userName(l.user), message: l.message, timestamp: l.timestamp, callLaterDate: l.call_later_date })),
  }));
  const pays = payments.map((p) => ({
    id: p.id, customerId: p.customer_id, customerName: p.customer_name, contactName: p.contact_name, branch: p.branch_name, amount: num(p.amount), received: num(p.received),
    balance: num(p.balance), date: p.date, createdAt: p.created_at, createdById: p.created_by ? p.created_by.id : null,
    receipts: (p.receipts || []).map((r) => ({ amount: num(r.amount), date: r.date, createdAt: r.created_at, recordedById: r.recorded_by ? r.recorded_by.id : null })),
    paymentLog: (p.contact_log || []).map((m) => ({ userId: m.user ? m.user.id : null, userName: userName(m.user), message: m.message, timestamp: m.timestamp, callLaterDate: m.call_later_date })),
  }));
  const taskRows = taskList.map((t) => ({
    id: t.id, status: t.status, dueDate: t.due_date, completedAt: t.completed_at, createdAt: t.created_at,
    assignees: (t.assignees || []).map((u) => u.id),
  }));
  const assigns = calls.map((a) => ({
    id: a.id, customerId: a.customer_id, customerName: a.customer_name, contactId: a.contact_id, contactName: a.contact_name, status: a.status, weekOf: a.week_of,
    remarks: a.remarks, calledAt: a.called_at, calledById: a.called_by ? a.called_by.id : null, calledByName: userName(a.called_by),
    assignedToId: a.assigned_to ? a.assigned_to.id : null, assignedToName: userName(a.assigned_to),
    attempts: (a.attempts || []).map((t) => ({ reason: t.reason, note: t.note, at: t.created_at || t.at, callAgainDate: t.call_again_date, byId: t.by ? t.by.id : (t.user ? t.user.id : null), byName: userName(t.by || t.user) })),
  }));
  return { companies, salesDocs, payments: pays, tasks: taskRows, assignments: assigns };
}
