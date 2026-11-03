"""Foundation and cross-cutting cases: sign-in (G-08, G-09), dialogs (G-10), mobile (G-07), Assign Call (O-04), approvals (X-01, X-02)."""
from harness import *
from flow_dashboard import check
from flow_customers import login, ok_dialog

def go(pg, h): pg.evaluate(f"location.hash='#/{h}'"); pg.wait_for_timeout(1800)

def signin(p):
    ok = True; b = launch(p)
    ctx = b.new_context(viewport={'width': 1280, 'height': 800}); pg = ctx.new_page()
    natives = []; pg.on('dialog', lambda d: (natives.append(d.message), d.dismiss()))
    pg.goto(APP + 'login/')
    ok &= check('G-08 step 1 shows only the User ID', pg.is_visible('#li-user') and not pg.is_visible('#li-pass'))
    pg.click('#useridSubmit'); ok &= check('G-08 an empty User ID is refused', pg.inner_text('#useridErr') == 'Enter your User ID.' and pg.is_visible('#useridErr'))
    pg.fill('#li-user', 'nobody'); pg.click('#useridSubmit'); ok &= check('G-08 step 2: password, with the ID echoed and a way back', pg.is_visible('#li-pass') and 'nobody' in pg.inner_text('#pinAsLabel') and pg.is_visible('#backToUseridLink'))
    pg.fill('#li-pass', 'wrong-pass-1'); pg.click('#pinSubmit'); pg.wait_for_timeout(1500)
    err = pg.inner_text('#loginErr')
    ok &= check('G-08 a wrong ID or password gives one message (it does not say which)', 'User ID or password' in err or 'incorrect' in err.lower() or 'invalid' in err.lower(), err)
    pg.click('#backToUseridLink'); pg.fill('#li-user', 'admin'); pg.click('#useridSubmit'); pg.click('#backToUseridLink'); ok &= check('G-08 "Not you? Change User ID" returns to step 1', pg.is_visible('#li-user') and not pg.is_visible('#li-pass'))
    pg.fill('#li-user', 'admin'); pg.click('#useridSubmit'); pg.fill('#li-pass', PW); pg.click('#pinSubmit'); pg.wait_for_timeout(2500)
    ok &= check('G-08 the right password lands on the app', '/360/' in pg.url and pg.locator('#app-view').count() == 1 and 'login' not in pg.url)
    ctx.close()
    # G-09 forgot password (sole admin: no verifier needed) then sign in with the new password
    ctx = b.new_context(viewport={'width': 1280, 'height': 800}); pg = ctx.new_page(); pg.goto(APP + 'login/')
    pg.fill('#li-user', 'manager'); pg.click('#useridSubmit'); pg.click('#forgotPasswordLink')
    ok &= check('G-09 reset form: verifier, new + confirm, back link', pg.is_visible('#rp-vuser') and pg.is_visible('#rp-vpass') and pg.is_visible('#rp-new') and pg.is_visible('#rp-confirm') and pg.is_visible('#resetPwCancel'))
    pg.click('#resetPwCancel'); ok &= check('G-09 "Back to sign in"', pg.is_visible('#li-pass') or pg.is_visible('#li-user'))
    pg.click('#forgotPasswordLink') if pg.is_visible('#forgotPasswordLink') else None
    if not pg.is_visible('#rp-new'):
        pg.fill('#li-user', 'manager') if pg.is_visible('#li-user') else None
        if pg.is_visible('#useridSubmit'): pg.click('#useridSubmit')
        pg.click('#forgotPasswordLink')
    pg.fill('#rp-vuser', 'admin'); pg.fill('#rp-vpass', PW); pg.fill('#rp-new', 'Brand-new-pw-77'); pg.fill('#rp-confirm', 'Different-pw-88'); pg.click('#resetPwSubmit'); pg.wait_for_timeout(1500)
    ok &= check('G-09 mismatching passwords are refused', "don't match" in pg.inner_text('#resetPwErr').lower() or 'match' in pg.inner_text('#resetPwErr').lower(), pg.inner_text('#resetPwErr'))
    pg.fill('#rp-vuser', 'admin'); pg.fill('#rp-vpass', 'not-the-password'); pg.fill('#rp-new', 'Brand-new-pw-77'); pg.fill('#rp-confirm', 'Brand-new-pw-77'); pg.click('#resetPwSubmit'); pg.wait_for_timeout(1500)
    ok &= check('G-09 a wrong verifying admin password is refused', pg.is_visible('#resetPwErr') and pg.inner_text('#resetPwErr') != '', pg.inner_text('#resetPwErr'))
    pg.fill('#rp-vuser', 'admin'); pg.fill('#rp-vpass', PW); pg.fill('#rp-new', 'Brand-new-pw-77'); pg.fill('#rp-confirm', 'Brand-new-pw-77'); pg.click('#resetPwSubmit'); pg.wait_for_timeout(2000)
    pg.fill('#li-user', 'manager') if pg.is_visible('#li-user') else None
    if pg.is_visible('#useridSubmit'): pg.click('#useridSubmit')
    pg.fill('#li-pass', 'Brand-new-pw-77'); pg.click('#pinSubmit'); pg.wait_for_timeout(2500)
    ok &= check('G-09 the new password signs in', '/360/' in pg.url and 'login' not in pg.url, pg.url)
    ok &= check('G-08/09 no browser dialogs were used', not natives, str(natives))
    ctx.close(); b.close(); return ok

def cross(p):
    ok = True; b = launch(p)
    ctx, pg = login(b, 'admin', geo=False)
    natives = []; pg.on('dialog', lambda d: (natives.append(d.message), d.dismiss()))
    # G-10 custom dialogs: Escape and the backdrop
    go(pg, 'payments'); pg.locator('[data-pay-act="delete"]').first.click(); pg.wait_for_timeout(500)
    ok &= check('G-10 a custom confirm appears (not a browser one)', pg.locator('#dlgOk').count() == 1 and not natives)
    pg.keyboard.press('Escape'); pg.mouse.click(5, 5); pg.wait_for_timeout(400)
    ok &= check('G-10 as in the reference, Escape and the backdrop do not answer the question', pg.locator('#dlgOk').count() == 1)
    pg.click('#dlgCancel'); pg.wait_for_timeout(400)
    ok &= check('G-10 Cancel closes it without confirming', pg.locator('#dlgOk').count() == 0 and pg.locator('#paymentsTableWrap tr').count() >= 2)
    # O-04 Assign Call
    go(pg, 'customers'); pg.click('#selectAllBox'); pg.wait_for_timeout(300)
    pg.click('#view-customers .row-menu-btn') if pg.locator('#view-customers .row-menu-btn').count() else None
    pg.evaluate("document.getElementById('bulkAssignCallBtn').click()"); pg.wait_for_timeout(600)
    ok &= check('O-04 Assign Call List dialog: staff + week', pg.locator('#callAssignOverlay.open').count() == 1 and pg.locator('#callAssignStaff option').count() >= 1 and pg.input_value('#callAssignWeek') != '')
    wk = pg.input_value('#callAssignWeek')
    import datetime as dt
    ok &= check('O-04 the week starts on a Monday', dt.date.fromisoformat(wk).weekday() == 0, wk)
    pg.click('#callAssignApplyBtn'); pg.wait_for_timeout(1500)
    dlg = lambda: pg.evaluate("document.querySelector('#dlgOk').closest('.modal').innerText")
    msg = dlg()
    ok &= check('O-04 assigning reports how many contacts were added, and the Do Not Disturb ones left out', msg.count('Added 14 contacts') == 1 and 'Do Not Disturb' in msg, msg)
    pg.click('#dlgOk'); pg.wait_for_timeout(500)
    pg.evaluate("document.getElementById('bulkAssignCallBtn').click()"); pg.wait_for_timeout(500); pg.click('#callAssignApplyBtn'); pg.wait_for_timeout(1500)
    msg2 = dlg()
    ok &= check('O-04 a repeat adds nothing and says they are already on the list', 'Added 0 contacts' in msg2 and 'already on that list' in msg2, msg2)
    pg.click('#dlgOk')
    ok &= check('no browser dialogs', not natives, str(natives))
    ctx.close()
    # G-07 mobile
    ctx = b.new_context(viewport={'width': 390, 'height': 800}); pg = ctx.new_page(); pg.goto(APP + 'login/'); app_login(pg, 'admin'); pg.wait_for_timeout(1500)
    ok &= check('G-07 mobile top bar: hamburger, bell, logout', pg.is_visible('#topbarBurger') and pg.is_visible('#mobileLogoutBtn') and pg.locator('#mobileTopbar button').count() >= 3)
    ok &= check('G-07 the sidebar starts hidden', not pg.evaluate("(()=>{const s=document.querySelector('.sidebar');const r=s.getBoundingClientRect();return r.right>0})()"))
    pg.click('#topbarBurger'); pg.wait_for_timeout(500)
    ok &= check('G-07 hamburger slides the sidebar in with a backdrop', pg.evaluate("(()=>{const s=document.querySelector('.sidebar');return s.getBoundingClientRect().right>0})()") and pg.evaluate("getComputedStyle(document.getElementById('sidebarBackdrop')).display!=='none'"))
    pg.click('#sidebarBackdrop', position={'x': 370, 'y': 400}); pg.wait_for_timeout(500)
    ok &= check('G-07 the backdrop closes it', not pg.evaluate("document.querySelector('.sidebar').getBoundingClientRect().right>0"))
    go(pg, 'sales/quotation')
    ok &= check('G-07 tables collapse: cells carry data-label', pg.locator('#salesTableWrap td[data-label]').count() > 0)
    ok &= check('G-07 no sideways scrolling of the page', pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), str(pg.evaluate("document.documentElement.scrollWidth")))
    ctx.close(); b.close(); return ok

def approvals(p):
    ok = True; b = launch(p)
    ctx, pg = login(b, 'sales', geo=False)           # a Sales Manager: edits and deletes go to approval
    made = pg.evaluate("""async () => {
      const csrf = document.cookie.split('; ').find(c => c.startsWith('csrftoken=')).split('=')[1];
      const cs = (await (await fetch('/360/api/customers/')).json()).results;
      const bs = (await (await fetch('/360/api/bootstrap/')).json()).branches;
      const r = await fetch('/360/api/sales-documents/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ type: 'enquiry', branch_id: bs[0].id, customer_id: cs[0].id, date: '2026-11-01', source: 'Telephonic', items: [{ item_name: 'Bearing', qty: 2 }] }) });
      return [r.status, (await r.text()).slice(0, 200)];
    }""")
    ok &= check('X-02 a Sales Manager can create an enquiry', made[0] == 201, str(made))
    go(pg, 'sales/enquiry')
    ok &= check('X-02 and sees it in the list with View / Edit / Delete', pg.locator('#salesTableWrap button').all_inner_texts()[:3] == ['View', 'Edit', 'Delete'])
    pg.locator('#salesTableWrap button', has_text='Delete').first.click(); pg.wait_for_timeout(500)
    ok &= check('X-02 deleting an enquiry asks to submit a request', 'Submit a request to delete ENQ-0001 for approval?' in pg.evaluate("document.querySelector('#dlgOk').closest('.modal').innerText")); pg.click('#dlgOk'); pg.wait_for_timeout(1500)
    msg = pg.evaluate("document.querySelector('#dlgOk') ? document.querySelector('#dlgOk').closest('.modal').innerText : ''")
    ok &= check('X-02 ...and says the request was submitted', 'Delete request submitted. A branch manager or admin needs to approve it.' in msg, msg)
    if pg.locator('#dlgOk').count(): pg.click('#dlgOk')
    ctx.close()
    ctx, pg = login(b, 'admin', geo=False); go(pg, 'dashboard')
    ok &= check('X-01 the Admin sees the request on the dashboard', pg.locator('[data-apv-approve]').count() >= 1 and 'Delete request' in pg.inner_text('#dashApprovals'), pg.inner_text('#dashApprovals')[:200])
    pg.locator('[data-apv-view]').first.click(); pg.wait_for_timeout(500)
    ok &= check('X-01 View details opens the request', pg.locator('#apvApprove').count() == 1); pg.click('#apvClose'); pg.wait_for_timeout(300)
    before = pg.locator('[data-apv-approve]').count()
    pg.locator('[data-apv-approve]').first.click(); pg.wait_for_timeout(600)
    if pg.locator('#dlgOk').count(): pg.click('#dlgOk'); pg.wait_for_timeout(1500)
    go(pg, 'dashboard')
    ok &= check('X-01 approving applies it and clears it from the list', pg.locator('[data-apv-approve]').count() == before - 1)
    ctx.close(); b.close(); return ok

def run(p, parts=('signin', 'cross', 'approvals')):
    ok = True
    if 'signin' in parts: ok &= signin(p)
    if 'cross' in parts: ok &= cross(p)
    if 'approvals' in parts: ok &= approvals(p)
    print('FINAL PASS' if ok else 'FINAL FAILED')

if __name__ == '__main__':
    import sys
    with sync_playwright() as p: run(p, tuple(sys.argv[1:]) or ('signin', 'cross', 'approvals'))
