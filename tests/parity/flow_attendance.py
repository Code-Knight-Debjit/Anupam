"""Scripted Attendance flows against the 360 app (cases AT-01..AT-07)."""
from harness import *
from flow_dashboard import check
import datetime as dt

def login(b, user, geo=True):
    kw = dict(viewport={'width': 1440, 'height': 900})
    if geo: kw.update(geolocation={'latitude': 13.08, 'longitude': 80.27}, permissions=['geolocation'])
    ctx = b.new_context(**kw); pg = ctx.new_page(); pg.goto(APP + 'login/'); app_login(pg, user)
    pg.evaluate("location.hash='#/attendance'"); pg.wait_for_timeout(1800); return ctx, pg

def run(p):
    ok = True; b = launch(p)
    soon = (dt.date.today() + dt.timedelta(days=5)).isoformat(); past = (dt.date.today() - dt.timedelta(days=2)).isoformat()
    ctx, pg = login(b, 'staff')
    ok &= check('AT-01 sections in order', all(pg.is_visible(s) for s in ('#attTodayCard', '#attMyStats', '#attMyTable', '#lvSubmitBtn')) and not pg.is_visible('#attTeamSection') and not pg.is_visible('#holFormCard'))
    pg.click('#attCheckInBtn'); pg.wait_for_timeout(1500)
    ok &= check('AT-02 check-in shows time and On time/Late chip', 'Checked in at' in pg.inner_text('#attTodayCard'))
    pg.fill('#lv-from', past); pg.fill('#lv-reason', 'x'); pg.click('#lvSubmitBtn'); pg.wait_for_timeout(600)
    ok &= check('AT-06 leave cannot start in the past', 'cannot start in the past' in pg.inner_text('#lvHint'))
    pg.fill('#lv-from', soon); pg.fill('#lv-reason', ''); pg.click('#lvSubmitBtn'); pg.wait_for_timeout(600)
    ok &= check('AT-06 reason required', 'Add a short reason' in pg.inner_text('#lvHint'))
    pg.fill('#lv-reason', 'Family function'); pg.click('#lvSubmitBtn'); pg.wait_for_timeout(1500)
    ok &= check('AT-06 request listed as Pending with Cancel', 'Family function' in pg.inner_text('#attMyLeaves') and pg.locator('[data-cancel]').count() >= 1)
    ctx.close()
    ctx, pg = login(b, 'manager')
    ok &= check('AT-07 manager sees team section, request waiting', pg.is_visible('#attTeamSection') and 'Sam Staff' in pg.inner_text('#attApprovals'))
    ok &= check('AT-05 manager holiday chips: own branch only, no "All branches"', pg.locator('#hol-all').count() == 0 and pg.locator('.hol-branch-check').count() == 1)
    before = pg.locator('[data-decide$=":approve"]').count()
    pg.locator('[data-decide$=":approve"]').first.click(); pg.wait_for_timeout(1500)
    ok &= check('AT-06 approving removes it from the approval list', pg.locator('[data-decide$=":approve"]').count() == before - 1)
    pg.fill('#hol-from', (dt.date.today() + dt.timedelta(days=20)).isoformat()); pg.fill('#hol-name', 'local fest'); pg.locator('.hol-branch-check').first.check(); pg.click('#holAddBtn'); pg.wait_for_timeout(1500)
    ok &= check('AT-05 holiday added with title-cased name and "Added by"', 'Local Fest' in pg.inner_text('#attHolidays') and 'Manny Manager' in pg.inner_text('#attHolidays'))
    # AT-04 correct a day for Sam: click his cell for yesterday
    ydt = (dt.date.today() - dt.timedelta(days=1)); mon = ydt.strftime('%Y-%m')
    pg.fill('#attTeamMonth', mon); pg.dispatch_event('#attTeamMonth', 'change'); pg.wait_for_timeout(1200)
    cell = pg.locator(f'td[data-att-d="{ydt.isoformat()}"]').nth(1)
    cell.click(); pg.wait_for_timeout(500)
    ok &= check('AT-04 correction dialog opens', 'Correct attendance' in pg.inner_text('.modal h2'))
    pg.select_option('#attDayStatus', 'Half day'); pg.fill('#attDayNote', 'left early'); pg.click('#attDaySave'); pg.wait_for_timeout(1500)
    ok &= check('AT-04 grid shows H for the corrected day', pg.locator(f'td[data-att-d="{ydt.isoformat()}"]', has_text='H').count() >= 1)
    ok &= check('AT-04 Export button present', pg.is_visible('#attExportBtn'))
    ctx.close()
    ctx, pg = login(b, 'admin')
    ok &= check('AT-05 admin chips include All branches', pg.locator('#hol-all').count() == 1 and pg.locator('.hol-branch-check').count() == 2)
    ok &= check('AT-05 admin may remove a branch manager\'s holiday', pg.locator('[data-delhol]').count() >= 1)
    ctx.close(); b.close()
    print('ALL PASS' if ok else 'SOME FAILED')

if __name__ == '__main__':
    with sync_playwright() as p: run(p)
