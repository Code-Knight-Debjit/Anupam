# Anupam 360 — Requirements for the Django build

Source: everything requested in the conversation that produced the standalone `contact_management.html` (the **reference app**), plus the behaviour verified in that app's code.
Company: **Anupam Bearings** — branches **Chennai** and **Bengaluru**. Users are the owner (Admin), branch managers, branch staff and sales managers.

> **How to read this file**
> * Every rule has an ID (`REQ-XXX-nn`). The same IDs appear in `tests/test_requirements.py` and `e2e/check_reference_app.py`.
> * **[Asked]** = you asked for it explicitly in the conversation. **[Reconstructed]** = built early in the conversation; I only have it from the first conversation summary and from the app's code, not your original wording — please confirm these. **[Assumed]** = a choice I made and disclosed; change freely.
> * `rules/anupam_rules.py` is the same logic as plain Python so you can lift it straight into Django services.

---
## 0. Global constraints [Asked]
* GST/billing-style paid services are **not** wanted; the free OpenStreetMap-style map stays (user rejected Google Maps and "any billing").
* Pipeline is **Enquiry → Quotation → Proforma / PO (sales order) → Delivery Challan**.
* Two branches with **independent document numbering**.
* Data must **never silently disappear** (see §14). In Django this is solved by the database; the reference app's browser-storage problem does not exist there.

## 1. Roles & permissions
| Capability | Admin | Branch Manager | Branch Staff | Sales Manager |
|---|---|---|---|---|
| See all customers | ✔ | ✔ | ✔ | only created-by-me or assigned-to-me (REQ-CUS-01) |
| Edit customer / contact directly | ✔ | ✔ | ✔ | **needs approval** (REQ-ROLE-02) |
| Delete customer directly | ✔ | ✔ | needs approval | needs approval |
| Edit/delete sales docs directly | ✔ | ✔ | ✔ | needs approval |
| Approve/reject approvals | ✔ | ✔ | – | – |
| Bulk-assign customers, exports | ✔ | ✔ | – | – |
| Full company dashboard | ✔ | personal | personal | personal (REQ-ROLE-05) |
| Manage lists, Import Excel, Backup/Restore, Users, Branch | ✔ only | – | – | – (REQ-ROLE-03) |
| Proforma, Delivery Challan, Pending PO, Payment Collection, Print Label menus | ✔ | ✔ | ✔ | **hidden** (REQ-ROLE-04) |
| Reports | all | all | own data | own data; **Sales Performance and Customer Activity hidden** (REQ-RPT-01) |

* REQ-ROLE-01 Exactly four roles: Admin, Branch Manager, Branch Staff, Sales Manager. [Asked/Reconstructed]
* REQ-ROLE-02 Sales Manager edit/delete of customers, contacts and enquiries creates an **approval request**; nothing changes until Admin/BM approves. [Asked]
* REQ-ROLE-03 Admin-only menus as above. [Reconstructed]
* REQ-ROLE-04 Sales Manager does not see back-office menus. [Reconstructed]
* REQ-ROLE-05 Non-admins get a *personal* dashboard (their own numbers). [Reconstructed]
* REQ-RPT-01 In Reports, Sales Staff: hide *Sales Performance* and *Customer Activity*; *Not Contacted* shows only their related customers; all other reports show only their own data. [Asked]

## 2. Customers, plants & contacts
Customer = a company **plant**. Fields: logo, name, plant, address, **area**, city, state, pincode, website, GST no., plant geo-location, head-office block (name, address, city, state, pincode, phone, geo), industry, source, potential, assigned-to (list of users), transport & courier preference, preferred languages, interested brands/products, created-by (+role, timestamp). Names/addresses are title-cased on save.
Contact = person at the customer: name, designation, phones, email, languages, DND flag, interaction history.

* REQ-CUS-01 Visibility: Admin/BM/Branch Staff see every customer; a Sales Manager sees only customers they **created** or that are **assigned to them**. [Asked]
* REQ-CUS-02 **Contact-level assignment**: when assigning a customer to a person you can share only some contacts (e.g. 2 of 4). The person then sees only those contacts. Admin/BM/Staff and the creator still see all. Stored as `contactAccess = {person: [contact ids]}`; **no entry = all contacts**. Selecting all contacts removes the restriction. [Asked]
* REQ-CUS-03 Selecting every contact (or none specified) must not leave a restriction record. [Asked, implied]
* REQ-CUS-04 De-assigning a person also removes their contact restriction. [Reconstructed]
* REQ-CUS-05 Several people can be assigned to one customer, each with their own contact selection. [Asked]
* REQ-CUS-06 The creator of a customer always sees all its contacts. [Reconstructed]
* REQ-CUS-07 Every customer drop-down shows **"Customer name, Plant, Area"** — never city. Applies to all sales panels, labels etc. [Asked]
* REQ-CUS-08 **Word-based search** in every customer drop-down: typing `su` lists names that start with "su" first, then names where *any later word* starts with "su", then anything containing it. [Asked]
* REQ-CUS-09 Duplicate detection when adding a customer: similar names (edit distance; threshold 0.80 similarity, 0.65 for names ≤ 4 chars) trigger a warning with options. [Reconstructed]
* Assignment UI: the former separate **Share** button was removed; contact-picking lives inside **Assign** (single customer → pick contacts; bulk → whole customers). [Asked]
* Back navigation: contact card → Back returns to the **customer list**. [Asked]
* Smart filters on the customer list: designation, state, area, industry, source, potential, brand, product, assigned-to, added-by, language, last call, last visit. Search box. [Reconstructed]
* Map & Nearby: nearby customers using the free map (no paid provider). [Asked]

## 3. Data model (suggested Django tables)
`Branch`, `User(role, branch(es), work_start, weekly_off, doj, active)`, `Customer`, `Contact`, `CustomerAssignment(customer, user)`, `ContactAccess(customer, user, contact)` (absence of rows = all), `Interaction`, `Task`, `TaskAssignee`, `SalesDocument(type, doc_number, branch, customer, status …)`, `SalesDocumentItem(…, supply_log, invoice_log)`, `DocCounter(type, branch, last_number)`, `Payment`, `PaymentReceipt`, `Approval`, `Notification`, `CallAssignment(week_of, user, contact)`, `AttendanceRecord`, `LeaveRequest`, `Holiday`, lookup lists (sources, job titles, industries, brands, products, categories, units, tax rates, sales persons, payment terms, languages, transport, courier), stock (products, suppliers, bills, transactions).

## 4. Sales pipeline & documents
* REQ-DOC-01 **Numbering** is generated per document type (Enquiry, Quotation, Proforma Invoice, Delivery Challan) **and per branch**. Format: `PREFIX-0001` or `PREFIX-0001-SUFFIX` — the sequence is zero-padded to 4 digits and joined with hyphens (e.g. `QUO-0001`, `ENQ-0012`). Defaults: ENQ, QUO, PI, DC (also SL / PUR reserved for stock bills). The counter only moves forward: deleting a document never frees its number, and a manually typed higher number pushes the counter up. The sequence is read as the **first run of digits** in the number. On start-up counters are rebuilt from existing documents so numbering always continues upward. [Asked/Reconstructed]
* REQ-DOC-02 Per-branch numbering settings (Branches → Document Numbering): prefix, suffix, start number for each type. A blank prefix falls back to the default; an empty suffix means none. Example: prefix `CHN/Q`, suffix `26-27`, start 100 → `CHN/Q-0100-26-27`. **Pending PO has no generated number** — it carries the customer's own PO number, typed by the user. The number can be edited by hand on the form. [Reconstructed]
* REQ-DOC-03 Entry-form line maths: `unit = rate × (1 − disc%) × (1 + tax%)`; `value = qty × unit`; total = Σ + packing (+tax) + freight (+tax) + other (+tax) + round-off. Discount/tax columns can be switched off per doc type. [Reconstructed]
* REQ-DOC-04 Linked documents: Quotation←Enquiry, Proforma←Quotation, Delivery Challan←PO. Statuses — Enquiry: Pending/Completed/Regretted; Quotation & Proforma: Pending/Win/Lose; PO: Pending/Part Pending/Hold/Completed. [Reconstructed]
* REQ-DOC-05 Visibility: Admin/BM/Staff see all docs; a Sales Manager sees enquiries/quotations they created or for customers assigned to them, and nothing in other types unless they created it. [Reconstructed]
* REQ-PO-01 **PO status is automatic** from the supply log: nothing supplied = Pending; some = Part Pending; all = Completed. [Reconstructed]
* REQ-PO-02 **Hold** is manual and never overwritten by the automatic status. [Reconstructed]
* REQ-PO-03 Per item: pending = ordered − supplied (never negative); invoice balance = ordered − invoiced. [Reconstructed]
* Sales Manager edit/delete of an enquiry → approval request (REQ-ROLE-02).
* Pending PO page lists open order lines; Delivery Challan records supply against the PO.

### 4.1 Print & PDF of sales documents [Asked, several rounds]
Header & footer unchanged; **no rounded corners**; customer details + document number/date panel + item table are **one joined block**; totals box border matches the table; **QR code must be visible** in both PDF and print; **company logo printed**; Ref and Date removed from the label (see §6).

## 5. Payments
* REQ-PAY-01 Payment collection tracks amount, receipts log, balance = amount − received (never negative); receiving more than the balance asks for confirmation. [Reconstructed]

## 6. Print Label (shipping labels) — menu entry in Sales panel only [Asked]
Removed from Delivery Challan / Quotation / Proforma and the other sales panels. Placed **after the Payment Collection button**. Two modes: from a sales document, or **custom label** (pick customer → pick person; address & details auto-fill).
* REQ-LBL-01 Defaults: paper **A4**, label size **A5**, FROM size **150 %**, **Attn and phone NOT printed**. Sizes offered: A4, A5, 4×4 in, **6×4 in portrait**; user chooses at print/PDF time (paper size, number of boxes, include person name/phone). [Asked]
* REQ-LBL-02 **Actual size, never stretched.** On an A4 sheet a smaller label keeps its true size and is tiled: A5 = half a sheet (landscape sheet, 2 per sheet), 4×4 = 4 per sheet, 6×4 = 2 per sheet. A4 label = 1 per page. [Asked]
* REQ-LBL-03 If paper = "label size", the page is the label (6×4 portrait = 101.6×152.4 mm). [Asked]
* REQ-LBL-04 Content order: DELIVER TO block on top (name, address, **area in bold**, city/state, PIN, optional Attn/phone), transport/courier/vehicle, "BOX n OF m", and the **FROM block (logo + company + address) always at the bottom**. No Ref or Date. A sales-document label does not print "From a sales document". [Asked]
* REQ-LBL-05 "Deliver to" name: if a customer is picked its name is used by default; if the user types a Deliver-to name, **that** is printed instead. [Asked]
* REQ-LBL-06 FROM block size selectable (100 / 125 / 150 / 200 %), default 150 %. [Asked]
* REQ-LBL-07 The contact person is **not auto-selected**; Attn is filled only when the user picks a person. With no person selected, Attn stays blank. [Asked]
* REQ-LBL-08 Both Print and **Download PDF** work and produce identical layout. "Glass look" styling in the label screen. Delivery challan with > 4–5 items still prints correctly. [Asked]

## 7. Tasks
* REQ-TSK-01 Task page main list = **my own tasks only**. Admin/BM have a **My tasks / Everyone** switch. [Asked]
* REQ-TSK-02 A separate panel **below the calendar** lists *tasks I assigned to others* ("Assigned by me") so the giver can follow up. A task assigned by Sanjeev to Devdutt appears in Devdutt's list and in Sanjeev's "Assigned by me". [Asked]
* REQ-TSK-03 **Only the creator can remove a task**; it stays on both creator's and assignee's panels until then. (Old tasks with no creator: Admin may remove.) [Asked]
* REQ-TSK-04 Assignee may update status; Admin/BM/creator manage the task. [Reconstructed]
* REQ-TSK-05 Multiple assignees supported; task kind (Call/Visit/Appointment/Task) from `taskType` or the title prefix. [Reconstructed]
* Task cards are **collapsible** (per card + collapse/expand all). Collapsed card shows title, due, status and a clear "▾ Hide / ▸ Show" button. [Asked]
* Branch Staff do not get the team task view in the main list (disclosed assumption). [Assumed]

## 8. Interactions, calls & visits
Interaction types: **Call, Visit, Appointment** (+ notes, follow-up date). Calls and Visits are **separate** concepts; Follow-up Calls (Sales) are kept separate; the Activity view merges all calls into one *Calls* section. Numbers in dashboards/reports are clickable and open the detailed list. [Asked]
* REQ-INT-01 A follow-up date creates a **task** for the logger. [Reconstructed]
* REQ-INT-02 An Appointment must have its appointment date. [Reconstructed]
* REQ-INT-03 Logging a **Visit** auto-closes that contact's open Appointment tasks. [Reconstructed]
* REQ-INT-04 **Joint visit/appointment**: each joint member gets their own task. [Reconstructed]
* REQ-INT-05 "Also met" contacts get a copy of the visit flagged `isCopy` (so counts are not doubled). [Reconstructed]
* REQ-INT-06 **Appointment → Visit %**: appointments taken vs visited, shown as a percentage; "appointments not visited" = appointments with no later visit. [Asked]

## 9. Outreach (weekly call assignments)
Admin/BM assign contacts to staff for the week (`weekOf` = Monday). DND contacts are skipped.
* **Known gap (REQ-OUT-GAP):** the reference app checks contact visibility for the *assigning admin*, so a contact hidden from a staff member by `contactAccess` can still be put on that member's call list. **Django build should filter by the assignee's `ContactAccess`.** No test is shipped for this because the reference app fails it; add the test when you implement it.

## 10. Attendance
* REQ-ATT-01 Working hours default 09:30–18:30 (per-user `work_start`); **10-minute grace**; later than grace = Late (shows minutes). [Asked]
* REQ-ATT-02 Day codes: P present, L late, H half-day, A absent, LV approved leave, O off/holiday. Weekly off (default Sunday), holidays (all or per branch), approved leave; absent only for past days; days before joining/attendance start are blank. [Asked/Reconstructed]
* REQ-ATT-03 Manual status override beats auto-calculation; monthly tally of present/late/half/absent/leave/off and worked minutes. [Reconstructed]
* REQ-ATT-04 **Location is recorded at check-in and check-out for everyone** (all roles); check-in requires a location; check-out cannot precede check-in. Office staff may check in from home; Admin can see each person's recorded location in the attendance detail. [Asked]
* REQ-ATT-05 Admin sees all active staff; Branch Manager sees their team; leave requests decided by Admin or the team's BM (not their own). [Reconstructed]
* Attendance page shows a **short summary first** with a button for the **detailed report**. [Asked]

## 11. Approvals & notifications
Types: **edit, delete, customer-access**. Pending list has a **View** option showing exactly what changed (before/after). Approver = Admin/BM. Requester is notified of the decision. [Asked]

## 12. Dashboard & reports
Dashboard (Admin: company-wide; others: personal). Reports: Sales Performance, Customer Activity, Not Contacted, User Performance, Sales Reports, Customer Reports, Payment Collection, Interaction Log. Calls and Visits reported separately; Customers-called and Customers-visited are distinct from call/visit counts. [Asked/Reconstructed]

## 13. Admin tools
Manage lists (sources, job titles, industries, brands, products, categories, units, tax rates, sales persons, payment terms, languages, transport, courier), Import Excel, Backup & Restore (all datasets — REQ-BAK-01), Users, Branch (numbering, letterhead, terms).

## 14. Storage / data-loss (reference app only)
User reported data vanishing on refresh. Cause unconfirmed (blocked browser storage or opening a new copy of the file). The reference app now shows a red warning banner (REQ-STO-01). **Not needed in Django** — use the database.

## 15. UI details to preserve [Asked]
Login screen wallpaper uses the **Anupam 360 logo** (untilted tiles, no cut-off pieces). Glass-look label screen. Searchable customer drop-downs everywhere. Back button behaves per screen.

---
## 16. Automations (things the system must do by itself)
Everything the app does automatically, in one place. All have tests (`REQ-AUT-nn` plus the earlier IDs noted).

| ID | Trigger | Automatic result |
|---|---|---|
| REQ-DOC-01 | New sales document | Next number for that **type + branch** is filled in; counter only moves forward |
| REQ-PO-01/02 | Supply logged against a PO | PO status becomes Pending / Part Pending / Completed; **Hold** is never overwritten |
| REQ-INT-01 | Call/Visit/Appointment logged with a follow-up date | A task is created for the logger |
| REQ-INT-03 | Visit logged | That contact's open Appointment tasks are closed automatically |
| REQ-INT-04 | Joint visit/appointment | Each joint member gets a task |
| REQ-INT-05 | "Also met" contacts on a visit | A flagged copy of the visit is added to each (not double-counted) |
| REQ-AUT-01 | Admin/BM assigns customers to staff for outreach | One entry per contact; **DND contacts skipped**; no duplicate for same staff + week; week always starts **Monday**; customer with no contacts gets one blank entry |
| REQ-AUT-02 | Sales Manager requests access to a customer | One pending request only; **every Admin and Branch Manager is notified**; on approval the requester is added to *assigned to* and notified |
| REQ-AUT-03 | Request rejected | Requester notified; nothing changes |
| REQ-AUT-04 | Approver approves an edit/delete request | The proposed change is applied (edit replaces the record, delete removes it) and the request leaves the pending list |
| REQ-AUT-05 | Assignee marks a task Done | The **creator is notified to verify** (only on a fresh completion, never for self-assigned tasks) |
| REQ-AUT-06 | Creator removes a task | If it was Done: assignees told "verified and completed"; otherwise the creator is told it was removed |
| REQ-AUT-07 | Task assigned to people | Each assignee (except yourself) is notified |
| REQ-AUT-08 | "Schedule follow-up" from a sales document | A Call/Visit/Appointment task linked to the document is created, assignee notified |
| REQ-AUT-09 | Leave requested / decided; holiday added | Admin notified of request; employee notified of decision; holiday notice to everyone (or to the chosen branches) |
| REQ-AUT-10 | Custom label: customer picked | Deliver-to, address, area, city, state, PIN, transport, courier fill automatically; **person and phone only when you pick a contact** |
| REQ-AUT-11 | Quotation saved that was created **from an enquiry** | The enquiry becomes **Completed** and the user is told |
| REQ-AUT-12 | Quotation/Proforma marked Win / Lose | **Win needs an Order Value**; Lose stores a reason; switching clears the other |
| REQ-AUT-13 | **New** Delivery Challan saved (with a branch) | One stock **OUT** entry per item (qty > 0), source "Delivery Challan"; editing never repeats it |
| REQ-LOG-01 | "Call me later" date entered in a document's / payment's contact log | A **Call task** is created for the person logging it |
| REQ-OUT-01 | Outreach call marked **Called** (first time) | A Call interaction is added to that contact's history ("Outreach — call completed." if no remarks) |
| REQ-OUT-02 | Outreach "Call log" (contact not reached) with a call-again date | A Call task is created for the **assigned staff member**; every attempt is kept |
| — | Saving a document | Prompt to Skip / Preview / Print / PDF (quotation, proforma, challan) |
| REQ-ATT-01..03 | Attendance viewed | Present / Late / Absent / Off / Leave worked out from check-in, holidays, weekly off and approved leave |
| REQ-CUS-09 | New customer name typed | Similar existing names are flagged as possible duplicates |
| — | Saving a customer | Name/address are title-cased |
| REQ-STO-01 | Browser storage blocked (HTML app only) | Red warning banner |

**Not automatic, on purpose:** no auto-assignment of customers to salespeople, no auto-emails/WhatsApp (nothing external was requested), and no automatic stock deduction (stock was not part of this pack).
**Gap:** the outreach rule in REQ-AUT-01 should also respect each staff member's `ContactAccess` in Django (REQ-OUT-GAP).

---
## 17. Sales documents — detail per type (reference app)
Common: customer (required), branch (required), date, document number (editable), contact (where applicable), remarks, **Clone** an existing document, view page with history, preview/print/PDF/Excel export, row actions menu, filters (customer, number, item, date, status, call-later, last-contact).

| Type | Contact | Items columns | Charges / extras | Link | Statuses |
|---|---|---|---|---|---|
| Enquiry | ✔ + **Source** | none (manual value) | – | – | Pending / Completed / Regretted |
| Quotation | ✔ | name, qty, unit, rate, discount %, tax % | packing, freight, other (each with tax %), round-off (auto, can be overridden), "show discount in PDF" toggle, valid-till, sales person, payment terms, **Terms & conditions** (branch default, editable, "save as default"), call log | from Enquiry | Pending / Win / Lose |
| Proforma Invoice | ✔ | as quotation | as quotation (no valid-till) | from Quotation | Pending / Win / Lose |
| Sales Order = **Pending PO** | – | name, ordered qty, rate, discount | customer's PO number | – | Pending / Part Pending / Hold / Completed |
| Delivery Challan | ✔ | name, make, qty, unit, rate, discount, tax | vehicle, transport, packing/freight/other, terms, call log; **no bank/QR block** | from PO | – (tracked by invoicing) |

* REQ-PRN-01 **Printed totals differ from the form**: with "show discount" off (default) the discount is folded into the rate and the rate is **rounded to a whole rupee**, amount = qty × that rate; with it on, the rate is shown as entered and amount = qty × rate × (1 − disc%). Line tax is **not** in the line amount: all line tax is added up into one **Tax Amount** after Sub Total. Make is shown in brackets after the item name on challans. [Reconstructed]
* REQ-PRN-02 Total = sub total + tax + packing(+tax) + freight(+tax) + other(+tax) + round-off. [Reconstructed]
* REQ-PRN-03 Total **in words**, Indian system (Lakh, Crore): "Rupees One Lakh Twenty Three Thousand … and Fifty Paise Only". [Reconstructed]
* REQ-PRN-04 Reports use the stored total, else the sum of item values, else a legacy value. [Reconstructed]
* REQ-DC-01 **Invoice Done** on a challan item: bill number (required), bill date, quantity (> 0); more than the balance asks for confirmation. A challan is *pending* while any item still has an uninvoiced balance. **DC History** lists fully invoiced items and every invoice transaction (filter by customer, item/DC no.). [Reconstructed]
* REQ-PO-04 **Supply** against a PO item is recorded by hand (date, qty > 0, remarks, editable/deletable), not generated from a challan; qty above pending asks for confirmation. Pending PO page has **Pricing** (read-only rate/discount/amount/value) and **Supply** buttons; **PO History** lists completed lines and supply transactions. [Reconstructed]
* Enquiry / Quotation / Proforma **History** pages: Win and Lose lists with filters, export to Excel/PDF. [Reconstructed]
* Sales Manager: can raise Enquiry and Quotation only; approval needed to edit/delete (REQ-ROLE-02).

## 18. Branches, letterhead & print formats [Asked / Reconstructed]
* Branch record: name, company name, address, phone, mobile, email, website, GST, Udyam, **bank details** (name, branch, A/C no., IFSC), **logo**, **dealer logo**, **footer image**, **payment QR image**, accent colour, **document format 1 or 2**, **watermark** (on/off, logo or text, size), terms, document-numbering settings (REQ-DOC-02).
* **Two print/PDF formats per branch** (Format 1 / Format 2) so different companies can keep different looks; Format 2 has no rounded corners and joins customer details, number/date panel and item table into one block, with the totals box border matching the table and the QR visible. Header and footer are shared. [Asked]
* Watermark can be applied to all PDFs/prints per branch; document theme: accent colour, footer label ("For Anupam Bearings"), signatory label, show logo, default terms. App logo and sidebar logo are changeable (Admin).

## 19. Dashboard
* **Admin (full)**: pending approvals box; pipeline tiles (open enquiries, open quotations, open proformas, pending POs, challans pending invoicing) that open the matching list; outstanding payments with the total and top 6 balances; employee table (customers added, contacts added, documents raised, last activity — numbers open the list); recent activity feed (10, expandable); attendance strip; calendar of tasks.
* **Everyone else (personal)**: tasks pending, due today, overdue; outreach calls pending; calls done, appointments taken, visits made, appointments not visited (REQ-INT-06); own pending enquiries / quotations / proformas / challans / POs; own payments pending and completed; period filter (date range); attendance strip with check-in/out; task calendar. [Asked/Reconstructed]
* Notifications **bell** (desktop and mobile) with unread count, list, click-through; created by the automations in §16.

## 20. Reports (filters: date range, branch, user — user picker only for Admin/BM)
1. **Sales Performance**: counts of enquiries, quotations, orders won; enquiry→quotation % and quotation→win %; quotation / won / lost / pending value; by-branch table; person-wise table; every number drills down to the customers (REQ-RPT-03).
2. **Customer Activity**: top customers by won value; new customers in the period.
3. **Not Contacted**: customers with no call (Call/Cold Call) and/or no visit in the last N days; mode = neither / not called / not visited / either; filters branch, state, area, user; "never" counted; longest gap first (REQ-RPT-02).
4. **User Performance**: per user — calls, visits, appointments (taken vs visited %), follow-up calls, customers called / visited, and a short attendance summary; every number drills down to the underlying list.
5. **Sales Reports** and **Customer Reports**: tabular reports with filters.
6. **Payment Collection**: outstanding by age — 0-30, 31-60, 61-90, 90+ days from the payment date — and by customer (invoiced, received, balance).
7. **Interaction Log**: filter by type (Call, Visit, Appointment, Sales Log, Payment Log, Outreach); clickable tiles.
All reports export to Excel and PDF. Sales Manager restrictions: REQ-RPT-01.

## 21. Payment collection [Reconstructed]
Form: customer, contact, branch, amount, date, remarks. Receipts are added over time (amount, date; more than the balance asks for confirmation). Lists: pending (balance > 0) and history (fully paid), filters, contact-log with "call me later" (REQ-LOG-01). Visibility: Admin/BM/Staff see all payments; others only those they created (REQ-PAY-02). Branch = the form's branch, else the creator's first branch. Ageing buckets in §20.

## 22. Contact log & messaging
Quotation / proforma / challan / payment each have a **contact log** (chat-style notes with the user and time, optional "call me later" date) and a **call log** with outcome (Answered, Busy, Not reachable, Not Answering). Phone numbers open WhatsApp (`wa.me`; a 10-digit number gets +91 added) or the dialler; emails can be copied. "Last contact on" and "Call me later" (none / overdue / today / upcoming) are list filters (REQ-LOG-01/02). [Reconstructed]

## 23. Interaction form on a contact [Reconstructed]
Types offered on the form: Call, Visit, Appointment (older data may also contain Cold Call, which is counted as a call); date, notes, follow-up date, link to a sales document, **joint** members, **also-met** contacts, add a new person on the spot. **Visit** can capture the GPS position (± accuracy, map link) and shows distance from the customer's pinned plant location. Interaction history per contact and customer; person profile page lists the contact's documents. Call types counted as "calls": Call and Cold Call (REQ-INT-07).

## 24. Users, login & security [Reconstructed]
* First run: create the first Admin account. Login = User ID then password. **Inactive users cannot sign in** (REQ-USR-01).
* User fields: name, user ID, password, role, phone, email, employee code, DOB, date of joining, working hours start/end, weekly off days, active, branch(es), plus Aadhaar and PAN numbers (treat as sensitive — encrypt/restrict in Django).
* Deactivate: Admin only; not yourself; at least one active Admin must remain. Remove: Admin only; not yourself; if the user owns records (customers created/assigned, tasks, documents, payments, outreach) their records must be **transferred to another user** first (REQ-USR-02).
* Admin/BM team scope: a Branch Manager's team = people sharing their branch(es).

## 25. Manage lists, Import, Backup
* **Manage lists** (Admin): sources, job titles, industries, brands, products, categories, units, tax rates, payment terms, languages (rename/delete/add), sales persons, transport and courier lists.
* **Import from Excel** (REQ-IMP-01): download a template (columns Company, Plant, Address, Area, City, State, Pincode, Website, GST Number, Plant Location, Head Office …, Industry, Source, Potential, Transport/Courier Preference, Preferred Languages, Assigned To, Interested Brands/Products, Contact Name, Job Title, Phone, Phone 2, Email). Same company on several rows = one customer with several contacts; existing customers are updated, blank cells keep saved data; header names tolerate case/spaces; map pins accept "lat, lng" or a Google Maps link; a summary says how many customers/contacts were added.
* **Backup & Restore** (Admin): one JSON with every dataset (REQ-BAK-01, list in `BACKUP_KEYS`); restore shows what the file contains and what an older backup lacks, **downloads a safety copy of current data first**, then replaces the data.
* Excel / PDF export of customer lists and every history/report page.

## 26. Not built / out of scope in the reference app
* **Stock**: the data tables (stock products, suppliers, bills, transactions) exist and challans write stock-OUT entries (REQ-AUT-13), but there is **no stock screen**. Decide whether the Django app needs one.
* No e-mail / WhatsApp sending (only links), no GST filing, no paid map or billing services.

## 27. More rules found in a second audit (of the app's own messages)
* REQ-USR-03 **Forgot password** (login screen): if another Admin exists, one of them must confirm with *their* password; new password at least 6 characters and must match the confirmation; the old numeric `pin` field is dropped. A sole Admin can reset without a verifier. **Django: store only hashed passwords** — the reference app keeps them in plain text, and Aadhaar/PAN as plain fields.
* REQ-GEO-01 Map pins (plant and head office) accept `lat, lng` (comma, semicolon or space) or a Google Maps link (`@lat,lng`, `?q=`, `!3d..!4d..`, …); out-of-range or unrecognised text is rejected with a message; pin remembers who set it and when; "use my current location" and "remove pin" ask for confirmation before replacing/removing.
* REQ-GEO-02 Distance between two pins is the great-circle distance, shown as `450 m`, `1.5 km`, `25 km`; a Visit shows distance from the customer's pin.
* REQ-CUS-10 Contact selection (tick contacts or whole customers): **copy e-mail addresses** (de-duplicated, blanks skipped) and **export a .vcf phonebook file** (name, company, title, mobile, e-mail) for Gmail/phone import; both refuse an empty selection.
* REQ-DOC-06 Saving a document: customer required; branch required; documents with items need at least one (blank rows are dropped); saving a new document asks nothing else.
* REQ-PO-05 Editing a Pending PO keeps each line's supply history; deleting a supply entry recalculates the PO status (Hold stays).
* REQ-TSK-06 Editing a task: Admin, Branch Manager or the creator only.
* REQ-LBL-09 A label cannot be made without a "who is it for" name (typed name or the picked customer).
* REQ-LST-01 Deleting a pick-list value (source, industry, brand, product, category, unit, tax rate, payment term, language, transport, courier, sales person) or a **branch** never changes records that already use it — they keep the old text. Approving a request removes it from the list; a request whose record no longer exists is dropped.
* Other guard-rails seen in the app: only Admin/BM may assign customers or outreach lists or remove outreach entries; a user cannot request access to a customer they already have, nor file two pending requests; check-in/out refuse without a location; a leave request can be cancelled by its owner; holidays can be added for all or selected branches and removed; "Nothing to export / print / download" messages for empty lists; watermark text required when watermark type is text.

## 28. How complete is this? (honest status)
**Checked line-by-line against the code:** roles & visibility, contact-level assignment, approvals, tasks, interactions, outreach, attendance, sales documents (all five types), numbering, printed totals, amount in words, PO / challan / invoice rules, payments, dashboards, every report's logic, Excel import, backup/restore, users/login/password, labels, map pins, notification triggers. 60 of the rules are also **proven identical** to the reference app by running both on the same inputs (`PARITY` checks).
**Checked only by reading screen text, not logic:** Map & Nearby page, customer detail page layout, the approvals "what changed" viewer, calendar widget, notification pop-over, smart-filter panel, mobile layout, sidebar/theme styling, the exact PDF/print pixel layout of quotations/proformas/challans.
**Not recoverable:** your exact words for requests made before 23 October.
If you spot anything not described here, send me the screen or the sentence and I will add a rule + test for it.

---
## Items I could not verify
0. **Correction made on review:** the first version of this pack described document numbers as `QUO1`; the real format is `QUO-0001` (REQ-DOC-01). Rules, tests and this file are fixed, and a parity check now compares the Python rules with the live app so this kind of slip is caught.
1. Requests from the **first part of the conversation** (before ~23 Oct) are reconstructed, not quoted.
2. Exact print/PDF pixel layout is verified only by eye in the reference app — the tests cover size/tiling/content rules, not visual fidelity.
3. Django-specific tests (models, views, permissions classes) are **not** included — they need your models. Share them and they can be written to the same REQ-IDs.
