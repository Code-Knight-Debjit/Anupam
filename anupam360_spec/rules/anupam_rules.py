"""
Anupam 360 — business rules as pure Python (no Django, no I/O).

These functions are a faithful port of the behaviour of the reference standalone HTML app
(contact_management.html). Use them in two ways:
  1. As the *specification* the tests in ../tests check.
  2. Inside your Django project (services layer / model methods / DRF permissions) so the web app
     behaves exactly like the reference.

All inputs are plain dicts that mirror the JSON the HTML app stores (see REQUIREMENTS.md section 3).
"""
from __future__ import annotations
import math
import re
from datetime import date, datetime, timedelta

ROLES = ("Admin", "Branch Manager", "Branch Staff", "Sales Manager")

# --------------------------------------------------------------------------- roles & permissions
def is_admin(u): return u.get("role") == "Admin"
def is_bm(u): return u.get("role") == "Branch Manager"
def is_bs(u): return u.get("role") == "Branch Staff"
def is_sm(u): return u.get("role") == "Sales Manager"

def can_direct_edit_delete(u): return is_admin(u) or is_bm(u)                      # bulk assign, exports, doc approvals
def can_edit_customer_direct(u): return is_admin(u) or is_bm(u) or is_bs(u)
def can_delete_customer_direct(u): return is_admin(u) or is_bm(u)
def can_direct_edit_delete_sales_doc(u): return is_admin(u) or is_bm(u) or is_bs(u)
def can_see_all_users_reports(u): return is_admin(u) or is_bm(u)
def uses_personal_dashboard(u): return not is_admin(u)                            # only Admin sees the full dashboard
def is_approver(u): return is_admin(u) or is_bm(u)

def needs_approval(u, action: str) -> bool:
    """Sales Manager edits/deletes of customers, contacts and enquiries go to Admin/Branch Manager."""
    if action in ("customer.edit", "contact.edit"):
        return not can_edit_customer_direct(u)
    if action == "customer.delete":
        return not can_delete_customer_direct(u)
    if action in ("salesdoc.edit", "salesdoc.delete"):
        return not can_direct_edit_delete_sales_doc(u)
    raise ValueError(action)

NAV_ALL = ["Dashboard", "Task", "Outreach", "Attendance", "Customer", "Map & Nearby", "Enquiry", "Quotation",
           "Proforma Invoice", "Delivery Challan", "Pending PO", "Payment Collection", "Print Label", "Reports",
           "Manage lists", "Import Excel", "Backup & restore", "Users", "Branch"]
ADMIN_ONLY_NAV = {"Manage lists", "Import Excel", "Backup & restore", "Users", "Branch"}
SALES_MANAGER_HIDDEN_NAV = {"Proforma Invoice", "Delivery Challan", "Pending PO", "Payment Collection", "Print Label"}

def nav_visible(u) -> list[str]:
    out = []
    for item in NAV_ALL:
        if item in ADMIN_ONLY_NAV and not is_admin(u): continue
        if is_sm(u) and item in SALES_MANAGER_HIDDEN_NAV: continue
        out.append(item)
    return out

REPORT_TABS = ["Sales Performance", "Customer Activity", "Not Contacted", "User Performance", "Sales Reports",
               "Customer Reports", "Payment Collection", "Interaction Log"]
def report_tabs_visible(u) -> list[str]:
    return [t for t in REPORT_TABS if not (is_sm(u) and t in ("Sales Performance", "Customer Activity"))]

# --------------------------------------------------------------------------- customers / contacts
def assigned_to(company) -> list[str]:
    a = company.get("assignedTo")
    if not a: return []
    return list(a) if isinstance(a, (list, tuple)) else [a]

def visible_companies(u, companies):
    if is_admin(u) or is_bm(u) or is_bs(u): return list(companies)
    return [c for c in companies if c.get("createdById") == u["id"] or u["name"] in assigned_to(c)]

def visible_contacts(u, company):
    """company['contactAccess'] = {person name: [contact ids]}. No entry => all contacts."""
    contacts = company.get("contacts") or []
    acc = company.get("contactAccess")
    if not acc or is_admin(u) or is_bm(u) or is_bs(u) or company.get("createdById") == u["id"]:
        return contacts
    ids = acc.get(u["name"])
    return [c for c in contacts if c["id"] in ids] if isinstance(ids, list) else contacts

def assign_customer(company, staff_name, contact_ids=None):
    """Assign (add) a person to a customer, optionally sharing only some contacts. Returns the company."""
    arr = assigned_to(company)
    if staff_name not in arr: arr.append(staff_name)
    company["assignedTo"] = arr
    total = len(company.get("contacts") or [])
    acc = dict(company.get("contactAccess") or {})
    if contact_ids is None or len(contact_ids) >= total: acc.pop(staff_name, None)
    else: acc[staff_name] = list(contact_ids)
    if acc: company["contactAccess"] = acc
    else: company.pop("contactAccess", None)
    return company

def deassign_customer(company, staff_name):
    company["assignedTo"] = [n for n in assigned_to(company) if n != staff_name]
    acc = dict(company.get("contactAccess") or {})
    acc.pop(staff_name, None)
    if acc: company["contactAccess"] = acc
    else: company.pop("contactAccess", None)
    return company

def company_label(c) -> str:
    plant = (c.get("plant") or "").strip()
    return f"{c.get('name')} — {plant}" if plant else (c.get("name") or "")

def company_select_label(c) -> str:
    """Customer pick-lists show: Customer name, Plant, Area (never city)."""
    return ", ".join(x for x in ((c.get(k) or "").strip() for k in ("name", "plant", "area")) if x)

def search_customers(options: list[str], query: str) -> list[str]:
    """Type 'su': names starting with it first, then names where a later word starts with it, then 'contains'."""
    q = query.strip().lower()
    if not q: return list(options)
    starts, words, contains = [], [], []
    for o in options:
        t = o.lower()
        if t.startswith(q): starts.append(o)
        elif any(w.startswith(q) for w in re.split(r"[\s,.\-()/&]+", t)): words.append(o)
        elif q in t: contains.append(o)
    return starts + words + contains

def levenshtein(a: str, b: str) -> int:
    if not a: return len(b)
    if not b: return len(a)
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i]
        for j in range(1, len(b) + 1):
            cur.append(prev[j - 1] if a[i - 1] == b[j - 1] else 1 + min(prev[j - 1], prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]

def name_similarity(a: str, b: str) -> float:
    if not a or not b: return 0.0
    return 1 - levenshtein(a, b) / (max(len(a), len(b)) or 1)

def near_duplicate(new_name: str, existing_name: str) -> bool:
    n, e = new_name.strip().lower(), existing_name.strip().lower()
    return name_similarity(n, e) >= (0.65 if len(n) <= 4 else 0.8)

def title_case_words(s: str) -> str:
    return re.sub(r"(^|[\s\-/(&.,])([a-z])", lambda m: m.group(1) + m.group(2).upper(), s or "")

# --------------------------------------------------------------------------- sales documents
DEFAULT_NUMBERING = {"enquiry": ("ENQ", "", 1), "quotation": ("QUO", "", 1), "dc": ("DC", "", 1),
                     "proforma": ("PI", "", 1), "sales": ("SL", "", 1), "purchase": ("PUR", "", 1)}
# NOTE: Pending PO ("po") has NO generated number — its number is the customer's own PO number, typed by the user.
PIPELINE = {"enquiry": None, "quotation": "enquiry", "proforma": "quotation", "po": None, "dc": "po"}  # linked-document type
STATUSES = {"enquiry": ["Pending", "Completed", "Regretted"], "quotation": ["Pending", "Win", "Lose"],
            "proforma": ["Pending", "Win", "Lose"], "po": ["Pending", "Part Pending", "Hold", "Completed"], "dc": []}

def numbering_cfg(doc_type: str, branch_cfg: dict | None = None) -> dict:
    """Per-branch override of prefix/suffix/start. Empty prefix -> default prefix; suffix '' is allowed (means none)."""
    d_prefix, d_suffix, d_start = DEFAULT_NUMBERING.get(doc_type, ("", "", 1))
    c = (branch_cfg or {}).get(doc_type) or {}
    return {"prefix": c["prefix"] if c.get("prefix") not in (None, "") else d_prefix,
            "suffix": c["suffix"] if c.get("suffix") is not None else d_suffix,
            "start": int(c["start"]) if c.get("start") not in (None, "") else d_start}

def format_doc_number(cfg: dict, seq: int) -> str:
    """PREFIX-0001 or PREFIX-0001-SUFFIX  (sequence zero-padded to 4 digits; hyphens only where a part exists)."""
    return f"{cfg['prefix']}{'-' if cfg['prefix'] else ''}{str(seq).zfill(4)}{('-' + cfg['suffix']) if cfg['suffix'] else ''}"

def doc_number_seq(doc_number: str) -> int:
    """The sequence is the FIRST run of digits in the number (so 'QUO-0007-26-27' -> 7)."""
    m = re.search(r"\d+", str(doc_number or ""))
    return int(m.group(0)) if m else 0

def next_doc_number(counters: dict, doc_type: str, branch: str, branch_cfg: dict | None = None) -> str:
    cfg = numbering_cfg(doc_type, branch_cfg)
    cur = counters.get(f"{doc_type}::{branch or '_default'}")
    return format_doc_number(cfg, cfg["start"] if cur is None else cur + 1)

def bump_counter(counters: dict, doc_type: str, branch: str, doc_number: str) -> dict:
    """Counter only moves forward — deleting documents never frees a number; a manually typed higher number pushes it up."""
    key = f"{doc_type}::{branch or '_default'}"
    seq = doc_number_seq(doc_number)
    if seq > counters.get(key, 0): counters[key] = seq
    return counters

def seed_counters(counters: dict, docs: list) -> dict:
    """On start-up the counters are rebuilt from existing documents so numbering always continues upward."""
    for d in docs:
        key = f"{d['type']}::{d.get('branch') or ''}" if d.get("branch") else f"{d['type']}::_default"
        counters[key] = max(counters.get(key, 0), doc_number_seq(d.get("docNumber")))
    return counters

def line_amounts(item: dict, has_discount=True, has_tax=True) -> dict:
    qty = item.get("qty") or 0
    rate = item.get("rate") or 0
    unit = rate * (1 - (item.get("discount") or 0) / 100) if has_discount else rate
    if has_discount and has_tax: unit *= 1 + (item.get("tax") or 0) / 100
    return {"amount": unit, "value": qty * unit}

def doc_total(items, packing=0, packing_tax=0, freight=0, freight_tax=0, other=0, other_tax=0, round_off=0,
              has_discount=True, has_tax=True) -> dict:
    sub = sum(line_amounts(i, has_discount, has_tax)["value"] for i in items)
    total = sub + packing * (1 + packing_tax / 100) + freight * (1 + freight_tax / 100) + other * (1 + other_tax / 100) + round_off
    return {"subTotal": sub, "totalAmount": total}

def visible_sales_docs(u, doc_type, docs, companies):
    allt = [d for d in docs if d["type"] == doc_type]
    if is_admin(u) or is_bm(u) or is_bs(u): return allt
    if is_sm(u) and doc_type in ("quotation", "enquiry"):
        out = []
        for d in allt:
            comp = next((c for c in companies if c["id"] == d.get("customerId")), None)
            if d.get("createdById") == u["id"] or (comp and u["name"] in assigned_to(comp)): out.append(d)
        return out
    return [d for d in allt if d.get("createdById") == u["id"]]

# --------------------------------------------------------------------------- PO / delivery
def item_supplied(item): return sum(float(r.get("qtySupplied") or 0) for r in item.get("supplyLog") or [])
def item_pending(item): return max(0, float(item.get("qty") or 0) - item_supplied(item))
def item_invoiced(item): return sum(float(r.get("qtyInvoiced") or 0) for r in item.get("invoiceLog") or [])
def item_balance(item): return max(0, float(item.get("qty") or 0) - item_invoiced(item))

def recompute_po_status(doc: dict) -> dict:
    """Automatic PO status from supply log; 'Hold' is manual and never overwritten."""
    if doc.get("type") != "po" or doc.get("orderStatus") == "Hold": return doc
    items = doc.get("items") or []
    ordered = sum(float(i.get("qty") or 0) for i in items)
    pending = sum(item_pending(i) for i in items)
    if ordered > 0 and pending <= 0: doc["orderStatus"] = "Completed"
    elif pending == ordered: doc["orderStatus"] = "Pending"
    else: doc["orderStatus"] = "Part Pending"
    return doc

# --------------------------------------------------------------------------- payments
def payment_received(p): return sum(float(r.get("amount") or 0) for r in p.get("receivedLog") or [])
def payment_balance(p): return max(0, float(p.get("amount") or 0) - payment_received(p))
def payment_overpay_needs_confirm(p, amount) -> bool: return amount > payment_balance(p)

# --------------------------------------------------------------------------- tasks
TASK_KINDS = ("Call", "Visit", "Appointment", "Task")
def task_assignees(t):
    if t.get("assignees"): return t["assignees"]
    return [{"id": t["assignedToId"], "name": t.get("assignedToName", "")}] if t.get("assignedToId") else []
def task_assigned_to(t, uid): return any(a["id"] == uid for a in task_assignees(t))
def task_kind(t):
    if t.get("taskType") in TASK_KINDS: return t["taskType"]
    title = (t.get("title") or "").strip()
    for k in ("Call", "Visit", "Appointment"):
        if re.match(rf"^{k}\b", title, re.I): return k
    return "Task"

def visible_tasks(u, tasks, scope_names=frozenset()):
    if is_admin(u) or is_bm(u): return list(tasks)
    if is_bs(u):
        return [t for t in tasks if any(a["name"] in scope_names for a in task_assignees(t)) or t.get("createdByName") in scope_names
                or task_assigned_to(t, u["id"]) or t.get("createdById") == u["id"]]
    return [t for t in tasks if task_assigned_to(t, u["id"]) or t.get("createdById") == u["id"]]

def main_task_list(u, tasks, scope="mine", scope_names=frozenset()):
    """Task page main list = the viewer's OWN tasks. Admin/BM may switch to scope='all'."""
    vis = visible_tasks(u, tasks, scope_names)
    if (is_admin(u) or is_bm(u)) and scope == "all": return vis
    return [t for t in vis if task_assigned_to(t, u["id"])]

def assigned_by_me(u, tasks):
    """Separate panel under the calendar: tasks I created that are assigned to others."""
    return [t for t in tasks if t.get("createdById") == u["id"] and not task_assigned_to(t, u["id"])]

def can_manage_task(u, t): return is_admin(u) or is_bm(u) or t.get("createdById") == u["id"]
def can_update_task_status(u, t): return can_manage_task(u, t) or task_assigned_to(t, u["id"])
def can_remove_task(u, t): return t.get("createdById") == u["id"]   # ONLY the creator removes a task

def complete_task(t, by_name, now=None):
    t["status"] = "Done"; t["completedAt"] = (now or datetime.now()).isoformat(); t["completedByName"] = by_name
    return t

def remove_task(u, t, tasks):
    """Removing is creator-only; the task vanishes from both creator and assignee lists."""
    if not can_remove_task(u, t): raise PermissionError("only the creator can remove a task")
    tasks.remove(t); return tasks

# --------------------------------------------------------------------------- interactions
def log_interaction(contact, company, user, type_, date_, notes="", followup_date="", also_met=(), joint_with=(), tasks=None):
    """Port of the contact-profile 'log interaction' behaviour. Returns the created interaction."""
    tasks = tasks if tasks is not None else []
    if type_ == "Appointment" and not followup_date:
        raise ValueError("appointment needs the appointment date")
    it = {"type": type_, "date": date_, "notes": notes, "userId": user["id"], "userName": user["name"],
          "followupDate": followup_date if type_ in ("Call", "Visit", "Appointment") else "",
          "alsoMet": [{"id": o["id"], "name": o["name"]} for o in also_met] if type_ == "Visit" else [],
          "jointWith": [{"id": e["id"], "name": e["name"]} for e in joint_with] if type_ in ("Visit", "Appointment") else []}
    contact.setdefault("interactions", []).append(it)
    if type_ == "Visit":
        for o in also_met:                                    # copy flagged so counts don't double count
            o.setdefault("interactions", []).append({"type": type_, "date": date_, "notes": notes, "userId": user["id"],
                                                     "userName": user["name"], "isCopy": True, "metWithName": contact["name"]})
    if it["followupDate"]:                                    # follow-up request becomes a task
        tasks.append({"title": f"{type_} {contact['name']} — {company['name']}", "assignedToId": user["id"],
                      "assignedToName": user["name"], "taskType": type_, "status": "Open", "dueDate": it["followupDate"],
                      "relatedContactId": contact["id"], "createdById": user["id"], "createdByName": user["name"]})
    if type_ == "Visit":                                      # a visit completes this contact's open appointment tasks
        for t in tasks:
            if t.get("relatedContactId") == contact["id"] and t["status"] != "Done" and task_kind(t) == "Appointment":
                t["status"] = "Done"; t["autoClosedByVisit"] = True
    for e in joint_with:                                      # each joint member gets their own task
        tasks.append({"title": f"Joint {type_.lower()} with {user['name']} — {contact['name']}, {company['name']}",
                      "assignedToId": e["id"], "assignedToName": e["name"], "taskType": type_, "status": "Open",
                      "dueDate": followup_date or date_, "relatedContactId": contact["id"],
                      "createdById": user["id"], "createdByName": user["name"]})
    return it

def appointments_not_visited(contact, user_id) -> int:
    ints = contact.get("interactions") or []
    n = 0
    for ap in ints:
        if ap["type"] != "Appointment" or ap.get("isCopy"): continue
        if not (ap["userId"] == user_id or any(j["id"] == user_id for j in ap.get("jointWith") or [])): continue
        if not any(v["type"] == "Visit" and v["date"] >= ap["date"] for v in ints): n += 1
    return n

def visit_percent_of_appointments(appointments: int, visited: int) -> int:
    return round(visited / appointments * 100) if appointments else 0

# --------------------------------------------------------------------------- attendance
ATT_GRACE_MIN = 10
ATT_DEFAULT_START, ATT_DEFAULT_END = "09:30", "18:30"
def _min(hm): h, m = hm.split(":"); return int(h) * 60 + int(m)

def att_day_status(emp, day: str, records, holidays, leaves, today: str, attendance_start: str = "") -> dict:
    """Return {code: P|L|H|A|LV|O|'', late: minutes, worked: minutes|None}. Mirrors attDayStatus()."""
    rec = next((r for r in records if r["userId"] == emp["id"] and r["date"] == day), None)
    out = {"code": "", "late": 0, "worked": None}
    if rec and rec.get("checkIn") and rec.get("checkOut"):
        w = _min(rec["checkOut"]) - _min(rec["checkIn"])
        if w >= 0: out["worked"] = w
    if rec and rec.get("checkIn"):
        l = _min(rec["checkIn"]) - _min(emp.get("workStart") or ATT_DEFAULT_START)
        if l > ATT_GRACE_MIN: out["late"] = l
    start_from = emp["doj"] if emp.get("doj") and emp["doj"] > attendance_start else attendance_start
    if start_from and day < start_from and not rec: return out
    if rec and rec.get("status"):
        m = {"Present": "P", "Half day": "H", "Absent": "A", "Leave": "LV", "Off / Holiday": "O"}.get(rec["status"])
        if m: out["code"] = m; return out
    if rec and rec.get("checkIn"): out["code"] = "L" if out["late"] else "P"; return out
    eb = set(emp.get("branches") or [])
    if any(h["from"] <= day <= h["to"] and (h.get("all") or eb & set(h.get("branches") or [])) for h in holidays):
        out["code"] = "O"; return out
    weekly = str(emp.get("weeklyOff", "0"))
    off = [] if weekly == "" else [int(x) for x in weekly.split(",")]
    dow = (date.fromisoformat(day).weekday() + 1) % 7        # JS getDay(): Sunday = 0
    if dow in off: out["code"] = "O"; return out
    if any(l["userId"] == emp["id"] and l["status"] == "Approved" and l["from"] <= day <= l["to"] for l in leaves):
        out["code"] = "LV"; return out
    if day < today: out["code"] = "A"
    return out

def att_tally(statuses) -> dict:
    t = dict(present=0, late=0, half=0, absent=0, leave=0, off=0, worked=0)
    for s in statuses:
        c = s["code"]
        if c == "P": t["present"] += 1
        elif c == "L": t["present"] += 1; t["late"] += 1
        elif c == "H": t["half"] += 1
        elif c == "A": t["absent"] += 1
        elif c == "LV": t["leave"] += 1
        elif c == "O": t["off"] += 1
        if s.get("worked"): t["worked"] += s["worked"]
    return t

def att_team(u, employees, scope_names=frozenset()):
    if is_admin(u): return [e for e in employees if e.get("active", True)]
    if is_bm(u): return [e for e in employees if e.get("active", True) and e["name"] in scope_names]
    return []

def can_decide_leave(u, leave, team_ids) -> bool:
    if is_admin(u): return True
    return is_bm(u) and leave["userId"] != u["id"] and leave["userId"] in team_ids

def check_in(records, user, today, now_hm, location):
    """Check-in needs a location for EVERY role; the location is stored on the record."""
    if not location: raise ValueError("location required")
    if any(r["userId"] == user["id"] and r["date"] == today and r.get("checkIn") for r in records): return records
    records.append({"userId": user["id"], "date": today, "checkIn": now_hm, "inLoc": location}); return records

def check_out(records, user, today, now_hm, location):
    rec = next((r for r in records if r["userId"] == user["id"] and r["date"] == today), None)
    if not rec or not rec.get("checkIn"): raise ValueError("check in first")
    if _min(now_hm) < _min(rec["checkIn"]): raise ValueError("check-out cannot be before check-in")
    if not location: raise ValueError("location required")
    rec["checkOut"] = now_hm; rec["outLoc"] = location; return rec

# --------------------------------------------------------------------------- shipping labels
LABEL_SIZES = {"a4": (210, 297), "a5": (148, 210), "4x4": (101.6, 101.6), "6x4": (101.6, 152.4)}
SHEET = (210, 297)
LABEL_DEFAULTS = {"paper": "a4", "size": "a5", "from_scale": 1.5, "print_attn": False, "print_phone": False, "boxes": 1}
FROM_SCALES = (1, 1.25, 1.5, 2)

def label_sheet_plan(size_key: str, boxes: int, on_sheet: bool = True) -> dict:
    """Labels keep their ORIGINAL size. On the A4 sheet smaller labels are tiled (A5 = half sheet, landscape sheet;
    4x4 = four per sheet; 6x4 = two per sheet); paper 'label' = page is the label size."""
    w, h = LABEL_SIZES[size_key]
    if not on_sheet: return {"page": (w, h), "per_page": 1, "pages": boxes}
    if w >= SHEET[0] or h >= SHEET[1]: return {"page": SHEET, "per_page": 1, "pages": boxes}
    best = None
    for sw, sh in (SHEET, SHEET[::-1]):
        for m in (5, 0):
            cols, rows = math.floor((sw - 2 * m) / w), math.floor((sh - 2 * m) / h)
            if cols >= 1 and rows >= 1 and (best is None or cols * rows > best["per_page"]):
                best = {"page": (sw, sh), "per_page": cols * rows, "cols": cols, "rows": rows, "margin": m}
    best["pages"] = math.ceil(boxes / best["per_page"])
    return best

def label_content(party: dict, print_attn=False, print_phone=False) -> dict:
    """What is printed. Order top->bottom: DELIVER TO (name, address, AREA in bold, city/state, PIN, optional Attn/phone),
    transport/courier/vehicle, BOX n OF m bar, then FROM block (logo + company + address) always last. No Ref/Date."""
    return {"deliver_to": party.get("customer"), "address": party.get("addrLines", []), "area_bold": party.get("area", ""),
            "city": party.get("cityLine", ""), "pin": party.get("pin", ""),
            "attn": party.get("attn", "") if print_attn else "", "phone": party.get("phone", "") if print_phone else "",
            "meta": [m for m in (("TRANSPORT", party.get("transport")), ("COURIER", party.get("courier")), ("VEHICLE", party.get("vehicle"))) if m[1]],
            "from_at_bottom": True}

def label_deliver_to(typed_name: str, picked_company: dict | None) -> str:
    """Typed 'Deliver to' wins; otherwise the picked customer's name."""
    return (typed_name or "").strip() or ((picked_company or {}).get("name", "").strip() if picked_company else "")

# --------------------------------------------------------------------------- backup / numbering of keys
BACKUP_KEYS = ["employees", "branches", "companies", "salesDocs", "docCounters", "payments", "tasks", "callAssignments",
               "notifications", "approvals", "attendance", "leaveRequests", "holidays", "attendanceStart", "stockProducts",
               "suppliers", "stockBills", "stockTransactions", "sources", "jobTitles", "industries", "brands", "products",
               "categories", "units", "taxRates", "salesPersons", "paymentTerms", "languages", "transportList", "courierList"]


# =========================================================================== AUTOMATIONS (side effects)
# --------------------------------------------------------------------------- outreach (weekly call list)
def monday_of(d: str) -> str:
    dt = date.fromisoformat(d)
    return (dt - timedelta(days=dt.weekday())).isoformat()

def assign_outreach(assignments: list, companies: list, company_ids, staff: dict, by: dict, week_raw: str, visible_ids=None):
    """One entry per contact; DND contacts skipped; a customer with no contacts gets one blank entry;
    the same (customer, contact, staff, week) is never added twice. weekOf is always the Monday.
    NOTE: contacts are taken from the *assigner's* view in the reference app (known gap REQ-OUT-GAP);
    pass `respect_assignee_access=True` semantics by filtering with visible_contacts(staff, c) in Django."""
    week = monday_of(week_raw)
    added = skipped = dnd = 0
    for c in companies:
        if c["id"] not in set(company_ids): continue
        if visible_ids is not None and c["id"] not in visible_ids: continue
        allc = c.get("contacts") or []
        targets = [x for x in allc if not x.get("dnd")] if allc else [None]
        dnd += len(allc) - (len(targets) if allc else 0)
        for ct in targets:
            cid = ct["id"] if ct else ""
            if any(a["customerId"] == c["id"] and a.get("contactId", "") == cid and a["assignedToId"] == staff["id"] and a["weekOf"] == week for a in assignments):
                skipped += 1; continue
            assignments.append({"customerId": c["id"], "contactId": cid, "contactName": ct["name"] if ct else "", "weekOf": week,
                                "status": "Pending", "assignedToId": staff["id"], "assignedById": by["id"]})
            added += 1
    return {"added": added, "skipped": skipped, "dnd_skipped": dnd}

# --------------------------------------------------------------------------- notifications
def notify(notifs: list, user_id, type_, text, **extra):
    notifs.append({"userId": user_id, "type": type_, "text": text, "read": False, **extra}); return notifs

def request_customer_access(approvals, notifs, employees, user, company):
    """Creates a 'customer-access' approval and notifies every Admin and Branch Manager. One pending request per user+customer."""
    if any(a["type"] == "customer-access" and a["companyId"] == company["id"] and a["requestedById"] == user["id"] for a in approvals):
        raise ValueError("already pending")
    approvals.append({"type": "customer-access", "companyId": company["id"], "requestedById": user["id"], "requestedByName": user["name"]})
    for e in employees:
        if e["role"] in ("Admin", "Branch Manager"):
            notify(notifs, e["id"], "customer-access-request", f'{user["name"]} requested access to customer "{company["name"]}".')
    return approvals

def approve_request(req, companies, approvals, notifs):
    """Approval applies the change. edit -> replace with proposed data; delete -> remove; customer-access -> add requester to assignedTo
    (and tell the requester). The request is removed from the pending list."""
    idx = next((i for i, c in enumerate(companies) if c["id"] == req.get("companyId")), -1)
    if req["type"] == "delete": companies[:] = [c for c in companies if c["id"] != req["companyId"]]
    elif req["type"] == "edit" and idx > -1: companies[idx] = req["proposedData"]
    elif req["type"] == "customer-access" and idx > -1:
        arr = assigned_to(companies[idx])
        if req["requestedByName"] not in arr: companies[idx] = {**companies[idx], "assignedTo": arr + [req["requestedByName"]]}
        notify(notifs, req["requestedById"], "customer-access-approved", f'Your access request for "{req["companyName"]}" was approved.')
    approvals[:] = [a for a in approvals if a is not req]
    return companies

def reject_request(req, approvals, notifs):
    approvals[:] = [a for a in approvals if a is not req]
    if req["type"] == "customer-access":
        notify(notifs, req["requestedById"], "customer-access-declined", f'Your access request for "{req["companyName"]}" was declined.')

def set_task_status(task, status, user, notifs, now=None):
    """Assignee marks Done -> the task's creator is told to verify (not if creator did it themself, nor if already Done)."""
    if not can_update_task_status(user, task): raise PermissionError("not allowed")
    was_done = task["status"] == "Done"
    task["status"] = status
    task["completedAt"] = (now or datetime.now()).isoformat() if status == "Done" else ""
    task["completedByName"] = user["name"] if status == "Done" else ""
    if status == "Done" and not was_done and task.get("createdById") and task["createdById"] != user["id"]:
        notify(notifs, task["createdById"], "task_done", f'{user["name"]} completed the task "{task["title"]}" — verify and mark it complete.')
    return task

def delete_task(user, task, tasks, notifs):
    """Creator-only. If the task was Done and the remover can manage it -> 'acknowledge': assignees are told it was verified.
    Otherwise the creator (if someone else) is told it was removed."""
    if not can_remove_task(user, task): raise PermissionError("only the creator can remove a task")
    acknowledging = task["status"] == "Done" and can_manage_task(user, task)
    tasks.remove(task)
    if task.get("createdById") and task["createdById"] != user["id"] and not acknowledging:
        notify(notifs, task["createdById"], "task_removed", f'{user["name"]} removed the task "{task["title"]}"')
    if acknowledging:
        for a in task_assignees(task):
            if a["id"] != user["id"]: notify(notifs, a["id"], "task_verified", f'{user["name"]} verified and marked "{task["title"]}" as complete.')
    return tasks

def create_task_for(user, assignees: list, title, due, tasks, notifs):
    """Assigning a task to others notifies each of them (not yourself)."""
    t = {"title": title, "assignees": [{"id": a["id"], "name": a["name"]} for a in assignees], "assignedToId": assignees[0]["id"],
         "assignedToName": assignees[0]["name"], "status": "Open", "dueDate": due, "createdById": user["id"], "createdByName": user["name"]}
    tasks.append(t)
    for a in assignees:
        if a["id"] != user["id"]: notify(notifs, a["id"], "task", f'{user["name"]} assigned you a task: "{title}"')
    return t

def schedule_from_sales_doc(user, doc, kind, due, who, tasks, notifs):
    """From a sales document: schedule a Call/Visit/Appointment task for someone; linked to the document; notifies the assignee."""
    who_name = doc.get("contactName") or "contact"
    title = f"Appointment with {who_name} — {doc.get('customerName','')}" if kind == "Appointment" else f"{kind} {who_name} — {doc.get('customerName','')}"
    t = {"title": title, "assignedToId": who["id"], "assignedToName": who["name"], "taskType": kind, "status": "Open", "dueDate": due,
         "relatedDocId": doc["id"], "relatedDocNumber": doc.get("docNumber", ""), "createdById": user["id"], "createdByName": user["name"]}
    tasks.append(t)
    if who["id"] != user["id"]: notify(notifs, who["id"], "task", f'{user["name"]} scheduled a {kind.lower()} for you: "{title}"')
    return t

def request_leave(leaves, notifs, employees, user, frm, to):
    leaves.append({"userId": user["id"], "from": frm, "to": to, "status": "Pending"})
    for e in employees:
        if e["role"] == "Admin" and e["id"] != user["id"]: notify(notifs, e["id"], "leave", f'{user["name"]} requested leave: {frm} – {to}.')
    return leaves

def decide_leave(leave, status, by, notifs, note=""):
    leave["status"] = status
    notify(notifs, leave["userId"], "leave", f'Your leave ({leave["from"]} – {leave["to"]}) was {status.lower()} by {by["name"]}.' + (f" {note}" if note else ""))
    return leave

def announce_holiday(notifs, employees, name, frm, to, branches=None):
    for e in employees:
        if branches is None or set(e.get("branches") or []) & set(branches): notify(notifs, e["id"], "leave", f"Holiday: {name} on {frm}" + (f" – {to}" if to != frm else ""))
    return notifs

# --------------------------------------------------------------------------- label auto-fill
def label_autofill_from_customer(company: dict, contact: dict | None = None) -> dict:
    """Custom label: picking a customer fills Deliver-to name + address + area/city/state/pin, transport/courier preference;
    the person (Attn) and phone are filled ONLY if the user explicitly picks a contact."""
    out = {"customer": company.get("name", ""), "address": company.get("address", ""), "area": company.get("area", ""), "city": company.get("city", ""),
           "state": company.get("state", ""), "pin": company.get("pincode", ""), "transport": company.get("transportPreference", ""),
           "courier": company.get("courierPreference", ""), "attn": "", "phone": ""}
    if contact: out["attn"] = contact.get("name", ""); out["phone"] = (contact.get("phones") or [""])[0] if isinstance(contact.get("phones"), list) else contact.get("phone", "")
    return out


# =========================================================================== SALES: print totals, words, outcomes, supply, invoice
def quotation_print_totals(doc: dict) -> dict:
    """Totals as PRINTED on Quotation / Proforma / Challan PDFs (differs from the entry-form total).
    * show_discount OFF (default): discount is folded into the rate and the rate is ROUNDED to a whole rupee; amount = qty x that rate.
    * show_discount ON: rate shown as entered, amount = qty x rate x (1 - disc%).
    * Line tax is NOT in the line amount: all line tax is totalled into one 'Tax Amount' after Sub Total.
    * total = subtotal + tax + packing(+tax) + freight(+tax) + other(+tax) + round-off."""
    show = bool(doc.get("showDiscountInPdf"))
    sub = tax_total = 0.0
    lines = []
    for i, it in enumerate(doc.get("items") or [], 1):
        qty, rate = float(it.get("qty") or 0), float(it.get("rate") or 0)
        disc, tax = float(it.get("discount") or 0), float(it.get("tax") or 0)
        if show: disp, amt = rate, qty * rate * (1 - disc / 100)
        else:
            disp = _js_round(rate * (1 - disc / 100)); amt = qty * disp
        t = amt * tax / 100; sub += amt; tax_total += t
        name = f"{it.get('itemName') or '—'} ({it['make']})" if it.get("make") else (it.get("itemName") or "—")
        lines.append({"sr": i, "name": name, "qty": qty, "rate": disp, "amount": amt, "tax": t})
    ch = lambda k, tk: float(doc.get(k) or 0) * (1 + float(doc.get(tk) or 0) / 100)
    total = sub + tax_total + ch("packingCharges", "packingTax") + ch("freightCharges", "freightTax") + ch("otherCharges", "otherChargesTax") + float(doc.get("roundOff") or 0)
    return {"lines": lines, "subTotal": sub, "taxTotal": tax_total, "total": total}

def _js_round(x: float) -> int:
    """JavaScript Math.round (half up), not Python's banker's rounding."""
    return math.floor(x + 0.5)

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen",
         "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
def number_to_words_indian(n: int) -> str:
    def two(x): return _ONES[x] if x < 20 else _TENS[x // 10] + (" " + _ONES[x % 10] if x % 10 else "")
    def three(x): return two(x) if x < 100 else _ONES[x // 100] + " Hundred" + (" " + two(x % 100) if x % 100 else "")
    n = int(n)
    if n == 0: return "Zero"
    parts = []
    for div, name in ((10000000, "Crore"), (100000, "Lakh"), (1000, "Thousand")):
        q, n = divmod(n, div)
        if q: parts.append(two(q) + " " + name)
    if n: parts.append(three(n))
    return " ".join(parts)

def amount_in_words(amount: float) -> str:
    amount = _js_round(float(amount or 0) * 100) / 100
    rupees = int(abs(amount)); paise = _js_round((abs(amount) - rupees) * 100)
    w = "Rupees " + number_to_words_indian(rupees)
    if paise > 0: w += " and " + number_to_words_indian(paise) + " Paise"
    w += " Only"
    return ("Minus " + w) if amount < 0 else w

def quotation_value_of(doc: dict) -> float:
    """Value used in reports: totalAmount if stored, else sum of item values, else legacy quotationValue."""
    if doc.get("totalAmount") is not None: return float(doc["totalAmount"] or 0)
    if doc.get("items"):
        t = 0.0
        for it in doc["items"]:
            if it.get("value") is not None: t += float(it["value"] or 0)
            else: t += float(it.get("qty") or 0) * float(it.get("rate") or 0) * (1 - float(it.get("discount") or 0) / 100) * (1 + float(it.get("tax") or 0) / 100)
        return t
    return float(doc.get("quotationValue") or 0)

def on_quotation_saved(quotation: dict, docs: list) -> str | None:
    """Saving a quotation that was created FROM an enquiry marks that enquiry 'Completed' (returns its number if it changed)."""
    if quotation.get("type") == "quotation" and quotation.get("refId"):
        enq = next((d for d in docs if d["id"] == quotation["refId"] and d["type"] == "enquiry"), None)
        if enq and enq.get("orderStatus") != "Completed":
            enq["orderStatus"] = "Completed"; return enq.get("docNumber")
    return None

def mark_outcome(doc: dict, status: str, order_value=None, lost_reason: str = "") -> dict:
    """Win needs an Order Value (stored as orderValue, clears lostReason). Lose stores the reason."""
    if doc["type"] not in ("quotation", "proforma"): raise ValueError("only quotation/proforma have Win/Lose")
    if status == "Win":
        if order_value in (None, ""): raise ValueError("order value required")
        doc["orderStatus"] = "Win"; doc["orderValue"] = float(order_value); doc.pop("lostReason", None)
    elif status == "Lose":
        doc["orderStatus"] = "Lose"; doc["lostReason"] = (lost_reason or "").strip()
    else: raise ValueError(status)
    return doc

def stock_out_from_dc(dc: dict, user: dict, transactions: list, is_new: bool) -> list:
    """A NEW delivery challan with a branch writes one stock 'OUT' transaction per item (qty > 0). Editing never repeats it."""
    if not (is_new and dc.get("type") == "dc" and dc.get("branch")): return transactions
    for it in dc.get("items") or []:
        if not it.get("itemName") or not it.get("qty"): continue
        transactions.append({"branch": dc["branch"], "itemName": it["itemName"], "make": it.get("make", ""), "type": "OUT", "qty": float(it["qty"]),
                             "source": "Delivery Challan", "refDocNumber": dc.get("docNumber"), "recordedById": user["id"]})
    return transactions

def record_supply(po_item: dict, qty: float, date_: str, user: dict, confirm_over=lambda pending: False) -> dict:
    """PO supply is entered manually (not auto from a challan). qty must be > 0; more than pending needs confirmation."""
    if not qty or qty <= 0: raise ValueError("quantity must be greater than zero")
    pend = item_pending(po_item)
    if qty > pend and not confirm_over(pend): raise ValueError("over supply not confirmed")
    po_item.setdefault("supplyLog", []).append({"date": date_, "qtySupplied": qty, "recordedById": user["id"]})
    return po_item

def record_invoice(dc_item: dict, bill_number: str, bill_date: str, qty: float, user: dict, confirm_over=lambda bal: False) -> dict:
    """'Invoice Done' on a delivery challan item: bill number and qty > 0 required; more than the balance needs confirmation."""
    if not (bill_number or "").strip(): raise ValueError("bill number required")
    if not qty or qty <= 0: raise ValueError("quantity must be greater than zero")
    bal = item_balance(dc_item)
    if qty > bal and not confirm_over(bal): raise ValueError("over invoice not confirmed")
    dc_item.setdefault("invoiceLog", []).append({"billNumber": bill_number.strip(), "billDate": bill_date, "qtyInvoiced": qty, "recordedById": user["id"]})
    return dc_item

def dc_is_pending(dc: dict) -> bool: return any(item_balance(i) > 0 for i in dc.get("items") or [])
def dc_history_completed(dc: dict): return [i for i in dc.get("items") or [] if item_balance(i) == 0 and float(i.get("qty") or 0) > 0]
def po_is_pending(po: dict) -> bool: return po.get("orderStatus") != "Completed"

# --------------------------------------------------------------------------- call log on documents / payments ("contact log")
def last_contact_on(doc):
    log = doc.get("callLog") or []
    return (log[-1].get("timestamp") or None) if log else None

def next_call_later_date(doc):
    dated = sorted((m for m in doc.get("callLog") or [] if m.get("callLaterDate")), key=lambda m: m.get("timestamp") or "", reverse=True)
    return dated[0]["callLaterDate"] if dated else None

def call_later_bucket(doc, today: str):
    cl = next_call_later_date(doc)
    if not cl: return "none"
    return "overdue" if cl < today else "today" if cl == today else "upcoming"

def add_contact_log(target: dict, text: str, user: dict, tasks: list, call_later_date: str = "", now: str = "", field: str = "callLog"):
    """Log a message on a quotation/proforma/challan/payment. 'Call me later' ALSO creates a Call task for the logger."""
    if not text: return None
    e = {"message": text, "userId": user["id"], "userName": user["name"], "timestamp": now or datetime.now().isoformat()}
    if call_later_date: e["callLaterDate"] = call_later_date
    target.setdefault(field, []).append(e)
    if call_later_date:
        tasks.append({"title": f"Call {target.get('contactName') or 'contact'} — {target.get('customerName') or ''}", "taskType": "Call", "status": "Open",
                      "dueDate": call_later_date, "assignedToId": user["id"], "assignedToName": user["name"], "createdById": user["id"], "createdByName": user["name"]})
    return e

def wa_link(phone: str):
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10: digits = "91" + digits
    return f"https://wa.me/{digits}?text=Hi%2C%20" if digits else None

# --------------------------------------------------------------------------- payments
def visible_payments(u, payments):
    if is_admin(u) or is_bm(u) or is_bs(u): return list(payments)
    return [p for p in payments if p.get("createdById") == u["id"]]

def payment_branch_of(p, employees):
    if p.get("branch"): return p["branch"]
    c = next((e for e in employees if e["id"] == p.get("createdById")), None)
    return ((c or {}).get("branches") or [""])[0]

def payment_age_bucket(days: int) -> str:
    return "0-30 days" if days <= 30 else "31-60 days" if days <= 60 else "61-90 days" if days <= 90 else "90+ days"

def receive_payment(p: dict, amount: float, date_: str, user: dict, confirm_over=lambda bal: False) -> dict:
    if not amount or amount <= 0: raise ValueError("amount must be greater than zero")
    bal = payment_balance(p)
    if amount > bal and not confirm_over(bal): raise ValueError("over payment not confirmed")
    p.setdefault("receivedLog", []).append({"amount": amount, "date": date_, "recordedById": user["id"]})
    return p

# --------------------------------------------------------------------------- outreach completion
def outreach_call_done(a: dict, remarks: str, user: dict, company: dict, now: str, today: str):
    """Marking an outreach call 'Called' (first time only) also logs a Call interaction on that contact."""
    was = a.get("status") == "Called"
    a.update(status="Called", remarks=remarks, calledAt=now, calledById=user["id"], calledByName=user["name"])
    if was: return None
    ct = next((c for c in company.get("contacts") or [] if c["id"] == a.get("contactId")), None)
    if not ct: return None
    it = {"type": "Call", "date": today, "notes": remarks or "Outreach — call completed.", "userId": user["id"], "userName": user["name"], "followupDate": ""}
    ct.setdefault("interactions", []).append(it); return it

def outreach_not_reached(a: dict, reason: str, note: str, call_again: str, user: dict, tasks: list):
    """'Call log' for an unreachable contact: keeps an attempt list; a call-again date creates a Call task for the ASSIGNED staff member."""
    a.setdefault("attempts", []).append({"reason": reason, "note": note, "byId": user["id"], "callAgainDate": call_again})
    if call_again:
        tasks.append({"title": f"Call {a.get('contactName') or 'contact'} — {a.get('customerName') or ''}", "taskType": "Call", "status": "Open",
                      "dueDate": call_again, "assignedToId": a["assignedToId"], "assignedToName": a.get("assignedToName", ""), "createdById": user["id"]})
    return a

def can_update_outreach(u, a): return a.get("assignedToId") == u["id"] or can_direct_edit_delete(u)

# --------------------------------------------------------------------------- dashboard / reports
DOI_CALL_TYPES = ("Call", "Cold Call")
INTERACTION_TYPES = ("Call", "Visit", "Appointment", "Sales Log", "Payment Log", "Outreach")
LOCATION_CAPTURE_TYPES = ("Visit",)

def personal_counts(me: str, companies, tasks, call_assignments, sales_docs, payments, in_period=lambda d: True):
    c = dict(callDone=0, apptTaken=0, apptVisited=0)
    for co in companies:
        for ct in co.get("contacts") or []:
            for i in ct.get("interactions") or []:
                if i.get("isCopy") or not (i.get("userId") == me or any(j["id"] == me for j in i.get("jointWith") or [])) or not in_period(i.get("date")): continue
                if i["type"] in DOI_CALL_TYPES: c["callDone"] += 1
                elif i["type"] == "Appointment": c["apptTaken"] += 1
                elif i["type"] == "Visit": c["apptVisited"] += 1
    c["tasksPending"] = sum(1 for t in tasks if task_assigned_to(t, me) and t["status"] != "Done")
    c["callingPending"] = sum(1 for a in call_assignments if a["assignedToId"] == me and a["status"] != "Called")
    mine = lambda d: d.get("createdById") == me or d.get("salesPersonId") == me
    docs = lambda t: [d for d in sales_docs if d["type"] == t and mine(d)]
    c["enquiryPending"] = sum(1 for d in docs("enquiry") if (d.get("orderStatus") or "Pending") == "Pending")
    c["quotationPending"] = sum(1 for d in docs("quotation") if (d.get("orderStatus") or "Pending") == "Pending")
    c["proformaPending"] = sum(1 for d in docs("proforma") if (d.get("orderStatus") or "Pending") == "Pending")
    c["dcPending"] = sum(1 for d in docs("dc") if dc_is_pending(d))
    c["poPending"] = sum(1 for d in docs("po") if po_is_pending(d))
    mp = [p for p in payments if p.get("createdById") == me]
    c["paymentPending"] = sum(1 for p in mp if payment_balance(p) > 0)
    c["paymentDone"] = sum(1 for p in mp if float(p.get("amount") or 0) > 0 and payment_balance(p) == 0)
    return c

def not_contacted(companies, days: int, mode: str, today: str):
    """Customers with no Call (Call/Cold Call) and/or no Visit in the last N days. mode: both | call | visit | either.
    A customer that was never called counts as 'beyond N days'. Sorted by the longest gap first."""
    def last(co, types):
        ds = [i.get("date") for ct in co.get("contacts") or [] for i in ct.get("interactions") or [] if i["type"] in types and i.get("date")]
        return max(ds) if ds else None
    def since(d): return None if not d else (date.fromisoformat(today) - date.fromisoformat(d)).days
    out = []
    for co in companies:
        lc, lv = last(co, DOI_CALL_TYPES), last(co, ("Visit",))
        dc, dv = since(lc), since(lv)
        no_call, no_visit = dc is None or dc > days, dv is None or dv > days
        hit = {"call": no_call, "visit": no_visit, "either": no_call or no_visit}.get(mode, no_call and no_visit)
        if hit: out.append({"id": co["id"], "daysSinceCall": dc, "daysSinceVisit": dv, "sort": max(99999 if dc is None else dc, 99999 if dv is None else dv)})
    return sorted(out, key=lambda r: -r["sort"])

def sales_conversion(enquiries: list, quotations: list) -> dict:
    won = [q for q in quotations if q.get("orderStatus") == "Win"]
    return {"enq_to_quo_pct": round(len(quotations) / len(enquiries) * 100) if enquiries else 0,
            "quo_to_win_pct": round(len(won) / len(quotations) * 100) if quotations else 0,
            "won_value": sum(quotation_value_of(q) for q in won)}

# --------------------------------------------------------------------------- customer import (Excel)
def import_customers(rows: list, companies: list, user: dict) -> dict:
    """Rows sharing a company name (case-insensitive) are one customer; one contact per row. Existing customers are UPDATED
    (blank cells keep what is saved). Names/addresses title-cased. Potential must be High/Medium/Low. List cells are comma-separated.
    A contact is skipped if the same name+phone already exists."""
    by = {(c["name"] or "").strip().lower(): c for c in companies}
    new = upd = newc = 0
    for r in rows:
        name = title_case_words(str(r.get("Company") or "").strip())
        if not name: continue
        comp = by.get(name.lower())
        if not comp:
            comp = {"id": f"imp{len(companies)}", "name": name, "assignedTo": [], "contacts": [], "createdById": user["id"], "createdByName": user["name"]}
            companies.append(comp); by[name.lower()] = comp; new += 1
        else: upd += 1
        for col, f in (("Plant", "plant"), ("Area", "area"), ("City", "city"), ("State", "state"), ("Pincode", "pincode"), ("Website", "website"), ("Industry", "industry"), ("Source", "source")):
            if r.get(col): comp[f] = str(r[col]).strip() if col == "Plant" else str(r[col])
        if r.get("Address"): comp["address"] = title_case_words(str(r["Address"]))
        if r.get("GST Number"): comp["gstNumber"] = str(r["GST Number"]).strip().upper()
        if r.get("Potential"):
            pm = {"high": "High", "medium": "Medium", "low": "Low"}.get(str(r["Potential"]).strip().lower())
            if pm: comp["potential"] = pm
        for col, f in (("Assigned To", "assignedTo"), ("Preferred Languages", "preferredLanguages"), ("Interested Brands", "interestedBrands"), ("Interested Products", "interestedProducts")):
            if r.get(col): comp[f] = [x.strip() for x in str(r[col]).split(",") if x.strip()]
        cn, ph = title_case_words(str(r.get("Contact Name") or "").strip()), str(r.get("Phone") or "").strip()
        if cn or ph or r.get("Phone 2") or r.get("Email"):
            if not any((x.get("name") or "").lower() == cn.lower() and (x.get("phone") or "") == ph for x in comp["contacts"]):
                comp["contacts"].append({"id": f"{comp['id']}-c{len(comp['contacts'])}", "name": cn, "jobTitle": str(r.get("Job Title") or "").strip(), "phone": ph,
                                         "phone2": str(r.get("Phone 2") or "").strip(), "email": str(r.get("Email") or "").strip()}); newc += 1
    return {"new": new, "updated": upd, "contacts": newc}

# --------------------------------------------------------------------------- users
def user_record_total(uid: str, name: str, companies, tasks, docs, payments, calls) -> int:
    return (sum(1 for c in companies if c.get("createdById") == uid) + sum(1 for c in companies if name in assigned_to(c)) +
            sum(1 for t in tasks if t.get("createdById") == uid) + sum(1 for t in tasks if task_assigned_to(t, uid)) +
            sum(1 for d in docs if d.get("createdById") == uid) + sum(1 for p in payments if p.get("createdById") == uid) +
            sum(1 for a in calls if a.get("assignedToId") == uid) + sum(1 for a in calls if a.get("assignedById") == uid))

def can_deactivate_user(actor: dict, target: dict, employees: list) -> tuple[bool, str]:
    if not is_admin(actor): return False, "Only an admin can change a user's status."
    if target["id"] == actor["id"]: return False, "You can't make your own account inactive."
    if target["role"] == "Admin" and not any(e["id"] != target["id"] and e["role"] == "Admin" and e.get("active", True) for e in employees):
        return False, "At least one active admin is required."
    return True, ""

def can_remove_user(actor: dict, target: dict, employees: list, record_total: int) -> tuple[bool, str]:
    if not is_admin(actor): return False, "Only an admin can remove users."
    if target["id"] == actor["id"]: return False, "You can't remove yourself while signed in."
    if record_total and len(employees) <= 1: return False, "No other user to transfer records to."
    return True, "needs_transfer" if record_total else "ok"

def can_login(emp: dict) -> bool: return emp.get("active", True) is not False


# =========================================================================== MISC RULES FOUND IN THE SECOND AUDIT
# --------------------------------------------------------------------------- map pins
def geo_parse(s: str):
    """Accepts 'lat, lng' (comma/semicolon/space) or a Google Maps link (!3d..!4d.., ?q=, ll=, query=, destination=, center=, @lat,lng).
    Returns {'lat','lng'} rounded to 6 places, or None if unrecognised / out of range."""
    from urllib.parse import unquote
    s = (s or "").strip()
    if not s: return None
    try: t = unquote(s)
    except Exception: t = s
    n = r"(-?\d+(?:\.\d+)?)"
    for pat in (rf"!3d{n}!4d{n}", rf"[?&](?:q|ll|query|destination|center)={n}\s*,\s*{n}", rf"@{n},\s*{n}", rf"^\s*{n}\s*[,;\s]\s*{n}\s*$"):
        m = re.search(pat, t)
        if not m: continue
        lat, lng = float(m.group(1)), float(m.group(2))
        if abs(lat) <= 90 and abs(lng) <= 180: return {"lat": round(lat, 6), "lng": round(lng, 6)}
    return None

def geo_dist_m(a: dict, b: dict) -> float:
    R_, r = 6371000, math.radians
    dlat, dlng = r(b["lat"] - a["lat"]), r(b["lng"] - a["lng"])
    h = math.sin(dlat / 2) ** 2 + math.cos(r(a["lat"])) * math.cos(r(b["lat"])) * math.sin(dlng / 2) ** 2
    return 2 * R_ * math.asin(math.sqrt(h))

def geo_fmt_dist(m: float) -> str:
    return f"{_js_round(m)} m" if m < 1000 else (f"{m/1000:.1f} km" if m < 10000 else f"{_js_round(m/1000)} km")

# --------------------------------------------------------------------------- login / password
MIN_PASSWORD = 6
def reset_password(target: dict, new_pw: str, confirm_pw: str, employees: list, verifier: dict | None = None, verifier_pw: str = "") -> dict:
    """'Forgot password' on the login screen. If another Admin exists, one of them must verify with THEIR password.
    New password >= 6 chars and must match the confirmation. The legacy 'pin' field is dropped."""
    others = [e for e in employees if e["id"] != target["id"] and e["role"] == "Admin"]
    if others:
        exp = None if not verifier else verifier.get("password", verifier.get("pin"))
        if verifier is None or verifier["id"] == target["id"] or verifier_pw != exp: raise PermissionError("That admin's password is incorrect.")
    if not new_pw or len(new_pw) < MIN_PASSWORD: raise ValueError("New password must be at least 6 characters.")
    if new_pw != confirm_pw: raise ValueError("Passwords don't match.")
    target["password"] = new_pw; target.pop("pin", None); return target

# --------------------------------------------------------------------------- contact selection exports
def selected_emails(contacts: list) -> list:
    seen, out = set(), []
    for c in contacts:
        e = c.get("email")
        if e and e not in seen: seen.add(e); out.append(e)
    return out

def vcard(contacts: list) -> str:
    cards = ["\n".join(x for x in ["BEGIN:VCARD", "VERSION:3.0", f"FN:{c.get('name') or 'Unnamed'}", f"ORG:{c['companyName']}" if c.get("companyName") else "",
                                    f"TITLE:{c['jobTitle']}" if c.get("jobTitle") else "", f"TEL;TYPE=CELL:{c['phone']}" if c.get("phone") else "",
                                    f"EMAIL:{c['email']}" if c.get("email") else "", "END:VCARD"] if x) for c in contacts]
    return "\n".join(cards)

# --------------------------------------------------------------------------- document form validation / editing
def validate_sales_doc(doc: dict, has_items_cfg: bool, has_branch_cfg: bool = True) -> str | None:
    """Return the first problem, or None. Customer and (where applicable) branch are required; documents with items need at least one."""
    if not doc.get("customerId"): return "Select a customer first."
    if has_branch_cfg and not doc.get("branch"): return "Select a branch first."
    items = [i for i in doc.get("items") or [] if i.get("itemName") or i.get("qty")]      # blank rows are dropped
    if has_items_cfg and not items: return "Add at least one item."
    return None

def keep_supply_on_edit(original_items: list, edited_rows: list) -> list:
    """Editing a Pending PO keeps each line's supply history (matched by the row's original position)."""
    out = []
    for r in edited_rows:
        it = dict(r["item"])
        oi = r.get("origIndex")
        if oi is not None and oi < len(original_items) and original_items[oi].get("supplyLog"): it["supplyLog"] = original_items[oi]["supplyLog"]
        if it.get("itemName") or it.get("qty"): out.append(it)
    return out

def delete_supply(po: dict, item_index: int, entry_index: int) -> dict:
    """Deleting a supply entry recalculates the PO status (Hold stays)."""
    po["items"][item_index]["supplyLog"].pop(entry_index); return recompute_po_status(po)

def can_edit_task(u, t): return can_manage_task(u, t)                  # Admin, Branch Manager, or the creator

def label_target_name(typed: str, company: dict | None) -> str:
    """A label needs a 'who is it for' name: the typed name or the picked customer's name; otherwise it is refused."""
    n = label_deliver_to(typed, company)
    if not n: raise ValueError("Enter who the label is for.")
    return n

# --------------------------------------------------------------------------- deleting lookup values keeps history as plain text
def delete_list_value(values: list, value: str, records: list, field: str):
    """Removing a value from a pick-list (source, industry, brand, branch, sales person …) never alters records that already use it:
    they keep the old value as free text. Returns the new list; records are untouched."""
    return [v for v in values if v != value], records
