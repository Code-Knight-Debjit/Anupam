# Anupam 360 ↔ reference — parity test cases

How to read this file. Every case is checked **twice**: once in `contact_management.html` (the expectation) and once
in `/360/` with the same seed data. A case passes only when 360 behaves/looks like the reference (theme aside).
`Auto` = covered by `tests/parity/` scripts (outline diff or scripted flow); `Man` = checked by hand with side-by-side
screenshots until a script exists. Status column: ☐ open · ☑ pass. Cases are refined during each tab's *Study* step
(extra cases get the next number; none are deleted).

Roles: **A** Admin · **BM** Branch Manager · **BS** Branch Staff · **SM** Sales Manager.
Seed data: 4 users (admin, manager, staff, sales), 2 branches (Chennai, Bengaluru), 6 customers / 15 contacts,
20 interactions, 8 sales documents (1 per type + win/lose/completed examples), 2 payments, 4 tasks, 2 outreach
assignments, attendance for 5 days, 1 leave request, 1 holiday.

---------------------------------------------------------------------------------------------------------------

## G · Global shell, login, dialogs

| ID | Case | Mode | ☐ |
|---|---|---|---|
| G-01 | Sidebar groups & order: **Dashboard** (Dashboard, Task, Outreach, Attendance) · **Vendors** (Customer, Map & Nearby) · **Sales** (Enquiry, Quotation, Proforma Invoice, Delivery Challan, Pending PO, Payment Collection, Print Label) · **Insights** (Reports) · (Manage lists) · **Main panel** (Import Excel, Backup & restore, Users, Branch) | Auto | ☑ |
| G-02 | Logo at the top of the sidebar; user chip (avatar initials, name, role) + **Logout** button + sidebar footer placement | Man | ☑ |
| G-03 | Role visibility: A sees everything; BM/BS/SM hide Import, Backup, Manage lists, Users, Branch; SM also hides Proforma, Delivery Challan, Pending PO, Payment Collection, Print Label; Dashboard hidden only if the role cannot see it | Auto | ☑ |
| G-04 | Nav badges: Task, Outreach, Attendance, Enquiry, Quotation, Proforma, DC, Pending PO, Payment Collection show the same counts as the reference (open/pending only, role-scoped, `99+` cap, hidden at 0) | Auto | ☑ |
| G-05 | Every user lands on Dashboard after login (customers if the role has no dashboard) | Auto | ☑ |
| G-06 | Top bar: bell icon top-right with unread badge; dropdown "Notifications" + "Mark all read"; clicking an item opens its target and marks it read | Auto | ☑ |
| G-07 | Mobile (≤ 900 px): hamburger header, slide-in sidebar with backdrop, mobile bell + logout; tables collapse with `data-label` cells | Man | ☑ |
| G-08 | Login step 1 "User ID" → Continue; step 2 "Password" → Sign in; "Not you? Change User ID"; wrong ID / wrong password messages; first-run "Create admin account" form (User ID, Your name, Create a password) | Auto | ☑ |
| G-09 | Forgot password flow: admin-verified reset (other admin's password), new + confirm password, "Back to sign in" | Auto | ☑ |
| G-10 | Custom dialogs (alert / confirm / prompt with optional input) instead of browser dialogs; Esc and backdrop behave as in the reference | Auto | ☑ |
| G-11 | Colour tokens: semantic colours (blue/green/purple/teal/pink tiles, amber/green/red status pills, role pills, WhatsApp green) identical to the reference palette; only brand skin differs | Man | ☐ |
| G-12 | Page title / eyebrow / heading / sub-line pattern on every view (`OVERVIEW` eyebrow, H1, grey sub-line); hero banner variant (`cust-hero`) on Customer, Sales, Task, Payment, Reports, Label | Man | ☐ |

## D · Dashboard

| ID | Case | Mode | ☐ |
|---|---|---|---|
| D-01 | Admin: heading "Dashboard", sub-line "Balance overview of everything — approvals, pipeline, and collections." | Auto | ☑ |
| D-02 | Greeting banner (Good morning/afternoon/evening, full name, weekday + date) with chips "N tasks due today" and "N overdue" | Auto | ☑ |
| D-03 | Attendance strip inside the banner: "Attendance · Not checked in yet / Checked in hh:mm", team "X of Y checked in · N leave request(s) waiting", **Check in / Check out** and **Open attendance** buttons; Check in works (GPS optional) | Auto | ☑ |
| D-04 | Section "Pending edit & delete approvals": list with Approve/Reject/View changes, or "Nothing waiting on your approval." | Auto | ☑ |
| D-05 | "Sales pipeline" five coloured tiles with icons: Open enquiries (blue), Open quotations (purple), Open proforma invoices (teal), Pending PO (orange), Delivery challans pending (pink); counts correct; click → that sales tab | Auto | ☑ |
| D-06 | "Payment collection" box: total outstanding + per-customer balances (customer name, not "—"); links to Payment Collection | Auto | ☑ |
| D-07 | "Team activity" table: Employee, Role (role pill), Customers added, Contacts added, Sales docs raised, Last activity; counts are click-through links | Auto | ☑ |
| D-08 | "Recent activity" panel with show-more | Auto | ☑ |
| D-09 | BM/BS/SM personal dashboard: "Show my activity for" select (Today / This week / This month / All time / Custom dates), From/To date inputs, Clear dates, personal tiles grid, personal pending approvals block | Auto | ☑ |
| D-10 | Personal tile counts (Done / Taken / Visited / pending tasks / overdue) equal the reference for each preset and custom range | Auto | ☑ |
| D-11 | Dashboard badge (nav) and "seen count" behaviour as reference | Man | ☑ |

## T · Task

| ID | Case | Mode | ☐ |
|---|---|---|---|
| T-01 | Layout: hero "Work / Task" + sub-line + **+ New Task**; left column (stats row, kind tabs, search + Filters, list); right column (calendar, Upcoming tasks, Assigned by me) — same placement | Auto | ☑ |
| T-02 | Scope switch **My tasks / Everyone** (A and BM only); kind tabs All / 📞 Calls / 📍 Visits / 📅 Appointments / ✔️ Other tasks with counts; **Collapse all / Expand all** | Auto | ☑ |
| T-03 | Stats row tiles (Open, Due today, Overdue, Done … as reference) with colours | Auto | ☑ |
| T-04 | Search placeholder "Search task, customer, contact or person"; **Filters** panel (badge with active count) with the same filter set | Auto | ☑ |
| T-05 | Month calendar: ‹ month › navigation, weekday header, day cells with coloured dots (Call / Visit / Appointment / Other legend), **Today** button, day click lists that day's tasks | Auto | ☑ |
| T-06 | "Upcoming tasks" list and "Assigned by me (n)" panel | Auto | ☑ |
| T-07 | New/Edit task form fields: title, description, type, due date, assignee, joint-with, priority, related customer/contact/document — same order and labels | Auto | ☑ |
| T-08 | Complete a task → creator gets a verification notification; creator verifies / reopens (flow identical to reference) | Auto | ☑ |
| T-09 | Remove: creator only (Admin for creator-less old tasks); others see no Delete | Auto | ☑ |
| T-10 | Task cards: priority/type colour coding, overdue highlight, collapsible detail, related-record chips | Man | ☑ |

## O · Outreach

| ID | Case | Mode | ☐ |
|---|---|---|---|
| O-01 | Hero block `callingListHero`, stats row, filter row, list — same order as reference; sub-line shows this week's progress | Auto | ☑ |
| O-02 | Each assignment card: customer, contact, phone/WhatsApp links, remarks, status pill, **Called / Not reached** actions, attempt history, "call again" date | Auto | ☑ |
| O-03 | Attempt reasons (Call not connecting / Not Answered / …) and call-later date behave as reference; completing an assignment logs an interaction on the contact | Auto | ☑ |
| O-04 | **Assign Call** (Customer list → Actions → Assign Call): pick person + week + contact per customer; Monday-based week; creates assignments; duplicate prevention message | Auto | ☑ |
| O-05 | Visibility: staff see only their own; A/BM see team with assignee filter | Auto | ☑ |

## AT · Attendance

| ID | Case | Mode | ☐ |
|---|---|---|---|
| AT-01 | Layout order: subline, Today card, **My month** (month picker, stats row, table), **Holidays** (form card + list), **Leave** (form card + my leaves), team section (leave approvals, Team attendance grid, Check-in & check-out times) | Auto | ☑ |
| AT-02 | Today card: check-in / check-out buttons, times, status pill (Present / Late / Half day), location capture note | Auto | ☑ |
| AT-03 | Status rules: 10-minute grace, late/half-day thresholds from the user's work hours, weekly off, holidays, leave — same letters P / L / H / A / LV / O in the grid | Auto | ☑ |
| AT-04 | Team grid: month + branch pickers, **Export to Excel**, click a cell to correct a day (admin/manager), legend text identical | Auto | ☑ |
| AT-05 | Holiday form (From, To optional, name, applies to branch chips) — A only; list with delete | Auto | ☑ |
| AT-06 | Leave request (From, To, Reason) → pending → approve/reject by manager; balance/status pills | Auto | ☑ |
| AT-07 | Role scope: A all staff, BM team, BS/SM themselves | Auto | ☑ |

## C · Customer (list, form, view, profile)

| ID | Case | Mode | ☐ |
|---|---|---|---|
| C-01 | Hero banner "🏢 Customer list" with stat chips **Customers / Contacts** and **+ Add customer** inside the banner | Auto | ☑ |
| C-02 | Search box (placeholder "Search company, city, area, industry, source, or contact name") + **Filters** button; filter panel with 14 controls: job title, state, area, industry, source, potential, brand, product, assignee, added by, language, last call, last visit + **Clear filters**; badge shows active count | Auto | ☑ |
| C-03 | Selection bar: "Select all shown" checkbox, count text, **Actions ▾** menu (Print, Excel Export, PDF Export, Assign, De-assign, Assign Call, Copy, Export G-contacts), **Clear selection**; export/assign items hidden for BS and SM | Auto | ☑ |
| C-04 | Customer **cards** in two columns: coloured left edge + tinted background by potential (High green, Medium amber, Low red, WhatsApp/Email grey/none), initials avatar (or uploaded logo), name, plant pill, potential pill, address, website link, checkbox, **View / Edit / Delete** buttons, "Contacts (n) Show ▾" expander listing contacts with tag by job title, phone, WhatsApp, email, per-contact selection | Auto | ☑ |
| C-05 | Search ranking and matching: name starts-with before contains, then city/area/industry/source/contact name | Auto | ☑ |
| C-06 | Visibility: SM sees only customers they created or are assigned; contact-level access restrictions respected; BS/BM/A see all | Auto | ☑ |
| C-07 | **Add customer** page (not modal): Back button, eyebrow "Customers", H1 "Add customer", sub-line; cards **Company details** (logo upload, Company name + duplicate-warning box, Plant/Unit, Address, Area, City with datalist, State select, Pincode, Website, GST Number, 📍 Plant location with "Use my location" / "View map"), **Head office (if different)** (name, address, city, state, pincode, phone, 📍 pin), **Business details** (Industry, Source, Potential, Transport Preference, Courier Preference selects), **Preferences & assignment** (language chips, Assign to chips, Added by, brand chips, product chips), **Contact persons** (grid header Name / Job title / WhatsApp No. / Phone 2 / Email, "+ Add another contact", per-row remove), Cancel / **Save customer** | Auto | ☑ |
| C-08 | Validation messages: company name required; duplicate/near-duplicate company warning with "open existing / add anyway"; GST format; pincode digits; phone normalisation; at least one contact rules as reference | Auto | ☑ |
| C-09 | Edit by A/BM/BS(non-delete) saves directly; Edit by SM creates an approval request; Delete by BS/SM creates an approval request; A/BM delete directly | Auto | ☑ |
| C-10 | **Customer view** page: Back, hero with avatar + name + address, **Check Transactions** + **Edit**; fields grid (Area, City, State, Pincode, Website, GST Number, Industry type, Source, Transport Preference, Courier Preference); "Location pins" grid; "Head office" grid (only when present); "Preferences & assignment" mini tiles; "Contact persons" cards | Auto | ☑ |
| C-11 | **Person profile** page: hero (avatar, name, sub), **✎ Edit** and **Do Not Disturb** toggle; "Contact card" (Company name, Job Title, Phone/WhatsApp Number, Phone 2, Email Address); "Date of Interaction" tiles (📞 Last call, ✉️ Last email, 📍 Last visit); "Log a new interaction" form (Type Call/Visit/Appointment, Date, follow-up/appointment date toggle button, Visit location capture, Joint visit with, Also met + "+ Add new person", Regarding document, Notes) + **Save Interaction**; "Interaction history"; "Sales documents" table + **More** | Auto | ☑ |
| C-12 | Interaction rules: visit location required/optional as reference; joint visit and also-met create linked entries on the other people; follow-up date creates a task/outreach as reference; DND contact blocks outreach & bulk lists | Auto | ☑ |
| C-13 | Contact edit dialog (name, job title, phones, email) from the customer view without opening the whole form | Auto | ☑ |
| C-14 | Remarks/paste-table helper (paste tab-separated text → aligned columns) where Remarks exist | Man | ☑ |
| C-15 | Actions: Print and PDF/Excel export of the selection (or all shown), column set identical; **Copy** (emails/phones to clipboard with manual-copy fallback); **Export G-contacts** CSV in Google Contacts format; **Assign / De-assign** modal (users + contacts); **Assign Call** modal (person, week, contact) | Auto | ☑ |
| C-16 | Company logo upload/remove, avatar fallback with initials and stable colour | Auto | ☑ |
| C-17 | Customer-location pins: capture via "Use my location", paste "lat, lng" or Google Maps link, "View map", distance display on the interaction ("N km from the pin"), set-by/at stamps | Auto | ☑ |

## M · Map & Nearby

| ID | Case | Mode | ☐ |
|---|---|---|---|
| M-01 | Header "Customers / Map & nearby"; toolbar order: show-select (Plants & head offices / Plants only / Head offices only / Customers with no pin), state select, assignee select, **📍 Near me**, radius select (Any distance, 5, 10, 25, 50, 100 km), count text | Auto | ☑ |
| M-02 | Map box left + list right (`map-wrap`); markers for plants vs head offices differ; list sorted by distance when "Near me" is used; clicking a list row centres the marker | Auto | ☑ |
| M-03 | "Customers with no pin" lists customers lacking coordinates with an Add-pin shortcut | Auto | ☑ |

## S · Sales: Enquiry · Quotation · Proforma · Delivery Challan · Pending PO

| ID | Case | Mode | ☐ |
|---|---|---|---|
| S-01 | Common list page: hero (eyebrow Sales, H1 = tab name, sub-line, **+ New <Doc>** button), stats row (quotation / proforma only), search "Search customer, no. or item", **Filters** (badge), **View All** (toggle/undo), **Actions ▾** (PO History / Export Excel / Export PDF / Print / Watermark…), filter row, table | Auto | ☑ |
| S-02 | Enquiry table columns: "Enquiry No. / Date / Branch / Added by", Customer Name, Contact Person (with WhatsApp link), Status (coloured select Pending amber / Completed green / Regretted red), row actions View / Edit / Delete; only Pending listed; button to Completed & Regretted history | Auto | ☑ |
| S-03 | Quotation table: "Quotation No. / Date / Branch / Added by", Company, Contact, Quotation Value, Order Status (Pending / Win / Lose), actions incl. **Contact Log**; filters Customer, Branch, Call later, Last contact, Clear; "Win and Lose Quotations" history screen (Won / Lost sections, filters, Excel/PDF/Print) | Auto | ☑ |
| S-04 | Proforma table + stats + filters (Customer, Branch, Call later, Last contact) + Win/Lose Proforma history | Auto | ☑ |
| S-05 | Delivery Challan table (pending-invoice balance per item), filter Branch, **Invoice Done** dialog (item, qty invoiced, invoice no/date) with balance validation, **DC History** (fully invoiced items + all invoice transactions) | Auto | ☑ |
| S-06 | Pending PO ("Sales Order") table with item-level supply status (Pending / Part Pending / Completed colours), filters Customer, Branch, PO No., Date, Item name, Make; **Pricing** dialog (MRP, Discount %, Rate after discount, Value, "Edit in Sales Order"); **Supply Qty** form (qty supplied ≤ balance, date, remarks); **Sales Order History** (completed orders + all supply transactions with filters/exports) | Auto | ☑ |
| S-07 | New/Edit form (view-salesform): Back, eyebrow, H1 "New <Doc>", fields shown per doc type exactly as `SALES_DOC_CONFIG` (Branch*, Document Number [editable number rules], Date, Customer + address line, Contact person, Source [enquiry], Order Status, Quotation Value, Reference, Vehicle number & Transport name [DC], Sales Person, Valid Till [quotation], Your Reference Number/Date, Payment Terms datalist, Remarks, Terms & Conditions + "use for all quotes of this branch") | Auto | ☑ |
| S-08 | Items grid (columns per type: Item name multiline, Qty/Ordered Qty, Unit, Rate, Discount, Tax; catalogue datalist; "+ Add item"; total line); charges block: Sub Total, Packing / Freight / Other charges each with tax %, Round Off with "(auto)", Total Amount; **SD** checkbox for printed discount column | Auto | ☑ |
| S-09 | Money rules: line amount = qty × rate × (1 − disc%) with tax; charges taxed at their own %; auto round-off; totals equal the reference to the paisa for the same inputs (Decimal, round-half-up) | Auto | ☑ |
| S-10 | Numbering: per-branch prefix/suffix/start; editable number allowed per config; duplicate-number rejection; counters survive deletes | Auto | ☑ |
| S-11 | Role rules: SM may raise only Enquiry & Quotation; SM edit/delete → approval request; A/BM/BS direct; BM/BS default to own branch filter, "View All" shows every branch | Auto | ☑ |
| S-12 | **Contact Log** (quotation): chat-style window, suggestion chips (Call not connecting, Not Answered, Call me later → date + Send), message textarea + Send; messages carry user + time; call-later date feeds the "Call later" filter | Auto | ☑ |
| S-13 | Win / Lose outcome dialog: Win asks Order Value; Lose asks reason (textarea); record moves to history; same for Proforma; Enquiry Completed / Regretted | Auto | ☑ |
| S-14 | Sales doc **View** page (DC and others): header details, items, totals, actions Edit / Print / PDF | Auto | ☑ |
| S-15 | Print / PDF / Excel for every doc type: company letterhead (branch name, address, GSTIN, phone, email, logo), title block, customer block, items table with the type's columns, charges, total + amount in words, terms, signatory; watermark options; list exports (Excel/PDF/Print) match the reference column sets | Man | ☑ |
| S-16 | Delivery Challan auto stock-out on save is kept; edit/delete of a DC reverses it | Auto | ☑ |

## P · Payment Collection

| ID | Case | Mode | ☐ |
|---|---|---|---|
| P-01 | List page: hero + **+ New Payment**, stats row, Filters (+badge), View All, Actions ▾ (Payment History …), filter row, table | Auto | ☑ |
| P-02 | New/Edit page: Customer, Contact person, Amount, Date, Branch*, Remarks / Reference; Cancel / Save | Auto | ☑ |
| P-03 | Payment **View** and **Received Payment** dialog (amount ≤ balance, date, mode, remarks); balance and status update; part-payment keeps it pending | Auto | ☑ |
| P-04 | Payment History page: "Fully collected" and "All receipts" tables with filters | Auto | ☑ |
| P-05 | Role visibility: SM hidden entirely; BM/BS default own branch; payments of SM restricted as spec | Auto | ☑ |

## L · Print Label

| ID | Case | Mode | ☐ |
|---|---|---|---|
| L-01 | Page: hero + sub-line; panel "Custom label" with: Pick customer (auto-fills), Pick person, Deliver to, Attn, Phone, Address, Area (printed bold), City/State, PIN, Transport/courier, From branch; **Print** and **Download PDF** | Auto | ☑ |
| L-02 | Options dialog on Print/PDF: Paper (A4 sheet at original size / Same as label size), FROM logo & address size, Label size, Number of boxes (1–99), Print person name (Attn), Print phone; label sizes A5/A6 etc. with sheet orientation rules | Auto | ☑ |
| L-03 | Label content: FROM block (branch letterhead + logo), TO block with bold area, boxes "n of N" | Man | ☑ |
| L-04 | Quick label from Customer list / Sales doc rows opens the same dialog with prefilled data | Auto | n/a — `labelPageDoc` exists in the reference but nothing calls it; no screen offers it |

## R · Reports

| ID | Case | Mode | ☐ |
|---|---|---|---|
| R-01 | Hero + sub-line; tab strip: Sales Performance · Customer Activity · Not Contacted · User Performance · Sales Reports · Customer Reports · Payment Collection · Interaction Log; filter row (date range, branch, user picker for A/BM); Export Excel / Export PDF / Print / Watermark… | Auto | ☑ |
| R-02 | Each tab's table columns and totals equal the reference for the same data (click-through numbers show the customers behind them) | Auto | ☑ |
| R-03 | Role rules: BS/SM own data only; SM has no Sales Performance / Customer Activity | Auto | ☑ |
| R-04 | User Performance: activity, customers called/visited, sales, tasks, collections, attendance per user | Auto | ☑ |

## ML · Manage lists (Admin)

| ID | Case | Mode | ☐ |
|---|---|---|---|
| ML-01 | Left tab list in order: Job titles, Sources, Industries, Brands, Products, Categories, Units, Tax %, Sales Persons, Payment Terms, Languages, Transport, Courier; right content with add row, rename, delete (never alters existing records) | Auto | ☑ |
| ML-02 | Sales Persons tab has name + phone; Tax % numeric; duplicate names rejected | Auto | ☑ |

## I · Import Excel · Backup & restore (Admin)

| ID | Case | Mode | ☐ |
|---|---|---|---|
| I-01 | Import page: "Bulk add / Import from Excel", "Customers" heading, panel "1. Get the template" (Download template .xlsx), panel "2. Upload your filled file" (.xlsx/.xls/.csv, **Import file**, hint, result box); one row per contact, rows with the same company grouped; error rows reported | Auto | ☑ |
| B-01 | Backup page: "Data safety / Backup & restore"; "Download a backup" panel with count chips + last-backup line + button; "Restore from a backup" panel (file input, description of file, Restore, confirmation, safety copy) | Auto | ☑ |
| B-02 | Backup file is importable by `import_360_backup` and round-trips seed data without loss | Auto | ☑ |

## U · Users · Branch (Admin)

| ID | Case | Mode | ☐ |
|---|---|---|---|
| U-01 | Users page: list panel (name, role pill, user ID, branches, status, Edit / Delete) then "Add a user" form with fields Name, User ID, Password, Role (4 options), Phone / WhatsApp, Email, Employee code, Aadhaar, PAN, Date of birth, Date of joining, Work starts/ends at, Weekly off, Status, Branch(es) chips; **Add user / Cancel edit** | Auto | ☑ |
| U-02 | Rules: password strictness (360 validators), Aadhaar/PAN/DOB masking for non-admin, branch required for BM/BS/SM, last admin cannot be removed/deactivated | Auto | ☑ |
| BR-01 | Branch page: "App logo" (preview, upload, Use default logo), "Sidebar logo" (preview, upload, Same as app logo), branch list with Edit / Delete, "Add a new branch…" + **Create branch** | Auto | ☑ |
| BR-02 | Branch edit: letterhead details (company name, address, GSTIN, phone, email, logo, bank details if present) and document numbering per type (prefix, suffix, start) | Auto | ☑ |

## X · Approvals & cross-cutting

| ID | Case | Mode | ☐ |
|---|---|---|---|
| X-01 | Approvals list: edit / delete / customer-access requests with "View changes" diff; approve applies, reject discards; routing by branch scope | Auto | ☑ |
| X-02 | Sales-doc approval requests from SM (enquiry/quotation edit & delete) | Auto | ☑ |
| X-03 | Final sweep: outline diff empty for every view × every role; screenshots reviewed side by side; all open cases closed | Auto | ◐ outline diff run for all 4 roles: only the items in deviation 19 remain; G-11 / G-12 and the side-by-side screenshot review are still manual |
