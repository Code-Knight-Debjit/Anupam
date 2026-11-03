"""Reports flows: every tab opens without errors, and the key numbers match the seed."""
from harness import *
from flow_dashboard import check
from flow_customers import login, ok_dialog

def go(pg, h): pg.evaluate(f"location.hash='#/{h}'"); pg.wait_for_timeout(2500)

def run(p):
    ok = True; b = launch(p)
    ctx, pg = login(b, 'admin', geo=False)
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    go(pg, 'reports')
    for tab in ('sales', 'customers', 'gap', 'userperf', 'salesx', 'custx', 'payments', 'interactions'):
        pg.click(f'#reportTabs [data-rtab="{tab}"]'); pg.wait_for_timeout(1500)
        txt = pg.inner_text('#reportBody')
        ok &= check(f'F tab {tab} renders', len(txt) > 20 and 'Something went wrong' not in txt, txt[:120].replace('\n', ' | '))
    ok &= check('F no console errors', not errs, '; '.join(errs[:3]))
    # drill-downs and exports
    import subprocess
    pg.click('#reportTabs [data-rtab="sales"]'); pg.wait_for_timeout(1200)
    pg.click('[data-sp="enquiry"]'); pg.wait_for_timeout(500)
    ok &= check('F Sales Performance drill: enquiries listed', 'Enquiries' in pg.inner_text('#drillTitle') and pg.locator('#drillTable tr').count() == 3, pg.inner_text('#drillSub'))
    with pg.expect_download() as dl: pg.click('#drillExcelBtn')
    ok &= check('F drill Excel download', dl.value.suggested_filename.endswith('.xlsx'), dl.value.suggested_filename)
    pg.click('#drillDoneBtn'); pg.wait_for_timeout(300)
    with pg.expect_download() as dl: pg.click('#reportExportExcelBtn')
    ok &= check('F Export Excel', dl.value.suggested_filename.startswith('anupam360-sales-performance'), dl.value.suggested_filename)
    with pg.expect_download() as dl: pg.click('#reportExportPdfBtn')
    path = dl.value.path(); data = open(path, 'rb').read(); txt = subprocess.run(['pdftotext', '-layout', path, '-'], capture_output=True, text=True).stdout
    ok &= check('F Export PDF has the letterhead, title block and cards', data[:4] == b'%PDF' and 'Sales Performance' in txt and 'ENQUIRIES' in txt and 'Generated' in txt, txt[:300])
    with pg.expect_popup() as pop: pg.click('#reportPrintBtn')
    pop.value.wait_for_load_state(); ok &= check('F Print opens the branded print page', 'Sales Performance' in pop.value.inner_text('body') and 'Generated' in pop.value.inner_text('body')); pop.value.close()
    pg.click('#view-reports .select-row button:has-text("Watermark")'); pg.wait_for_timeout(400)
    ok &= check('F Watermark dialog opens', pg.locator('#wmOverlay.open').count() == 1); pg.click('#wmCancelBtn')
    pg.click('#reportTabs [data-rtab="userperf"]'); pg.wait_for_timeout(800); pg.select_option('#upRange', '90'); pg.wait_for_timeout(2000)
    ok &= check('F User Performance 90 days: calls and visits counted', pg.inner_text('#reportBody .dash-card.drillable .n') != '0')
    pg.click('#reportBody .dash-card.drillable'); pg.wait_for_timeout(500)
    ok &= check('F Calls & visits drill lists the customers', 'Calls & visits' in pg.inner_text('#drillTitle') and pg.locator('#drillTable tr').count() > 2, pg.inner_text('#drillSub')); pg.click('#drillCloseBtn')
    with pg.expect_download() as dl: pg.click('#reportExportExcelBtn')
    ok &= check('F User Performance Excel (several sheets)', dl.value.suggested_filename.startswith('anupam360-user-performance'))
    with pg.expect_download() as dl: pg.click('#reportExportPdfBtn')
    txt = subprocess.run(['pdftotext', '-layout', dl.value.path(), '-'], capture_output=True, text=True).stdout
    ok &= check('F User Performance PDF has attendance calendars and the legend', 'attendance' in txt and 'Present (late)' in txt, txt[:200])
    ctx.close()
    ctx, pg = login(b, 'sales', geo=False); go(pg, 'reports')
    ok &= check('F Sales Manager: Sales Performance and Customer Activity tabs are hidden', not pg.is_visible('#reportTabs [data-rtab="sales"]') and not pg.is_visible('#reportTabs [data-rtab="customers"]') and pg.is_visible('#reportTabs [data-rtab="gap"]'))
    ok &= check('F ...and the user picker is not offered', pg.locator('#gapUser, #rptUser').count() == 0); ctx.close()
    ctx, pg = login(b, 'staff', geo=False); go(pg, 'reports'); pg.click('#reportTabs [data-rtab="userperf"]'); pg.wait_for_timeout(1500)
    ok &= check('F Branch Staff sees only themselves in User Performance', pg.inner_text('#reportBody .dash-card .n') == '1' and pg.locator('#upUser').count() == 0)
    ctx.close(); b.close()
    print('REPORTS PASS' if ok else 'REPORTS FAILED')

if __name__ == '__main__':
    with sync_playwright() as p: run(p)
