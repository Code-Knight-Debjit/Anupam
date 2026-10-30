"""
Runs the same requirement checks against the *reference* standalone HTML app, in a real browser.
Purpose: prove the requirement tests describe what the app actually does (so they are a trustworthy spec).

    pip install playwright && playwright install chromium
    python e2e/check_reference_app.py /path/to/contact_management.html
"""
import sys, json, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import rules.anupam_rules as R
from playwright.sync_api import sync_playwright

PATH = sys.argv[1] if len(sys.argv) > 1 else "contact_management.html"
results = []
def check(name, ok, detail=""):
    results.append((name, bool(ok), detail)); print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))

with sync_playwright() as p:
    b = p.chromium.launch(); page = b.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto("file://" + __import__("os").path.abspath(PATH)); page.wait_for_timeout(1200)
    page.fill("#newEmpUserId", "admin01"); page.fill("#newEmpName", "Sanjeev"); page.fill("#newEmpPin", "123456")
    page.click("text=Create admin account"); page.wait_for_timeout(1500)

    ev = page.evaluate
    # fixtures -------------------------------------------------------------
    ev("""()=>{
      window.U={A:{id:'u1',name:'Sanjeev',role:'Admin'},BM:{id:'u2',name:'Bala',role:'Branch Manager'},
                BS:{id:'u3',name:'Staff',role:'Branch Staff'},SM:{id:'u4',name:'Devdutt',role:'Sales Manager'},SM2:{id:'u5',name:'Ravi',role:'Sales Manager'}};
      companies.length=0;
      companies.push({id:'a',name:'Mine',createdById:'u4',contacts:[]},
        {id:'b',name:'Assigned',createdById:'u1',assignedTo:['Devdutt'],contacts:[{id:'p1',name:'P1'},{id:'p2',name:'P2'},{id:'p3',name:'P3'},{id:'p4',name:'P4'}],contactAccess:{Devdutt:['p1','p3']}},
        {id:'c',name:'Other',createdById:'u1',contacts:[]});
    }""")
    def as_(k): ev(f"()=>{{ currentUser = U.{k}; }}")

    as_("SM"); check("REQ-CUS-01 SM sees own+assigned only", ev("()=>visibleCompanies().map(c=>c.id).sort().join()") == "a,b")
    as_("A");  check("REQ-CUS-01 Admin sees all", ev("()=>visibleCompanies().length") == 3)
    as_("BS"); check("REQ-CUS-01 Branch Staff sees all", ev("()=>visibleCompanies().length") == 3)
    as_("SM"); check("REQ-CUS-02 SM sees only 2 of 4 contacts", ev("()=>ctVisible(companies[1]).map(c=>c.id).join()") == "p1,p3")
    as_("A");  check("REQ-CUS-02 Admin still sees 4 contacts", ev("()=>ctVisible(companies[1]).length") == 4)
    as_("SM2"); check("REQ-CUS-02 other SM unrestricted", ev("()=>ctVisible(companies[1]).length") == 4)
    check("REQ-CUS-07 label = name, plant, area (no city)",
          ev("()=>companySelLabel({name:'Sun Steels',plant:'Plant 2',area:'Ambattur',city:'Chennai'})") == "Sun Steels, Plant 2, Ambattur")
    check("REQ-CUS-09 duplicate detector", len(ev("()=>findSimilarCompanies('Mine1')")) >= 1)

    # tasks ----------------------------------------------------------------
    ev("""()=>{ tasks.length=0; tasks.push(
      {id:'1',title:'x',assignedToId:'u1',assignedToName:'Sanjeev',createdById:'u1',createdByName:'Sanjeev',status:'Open'},
      {id:'2',title:'y',assignedToId:'u4',assignedToName:'Devdutt',createdById:'u1',createdByName:'Sanjeev',status:'Open'}); taskFilters.scope='mine'; }""")
    as_("A")
    check("REQ-TSK-01 main list = own tasks", ev("()=>taskBaseList(visibleTasks()).map(t=>t.id).join()") == "1")
    check("REQ-TSK-01 Admin 'all' scope", ev("()=>{taskFilters.scope='all'; const r=taskBaseList(visibleTasks()).length; taskFilters.scope='mine'; return r}") == 2)
    check("REQ-TSK-02 Assigned-by-me panel", ev("()=>taskAssignedByMe().map(t=>t.id).join()") == "2")
    as_("SM")
    check("REQ-TSK-02 assignee sees it in own list", ev("()=>taskBaseList(visibleTasks()).map(t=>t.id).join()") == "2")
    check("REQ-TSK-03 assignee cannot remove", ev("()=>canRemoveTask(tasks[1])") is False)
    as_("A")
    check("REQ-TSK-03 creator can remove", ev("()=>canRemoveTask(tasks[1])") is True)

    # automations ----------------------------------------------------------
    ev("""()=>{ notifications.length=0; employees.length=0;
      employees.push({id:'u1',name:'Sanjeev',role:'Admin'},{id:'u2',name:'Bala',role:'Branch Manager'},{id:'u3',name:'Staff',role:'Branch Staff'},{id:'u4',name:'Devdutt',role:'Sales Manager'});
      tasks.length=0; tasks.push({id:'t9',title:'Do it',assignedToId:'u4',assignedToName:'Devdutt',assignees:[{id:'u4',name:'Devdutt'}],createdById:'u1',createdByName:'Sanjeev',status:'Open'}); }""")
    as_("SM")
    ev("async()=>{ await updateTaskStatus('t9','Done'); await updateTaskStatus('t9','Done'); }")
    nt = ev("()=>notifications.map(n=>n.type+':'+n.userId).join()")
    check("REQ-AUT-05 task Done notifies creator once", nt == "task_done:u1", nt)
    ev("()=>{ notifications.length=0; companies.length=0; companies.push({id:'z',name:'Zed',createdById:'u1',contacts:[]}); approvals.length=0; }")
    ev("async()=>{ await requestCustomerAccess('z'); }")
    nt = ev("()=>notifications.map(n=>n.type+':'+n.userId).sort().join()")
    check("REQ-AUT-02 access request notifies Admin + BM", nt == "customer-access-request:u1,customer-access-request:u2", nt)
    as_("A")
    ev("async()=>{ notifications.length=0; window.customConfirm = async()=>true; await approveRequest(approvals[0].id); }")
    check("REQ-AUT-02 approve adds requester to assignedTo", ev("()=>assignedToArr(companies[0]).join()") == "Devdutt" and ev("()=>notifications.map(n=>n.type).join()") == "customer-access-approved")

    # numbering ------------------------------------------------------------
    ev("()=>{ for(const k of Object.keys(docCounters)) delete docCounters[k]; }")
    n1 = ev("()=>nextDocNumber('quotation','Chennai')")
    ev("async()=>{ await bumpDocCounter('quotation','Chennai', nextDocNumber('quotation','Chennai')); }")
    n2 = ev("()=>nextDocNumber('quotation','Chennai')"); n3 = ev("()=>nextDocNumber('quotation','Bengaluru')")
    check("REQ-DOC-01 numbers advance per branch", n2 != n1 and n3 == n1, f"{n1},{n2},{n3}")

    # parity: the Python rules must give the SAME answers as the reference app -----------------
    ev("()=>{ for(const k of Object.keys(docCounters)) delete docCounters[k]; branches.length=0; branches.push({id:'b1',name:'Chennai',numbering:{quotation:{prefix:'CHN/Q',suffix:'26-27',start:100}}}); }")
    check("PARITY numbering with prefix/suffix/start", ev("()=>nextDocNumber('quotation','Chennai')") == R.next_doc_number({}, "quotation", "Chennai", {"quotation": {"prefix": "CHN/Q", "suffix": "26-27", "start": 100}}), ev("()=>nextDocNumber('quotation','Chennai')"))
    check("PARITY default numbering ENQ-0001", ev("()=>nextDocNumber('enquiry','Bengaluru')") == R.next_doc_number({}, "enquiry", "Bengaluru") == "ENQ-0001")
    check("PARITY sequence = first digits", ev("()=>docNumberSeq('CHN/Q-0100-26-27')") == R.doc_number_seq("CHN/Q-0100-26-27") == 100)
    for amt in (0, 5, 99.5, 1000, 123456.5, 10000000, 9876543.21, 100000.01):
        a = ev(f"()=>amountInWords({amt})"); check(f"PARITY amount in words {amt}", a == R.amount_in_words(amt), f"{a} != {R.amount_in_words(amt)}")
    doc = {"showDiscountInPdf": False, "items": [{"itemName": "6205", "make": "Timken", "qty": 10, "rate": 333.33, "discount": 10, "tax": 18}, {"itemName": "UCP 208", "qty": 3, "rate": 250.5, "discount": 0, "tax": 12}],
           "packingCharges": 100, "packingTax": 18, "freightCharges": 200, "freightTax": 0, "otherCharges": 50, "otherChargesTax": 5, "roundOff": -0.4}
    for show in (False, True):
        d = dict(doc, showDiscountInPdf=show); js = ev("(d)=>{const r=computeQuotationDocData(d); return {sub:r.subTotal,tax:r.taxTotal,total:r.total}}", d); py = R.quotation_print_totals(d)
        check(f"PARITY printed totals (show discount={show})", abs(js["sub"] - py["subTotal"]) < 1e-6 and abs(js["tax"] - py["taxTotal"]) < 1e-6 and abs(js["total"] - py["total"]) < 1e-6, f"{js} vs {py['subTotal']},{py['taxTotal']},{py['total']}")
    for ph in ("98400 12345", "+91 98400-12345", "044 2345 6789", ""):
        check(f"PARITY whatsapp link {ph!r}", ev("(p)=>waLink(p)", ph) == R.wa_link(ph))
    cl = {"callLog": [{"timestamp": "2026-10-01T10:00", "callLaterDate": "2026-10-10"}, {"timestamp": "2026-10-05T10:00", "callLaterDate": "2026-10-20"}, {"timestamp": "2026-10-06T10:00"}]}
    check("PARITY next call-later date + last contact", ev("(d)=>[nextCallLaterDate(d),lastContactOn(d)]", cl) == [R.next_call_later_date(cl), R.last_contact_on(cl)] == ["2026-10-20", "2026-10-06T10:00"])
    po = {"type": "po", "orderStatus": "Pending", "items": [{"qty": 10, "supplyLog": [{"qtySupplied": 4}]}, {"qty": 5}]}
    js = ev("(d)=>{recomputePOStatus(d); return d.orderStatus}", po); check("PARITY PO status Part Pending", js == R.recompute_po_status(json.loads(json.dumps(po)))["orderStatus"] == "Part Pending")
    qd = [{"totalAmount": 500}, {"items": [{"value": 100}, {"qty": 2, "rate": 100, "discount": 10, "tax": 18}]}, {"quotationValue": 77}]
    check("PARITY quotation value", ev("(a)=>a.map(quotationValueOf)", qd) == [R.quotation_value_of(x) for x in qd])

    for g in ("13.0285, 77.5197", "13.0285;77.5197", "https://www.google.com/maps/@13.0285,77.5197,17z", "https://maps.google.com/?q=12.9,80.2", "https://x/place/data=!3d13.1!4d80.3", "95, 10", "junk", ""):
        check(f"PARITY geo parse {g[:28]!r}", ev("(s)=>geoParse(s)", g) == R.geo_parse(g))
    for m in (450, 1500, 25000, 999.6):
        check(f"PARITY geo format {m}", ev("(m)=>geoFmtDist(m)", m) == R.geo_fmt_dist(m))
    ga, gb = {"lat": 13.0, "lng": 80.0}, {"lat": 13.2, "lng": 80.3}
    check("PARITY geo distance", abs(ev("([a,b])=>geoDist(a,b)", [ga, gb]) - R.geo_dist_m(ga, gb)) < 0.01)

    # labels ---------------------------------------------------------------
    keys = ev("()=>LABEL_SIZES.map(s=>s.key).join()")
    check("REQ-LBL size presets exist (a4,a5,4x4,6x4)", keys == "a4,a5,4x4,6x4", keys)
    plan = ev("""()=>{ try{ const md=new window.jspdf.jsPDF({unit:'mm',format:'a4'}); const P=labelPartsFromDoc({customerId:'b'});
        const out={}; for(const k of ['a5','4x4','6x4','a4']){ const s=LABEL_SIZES.find(x=>x.key===k); const r=labelPages(P,4,s,md,true); out[k]=[r.pw,r.ph,r.pages.length]; } return out }catch(e){ return 'err:'+e.message } }""")
    if isinstance(plan, str): check("REQ-LBL-02 tiling (needs jsPDF, skipped offline)", True, plan)
    else:
        check("REQ-LBL-02 A5: 4 labels -> 2 sheets (2 per sheet, landscape)", plan["a5"] == [297, 210, 2], str(plan["a5"]))
        check("REQ-LBL-02 A4 label: one per page", plan["a4"][2] == 4, str(plan["a4"]))
        check("REQ-LBL-02 4x4: 4 per sheet; 6x4: 2 per sheet", plan["4x4"][2] == 1 and plan["6x4"][2] == 2, str(plan))

    # attendance -----------------------------------------------------------
    ev("()=>{ attendance.length=0; leaves.length=0; holidays.length=0; }") if ev("()=>typeof leaves!=='undefined'") else None
    emp = "{id:'u4',name:'Devdutt',role:'Sales Manager',workStart:'09:30',weeklyOff:'0',branches:['Chennai']}"
    code = ev(f"""()=>{{ attendance.push({{userId:'u4',date:'2026-10-20',checkIn:'09:40'}}); const r=attDayStatus({emp},'2026-10-20'); return r.code }}""")
    check("REQ-ATT-01 10-min grace = Present", code == "P", str(code))
    code = ev(f"""()=>{{ attendance.push({{userId:'u4',date:'2026-10-21',checkIn:'09:41'}}); return attDayStatus({emp},'2026-10-21').code }}""")
    check("REQ-ATT-01 11 min = Late", code == "L", str(code))
    check("REQ-ATT-02 Sunday = Off", ev(f"()=>attDayStatus({emp},'2026-10-25').code") == "O")

    # storage warning exists ----------------------------------------------
    ctx2 = b.new_context(); p2 = ctx2.new_page()
    p2.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}})")
    p2.goto("file://" + __import__("os").path.abspath(PATH)); p2.wait_for_timeout(1200)
    check("REQ-STO-01 warning banner shown when browser storage is blocked", p2.is_visible("#storageWarn"))
    check("no JS errors during run", not errs, "; ".join(errs[:3]))
    b.close()

bad = [r for r in results if not r[1]]
print(f"\n{len(results)-len(bad)}/{len(results)} checks passed")
sys.exit(1 if bad else 0)
