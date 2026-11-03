"""Scripted Dashboard flows against the 360 app (cases D-03..D-10 of docs/360/PARITY_TESTS.md)."""
from harness import *

def check(name, ok, extra=''):
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{extra}]' if extra else ''))
    return ok

def run(p):
    ok = True
    b = launch(p)
    ctx = b.new_context(viewport={'width': 1440, 'height': 900}, geolocation={'latitude': 13.0827, 'longitude': 80.2707}, permissions=['geolocation'])
    pg = ctx.new_page(); pg.goto(APP + 'login/'); app_login(pg, 'admin'); pg.wait_for_timeout(1200)
    # D-05 tile click opens the sales tab
    pg.click('#dashPipeline .pipe-2'); pg.wait_for_timeout(600)
    ok &= check('D-05 quotation tile opens #/sales/quotation', pg.evaluate('location.hash') == '#/sales/quotation')
    pg.evaluate("location.hash='#/dashboard'"); pg.wait_for_timeout(1200)
    # D-03 check in / out
    ok &= check('D-03 not checked in yet', 'Not checked in yet' in pg.inner_text('.dash-hero .att'))
    pg.click('#dashCheckInBtn'); pg.wait_for_timeout(1500)
    ok &= check('D-03 check-in recorded', 'Checked in at' in pg.inner_text('.dash-hero .att'), pg.inner_text('.dash-hero .att')[:60])
    pg.click('#dashCheckOutBtn'); pg.wait_for_timeout(1500)
    ok &= check('D-03 check-out shows worked time', 'worked' in pg.inner_text('.dash-hero .att'))
    # D-07 drill-down + D-08 view more
    pg.click('#dashTable [data-drill=customers]'); pg.wait_for_timeout(800)
    ok &= check('D-07 customers drill dialog', 'Customers added' in pg.inner_text('.modal h2') and pg.locator('.modal tr').count() >= 2)
    pg.click('#eaClose'); pg.wait_for_timeout(200)
    more = pg.locator('#dashActivityMoreBtn')
    ok &= check('D-08 view more present', more.count() == 1 and 'View more' in more.inner_text(), more.inner_text() if more.count() else '')
    more.click(); pg.wait_for_timeout(1200)
    ok &= check('D-08 all activity listed then Show less', pg.locator('#dashActivity .activity-item').count() > 10 and 'Show less' in pg.inner_text('#dashActivityMoreBtn'))
    ctx.close()
    # personal: period select + custom dates
    ctx = b.new_context(viewport={'width': 1440, 'height': 900}); pg = ctx.new_page(); pg.goto(APP + 'login/'); app_login(pg, 'staff'); pg.wait_for_timeout(1200)
    ok &= check('D-09 personal grid shown, company view hidden', pg.is_visible('#dashPersonal') and not pg.is_visible('#dashFull'))
    pg.select_option('#dashPeriodSelect', 'all'); pg.wait_for_timeout(900)
    ok &= check('D-09 period label follows the select', 'all time' in pg.inner_text('#dashPersonalGrid'))
    pg.fill('#dashFrom', '2026-10-01'); pg.wait_for_timeout(900)
    ok &= check('D-09 custom dates switch the select to Custom and show Clear dates', pg.input_value('#dashPeriodSelect') == 'custom' and pg.is_visible('#dashRangeClear'))
    pg.click('#dashRangeClear'); pg.wait_for_timeout(900)
    ok &= check('D-09 Clear dates returns to This month', pg.input_value('#dashPeriodSelect') == 'month')
    ctx.close()
    # D-04 approvals: a Sales Manager's customer edit becomes a request; the admin sees it with View changes / Approve / Reject
    ctx = b.new_context(viewport={'width': 1440, 'height': 900}); pg = ctx.new_page(); pg.goto(APP + 'login/'); app_login(pg, 'sales'); pg.wait_for_timeout(1000)
    res = pg.evaluate('''async () => {
      const csrf = document.cookie.match(/csrftoken=([^;]+)/)[1];
      const list = await (await fetch('/360/api/customers/', {credentials:'same-origin'})).json();
      const c = list.results[0];
      const r = await fetch('/360/api/customers/' + c.id + '/', {method:'PATCH', credentials:'same-origin', headers:{'Content-Type':'application/json','X-CSRFToken':csrf}, body: JSON.stringify({city:'Parity City', version:c.version})});
      return {status:r.status, name:c.name};
    }''')
    ok &= check('D-04 SM edit is accepted as a request', res['status'] in (200, 201, 202), str(res))
    ctx.close()
    ctx = b.new_context(viewport={'width': 1440, 'height': 900}); pg = ctx.new_page(); pg.goto(APP + 'login/'); app_login(pg, 'admin'); pg.wait_for_timeout(1500)
    ok &= check('D-04 approval listed with the three buttons', pg.locator('#dashApprovals .activity-item').count() == 1 and pg.locator('[data-apv-view]').count() == 1)
    ok &= check('D-04 sidebar Dashboard badge counts it', pg.inner_text('#dashBadge') == '1')
    pg.click('[data-apv-view]'); pg.wait_for_timeout(800)
    ok &= check('D-04 View changes dialog shows current vs proposed', 'Parity City' in pg.inner_text('.modal') and 'proposed' in pg.inner_text('.modal').lower())
    pg.click('#apvApprove'); pg.wait_for_timeout(900)
    pg.click('#dlgOk') if pg.is_visible('#dlgOk') else None; pg.wait_for_timeout(1200)
    ok &= check('D-04 approve clears the list', 'Nothing waiting' in pg.inner_text('#dashApprovals'))
    ctx.close(); b.close()
    print('ALL PASS' if ok else 'SOME FAILED')

if __name__ == '__main__':
    with sync_playwright() as p:
        run(p)
