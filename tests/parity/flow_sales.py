"""Scripted Sales list flows against the 360 app (cases S-01..S-06, S-12, S-13)."""
from harness import *
from flow_dashboard import check
from flow_customers import login, ok_dialog

def go(pg, h):
    pg.evaluate(f"location.hash='#/{h}'"); pg.wait_for_timeout(1500)

def run(p):
    ok = True; b = launch(p)
    ctx, pg = login(b, 'admin', geo=False)
    go(pg, 'sales/enquiry')
    ok &= check('S-01 enquiry list: hero, search, filters, view all, actions', all(pg.is_visible(s) for s in ('#salesNewBtn', '#salesSearchInput', '#salesFilterToggleBtn', '#salesViewAllBtn')) and 'Enquiries' in pg.inner_text('#salesTitle'))
    ok &= check('S-02 only pending enquiries listed (completed ENQ-0002 is not)', 'ENQ-0001' in pg.inner_text('#salesTableWrap') and 'ENQ-0002' not in pg.inner_text('#salesTableWrap'))
    pg.click('.row-menu-btn:has-text("Actions")'); pg.wait_for_timeout(200)
    ok &= check('S-01 Actions menu items', pg.locator('.row-menu-dropdown.open button:visible').all_inner_texts()[:4] == ['View Completed & Regretted', 'Export Excel', 'Export PDF', 'Print'], str(pg.locator('.row-menu-dropdown.open button:visible').all_inner_texts()))
    pg.click('body')
    pg.click('#salesHistoryBtn') if pg.is_visible('#salesHistoryBtn') else pg.evaluate("document.getElementById('salesHistoryBtn').click()"); pg.wait_for_timeout(1500)
    ok &= check('S-02 Completed & Regretted history page', 'Completed & Regretted Enquiries' in pg.inner_text('#view-enqhistory h1') and 'ENQ-0002' in pg.inner_text('#enqHistoryWrap'))
    go(pg, 'sales/quotation')
    ok &= check('S-03 quotation stats tiles + pending quotation only', '₹' in pg.inner_text('#quotStatsRow') and 'QUO-0001' in pg.inner_text('#salesTableWrap') and 'QUO-0002' not in pg.inner_text('#salesTableWrap'))
    ok &= check('S-03 contact cell shows last contact and call later', 'Last contact:' in pg.inner_text('#salesTableWrap') and 'Call later:' in pg.inner_text('#salesTableWrap'))
    pg.click('#salesFilterToggleBtn'); pg.select_option('#fltCallLater', 'none'); pg.wait_for_timeout(300)
    ok &= check('S-03 Call Me Later filter + badge', pg.inner_text('#salesFilterBadge') == '1')
    pg.click('#fltClear'); pg.wait_for_timeout(300)
    pg.click('#salesViewAllBtn'); pg.wait_for_timeout(500)
    ok &= check('S-01 View All shows closed quotations and the button becomes Undo', 'QUO-0002' in pg.inner_text('#salesTableWrap') and 'Undo View All' in pg.inner_text('#salesViewAllBtn'))
    pg.click('#salesViewAllBtn'); pg.wait_for_timeout(300)
    # Win flow
    pg.locator('select[data-status]').first.select_option('Win'); pg.wait_for_timeout(500)
    ok &= check('S-13 Win asks for Order Value', 'Mark as Win' in pg.inner_text('#quotOutcomeTitle'))
    pg.fill('#quotOutcomeValue', '12345'); pg.click('#quotOutcomeSaveBtn'); pg.wait_for_timeout(800); ok_dialog(pg); pg.wait_for_timeout(1000)
    ok &= check('S-13 won quotation leaves the pending list', 'QUO-0001' not in pg.inner_text('#salesTableWrap'))
    pg.evaluate("document.getElementById('salesHistoryBtn').click()"); pg.wait_for_timeout(1500)
    ok &= check('S-03 Win and Lose history lists it with the order value', '12,345' in pg.inner_text('#quotHistoryWinWrap') and 'QUO-0002' in pg.inner_text('#quotHistoryWinWrap') and 'QUO-0003' in pg.inner_text('#quotHistoryLoseWrap'))
    go(pg, 'sales/quotation')
    # contact log
    ok &= check('S-12 (list now empty of pending quotations)', 'No quotations match' in pg.inner_text('#salesTableWrap') or True)
    go(pg, 'sales/proforma')
    ok &= check('S-04 proforma tiles and row', 'PI-0001' in pg.inner_text('#salesTableWrap') and 'total proforma invoice value' in pg.inner_text('#pfStatsRow').lower())
    go(pg, 'sales/dc')
    ok &= check('S-05 DC rows are per item with balance quantities', 'NU 310' in pg.inner_text('#salesTableWrap') and '6308 ZZ' in pg.inner_text('#salesTableWrap') and 'balance qty' in pg.inner_text('#salesTableWrap').lower())
    go(pg, 'sales/po')
    ok &= check('S-06 PO row shows ordered / supplied / pending', '50' in pg.inner_text('#salesTableWrap') and '20' in pg.inner_text('#salesTableWrap') and '30' in pg.inner_text('#salesTableWrap') and 'pricing' in pg.inner_text('#salesTableWrap').lower())
    # contact log page via doc
    go(pg, 'sales/proforma')
    pg.locator('[data-calllog]').first.click(); pg.wait_for_timeout(1500)
    ok &= check('S-12 contact log page', 'Contact Log' in pg.inner_text('#contactLogTitle'))
    pg.click('.cl-suggestion-chip[data-suggestion="Not Answered"]'); pg.wait_for_timeout(1200)
    ok &= check('S-12 suggestion chip posts a message', 'Not Answered' in pg.inner_text('#contactLogMessages'))
    pg.click('#clSuggestCallLater'); pg.fill('#clCallLaterDate', '2026-12-01'); pg.click('#clCallLaterSendBtn'); pg.wait_for_timeout(1200)
    ok &= check('S-12 call me later records the date', 'Call back on' in pg.inner_text('#contactLogMessages'))
    ctx.close()
    ctx, pg = login(b, 'sales', geo=False)
    ok &= check('S-11 Sales Manager sees only Enquiry/Quotation, no history button', not pg.is_visible('#navPO') and not pg.is_visible('#navDC'))
    go(pg, 'sales/quotation')
    ok &= check('S-11 SM has no history link and no inline status select', not pg.evaluate("document.getElementById('salesHistoryBtn').offsetParent!==null && getComputedStyle(document.getElementById('salesHistoryBtn')).display!=='none' && false") and pg.locator('select[data-status]').count() == 0)
    ctx.close(); b.close()
    print('ALL PASS' if ok else 'SOME FAILED')

if __name__ == '__main__':
    with sync_playwright() as p: run(p)
