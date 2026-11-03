"""Scripted Outreach flows against the 360 app (cases O-01..O-05)."""
from harness import *
from flow_dashboard import check

def run(p):
    ok = True; b = launch(p)
    ctx = b.new_context(viewport={'width': 1440, 'height': 900}); pg = ctx.new_page(); pg.goto(APP + 'login/'); app_login(pg, 'staff')
    pg.evaluate("location.hash='#/callinglist'"); pg.wait_for_timeout(1500)
    ok &= check('O-01 hero, tiles, filter bar, list', all(pg.is_visible(s) for s in ('#callingListHero .ol-ring', '#callingListStatsRow', '#clSearch', '#clFilterWeek')) and pg.locator('.ol-card').count() == 2)
    ok &= check('O-05 staff has no staff filter, no Remove', not pg.is_visible('#clFilterStaff') and pg.locator('[data-remove]').count() == 0)
    card = pg.locator('.ol-card', has_text='Deccan Agro')
    card.locator('[data-notreached]').click(); pg.wait_for_timeout(500)
    pg.select_option('#cnrReason', 'Busy'); pg.fill('#cnrNote', 'try after lunch'); pg.fill('#cnrAgain', '2026-11-12'); pg.click('#cnrSaveBtn'); pg.wait_for_timeout(1500)
    txt = pg.locator('.ol-card', has_text='Deccan Agro').inner_text()
    ok &= check('O-02/03 attempt logged, entry stays pending', 'Attempted · Busy (1)' in txt and 'Last attempt:' in txt and 'Call again on' in txt, txt[:100].replace('\n', ' '))
    pg.evaluate("location.hash='#/tasks'"); pg.wait_for_timeout(1500)
    ok &= check('O-03 call-again date added a Call task', 'Call Ravi' in pg.inner_text('#taskListWrap') or 'Ravi' in pg.inner_text('#taskListWrap'))
    pg.evaluate("location.hash='#/callinglist'"); pg.wait_for_timeout(1500)
    pg.locator('.ol-card', has_text='Southern Packaging').locator('[data-completed]').click(); pg.wait_for_timeout(500)
    pg.fill('#callRemarksText', 'Sent catalogue on WhatsApp'); pg.click('#callRemarksSaveBtn'); pg.wait_for_timeout(1500)
    ok &= check('O-03 completed call leaves the list', pg.locator('.ol-card', has_text='Southern Packaging').count() == 0 and pg.locator('.ol-card').count() == 1)
    ok &= check('O-01 progress ring updates to 50%', '50%' in pg.inner_text('.ol-ring'), pg.inner_text('.ol-ring').replace('\n', ' '))
    ctx.close()
    ctx = b.new_context(viewport={'width': 1440, 'height': 900}); pg = ctx.new_page(); pg.goto(APP + 'login/'); app_login(pg, 'admin')
    pg.evaluate("location.hash='#/callinglist'"); pg.wait_for_timeout(1500)
    ok &= check('O-05 admin groups by person with a staff filter and Remove', pg.locator('.tsec .avatar').count() >= 1 and pg.is_visible('#clFilterStaff') and pg.locator('[data-remove]').count() >= 1)
    ctx.close(); b.close()
    print('ALL PASS' if ok else 'SOME FAILED')

if __name__ == '__main__':
    with sync_playwright() as p: run(p)
