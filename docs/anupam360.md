# Anupam 360 — Django module

The CRM/ERP module for **Anupam Bearings** (branches **Chennai** and **Bengaluru**), served at `/360/`. It is the
`threesixty` app of this project, built to the spec pack in `anupam360_spec/` (`REQUIREMENTS.md` is the source of
truth; `rules/anupam_rules.py` is the executable specification).

## 1. Architecture

```
browser (vanilla-JS SPA, /360/)  ──fetch JSON──▶  threesixty/api/views_*.py   (thin: auth, parse, serialize)
                                                         │
                                                         ▼
                                    threesixty/services/*.py               (all business rules, one transaction per action)
                                                         │         ╲
                                                         ▼          ╲──▶ threesixty/rules/anupam_rules.py (pure spec rules, copied verbatim)
                                    threesixty/models/*.py  ──▶  database (Postgres in production, SQLite in tests)
```

* **Views never hold rules.** `api/` parses the request, calls a service, serialises the result. Permissions are
  enforced on the server in the service / queryset, never only in the UI.
* **Services** are where the spec lives: `numbering`, `documents`, `approvals`, `contacts` (contact-level access),
  `customers`, `interactions`, `tasks`, `outreach`, `payments`, `labels`, `printing` + `pdf_documents`, `attendance`,
  `reports`, `users`, `lists`, `backup`, `audit`, `exports`, `excel_import`.
* **`threesixty/rules/anupam_rules.py` is an exact copy of `anupam360_spec/rules/anupam_rules.py`** (a test fails if
  they drift). Services call it (amount in words, attendance day status, outreach week, search order, …).
* **`threesixty/rules/adapter.py`** re-exposes the spec rules with Django-backed replacements, so the 90 unchanged
  spec tests run against the real code too (`tests/test_spec_requirements_django.py`).
* Auth reuses Django sessions. `/360/login/` is the sign-in page (rate limited; Django password hashing; admin-confirmed
  password reset; first-admin form). `/dashboard/login/` still works and forwards 360 users to `/360/`.
* Time: `TIME_ZONE = "Asia/Kolkata"`, `USE_TZ = True`. "Today", the Monday week start and the 10-minute attendance
  grace use local time.
* Money is `Decimal`. Where the reference app used JavaScript `Math.round` (the rounded discounted rate on printed
  documents) the code uses round-half-up, not Python's default.

## 2. Models (text diagram)

```
Branch ─┬─ BranchNumbering(doc_type)            # DocCounter: prefix / suffix / start / last_issued, locked with select_for_update
        ├─ EmployeeProfile ── User (auth)       # role, branches, work hours, weekly off, Aadhaar/PAN (encrypted)
        └─ Holiday (all branches or chosen)
LookupItem(kind, name)   SalesPerson   SiteSetting(key, json)
Customer ─┬─ Contact ── Interaction (Call / Visit / Appointment; also_met, joint_with, GPS)
          ├─ ContactAccess(customer, user, contact)   # rows restrict; NO rows = all contacts
          └─ assigned_to (users)
SalesDocument(type, branch, customer, contact, reference) ── SalesDocumentItem ─┬─ SupplyLogEntry   (Pending PO)
          │                                                                      └─ InvoiceLogEntry  (Delivery Challan)
          └─ DocumentCallLog (contact log: message, outcome, call_later_date)
PaymentCollection ─┬─ PaymentReceipt        └─ PaymentContactLog
Task (assigned_to + joint_with, related customer/contact/document)   Notification   CallAssignment ── CallAttempt
ApprovalRequest(type edit|delete|customer-access, before_data, proposed_data)   AttendanceRecord   LeaveRequest
StockProduct / Supplier / StockBill / StockTransaction (only the stock-OUT written by a new challan is used; no stock screens)
AuditLog (append-only)
```

Deleting a pick-list value, sales person or branch never alters existing records (they are deactivated, or the record
keeps a text copy). Documents, payments and customers use `PROTECT`.

## 3. Role–permission matrix (enforced server-side)

| Capability | Admin | Branch Manager | Branch Staff | Sales Manager |
|---|---|---|---|---|
| See customers | all | all | all | created by me or assigned to me |
| See contacts of a customer | all | all | all | all, unless restricted by `ContactAccess` (creator always sees all) |
| Edit customer / contact | direct | direct | direct | **approval** |
| Delete customer | direct | direct | **approval** | **approval** |
| Edit / delete sales documents (incl. quotations) | direct | direct | direct | **approval** |
| Raise document types | all | all | all | **Enquiry and Quotation only** |
| Approve / reject | all | requests from their branch scope | – | – |
| Assign customers, outreach lists, exports | ✔ | ✔ (own team) | – | – |
| Manage lists, Import Excel, Backup/Restore, Users, Branches, Audit log | ✔ | – | – | – |
| Proforma / Challan / Pending PO / Payment Collection / Print Label | ✔ | ✔ | ✔ | hidden (Print Label also refused) |
| Payments visible | all | all | all | own |
| Tasks: main list | own | own (+ Everyone switch) | own | own |
| Tasks: remove | creator only (Admin for creator-less old tasks) | creator | creator | creator |
| Reports | all data, user picker | all data, user picker | own data | own data; no Sales Performance / Customer Activity |
| Dashboard | company-wide | personal | personal | personal |
| Attendance view | all active staff | their team | themselves | themselves |
| Aadhaar / PAN / date of birth | plain | masked (own record only) | masked (own) | masked (own) |

## 4. Document numbering

`DocCounter` is `BranchNumbering(branch, doc_type)`. `allocate_next_number()` locks the row with `select_for_update()`
inside `transaction.atomic()` and advances `last_issued`, so two users can never get the same number
(`manage.py check_360_numbering_concurrency` proves it on PostgreSQL). Format `PREFIX-0001[-SUFFIX]`; a blank prefix
falls back to ENQ / QUO / PI / DC; the sequence is the *first* run of digits; the counter only moves forward (deleting
a document never frees a number; a hand-typed higher number pushes it up). **Pending PO has no generated number** — it
carries the customer's own PO number.

## 5. Approvals

A Sales Manager's edit/delete of a customer, contact or any sales document creates an `ApprovalRequest` holding the
target's state **before** and the **proposed** change; nothing is applied until an Admin / Branch Manager approves.
One pending request per person, target and kind. Approvers see a "what changed" list
(`GET /approvals/<id>/changes/`), requesters and approvers are notified, and a pending request whose record has
disappeared is dropped. Applying runs in one transaction — if it fails the request stays pending. Customer-access
requests notify every Admin and Branch Manager and, on approval, add the requester to *assigned to*.

## 6. Running the tests

```bash
.venv/bin/python -m pytest tests anupam360_spec --ignore=tests/test_rag.py      # everything (needs no Postgres/Redis)
.venv/bin/python -m pytest anupam360_spec/tests                                  # the 90 spec tests on the pure rules
.venv/bin/python -m pytest tests/test_spec_requirements_django.py                # the same 90 on the Django adapter
python manage.py check_360_numbering_concurrency                                  # real concurrency, PostgreSQL only
```

`tests/test_rag.py` and three chat/RAG view tests need `numpy` (not part of this module). Tests are named `test_REQ_…`
so a failure points at a requirement; `tests/test_traceability.py` fails if a requirement has no test.

## 7. Operations

* `FIELD_ENCRYPTION_KEY` (settings / env): Fernet key for Aadhaar / PAN. Generate one and keep it with your secrets;
  without it a key is derived from `SECRET_KEY`. `python manage.py encrypt_360_sensitive_fields` encrypts rows written
  before the field was encrypted (reading works either way).
* `BACKUP_DIR` (default `./backups`, git-ignored): safety copies written before a restore. Backups contain password
  hashes — never put this under `MEDIA_ROOT`.
* Backup file = JSON of every dataset. Uploaded image *files* are not inside it (copy `media/`). The audit log is not
  restored (append-only).

## 8. Decisions taken from the spec (please confirm)

* Sales Manager quotation edits go through approval (spec §1, REQ-ROLE-02) — the older audit note that blocked them is superseded.
* A sole Admin can reset their own password on the sign-in page without a verifier (REQ-USR-03, as specified). The
  reset form is rate limited, but this is weaker than requiring a second person: consider disabling it in production.
* Password minimum is 6 characters (REQ-USR-03); Django's stricter validators are not applied.
* "Own data" in Reports applies to Branch Staff as well as Sales Managers (the §1 table); Not Contacted shows
  only customers they created or are assigned.
* Contact-log "call me later" and outreach "call again" tasks are created as Call tasks (REQ-LOG-01, REQ-OUT-02).
* Tasks keep the model status `Completed`; the spec's "Done" is accepted on input.
* Employee list: only Admin (and the person themself) sees phone, birth date, work schedule, Aadhaar, PAN.
* [Reconstructed/Assumed in the spec] Stock screens are not built (§26); only the stock-OUT record exists.

## 9. Traceability: requirement → code → tests

"Spec" = `anupam360_spec/tests/test_requirements.py` (also run on the Django adapter).

| Requirement | Code (under `threesixty/`) | Tests (under `tests/`) |
|---|---|---|
| REQ-ATT-01 | services/attendance.py | anupam360_spec/test_requirements.py, test_threesixty_phase7.py |
| REQ-ATT-02 | services/attendance.py | anupam360_spec/test_requirements.py, test_threesixty_phase7.py |
| REQ-ATT-03 | services/attendance.py | anupam360_spec/test_requirements.py, test_threesixty_phase7.py |
| REQ-ATT-04 | services/attendance.py | anupam360_spec/test_requirements.py, test_threesixty_phase7.py |
| REQ-ATT-05 | services/attendance.py | anupam360_spec/test_requirements.py, test_threesixty_phase7.py |
| REQ-AUT-01 | services/outreach.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-AUT-02 | services/approvals.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-AUT-03 | services/approvals.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-AUT-04 | services/approvals.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-AUT-05 | services/tasks.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-AUT-06 | services/tasks.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-AUT-07 | services/tasks.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-AUT-08 | services/tasks.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py, test_threesixty_phase4.py |
| REQ-AUT-09 | services/attendance.py | anupam360_spec/test_requirements.py, test_threesixty_phase7.py |
| REQ-AUT-10 | services/labels.py | anupam360_spec/test_requirements.py, test_threesixty_phase6.py |
| REQ-AUT-11 | services/documents.py | anupam360_spec/test_requirements.py, test_threesixty_phase4.py |
| REQ-AUT-12 | services/documents.py | anupam360_spec/test_requirements.py, test_threesixty_phase4.py |
| REQ-AUT-13 | services/documents.py | anupam360_spec/test_requirements.py, test_threesixty_phase4.py |
| REQ-BAK-01 | services/backup.py | anupam360_spec/test_requirements.py, test_threesixty_phase9.py |
| REQ-CUS-01 | services/contacts.py, services/customers.py, api/views_customers.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-CUS-02 | services/contacts.py, services/customers.py, api/views_customers.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-CUS-03 | services/contacts.py, services/customers.py, api/views_customers.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-CUS-04 | services/contacts.py, services/customers.py, api/views_customers.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-CUS-05 | services/contacts.py, services/customers.py, api/views_customers.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-CUS-06 | services/contacts.py, services/customers.py, api/views_customers.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-CUS-07 | services/contacts.py, services/customers.py, api/views_customers.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-CUS-08 | services/contacts.py, services/customers.py, api/views_customers.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-CUS-09 | services/contacts.py, services/customers.py, api/views_customers.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-CUS-10 | services/contacts.py, services/customers.py, api/views_customers.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-DC-01 | services/documents.py | anupam360_spec/test_requirements.py, test_threesixty_phase4.py |
| REQ-DOC-01 | services/numbering.py, services/documents.py, services/totals.py | anupam360_spec/test_requirements.py, test_threesixty_phase1.py, test_threesixty_phase4.py |
| REQ-DOC-02 | services/numbering.py, services/documents.py, services/totals.py | anupam360_spec/test_requirements.py, test_threesixty_numbering.py, test_threesixty_phase1.py, test_threesixty_phase4.py |
| REQ-DOC-03 | services/numbering.py, services/documents.py, services/totals.py | anupam360_spec/test_requirements.py, test_threesixty_phase4.py |
| REQ-DOC-04 | services/numbering.py, services/documents.py, services/totals.py | anupam360_spec/test_requirements.py |
| REQ-DOC-05 | services/numbering.py, services/documents.py, services/totals.py | anupam360_spec/test_requirements.py, test_threesixty_phase4.py |
| REQ-DOC-06 | services/numbering.py, services/documents.py, services/totals.py | anupam360_spec/test_requirements.py, test_threesixty_phase4.py |
| REQ-GEO-01 | services/customers.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-GEO-02 | services/customers.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-IMP-01 | services/excel_import.py | anupam360_spec/test_requirements.py, test_threesixty_phase2.py |
| REQ-INT-01 | services/interactions.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-INT-02 | services/interactions.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-INT-03 | services/interactions.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-INT-04 | services/interactions.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-INT-05 | services/interactions.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-INT-06 | services/interactions.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py, test_threesixty_phase8.py |
| REQ-INT-07 | services/interactions.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-LBL-01 | services/labels.py | anupam360_spec/test_requirements.py, test_threesixty_phase6.py |
| REQ-LBL-02 | services/labels.py | anupam360_spec/test_requirements.py, test_threesixty_phase6.py |
| REQ-LBL-03 | services/labels.py | anupam360_spec/test_requirements.py, test_threesixty_phase6.py |
| REQ-LBL-04 | services/labels.py | anupam360_spec/test_requirements.py, test_threesixty_phase6.py |
| REQ-LBL-05 | services/labels.py | anupam360_spec/test_requirements.py, test_threesixty_phase6.py |
| REQ-LBL-06 | services/labels.py | anupam360_spec/test_requirements.py, test_threesixty_phase6.py |
| REQ-LBL-07 | services/labels.py | test_threesixty_phase6.py |
| REQ-LBL-08 | services/labels.py | test_threesixty_phase6.py |
| REQ-LBL-09 | services/labels.py | anupam360_spec/test_requirements.py, test_threesixty_phase6.py |
| REQ-LOG-01 | services/documents.py, services/payments.py | anupam360_spec/test_requirements.py, test_threesixty_phase4.py, test_threesixty_phase6.py |
| REQ-LST-01 | services/lists.py | anupam360_spec/test_requirements.py, test_threesixty_phase1.py |
| REQ-OUT-01 | services/outreach.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-OUT-02 | services/outreach.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-OUT-GAP | services/outreach.py | test_threesixty_phase3.py |
| REQ-PAY-01 | services/payments.py | anupam360_spec/test_requirements.py, test_threesixty_phase6.py |
| REQ-PAY-02 | services/payments.py | anupam360_spec/test_requirements.py, test_threesixty_phase6.py |
| REQ-PO-01 | services/documents.py | anupam360_spec/test_requirements.py, test_threesixty_phase4.py |
| REQ-PO-02 | services/documents.py | anupam360_spec/test_requirements.py, test_threesixty_phase4.py |
| REQ-PO-03 | services/documents.py | anupam360_spec/test_requirements.py, test_threesixty_phase4.py |
| REQ-PO-04 | services/documents.py | anupam360_spec/test_requirements.py, test_threesixty_phase4.py |
| REQ-PO-05 | services/documents.py | anupam360_spec/test_requirements.py, test_threesixty_phase4.py |
| REQ-PRN-01 | services/printing.py, services/pdf_documents.py | anupam360_spec/test_requirements.py, test_threesixty_phase5.py |
| REQ-PRN-02 | services/printing.py, services/pdf_documents.py | anupam360_spec/test_requirements.py |
| REQ-PRN-03 | services/printing.py, services/pdf_documents.py | anupam360_spec/test_requirements.py, test_threesixty_phase5.py |
| REQ-PRN-04 | services/printing.py, services/pdf_documents.py | anupam360_spec/test_requirements.py, test_threesixty_phase5.py |
| REQ-ROLE-01 | permissions.py, services/nav.py, services/approvals.py | anupam360_spec/test_requirements.py |
| REQ-ROLE-02 | permissions.py, services/nav.py, services/approvals.py | anupam360_spec/test_requirements.py, test_threesixty_api.py, test_threesixty_permissions.py, test_threesixty_phase1.py, test_threesixty_phase2.py, test_threesixty_phase4.py |
| REQ-ROLE-03 | permissions.py, services/nav.py, services/approvals.py | anupam360_spec/test_requirements.py, test_threesixty_phase1.py |
| REQ-ROLE-04 | permissions.py, services/nav.py, services/approvals.py | anupam360_spec/test_requirements.py, test_threesixty_phase1.py |
| REQ-ROLE-05 | permissions.py, services/nav.py, services/approvals.py | anupam360_spec/test_requirements.py, test_threesixty_phase8.py |
| REQ-RPT-01 | services/reports.py, services/nav.py | anupam360_spec/test_requirements.py, test_threesixty_phase1.py, test_threesixty_phase8.py |
| REQ-RPT-02 | services/reports.py, services/nav.py | anupam360_spec/test_requirements.py |
| REQ-RPT-03 | services/reports.py, services/nav.py | anupam360_spec/test_requirements.py, test_threesixty_phase8.py |
| REQ-STO-01 | — (HTML app only) | — |
| REQ-TSK-01 | services/tasks.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-TSK-02 | services/tasks.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-TSK-03 | services/tasks.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-TSK-04 | services/tasks.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-TSK-05 | services/tasks.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-TSK-06 | services/tasks.py | anupam360_spec/test_requirements.py, test_threesixty_phase3.py |
| REQ-USR-01 | services/users.py, views.py | anupam360_spec/test_requirements.py, test_threesixty_phase1.py |
| REQ-USR-02 | services/users.py, views.py | anupam360_spec/test_requirements.py, test_threesixty_phase9.py |
| REQ-USR-03 | services/users.py, views.py | anupam360_spec/test_requirements.py, test_threesixty_phase1.py |

## 10. Manual QA checklist

Log in as each role (create them under *Users*) and check:

1. **Admin** — Users: create a Branch Manager, Branch Staff and Sales Manager with a branch each; Branch: letterhead, bank,
   logo, QR, format 2, watermark, numbering for Quotation (`CHN/Q`, `26-27`, start 100) → next quotation is `CHN/Q-0100-26-27`.
   Manage lists: remove a language used by a customer → it is hidden, the customer keeps it.
   Backup & restore: download, change something, restore → back; a safety copy is listed. Audit log shows it.
2. **Sales Manager** — sees only own/assigned customers; no Proforma / Challan / Pending PO / Payments / Print Label menus;
   Reports has no Sales Performance / Customer Activity. Edit a customer and a quotation → "sent for approval", record unchanged.
   Add a customer similar to an existing one you can't see → duplicate warning with *Request access*.
3. **Branch Manager / Admin** — Approvals: open "view what changed", approve one, reject one; requester gets a notification.
   Assign a customer to the Sales Manager with only 2 of 4 contacts → they see only those 2 (customer page, tasks, outreach, labels).
4. **Branch Staff** — Enquiry → Quotation from the enquiry (enquiry becomes Completed) → Win with an order value →
   Proforma → Pending PO + manual supply (Part Pending → Completed; Hold stays) → Delivery Challan (stock OUT written once)
   → Invoice Done. Save a quotation → Skip / Preview / Print / PDF prompt; the three show the same PDF with logo, QR, totals, words.
5. **Print Label** — A4 + A5 + 2 boxes → two A5 labels on a landscape sheet at real size; 6×4 with paper "label size"; FROM
   block at the bottom at 150 %; Attn/phone absent until a person is picked and ticked.
6. **Attendance** — check in without allowing location → refused; allowed → recorded; 09:41 shows Late 11 min; leave request →
   Admin notified; Branch Manager cannot decide their own. Admin sees locations; a manager does not.
7. **Payments** — create with date/remarks; receipt larger than the balance asks to confirm; ageing bucket shows; "call me later" makes a task.
8. **Reports/Dashboard** — click any number → the records behind it; export to Excel/PDF; Admin dashboard vs personal dashboard.
