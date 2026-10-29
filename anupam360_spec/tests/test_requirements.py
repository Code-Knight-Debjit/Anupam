"""
Requirement checks for Anupam 360. Each test is tagged with the REQ-ID from REQUIREMENTS.md.
Run:  pytest -v tests/test_requirements.py
To check YOUR Django implementation, edit tests/adapter.py (see README) or import your own services in place of
`rules.anupam_rules` — the test inputs/expected outputs stay the same.
"""
import pytest
from datetime import datetime
import rules.anupam_rules as R

ADMIN = {"id": "u1", "name": "Sanjeev", "role": "Admin"}
BM = {"id": "u2", "name": "Bala", "role": "Branch Manager"}
BS = {"id": "u3", "name": "Staff", "role": "Branch Staff"}
SM = {"id": "u4", "name": "Devdutt", "role": "Sales Manager"}
SM2 = {"id": "u5", "name": "Ravi", "role": "Sales Manager"}

def mk_company(**kw):
    c = {"id": "c1", "name": "Sun Steels", "plant": "Plant 2", "area": "Ambattur", "city": "Chennai", "createdById": "u1",
         "contacts": [{"id": f"p{i}", "name": f"P{i}"} for i in range(1, 5)]}
    c.update(kw); return c

# ---------------------------------------------------------------- roles / permissions
def test_REQ_ROLE_01_four_roles():
    assert R.ROLES == ("Admin", "Branch Manager", "Branch Staff", "Sales Manager")

def test_REQ_ROLE_02_sales_manager_edits_need_approval():
    assert R.needs_approval(SM, "customer.edit") and R.needs_approval(SM, "customer.delete")
    for u in (ADMIN, BM): assert not R.needs_approval(u, "customer.delete")
    assert not R.needs_approval(BS, "customer.edit") and R.needs_approval(BS, "customer.delete")

def test_REQ_ROLE_03_only_admin_sees_admin_menus():
    for item in R.ADMIN_ONLY_NAV:
        assert item in R.nav_visible(ADMIN)
        for u in (BM, BS, SM): assert item not in R.nav_visible(u)

def test_REQ_ROLE_04_sales_manager_hides_back_office_panels():
    nav = R.nav_visible(SM)
    for item in ("Proforma Invoice", "Delivery Challan", "Pending PO", "Payment Collection", "Print Label"):
        assert item not in nav
    assert "Quotation" in nav and "Enquiry" in nav

def test_REQ_ROLE_05_non_admin_gets_personal_dashboard():
    assert not R.uses_personal_dashboard(ADMIN)
    for u in (BM, BS, SM): assert R.uses_personal_dashboard(u)

def test_REQ_RPT_01_sales_staff_report_tabs_hidden():
    tabs = R.report_tabs_visible(SM)
    assert "Sales Performance" not in tabs and "Customer Activity" not in tabs
    assert "Not Contacted" in tabs
    assert "Sales Performance" in R.report_tabs_visible(ADMIN)

# ---------------------------------------------------------------- customer visibility / contact-level assignment
def test_REQ_CUS_01_sales_manager_sees_own_and_assigned_only():
    cs = [mk_company(id="a", createdById="u4"), mk_company(id="b", createdById="u1", assignedTo=["Devdutt"]),
          mk_company(id="c", createdById="u1")]
    assert {c["id"] for c in R.visible_companies(SM, cs)} == {"a", "b"}
    assert len(R.visible_companies(ADMIN, cs)) == 3 and len(R.visible_companies(BS, cs)) == 3

def test_REQ_CUS_02_assign_two_of_four_contacts():
    c = R.assign_customer(mk_company(), "Devdutt", ["p1", "p3"])
    assert c["assignedTo"] == ["Devdutt"] and c["contactAccess"] == {"Devdutt": ["p1", "p3"]}
    assert [p["id"] for p in R.visible_contacts(SM, c)] == ["p1", "p3"]
    assert len(R.visible_contacts(ADMIN, c)) == 4            # admin still sees everyone
    assert len(R.visible_contacts(SM2, mk_company(assignedTo=["Ravi"]))) == 4

def test_REQ_CUS_03_all_contacts_means_no_restriction():
    c = R.assign_customer(mk_company(), "Devdutt", ["p1", "p2", "p3", "p4"])
    assert "contactAccess" not in c
    c = R.assign_customer(mk_company(), "Devdutt")
    assert "contactAccess" not in c

def test_REQ_CUS_04_deassign_clears_access():
    c = R.assign_customer(mk_company(), "Devdutt", ["p1"])
    R.deassign_customer(c, "Devdutt")
    assert c["assignedTo"] == [] and "contactAccess" not in c

def test_REQ_CUS_05_multi_assign_independent_access():
    c = R.assign_customer(mk_company(), "Devdutt", ["p1"])
    R.assign_customer(c, "Ravi", ["p2", "p4"])
    assert [p["id"] for p in R.visible_contacts(SM, c)] == ["p1"]
    assert [p["id"] for p in R.visible_contacts(SM2, c)] == ["p2", "p4"]

def test_REQ_CUS_06_creator_always_sees_all_contacts():
    c = mk_company(createdById="u4", contactAccess={"Devdutt": ["p1"]})
    assert len(R.visible_contacts(SM, c)) == 4

def test_REQ_CUS_07_dropdown_label_name_plant_area_no_city():
    assert R.company_select_label(mk_company()) == "Sun Steels, Plant 2, Ambattur"
    assert "Chennai" not in R.company_select_label(mk_company())
    assert R.company_select_label(mk_company(plant="")) == "Sun Steels, Ambattur"

def test_REQ_CUS_08_word_based_customer_search():
    opts = ["Kumar Suresh Steels", "Sun Steels", "Supreme Auto", "Ram Industries", "Maruthi Su Traders"]
    got = R.search_customers(opts, "su")
    assert got[:2] == ["Sun Steels", "Supreme Auto"]                    # starts-with first
    assert set(got[2:4]) == {"Kumar Suresh Steels", "Maruthi Su Traders"}  # word-start next
    assert "Ram Industries" not in got
    assert R.search_customers(opts, "") == opts

def test_REQ_CUS_09_duplicate_detection():
    assert R.near_duplicate("Sun Steels", "Sun Steel")
    assert not R.near_duplicate("Sun Steels", "Ram Industries")
    assert R.near_duplicate("Abc", "Abd")                      # short names use looser 0.65
    assert R.title_case_words("sun steels-ltd") == "Sun Steels-Ltd"

# ---------------------------------------------------------------- numbering / totals / PO
def test_REQ_DOC_01_numbering_per_branch_forward_only():
    ctr = {}
    assert R.next_doc_number(ctr, "quotation", "Chennai") == "QUO-0001"
    R.bump_counter(ctr, "quotation", "Chennai", "QUO-0001"); R.bump_counter(ctr, "quotation", "Chennai", "QUO-0002")
    assert R.next_doc_number(ctr, "quotation", "Chennai") == "QUO-0003"
    assert R.next_doc_number(ctr, "quotation", "Bengaluru") == "QUO-0001"      # branches independent
    assert R.next_doc_number(ctr, "enquiry", "Chennai") == "ENQ-0001"          # types independent
    R.bump_counter(ctr, "quotation", "Chennai", "QUO-0001")                    # deleting / re-saving older never lowers it
    assert ctr["quotation::Chennai"] == 2
    R.bump_counter(ctr, "quotation", "Chennai", "QUO-0010")                    # manual higher number pushes forward
    assert R.next_doc_number(ctr, "quotation", "Chennai") == "QUO-0011"

def test_REQ_DOC_02_branch_prefix_suffix_start():
    cfg = {"quotation": {"prefix": "CHN/Q", "suffix": "26-27", "start": 100}}
    assert R.next_doc_number({}, "quotation", "Chennai", cfg) == "CHN/Q-0100-26-27"
    assert R.next_doc_number({}, "quotation", "Chennai", {"quotation": {"prefix": "", "suffix": ""}}) == "QUO-0001"   # blank prefix -> default
    assert R.format_doc_number({"prefix": "", "suffix": "", "start": 1}, 7) == "0007"
    ctr = {}; R.bump_counter(ctr, "quotation", "Chennai", "CHN/Q-0100-26-27")
    assert ctr["quotation::Chennai"] == 100                                   # sequence = FIRST digits, not the year suffix

def test_REQ_DOC_02b_counters_seeded_from_existing_docs():
    docs = [{"type": "quotation", "branch": "Chennai", "docNumber": "QUO-0007"}, {"type": "quotation", "branch": "Chennai", "docNumber": "QUO-0003"}]
    assert R.next_doc_number(R.seed_counters({}, docs), "quotation", "Chennai") == "QUO-0008"

def test_REQ_DOC_03_line_and_total_math():
    items = [{"qty": 10, "rate": 100, "discount": 10, "tax": 18}, {"qty": 1, "rate": 50, "discount": 0, "tax": 0}]
    t = R.doc_total(items, packing=100, packing_tax=18, freight=200, freight_tax=0, round_off=-0.5)
    assert round(t["subTotal"], 2) == round(10 * 100 * .9 * 1.18 + 50, 2)
    assert round(t["totalAmount"], 2) == round(t["subTotal"] + 118 + 200 - 0.5, 2)
    assert R.line_amounts({"qty": 2, "rate": 100, "discount": 50, "tax": 99}, has_discount=True, has_tax=False)["value"] == 100

def test_REQ_DOC_04_pipeline_links_and_statuses():
    assert R.PIPELINE["quotation"] == "enquiry" and R.PIPELINE["dc"] == "po"
    assert R.STATUSES["quotation"] == ["Pending", "Win", "Lose"]
    assert R.STATUSES["po"] == ["Pending", "Part Pending", "Hold", "Completed"]

def test_REQ_DOC_05_sales_doc_visibility_for_sales_manager():
    comp = mk_company(assignedTo=["Devdutt"])
    docs = [{"type": "quotation", "createdById": "u4", "customerId": "x"}, {"type": "quotation", "createdById": "u1", "customerId": "c1"},
            {"type": "quotation", "createdById": "u1", "customerId": "zz"}, {"type": "dc", "createdById": "u1", "customerId": "c1"}]
    got = R.visible_sales_docs(SM, "quotation", docs, [comp])
    assert len(got) == 2
    assert len(R.visible_sales_docs(ADMIN, "quotation", docs, [comp])) == 3

def test_REQ_PO_01_status_from_supply_log():
    po = {"type": "po", "orderStatus": "Pending", "items": [{"qty": 10, "supplyLog": []}, {"qty": 5, "supplyLog": []}]}
    assert R.recompute_po_status(po)["orderStatus"] == "Pending"
    po["items"][0]["supplyLog"] = [{"qtySupplied": 4}]
    assert R.recompute_po_status(po)["orderStatus"] == "Part Pending"
    po["items"][0]["supplyLog"].append({"qtySupplied": 6}); po["items"][1]["supplyLog"] = [{"qtySupplied": 5}]
    assert R.recompute_po_status(po)["orderStatus"] == "Completed"

def test_REQ_PO_02_hold_is_manual_and_sticky():
    po = {"type": "po", "orderStatus": "Hold", "items": [{"qty": 1, "supplyLog": [{"qtySupplied": 1}]}]}
    assert R.recompute_po_status(po)["orderStatus"] == "Hold"

def test_REQ_PO_03_pending_and_balance_per_item():
    it = {"qty": 10, "supplyLog": [{"qtySupplied": 3}, {"qtySupplied": 2}], "invoiceLog": [{"qtyInvoiced": 4}]}
    assert R.item_pending(it) == 5 and R.item_balance(it) == 6
    assert R.item_pending({"qty": 1, "supplyLog": [{"qtySupplied": 5}]}) == 0     # never negative

# ---------------------------------------------------------------- payments
def test_REQ_PAY_01_balance_and_overpay_confirm():
    p = {"amount": 1000, "receivedLog": [{"amount": 400}]}
    assert R.payment_received(p) == 400 and R.payment_balance(p) == 600
    assert R.payment_overpay_needs_confirm(p, 700) and not R.payment_overpay_needs_confirm(p, 600)

# ---------------------------------------------------------------- tasks
def T(**kw):
    t = {"id": "t", "title": "Do", "assignedToId": "u4", "assignedToName": "Devdutt", "createdById": "u1", "createdByName": "Sanjeev", "status": "Open"}
    t.update(kw); return t

def test_REQ_TSK_01_main_list_is_only_my_tasks():
    tasks = [T(id="1", assignedToId="u1", assignedToName="Sanjeev"), T(id="2", assignedToId="u4")]
    assert [t["id"] for t in R.main_task_list(ADMIN, tasks)] == ["1"]
    assert {t["id"] for t in R.main_task_list(ADMIN, tasks, scope="all")} == {"1", "2"}   # Everyone toggle (Admin/BM)
    assert [t["id"] for t in R.main_task_list(SM, tasks, scope="all")] == ["2"]           # SM cannot widen

def test_REQ_TSK_02_assigned_by_me_panel():
    """Sanjeev assigns to Devdutt -> shows under Sanjeev's 'Assigned by me' and in Devdutt's list."""
    tasks = [T(id="1"), T(id="2", assignedToId="u1", assignedToName="Sanjeev")]
    assert [t["id"] for t in R.assigned_by_me(ADMIN, tasks)] == ["1"]
    assert [t["id"] for t in R.main_task_list(SM, tasks)] == ["1"]
    assert R.assigned_by_me(SM, tasks) == []

def test_REQ_TSK_03_only_creator_can_remove():
    t = T()
    assert R.can_remove_task(ADMIN, t) and not R.can_remove_task(SM, t) and not R.can_remove_task(BM, t)
    tasks = [t]
    with pytest.raises(PermissionError): R.remove_task(SM, t, tasks)
    R.remove_task(ADMIN, t, tasks); assert tasks == []

def test_REQ_TSK_04_assignee_can_update_status_but_not_manage():
    t = T()
    assert R.can_update_task_status(SM, t) and not R.can_manage_task(SM, t)
    assert R.can_update_task_status(BM, t) and not R.can_update_task_status(SM2, t)

def test_REQ_TSK_05_multi_assignee_and_kind_detection():
    t = T(assignees=[{"id": "u4", "name": "D"}, {"id": "u5", "name": "R"}])
    assert R.task_assigned_to(t, "u5")
    assert R.task_kind(T(title="Call Sun Steels")) == "Call" and R.task_kind(T(title="appointment with X")) == "Appointment"
    assert R.task_kind(T(title="Prepare report")) == "Task" and R.task_kind(T(taskType="Visit")) == "Visit"

# ---------------------------------------------------------------- interactions
def _ctx():
    comp = mk_company(); contact = comp["contacts"][0]
    return comp, contact

def test_REQ_INT_01_followup_creates_task():
    comp, c = _ctx(); tasks = []
    R.log_interaction(c, comp, SM, "Call", "2026-10-01", followup_date="2026-10-05", tasks=tasks)
    assert len(tasks) == 1 and tasks[0]["dueDate"] == "2026-10-05" and tasks[0]["assignedToId"] == "u4"

def test_REQ_INT_02_appointment_requires_date():
    comp, c = _ctx()
    with pytest.raises(ValueError): R.log_interaction(c, comp, SM, "Appointment", "2026-10-01", tasks=[])

def test_REQ_INT_03_visit_closes_open_appointment_tasks():
    comp, c = _ctx(); tasks = []
    R.log_interaction(c, comp, SM, "Appointment", "2026-10-01", followup_date="2026-10-03", tasks=tasks)
    assert tasks[0]["status"] == "Open"
    R.log_interaction(c, comp, SM, "Visit", "2026-10-03", tasks=tasks)
    assert tasks[0]["status"] == "Done" and tasks[0]["autoClosedByVisit"]

def test_REQ_INT_04_joint_visit_makes_tasks_for_members():
    comp, c = _ctx(); tasks = []
    R.log_interaction(c, comp, SM, "Visit", "2026-10-01", joint_with=[{"id": "u2", "name": "Bala"}], tasks=tasks)
    assert [t["assignedToId"] for t in tasks] == ["u2"]

def test_REQ_INT_05_also_met_copies_flagged():
    comp, c = _ctx(); other = comp["contacts"][1]
    R.log_interaction(c, comp, SM, "Visit", "2026-10-01", also_met=[other], tasks=[])
    assert other["interactions"][0]["isCopy"] and other["interactions"][0]["metWithName"] == "P1"

def test_REQ_INT_06_appointment_visit_percentage():
    comp, c = _ctx(); tasks = []
    R.log_interaction(c, comp, SM, "Appointment", "2026-10-01", followup_date="2026-10-02", tasks=tasks)
    R.log_interaction(c, comp, SM, "Appointment", "2026-10-20", followup_date="2026-10-21", tasks=tasks)
    R.log_interaction(c, comp, SM, "Visit", "2026-10-05", tasks=tasks)
    assert R.appointments_not_visited(c, "u4") == 1
    assert R.visit_percent_of_appointments(2, 1) == 50 and R.visit_percent_of_appointments(0, 0) == 0

# ---------------------------------------------------------------- attendance
EMP = {"id": "u4", "name": "Devdutt", "workStart": "09:30", "weeklyOff": "0", "branches": ["Chennai"]}
def st(day, recs=(), hol=(), leaves=(), today="2026-10-29", emp=EMP):
    return R.att_day_status(emp, day, list(recs), list(hol), list(leaves), today)

def test_REQ_ATT_01_grace_and_late():
    assert st("2026-10-20", [{"userId": "u4", "date": "2026-10-20", "checkIn": "09:40"}])["code"] == "P"   # 10 min grace
    r = st("2026-10-20", [{"userId": "u4", "date": "2026-10-20", "checkIn": "09:41", "checkOut": "18:30"}])
    assert r["code"] == "L" and r["late"] == 11 and r["worked"] == 529

def test_REQ_ATT_02_sunday_off_holiday_leave_absent():
    assert st("2026-10-25")["code"] == "O"                                          # Sunday
    assert st("2026-10-21", hol=[{"from": "2026-10-21", "to": "2026-10-21", "all": True}])["code"] == "O"
    assert st("2026-10-21", hol=[{"from": "2026-10-21", "to": "2026-10-21", "branches": ["Bengaluru"]}])["code"] == "A"
    assert st("2026-10-22", leaves=[{"userId": "u4", "status": "Approved", "from": "2026-10-22", "to": "2026-10-23"}])["code"] == "LV"
    assert st("2026-10-22", leaves=[{"userId": "u4", "status": "Pending", "from": "2026-10-22", "to": "2026-10-23"}])["code"] == "A"
    assert st("2026-10-30")["code"] == ""                                           # future day is blank

def test_REQ_ATT_03_manual_override_and_tally():
    s = [st("2026-10-20", [{"userId": "u4", "date": "2026-10-20", "status": "Half day"}]),
         st("2026-10-21", [{"userId": "u4", "date": "2026-10-21", "checkIn": "10:00", "checkOut": "18:00"}]),
         st("2026-10-22")]
    t = R.att_tally(s)
    assert (t["half"], t["present"], t["late"], t["absent"], t["worked"]) == (1, 1, 1, 1, 480)

def test_REQ_ATT_04_location_for_everyone_and_order():
    recs = []
    for u in (ADMIN, BM, BS, SM):
        R.check_in(recs, u, "2026-10-29", "09:30", {"lat": 13.0, "lng": 80.2})
        assert recs[-1]["inLoc"]["lat"] == 13.0
    with pytest.raises(ValueError): R.check_in(recs, ADMIN, "2026-10-30", "09:30", None)
    with pytest.raises(ValueError): R.check_out(recs, ADMIN, "2026-10-29", "08:00", {"lat": 1, "lng": 1})
    assert R.check_out(recs, ADMIN, "2026-10-29", "18:30", {"lat": 1, "lng": 1})["outLoc"]

def test_REQ_ATT_05_team_scope_and_leave_decisions():
    emps = [dict(ADMIN, active=True), dict(SM, active=True), dict(SM2, active=False)]
    assert {e["id"] for e in R.att_team(ADMIN, emps)} == {"u1", "u4"}
    assert [e["id"] for e in R.att_team(BM, emps, scope_names={"Devdutt"})] == ["u4"]
    assert R.att_team(SM, emps) == []
    lv = {"userId": "u4"}
    assert R.can_decide_leave(ADMIN, lv, set()) and R.can_decide_leave(BM, lv, {"u4"})
    assert not R.can_decide_leave(BM, {"userId": "u2"}, {"u2"}) and not R.can_decide_leave(SM, lv, {"u4"})

# ---------------------------------------------------------------- labels
def test_REQ_LBL_01_defaults():
    d = R.LABEL_DEFAULTS
    assert d["paper"] == "a4" and d["size"] == "a5" and d["from_scale"] == 1.5
    assert d["print_attn"] is False and d["print_phone"] is False

def test_REQ_LBL_02_original_size_tiled_on_a4():
    p = R.label_sheet_plan("a5", 3)
    assert p["page"] == (297, 210) and p["per_page"] == 2 and p["pages"] == 2      # A5 = half an A4
    assert R.label_sheet_plan("4x4", 8)["per_page"] == 4 and R.label_sheet_plan("6x4", 4)["per_page"] == 2
    a4 = R.label_sheet_plan("a4", 2); assert a4["per_page"] == 1 and a4["pages"] == 2

def test_REQ_LBL_03_label_sized_page_when_not_on_sheet():
    p = R.label_sheet_plan("6x4", 3, on_sheet=False)
    assert p["page"] == (101.6, 152.4) and p["pages"] == 3                       # 6x4 portrait

def test_REQ_LBL_04_attn_phone_off_by_default_and_from_last():
    party = {"customer": "Sun Steels", "area": "Ambattur", "attn": "Mr P", "phone": "98400", "transport": "VRL"}
    c = R.label_content(party)
    assert c["attn"] == "" and c["phone"] == "" and c["from_at_bottom"]
    assert c["area_bold"] == "Ambattur" and ("TRANSPORT", "VRL") in c["meta"]
    c2 = R.label_content(party, True, True); assert c2["attn"] == "Mr P" and c2["phone"] == "98400"
    assert "ref" not in c and "date" not in c                                    # Ref/Date removed

def test_REQ_LBL_05_deliver_to_typed_name_wins():
    comp = mk_company()
    assert R.label_deliver_to("", comp) == "Sun Steels"
    assert R.label_deliver_to("Site Store", comp) == "Site Store"
    assert R.label_deliver_to("", None) == ""

def test_REQ_LBL_06_from_scale_options():
    assert R.FROM_SCALES == (1, 1.25, 1.5, 2)

# ---------------------------------------------------------------- backup
def test_REQ_BAK_01_backup_covers_all_datasets():
    for k in ("companies", "salesDocs", "docCounters", "payments", "tasks", "attendance", "approvals", "callAssignments", "employees"):
        assert k in R.BACKUP_KEYS


# =========================================================================== AUTOMATIONS
def NOTE_TYPES(n): return [x["type"] for x in n]

def test_REQ_AUT_01_outreach_one_per_contact_skips_dnd_and_dupes():
    comp = mk_company(); comp["contacts"][1]["dnd"] = True
    a = []
    r = R.assign_outreach(a, [comp], ["c1"], SM, ADMIN, "2026-10-29")          # a Thursday
    assert r == {"added": 3, "skipped": 0, "dnd_skipped": 1} and all(x["weekOf"] == "2026-10-26" for x in a)   # Monday
    assert R.assign_outreach(a, [comp], ["c1"], SM, ADMIN, "2026-10-27")["skipped"] == 3                   # same week: no duplicates
    assert R.assign_outreach(a, [comp], ["c1"], SM, ADMIN, "2026-11-03")["added"] == 3                     # next week: new entries
    assert R.assign_outreach([], [mk_company(contacts=[])], ["c1"], SM, ADMIN, "2026-10-29")["added"] == 1  # no contacts -> one blank entry

def test_REQ_AUT_02_customer_access_request_notifies_approvers_and_applies():
    emps = [dict(ADMIN), dict(BM), dict(BS), dict(SM)]; comp = mk_company(); ap, n = [], []
    R.request_customer_access(ap, n, emps, SM, comp)
    assert sorted(x["userId"] for x in n) == ["u1", "u2"]
    with pytest.raises(ValueError): R.request_customer_access(ap, n, emps, SM, comp)          # one pending request only
    req = ap[0]; req["companyName"] = comp["name"]; cs = [comp]; n.clear()
    R.approve_request(req, cs, ap, n)
    assert cs[0]["assignedTo"] == ["Devdutt"] and ap == [] and NOTE_TYPES(n) == ["customer-access-approved"] and n[0]["userId"] == "u4"

def test_REQ_AUT_03_reject_notifies_and_changes_nothing():
    req = {"type": "customer-access", "companyId": "c1", "companyName": "Sun Steels", "requestedById": "u4", "requestedByName": "Devdutt"}
    ap, n, cs = [req], [], [mk_company()]
    R.reject_request(req, ap, n)
    assert ap == [] and NOTE_TYPES(n) == ["customer-access-declined"] and "assignedTo" not in cs[0]

def test_REQ_AUT_04_approved_edit_and_delete_are_applied():
    c = mk_company(); cs = [c]
    R.approve_request({"type": "edit", "companyId": "c1", "proposedData": dict(c, name="Sun Steel Works")}, cs, [], [])
    assert cs[0]["name"] == "Sun Steel Works"
    R.approve_request({"type": "delete", "companyId": "c1"}, cs, [], [])
    assert cs == []

def test_REQ_AUT_05_task_done_notifies_creator_only_once():
    t = T(); n = []
    R.set_task_status(t, "Done", SM, n)
    assert NOTE_TYPES(n) == ["task_done"] and n[0]["userId"] == "u1" and t["completedByName"] == "Devdutt"
    R.set_task_status(t, "Done", SM, n); assert len(n) == 1                                   # not a fresh completion
    n.clear(); R.set_task_status(T(createdById="u4"), "Done", SM, n); assert n == []         # self-assigned: no notice
    with pytest.raises(PermissionError): R.set_task_status(T(), "Done", SM2, [])

def test_REQ_AUT_06_remove_and_verify_notifications():
    t = T(status="Done"); n = []
    R.delete_task(ADMIN, t, [t], n)                                                           # creator acknowledges a done task
    assert NOTE_TYPES(n) == ["task_verified"] and n[0]["userId"] == "u4"
    t2 = T(createdById="u4", createdByName="Devdutt", assignedToId="u1", assignedToName="Sanjeev", status="Open"); n = []
    with pytest.raises(PermissionError): R.delete_task(ADMIN, t2, [t2], n)                    # assignee cannot remove

def test_REQ_AUT_07_assigning_task_notifies_each_assignee_not_self():
    tasks, n = [], []
    R.create_task_for(ADMIN, [{"id": "u1", "name": "Sanjeev"}, {"id": "u4", "name": "Devdutt"}, {"id": "u5", "name": "Ravi"}], "Visit ABC", "2026-11-01", tasks, n)
    assert sorted(x["userId"] for x in n) == ["u4", "u5"] and len(tasks) == 1

def test_REQ_AUT_08_schedule_follow_up_from_sales_document():
    doc = {"id": "d1", "docNumber": "QUO5", "customerName": "Sun Steels", "contactName": "P1"}
    tasks, n = [], []
    t = R.schedule_from_sales_doc(ADMIN, doc, "Appointment", "2026-11-02", SM, tasks, n)
    assert t["title"] == "Appointment with P1 — Sun Steels" and t["relatedDocNumber"] == "QUO5" and n[0]["userId"] == "u4"
    n.clear(); R.schedule_from_sales_doc(SM, doc, "Call", "2026-11-02", SM, tasks, n); assert n == []   # for myself: no notice

def test_REQ_AUT_09_leave_and_holiday_notifications():
    emps = [dict(ADMIN), dict(SM, branches=["Chennai"]), dict(SM2, branches=["Bengaluru"])]; lv, n = [], []
    R.request_leave(lv, n, emps, SM, "2026-11-02", "2026-11-03")
    assert [x["userId"] for x in n] == ["u1"]
    n.clear(); R.decide_leave(lv[0], "Approved", ADMIN, n, "enjoy"); assert n[0]["userId"] == "u4" and "approved" in n[0]["text"]
    n.clear(); R.announce_holiday(n, emps, "Diwali", "2026-11-08", "2026-11-08"); assert len(n) == 3
    n.clear(); R.announce_holiday(n, emps, "Local", "2026-11-09", "2026-11-09", branches=["Chennai"]); assert [x["userId"] for x in n] == ["u4"]

def test_REQ_AUT_10_custom_label_autofill_and_no_auto_person():
    comp = mk_company(address="12 Mount Rd", pincode="600058", state="TN", transportPreference="VRL", courierPreference="DTDC")
    f = R.label_autofill_from_customer(comp)
    assert f["customer"] == "Sun Steels" and f["area"] == "Ambattur" and f["pin"] == "600058" and f["transport"] == "VRL"
    assert f["attn"] == "" and f["phone"] == ""                                               # person NOT auto-selected
    g = R.label_autofill_from_customer(comp, {"name": "P2", "phone": "98400"}); assert g["attn"] == "P2" and g["phone"] == "98400"


# =========================================================================== SALES / DOCUMENT AUTOMATIONS
def test_REQ_PRN_01_printed_totals_fold_discount_and_round():
    doc = {"items": [{"itemName": "6205", "make": "Timken", "qty": 10, "rate": 333.33, "discount": 10, "tax": 18}], "showDiscountInPdf": False}
    t = R.quotation_print_totals(doc)
    assert t["lines"][0]["rate"] == 300 and t["lines"][0]["amount"] == 3000 and t["lines"][0]["name"] == "6205 (Timken)"   # 299.997 -> 300
    assert t["subTotal"] == 3000 and round(t["taxTotal"], 2) == 540 and round(t["total"], 2) == 3540
    shown = R.quotation_print_totals(dict(doc, showDiscountInPdf=True))
    assert shown["lines"][0]["rate"] == 333.33 and round(shown["subTotal"], 2) == 2999.97

def test_REQ_PRN_02_charges_tax_and_roundoff_in_total():
    doc = {"items": [{"qty": 1, "rate": 1000, "discount": 0, "tax": 0}], "packingCharges": 100, "packingTax": 18, "freightCharges": 50, "roundOff": -0.5}
    assert round(R.quotation_print_totals(doc)["total"], 2) == round(1000 + 118 + 50 - 0.5, 2)

def test_REQ_PRN_03_amount_in_words_indian_system():
    assert R.amount_in_words(0) == "Rupees Zero Only"
    assert R.amount_in_words(1000) == "Rupees One Thousand Only"
    assert R.amount_in_words(123456.5) == "Rupees One Lakh Twenty Three Thousand Four Hundred Fifty Six and Fifty Paise Only"
    assert R.amount_in_words(10000000) == "Rupees One Crore Only"
    assert R.amount_in_words(-5) == "Minus Rupees Five Only"

def test_REQ_PRN_04_report_value_of_a_quotation():
    assert R.quotation_value_of({"totalAmount": 500}) == 500
    assert R.quotation_value_of({"items": [{"value": 100}, {"qty": 2, "rate": 100, "discount": 10, "tax": 18}]}) == pytest.approx(100 + 212.4)
    assert R.quotation_value_of({"quotationValue": 77}) == 77

def test_REQ_AUT_11_quotation_from_enquiry_completes_the_enquiry():
    docs = [{"id": "e1", "type": "enquiry", "docNumber": "ENQ-0001", "orderStatus": "Pending"}]
    assert R.on_quotation_saved({"type": "quotation", "refId": "e1"}, docs) == "ENQ-0001" and docs[0]["orderStatus"] == "Completed"
    assert R.on_quotation_saved({"type": "quotation", "refId": "e1"}, docs) is None            # already completed: no repeat message
    assert R.on_quotation_saved({"type": "quotation"}, docs) is None

def test_REQ_AUT_12_win_needs_value_lose_keeps_reason():
    q = {"type": "quotation", "orderStatus": "Pending", "lostReason": "price"}
    with pytest.raises(ValueError): R.mark_outcome(q, "Win")
    R.mark_outcome(q, "Win", 150000); assert q["orderStatus"] == "Win" and q["orderValue"] == 150000 and "lostReason" not in q
    R.mark_outcome(q, "Lose", lost_reason=" too costly "); assert q["orderStatus"] == "Lose" and q["lostReason"] == "too costly"
    with pytest.raises(ValueError): R.mark_outcome({"type": "dc"}, "Win", 1)

def test_REQ_AUT_13_new_challan_writes_stock_out_once():
    dc = {"type": "dc", "branch": "Chennai", "docNumber": "DC-0001", "items": [{"itemName": "6205", "qty": 10, "make": "Timken"}, {"itemName": "", "qty": 5}, {"itemName": "X", "qty": 0}]}
    tx = R.stock_out_from_dc(dc, ADMIN, [], is_new=True)
    assert len(tx) == 1 and tx[0]["type"] == "OUT" and tx[0]["qty"] == 10 and tx[0]["refDocNumber"] == "DC-0001"
    assert R.stock_out_from_dc(dc, ADMIN, [], is_new=False) == []                                # editing does not repeat it
    assert R.stock_out_from_dc(dict(dc, branch=""), ADMIN, [], True) == []                       # needs a branch

def test_REQ_PO_04_supply_is_manual_and_over_supply_needs_confirm():
    it = {"qty": 10}
    with pytest.raises(ValueError): R.record_supply(it, 0, "2026-10-01", SM)
    R.record_supply(it, 6, "2026-10-01", SM); assert R.item_pending(it) == 4
    with pytest.raises(ValueError): R.record_supply(it, 9, "2026-10-02", SM)
    R.record_supply(it, 9, "2026-10-02", SM, confirm_over=lambda p: True); assert R.item_pending(it) == 0

def test_REQ_DC_01_invoice_done_rules():
    it = {"qty": 10}
    with pytest.raises(ValueError): R.record_invoice(it, " ", "2026-10-01", 5, ADMIN)
    with pytest.raises(ValueError): R.record_invoice(it, "B1", "2026-10-01", 0, ADMIN)
    R.record_invoice(it, "B1", "2026-10-01", 4, ADMIN); assert R.item_balance(it) == 6
    with pytest.raises(ValueError): R.record_invoice(it, "B2", "2026-10-02", 7, ADMIN)
    dc = {"items": [it]}; assert R.dc_is_pending(dc)
    R.record_invoice(it, "B2", "2026-10-02", 6, ADMIN); assert not R.dc_is_pending(dc) and R.dc_history_completed(dc) == [it]

def test_REQ_LOG_01_call_me_later_creates_task_and_filters():
    d = {"customerName": "Sun", "contactName": "P1"}; tasks = []
    R.add_contact_log(d, "Will confirm", SM, tasks, now="2026-10-01T10:00")
    assert tasks == [] and R.call_later_bucket(d, "2026-10-29") == "none" and R.last_contact_on(d) == "2026-10-01T10:00"
    R.add_contact_log(d, "Call next week", SM, tasks, call_later_date="2026-10-25", now="2026-10-02T10:00")
    assert len(tasks) == 1 and tasks[0]["taskType"] == "Call" and tasks[0]["dueDate"] == "2026-10-25" and tasks[0]["assignedToId"] == "u4"
    assert R.call_later_bucket(d, "2026-10-29") == "overdue" and R.call_later_bucket(d, "2026-10-25") == "today" and R.call_later_bucket(d, "2026-10-20") == "upcoming"
    assert R.add_contact_log(d, "", SM, tasks) is None

def test_REQ_LOG_02_whatsapp_link_adds_91_to_10_digit_numbers():
    assert R.wa_link("98400 12345").startswith("https://wa.me/919840012345")
    assert R.wa_link("+91 98400-12345").startswith("https://wa.me/919840012345") and R.wa_link("") is None

# ---------------------------------------------------------------- payments
def test_REQ_PAY_02_payment_visibility_and_receive_rules():
    ps = [{"id": 1, "createdById": "u4", "amount": 100}, {"id": 2, "createdById": "u1", "amount": 50}]
    assert [p["id"] for p in R.visible_payments(SM, ps)] == [1] and len(R.visible_payments(BS, ps)) == 2
    p = {"amount": 1000}
    with pytest.raises(ValueError): R.receive_payment(p, 0, "2026-10-01", BS)
    R.receive_payment(p, 400, "2026-10-01", BS); assert R.payment_balance(p) == 600
    with pytest.raises(ValueError): R.receive_payment(p, 700, "2026-10-02", BS)
    R.receive_payment(p, 700, "2026-10-02", BS, confirm_over=lambda b: True); assert R.payment_balance(p) == 0

def test_REQ_PAY_03_ageing_buckets_and_branch_fallback():
    assert [R.payment_age_bucket(d) for d in (0, 30, 31, 60, 61, 90, 91)] == ["0-30 days", "0-30 days", "31-60 days", "31-60 days", "61-90 days", "61-90 days", "90+ days"]
    assert R.payment_branch_of({"branch": "Chennai"}, []) == "Chennai"
    assert R.payment_branch_of({"createdById": "u4"}, [{"id": "u4", "branches": ["Bengaluru"]}]) == "Bengaluru"

# ---------------------------------------------------------------- outreach completion
def test_REQ_OUT_01_called_logs_interaction_once():
    comp = mk_company(); a = {"contactId": "p1", "status": "Pending"}
    it = R.outreach_call_done(a, "spoke", SM, comp, "2026-10-29T10:00", "2026-10-29")
    assert a["status"] == "Called" and it["type"] == "Call" and comp["contacts"][0]["interactions"][0]["notes"] == "spoke"
    assert R.outreach_call_done(a, "edited", SM, comp, "x", "2026-10-30") is None and len(comp["contacts"][0]["interactions"]) == 1   # editing remarks only
    assert R.outreach_call_done({"contactId": "p2"}, "", SM, comp, "x", "2026-10-29")["notes"] == "Outreach — call completed."

def test_REQ_OUT_02_not_reached_makes_task_for_assignee():
    a = {"assignedToId": "u4", "assignedToName": "Devdutt", "contactName": "P1", "customerName": "Sun"}; tasks = []
    R.outreach_not_reached(a, "Busy", "", "", ADMIN, tasks); assert tasks == [] and len(a["attempts"]) == 1
    R.outreach_not_reached(a, "Not reachable", "ring later", "2026-11-02", ADMIN, tasks)
    assert len(a["attempts"]) == 2 and tasks[0]["assignedToId"] == "u4" and tasks[0]["dueDate"] == "2026-11-02"

def test_REQ_OUT_03_who_can_update_an_outreach_call():
    a = {"assignedToId": "u4"}
    assert R.can_update_outreach(SM, a) and R.can_update_outreach(ADMIN, a) and R.can_update_outreach(BM, a)
    assert not R.can_update_outreach(SM2, a) and not R.can_update_outreach(BS, a)

# ---------------------------------------------------------------- dashboards & reports
def test_REQ_DSH_01_personal_counts():
    comp = mk_company(); ct = comp["contacts"][0]; tasks = []
    R.log_interaction(ct, comp, SM, "Call", "2026-10-01", tasks=tasks)
    R.log_interaction(ct, comp, SM, "Appointment", "2026-10-02", followup_date="2026-10-03", tasks=tasks)
    R.log_interaction(ct, comp, SM, "Visit", "2026-10-03", tasks=tasks)
    ct["interactions"].append({"type": "Cold Call", "date": "2026-10-04", "userId": "u4"})
    docs = [{"type": "quotation", "createdById": "u4", "orderStatus": "Pending"}, {"type": "quotation", "createdById": "u4", "orderStatus": "Win"},
            {"type": "dc", "createdById": "u4", "items": [{"qty": 5}]}, {"type": "po", "createdById": "u4", "orderStatus": "Completed"}]
    pays = [{"createdById": "u4", "amount": 100, "receivedLog": []}, {"createdById": "u4", "amount": 100, "receivedLog": [{"amount": 100}]}]
    c = R.personal_counts("u4", [comp], tasks, [{"assignedToId": "u4", "status": "Pending"}], docs, pays)
    assert (c["callDone"], c["apptTaken"], c["apptVisited"]) == (2, 1, 1)                        # Cold Call counts as a call
    assert c["quotationPending"] == 1 and c["dcPending"] == 1 and c["poPending"] == 0
    assert c["paymentPending"] == 1 and c["paymentDone"] == 1 and c["callingPending"] == 1

def test_REQ_RPT_02_not_contacted_modes():
    a = mk_company(id="a"); b = mk_company(id="b"); c = mk_company(id="c")
    a["contacts"][0]["interactions"] = [{"type": "Call", "date": "2026-10-28"}, {"type": "Visit", "date": "2026-10-28"}]
    b["contacts"][0]["interactions"] = [{"type": "Call", "date": "2026-10-28"}]
    c["contacts"][0]["interactions"] = [{"type": "Visit", "date": "2026-06-01"}]
    ids = lambda mode: [r["id"] for r in R.not_contacted([a, b, c], 30, mode, "2026-10-29")]
    assert ids("both") == ["c"] and ids("call") == ["c"] and sorted(ids("visit")) == ["b", "c"] and sorted(ids("either")) == ["b", "c"]
    assert R.not_contacted([c], 30, "both", "2026-10-29")[0]["daysSinceVisit"] > 100

def test_REQ_RPT_03_sales_conversion_percentages():
    enq = [{}, {}, {}, {}]; quo = [{"orderStatus": "Win", "totalAmount": 1000}, {"orderStatus": "Lose"}]
    r = R.sales_conversion(enq, quo)
    assert r == {"enq_to_quo_pct": 50, "quo_to_win_pct": 50, "won_value": 1000} and R.sales_conversion([], [])["enq_to_quo_pct"] == 0

def test_REQ_INT_07_types_and_location_capture():
    assert R.INTERACTION_TYPES == ("Call", "Visit", "Appointment", "Sales Log", "Payment Log", "Outreach")
    assert R.LOCATION_CAPTURE_TYPES == ("Visit",)

# ---------------------------------------------------------------- import / users
def test_REQ_IMP_01_excel_import_rules():
    comps = [{"id": "x", "name": "Sun Steels", "city": "Chennai", "contacts": [{"id": "k", "name": "Ravi", "phone": "111"}]}]
    rows = [{"Company": "sun steels", "City": "", "Potential": "high", "Contact Name": "ravi", "Phone": "111"},
            {"Company": "sun steels", "Contact Name": "meena kumar", "Phone": "222", "Assigned To": "Devdutt, Ravi"},
            {"Company": "new tech ltd", "Address": "12 mount road", "GST Number": " 33abc ", "Potential": "Urgent", "Contact Name": "joe"},
            {"Company": ""}]
    r = R.import_customers(rows, comps, ADMIN)
    assert r == {"new": 1, "updated": 2, "contacts": 2}
    assert comps[0]["city"] == "Chennai" and comps[0]["potential"] == "High" and comps[0]["assignedTo"] == ["Devdutt", "Ravi"]   # blank keeps value
    assert [c["name"] for c in comps[0]["contacts"]] == ["Ravi", "Meena Kumar"]                                                  # same name+phone skipped
    n = comps[1]; assert n["name"] == "New Tech Ltd" and n["address"] == "12 Mount Road" and n["gstNumber"] == "33ABC" and "potential" not in n

def test_REQ_USR_01_deactivate_and_remove_rules():
    emps = [dict(ADMIN), dict(BM), dict(SM)]
    assert R.can_deactivate_user(BM, SM, emps)[0] is False
    assert R.can_deactivate_user(ADMIN, ADMIN, emps)[0] is False                                  # not yourself
    other_admin = {"id": "u9", "name": "Boss", "role": "Admin"}
    assert R.can_deactivate_user(ADMIN, other_admin, emps + [other_admin])[0] is True            # another admin exists
    assert R.can_deactivate_user(dict(ADMIN, id="u8"), ADMIN, [dict(ADMIN)])[0] is False          # last active admin
    assert R.can_deactivate_user(ADMIN, SM, emps)[0] is True
    assert R.can_remove_user(ADMIN, ADMIN, emps, 0)[0] is False and R.can_remove_user(BM, SM, emps, 0)[0] is False
    assert R.can_remove_user(ADMIN, SM, emps, 0) == (True, "ok") and R.can_remove_user(ADMIN, SM, emps, 5) == (True, "needs_transfer")
    assert R.can_login({"active": False}) is False and R.can_login({}) is True

def test_REQ_USR_02_record_count_decides_transfer():
    comp = mk_company(createdById="u4", assignedTo=["Devdutt"])
    assert R.user_record_total("u4", "Devdutt", [comp], [T()], [{"createdById": "u4"}], [{"createdById": "u4"}], [{"assignedToId": "u4"}]) == 6
    assert R.user_record_total("u5", "Ravi", [comp], [T()], [], [], []) == 0


# =========================================================================== SECOND-AUDIT ADDITIONS
def test_REQ_GEO_01_parse_pins():
    assert R.geo_parse("13.0285, 77.5197") == {"lat": 13.0285, "lng": 77.5197}
    assert R.geo_parse("13.0285;77.5197") == {"lat": 13.0285, "lng": 77.5197} and R.geo_parse("-13.5 77.5")["lat"] == -13.5
    assert R.geo_parse("https://www.google.com/maps/@13.0285,77.5197,17z") == {"lat": 13.0285, "lng": 77.5197}
    assert R.geo_parse("https://maps.google.com/?q=12.9,80.2") == {"lat": 12.9, "lng": 80.2}
    assert R.geo_parse("https://x/place/data=!3d13.1!4d80.3") == {"lat": 13.1, "lng": 80.3}
    assert R.geo_parse("") is None and R.geo_parse("not a place") is None and R.geo_parse("95, 10") is None and R.geo_parse("10, 190") is None

def test_REQ_GEO_02_distance_and_format():
    a, b = {"lat": 13.0, "lng": 80.0}, {"lat": 13.0, "lng": 80.01}
    assert 1000 < R.geo_dist_m(a, b) < 1200
    assert R.geo_fmt_dist(450) == "450 m" and R.geo_fmt_dist(1500) == "1.5 km" and R.geo_fmt_dist(25000) == "25 km"

def test_REQ_USR_03_password_reset_rules():
    emps = [dict(ADMIN, password="adminpw"), dict(BM, password="old"), dict(SM, password="x")]
    tgt = emps[1]
    with pytest.raises(PermissionError): R.reset_password(tgt, "newpass1", "newpass1", emps, emps[0], "wrong")      # another admin must verify
    with pytest.raises(PermissionError): R.reset_password(tgt, "newpass1", "newpass1", emps, None)
    with pytest.raises(ValueError): R.reset_password(tgt, "abc", "abc", emps, emps[0], "adminpw")                 # < 6 chars
    with pytest.raises(ValueError): R.reset_password(tgt, "newpass1", "newpass2", emps, emps[0], "adminpw")       # mismatch
    tgt["pin"] = "1234"; R.reset_password(tgt, "newpass1", "newpass1", emps, emps[0], "adminpw")
    assert tgt["password"] == "newpass1" and "pin" not in tgt
    only_admin = [dict(ADMIN, password="a")]; R.reset_password(only_admin[0], "abcdef", "abcdef", only_admin)     # sole admin: no verifier needed
    assert only_admin[0]["password"] == "abcdef"

def test_REQ_CUS_10_contact_exports():
    cs = [{"name": "P1", "email": "a@x.com", "phone": "9840012345", "companyName": "Sun", "jobTitle": "Purchase"}, {"name": "P2", "email": "a@x.com"}, {"name": "P3"}]
    assert R.selected_emails(cs) == ["a@x.com"]                                   # de-duplicated, blanks skipped
    v = R.vcard(cs)
    assert v.count("BEGIN:VCARD") == 3 and "FN:P1" in v and "ORG:Sun" in v and "TITLE:Purchase" in v and "TEL;TYPE=CELL:9840012345" in v and "EMAIL:a@x.com" in v
    assert "TEL" not in R.vcard([{"name": "P3"}])

def test_REQ_DOC_06_form_validation():
    ok = {"customerId": "c1", "branch": "Chennai", "items": [{"itemName": "6205", "qty": 1}]}
    assert R.validate_sales_doc(ok, True) is None
    assert R.validate_sales_doc(dict(ok, customerId=""), True) == "Select a customer first."
    assert R.validate_sales_doc(dict(ok, branch=""), True) == "Select a branch first."
    assert R.validate_sales_doc(dict(ok, items=[{"itemName": "", "qty": 0}]), True) == "Add at least one item."
    assert R.validate_sales_doc(dict(ok, items=[]), False) is None                # enquiries have no items

def test_REQ_PO_05_edit_keeps_supply_and_delete_recalculates():
    orig = [{"itemName": "A", "qty": 10, "supplyLog": [{"qtySupplied": 10}]}, {"itemName": "B", "qty": 5}]
    out = R.keep_supply_on_edit(orig, [{"item": {"itemName": "A", "qty": 12}, "origIndex": 0}, {"item": {"itemName": "", "qty": 0}}, {"item": {"itemName": "C", "qty": 1}}])
    assert [i["itemName"] for i in out] == ["A", "C"] and out[0]["supplyLog"] and "supplyLog" not in out[1]
    po = {"type": "po", "orderStatus": "Completed", "items": [{"qty": 10, "supplyLog": [{"qtySupplied": 10}]}]}
    assert R.delete_supply(po, 0, 0)["orderStatus"] == "Pending"
    po2 = {"type": "po", "orderStatus": "Hold", "items": [{"qty": 10, "supplyLog": [{"qtySupplied": 4}]}]}
    assert R.delete_supply(po2, 0, 0)["orderStatus"] == "Hold"

def test_REQ_TSK_06_who_can_edit_a_task():
    t = T()
    assert R.can_edit_task(ADMIN, t) and R.can_edit_task(BM, t) and not R.can_edit_task(SM, t)
    assert R.can_edit_task(SM, T(createdById="u4"))

def test_REQ_LBL_09_label_needs_a_name():
    assert R.label_target_name("", mk_company()) == "Sun Steels" and R.label_target_name("Site", None) == "Site"
    with pytest.raises(ValueError): R.label_target_name("  ", None)

def test_REQ_LST_01_deleting_a_list_value_keeps_old_records():
    recs = [{"source": "Referral"}]
    vals, recs2 = R.delete_list_value(["Referral", "Web"], "Referral", recs, "source")
    assert vals == ["Web"] and recs2 == [{"source": "Referral"}]
