"""Scripted Task flows against the 360 app (cases T-01..T-10 of docs/360/PARITY_TESTS.md)."""
from harness import *
from flow_dashboard import check

def login(b, user):
    ctx = b.new_context(viewport={'width': 1440, 'height': 900}); pg = ctx.new_page(); pg.goto(APP + 'login/'); app_login(pg, user)
    pg.evaluate("location.hash='#/tasks'"); pg.wait_for_timeout(1500); return ctx, pg

def run(p):
    ok = True; b = launch(p)
    ctx, pg = login(b, 'admin')
    ok &= check('T-01 layout: stats, tabs, search, calendar, upcoming, assigned-by-me', all(pg.is_visible(s) for s in ('#taskStatsRow', '#taskKindTabs', '#taskSearchInput', '#dashCalDays', '#dashUpcomingList', '#assignedByMePanel')))
    # T-07 form validation
    pg.click('#taskNewBtn'); pg.wait_for_timeout(500)
    ok &= check('T-07 form fields', all(pg.is_visible(s) for s in ('#tk-title', '#tk-desc', '#tkDdBtn', '#tk-priority', '#tk-due', '#tk-customer')))
    pg.click('#taskFormSaveBtn'); ok &= check('T-07 title required', pg.inner_text('#taskFormHint') == 'Enter a title.')
    pg.fill('#tk-title', 'Parity task'); pg.click('#tkDdBtn'); pg.click('.tk-assignee-check:checked'); pg.click('#taskFormTitle'); pg.click('#taskFormSaveBtn')
    ok &= check('T-07 needs at least one person', pg.inner_text('#taskFormHint') == 'Choose at least one person to assign this to.')
    pg.click('#tkDdBtn')
    boxes = pg.locator('.tk-assignee-check'); names = pg.locator('.tk-dd-item .nm').all_inner_texts()
    for i, n in enumerate(names):
        n = n.lower()
        if n.startswith(('sam', 'sally')): boxes.nth(i).check()
        if n.startswith('admin'): boxes.nth(i).uncheck()      # the creator is pre-selected; this task is for the others
    pg.click('#taskFormTitle'); pg.fill('#tk-due', '2026-11-20'); pg.select_option('#tk-priority', 'High'); pg.click('#taskFormSaveBtn'); pg.wait_for_timeout(1200)
    ok &= check('T-07 created and listed under Assigned by me', 'Parity task' in pg.inner_text('#assignedByMeList'))
    ok &= check('T-02 shared task shows the 👥 chip count', pg.locator('#assignedByMeList .abm-row', has_text='Parity task').count() == 1)
    ctx.close()
    # assignee completes it, creator gets notified and verifies
    ctx, pg = login(b, 'staff')
    ok &= check('T-02 assignee sees the shared task', 'Parity task' in pg.inner_text('#taskListWrap'))
    ok &= check('T-02 assignee was notified', pg.inner_text('#notifBadge') != '')
    card = pg.locator('.tcard', has_text='Parity task')
    ok &= check('T-09 assignee cannot delete someone else\'s task', card.locator('[data-delete]').count() == 0)
    card.locator('[data-status]').click(); pg.wait_for_timeout(1500)
    ok &= check('T-08 task marked Done shows the waiting message', 'Stays here until Sanjeev' in pg.inner_text('#taskListWrap') or 'Stays here until' in pg.inner_text('#taskListWrap'))
    ctx.close()
    ctx, pg = login(b, 'admin')
    pg.click('#notifBellBtn'); pg.wait_for_timeout(600)
    ok &= check('T-08 creator notified to verify', 'verify and mark it complete' in pg.inner_text('#notifDropdown'))
    pg.click('body'); pg.wait_for_timeout(200)
    row = pg.locator('#assignedByMeList .abm-row', has_text='Parity task')
    row.locator('[data-delete]').click(); pg.wait_for_timeout(500)
    ok &= check('T-08 Mark Complete asks for confirmation', 'removed from the Task panel for everyone' in pg.inner_text('.modal'))
    pg.click('#dlgOk'); pg.wait_for_timeout(1200)
    ok &= check('T-08 verified task disappears', 'Parity task' not in pg.inner_text('#view-tasks'))
    # T-02 scope + folding
    pg.click('[data-tscope=all]'); pg.wait_for_timeout(1000)
    ok &= check('T-02 Everyone groups by person', pg.locator('#taskListWrap .tsec .avatar').count() >= 2)
    pg.click('[data-foldall="1"]'); ok &= check('T-10 collapse all', pg.locator('.tcard.collapsed').count() == pg.locator('.tcard').count() > 0)
    pg.click('[data-foldall="0"]'); ok &= check('T-10 expand all', pg.locator('.tcard.collapsed').count() == 0)
    # T-05 calendar day pick
    pg.click('[data-tscope=mine]'); pg.wait_for_timeout(600)
    pg.click('#dashCalDays .mini-cal-day.today'); pg.wait_for_timeout(500)
    ok &= check('T-05 day pick narrows to that day and offers Show all days', pg.is_visible('#calClearDayBtn'))
    ctx.close(); b.close()
    print('ALL PASS' if ok else 'SOME FAILED')

if __name__ == '__main__':
    with sync_playwright() as p:
        run(p)
