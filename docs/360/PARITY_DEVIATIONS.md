# Conscious deviations from `contact_management.html`

Everything not listed here is meant to be identical. Each entry says what differs, why, and what the user sees.

| # | Where | Reference does | 360 does | Why |
|---|---|---|---|---|
| 1 | Skin | Slate sidebar, system font, amber accent, image logo | Near-black sidebar, Space Grotesk / Inter, brand orange, "360" wordmark | **The allowed theme difference.** Semantic colours (tiles, potential, statuses, roles) are unchanged. |
| 2 | Sign-in | Step 1 checks the User ID exists ("User ID not found") | Step 1 only collects the ID; a wrong ID or password gives one generic message after step 2 | Avoids telling strangers which user IDs exist; the screens and flow are otherwise the same. |
| 3 | Sign-in / reset | Reset lists the other admins in a drop-down | Reset asks for the confirming admin's User ID | The drop-down would publish the admin list on the login page. |
| 4 | Sidebar footer | "Switch user" swaps the person in the same page | "Switch user" logs out to the sign-in page | One Django session per browser; same result for the person. |
| 5 | Task page | Switching **My tasks / Everyone** leaves the stat tiles showing the previous scope's numbers | Tiles refresh with the list | The reference behaviour is a stale-render bug. |
| 6 | Task page | "Upcoming (future date)" also counts tasks due **today** (date string parsed as UTC midnight) | Strictly after today | The tile's own label says "future date". |
| 7 | Sidebar | — | Audit log and Approvals screens are reachable from the Backup page / Dashboard rather than their own menu entries | They exist in the spec pack, not in the reference; the sidebar stays identical. |
| 8 | Time | Browser clock | Browser clock for the page, server clock (Asia/Kolkata) for stored dates and attendance rules | Rules (grace period, week start) must not depend on the visitor's device. |
| 9 | Attendance | Check-in / check-out locations are shown to every viewer of a record | Shown to the Admin and to the person themselves only | Privacy rule of the spec pack (REQ-ATT-04); the rest of the page is identical. |
| 10 | Branch defaults | A user's "own branch" is the first branch in the order it was typed on the user (Chennai for the seeded admin) | The first branch by internal id (Bengaluru) | A user's branches are an unordered set on the server; only matters for users with several branches. |
| 11 | Reports | Built in the browser from every list the user holds | Built in the browser from the same lists, but those lists are scoped by the server (a user can only report on what they may see); the older server report endpoints stay for the API and exports | Same screens and numbers; no rule is duplicated for the people who may not see the data. |
| 12 | Lists | Branches and people are listed in the order they were typed | Listed alphabetically | The server keeps no typing order. |
| 13 | Backup | Restore downloads a safety copy of the current data to the browser | The server writes the safety copy (and names it after the restore); the page does not list them | The backup is a server-side file in the server's own format, so a safety copy belongs on the server. |
| 14 | Manage lists | Transport / courier details live in the list entry | Same, stored in a new `details` field of the list entry (migration 0014) | The existing `extra` text field is too short and unstructured. |
| 15 | Users form | Password hint "6+ characters" | Hint "At least 8 characters"; the server's password rules apply (length, not common, not all digits, not like the name) | The stricter rule was chosen earlier by the owner. |
| 16 | Users form | Rules checked in the browser only | The same rules are checked by the server too (phone, email, Aadhaar, PAN, dates, branches) | The server must not trust the browser. |
| 17 | Branch numbering | Six document types, including Sales and Purchase | Four (Enquiry, Quotation, Delivery Challan, Proforma Invoice); Pending PO uses the customer's own number | Sales / Purchase numbers belong to the stock bills, which the reference no longer shows. |
| 18 | App / sidebar logo | Stored as text inside the shared settings | Stored as an image file on the server (the sign-in page, sidebar, mobile header and each branch's default letterhead / watermark logo follow it) | The sign-in page and the PDF builder need the file, not browser storage. |
| 19 | Role sweep leftovers | — | For a Sales Manager the Outreach week filter and the Map state filter list one option fewer than the reference; the Print Label branch drop-down opens on a different first branch (see 10) | The option lists come from the data each role may see; not yet traced to a rule. Open item. |
