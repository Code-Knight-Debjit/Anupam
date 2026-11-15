# 360 — UX fixes (2026-11-15)

## TODO
- [x] 1. Editing a document: changing the **branch** re-numbers it (server allocates from the new branch's counter; form previews it; switching back restores the original number).
- [x] 2. "Use this in future for all quotes of all customers (this branch)": the branch default really is used by the next new document (server + form cache refreshed).
- [x] 3. Row **Menu** in the Sales tables opens **above** the button when there is no room below.
- [x] 4. **Customer search** (all Sales forms/filters, Payment, Task): one combobox — type, see matching customers below (contiguous text match, "Lin" ≠ L…i…n), and a "+ Create new customer" entry that creates the customer in a dialog **without leaving the form**, selects it, and keeps everything already typed.
- [x] 5. **Print = PDF**: Print now prints the very same PDF the PDF button downloads (no browser header/footer, no floating footer image). PDF output unchanged.
- [x] 6. **Task form**: fix the broken "Assign to" dropdown.
- [x] 7. **Enquiry → assign to employees**; the assignment appears as a task in each assignee's Task tab.
- [x] 8. **Pagination** (Gmail style "1–25 of 342 ‹ ›", rows-per-page) on every long list and every Reports table.
- [x] 9. Tests (pytest for server rules, Playwright checks for the UI), deviations noted.

## Plan
1. Server first (1, 2, 7) with pytest — `services/documents.py` (branch move, terms default), `services/tasks.py` + `api/views_sales.py` (assign enquiry), serializer (assignees on a document).
2. Shared client pieces: `combobox.js` (searchable customer picker + inline create), `pager.js` (Gmail pager, wraps tables/lists after they render), row-menu flip in `customer_common.js`.
3. Wire them into salesform / sales list / payments / tasks; fix the task dropdown CSS.
4. Print: hand the generated PDF blob to a hidden iframe and print that, through a hook in the generator (`tests/parity/gen_docprint.py`) so the generated file and the generator stay in step.
5. Verify in a real browser against a throw-away database (never db.sqlite3).

## Result (2026-11-15)
All nine items are done and verified in a real browser against a throw-away database; `tests/test_threesixty_ux_fixes.py` (17 cases) covers the server rules, the whole suite passes apart from the 3 pre-existing numpy/RAG failures. Deliberate differences are numbered 23–28 in `PARITY_DEVIATIONS.md`.
Print, checked: the PDF handed to the printer is byte-identical to the downloaded PDF apart from its timestamp/ID (headless Chrome with only the final `print()` call stubbed), and in headed Chrome the real `print()` on that PDF frame runs without crashing the page. (Calling `print()` on a PDF frame crashes *headless* Chrome's renderer — a headless limitation; the old HTML print was fine there only because it never built a PDF.) What no script can judge is the look of the print dialog itself — worth one glance in your own browser.
