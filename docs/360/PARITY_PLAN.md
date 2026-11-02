# Anupam 360 ↔ `contact_management.html` — 1:1 parity plan

**Goal.** The Django module at `/360/` must be a 1:1 replica of the reference single-file app
(`contact_management.html`, 15 091 lines, kept in the repo root, git-ignored): same tabs, same placement of every
calendar / card / box / table / button, same fields and forms, same rules and behaviour, same colour coding.
**The only intended difference is the theme** (fonts, sidebar/page skin, the orange brand gradient).

**Source of truth.** The reference HTML. `anupam360_spec/` and `docs/anupam360.md` describe the business rules and
stay valid; where the reference and the current 360 UI disagree, the reference wins for *what the user sees and
can do*, the spec wins for *server-side rules* (permissions, numbering, money).

## 1. Baseline (measured 2026-11-02, same seed data in both apps, admin user)

`tests/parity/` snapshots every top-level view of both apps and diffs the visible headings, labels, buttons, column
headers and filters. Missing-in-360 counts at the start of this work:

| View | missing | | View | missing |
|---|---|---|---|---|
| Dashboard | 13 | | Sales · Enquiry | 13 |
| Task | 26 | | Sales · Quotation | 13 |
| Outreach | 10 | | Sales · Proforma | 13 |
| Attendance | 49 | | Sales · Delivery Challan | 13 |
| Customer (list) | 19 | | Sales · Pending PO | 19 |
| Map & Nearby | 4 | | Payment Collection | 12 |
| Print Label | 14 | | Reports | 17 |
| Manage lists | 16 | | Import Excel | 6 |
| Backup & restore | 5 | | Users | 37 |
| Branch | 12 | | **Total (top-level only)** | **311** |

Sub-screens (customer form, customer view, person profile, sales form, contact log, histories, payment form, …) are
not in that number — they are checked separately in the per-tab passes below. Visual comparison confirms the gap is
structural, not cosmetic: e.g. the reference Customer list is a two-column colour-coded card grid with a hero
banner, stat chips, a Filters panel and an Actions menu; the 360 shows a plain table.

## 2. Approach

1. **Reference CSS ported, skinned by tokens.** `threesixty/static/threesixty/css/app.css` is rebuilt from the
   reference stylesheet (class names kept: `.view-head.cust-hero`, `.panel-box`, `.form-card`, `.dash-grid`,
   `.cv-pref-grid`, `.chip-group`, `.row-menu-wrap`, `.mini-cal-*`, `.task-*`, …). Only the root tokens differ:
   page/sidebar skin, fonts, brand orange. **Colour coding is kept verbatim** — pipeline tiles (blue / purple / teal /
   orange / pink), potential (High green, Medium amber, Low red, WhatsApp/Email grey), order statuses
   (Pending amber, Win/Completed green, Lose/Regretted red, Part Pending orange), calendar legend, role pills.
2. **Reference DOM, 360 data layer.** Each view is rewritten to emit the reference's DOM structure (same order,
   same ids where practical) and drive the existing `/360/api/` services instead of `window.storage`.
   Business rules stay on the server (permissions, numbering, money, approvals). Where the reference does
   something the API cannot yet do, the API/service is extended (with tests) — never faked in the browser.
3. **Tab-by-tab, in sidebar order.** Each tab goes through the same five steps:
   *Study* (read reference HTML + JS for that tab, list every element, rule, colour) →
   *Cases* (write/extend the test cases in `PARITY_TESTS.md`) →
   *Build* (CSS + view JS + API gaps) →
   *Compare* (run the harness: side-by-side screenshots + structural diff + scripted interaction on both apps with
   the same data) →
   *Sign-off* (all cases for the tab pass; status table below updated, commit).
4. **Back-and-forth verification.** Every tab is opened in the reference and in 360 under all four roles
   (Admin, Branch Manager, Branch Staff, Sales Manager) and, for sales tabs, for each document type. A tab is not
   "done" until the diff is empty except for theme differences and every case below is ticked.

## 3. Verification harness (`tests/parity/`)

* `harness.py` — Playwright (system Chrome) helpers: logs into the reference file (served on :8020) and 360 (:8010).
* `mkseed.py` — builds one backup-format JSON (4 users, 6 customers / 15 contacts / interactions / geo pins,
  8 sales documents, payments + receipts, tasks, outreach, attendance, leave, holiday). It is injected into the
  reference through its own `BACKUP_ITEMS` setters and into 360 through `manage.py import_360_backup`, so both apps
  show identical data.
* `snapshot.py` / `diff_outline.py` — full-page screenshots + normalised outline of every view in both apps and the
  missing/extra diff above. Extended per tab with scripted flows (open form, add contact, change status, …).
* Run locally: `python -m venv /tmp/pw && /tmp/pw/bin/pip install playwright`, start the 360 test server on a
  throw-away DB (never the real `db.sqlite3`), then `python tests/parity/snapshot.py && python tests/parity/diff_outline.py -v`.

## 4. Order of work and status

Legend: ☐ not started · ◐ in progress · ☑ signed off (all cases pass, diff clean).

| # | Area | Reference sections | Status |
|---|---|---|---|
| 0 | **Foundation**: tokens + reference CSS, app shell, sidebar (groups, order, role visibility, badges, user chip, logout), top bar + notification bell, dialogs/toasts, login + forgot password + first-admin | CSS, body L1–162, JS 850–1124 | ☐ |
| 1 | **Dashboard** (admin full + personal for BM/BS/SM, attendance strip, approvals, pipeline tiles, payments, team activity, recent activity) | body L163–212, JS 3148–3575 | ☐ |
| 2 | **Task** (+ notifications, task-bar calendar, upcoming, assigned by me) | body L813–858, JS 9329–9678, 10025–10152, 3436–3575 | ☐ |
| 3 | **Outreach** (+ Assign Call from the customer list) | body L858–872, JS 9678–10025, 1899–1965 | ☐ |
| 4 | **Attendance** | body L872–937, JS 8662–9062 | ☐ |
| 5 | **Customer**: list (cards, stats, filters, actions menu, selection, copy / G-contacts / export), add/edit form (Company details, Head office, Business details, Preferences & assignment, Contact persons), customer view (+ location pins, head office, contacts), person profile (+ Date of Interaction, log interaction, also-met, joint visit, documents), contact edit, duplicate handling, remarks table paste | body L213–294, L1077–1228, L1229–1480, JS 1124–2831 | ☐ |
| 6 | **Map & Nearby** | body L318–343, JS 1124–1323 | ☐ |
| 7 | **Enquiry** (list, form, history) | body L494–665, JS 4776–5900 | ☐ |
| 8 | **Quotation** (list, form, charges/SD, Contact Log, Win/Lose history, outcome dialog) | JS 4916–6746 | ☐ |
| 9 | **Proforma Invoice** (list, form, Win/Lose history) | JS 6746–6969 | ☐ |
| 10 | **Delivery Challan** (list, form, view, Invoice Done, DC history) | JS 8043–8443 | ☐ |
| 11 | **Pending PO** (list, form, pricing dialog, Supply Qty, PO history) | JS 8443–8662 | ☐ |
| 12 | Sales print/PDF/Excel exports + watermark (all doc types) | JS 8548–9330 | ☐ |
| 13 | **Payment Collection** (list, form, view, Received, history) | body L965–1076, JS 10152–10511 | ☐ |
| 14 | **Print Label** | body L937–964, JS 6091–6746 | ☐ |
| 15 | **Reports** (8 tabs + exports) | body L989–1016, JS 10511–11560 | ☐ |
| 16 | **Manage lists** (13 tabs) | body L464–493, JS 3575–3845 | ☐ |
| 17 | **Import Excel**, **Backup & restore** | body L294–367, JS 2831–3148 | ☐ |
| 18 | **Users**, **Branch** (+ letterhead details, document numbering, app/sidebar logo) | body L368–463, JS 3845–4498 | ☐ |
| 19 | **Approvals** screens + cross-cutting: responsive/mobile header, accessibility, role matrix sweep, final full diff | JS 4498–4705 | ☐ |

Order rationale: Foundation first (every tab depends on the CSS and shell); then the sidebar order the user listed
(Dashboard → Task → Outreach → Attendance → Customer → Map → sales tabs → payments → labels → reports → admin).
Customer comes before the sales tabs because every sales form picks a customer + contact.

## 5. Assumptions to confirm (non-blocking)

* "Theme" = the 360 skin (near-black sidebar, Space Grotesk / Inter, brand orange `#ff6a00`, light content area)
  stays; the reference's slate sidebar / system font / amber accent are not copied. Semantic colours are copied.
* The reference "Switch user" link and the localStorage data layer are replaced by Django sessions (one login),
  which is the existing 360 design; the Users page and role behaviour are otherwise identical.
* Stock screens are out of scope (the reference removed them too); the Delivery Challan auto stock-out stays.

## 6. Risks

* Size: the reference app is ~11.5k lines of UI logic; the existing 360 JS is ~200 KB of simplified views. Work is
  large and is done tab by tab with a commit per signed-off tab.
* API gaps will surface per tab (e.g. contact-person profile data, head-office pins, bulk actions). Each gap is
  closed in the service layer with a test before the UI relies on it.
* Printed documents (PDF/print) are pixel-heavy; they are verified by structure (letterhead, title block, table
  columns, totals, amount in words) rather than pixel equality.
