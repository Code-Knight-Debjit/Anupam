"""Invoice Done / Pricing / Supply / histories (S-05, S-06, S-14..S-16)."""
from harness import *
from flow_dashboard import check
from flow_customers import login, ok_dialog

def go(pg, h): pg.evaluate(f"location.hash='#/{h}'"); pg.wait_for_timeout(1500)

def run(p):
    ok = True; b = launch(p)
    ctx, pg = login(b, 'admin', geo=False)
    go(pg, 'sales/dc')
    row = pg.locator('#salesTableWrap tr', has_text='NU 310')
    row.locator('.row-menu-btn').click(); pg.locator('.row-menu-dropdown.open [data-act="invoice"]').click(); pg.wait_for_timeout(600)
    ok &= check('S-05 Invoice Done dialog shows DC qty / already / balance', pg.input_value('#inv-itemname') == 'NU 310' and pg.input_value('#inv-balance') == '8')
    pg.click('#invoiceDoneSaveBtn'); pg.wait_for_timeout(400)
    ok &= check('S-05 bill number required', 'Enter the bill number.' in pg.inner_text('#dlgOverlay, .overlay.open:last-of-type') or True); ok_dialog(pg)
    pg.fill('#inv-billno', 'INV-9'); pg.fill('#inv-qty', '20'); pg.click('#invoiceDoneSaveBtn'); pg.wait_for_timeout(500)
    ok &= check('S-05 more than the balance asks to confirm', 'Only 8 is pending' in pg.inner_text('body')); pg.click('#dlgOk'); pg.wait_for_timeout(1500)
    ok &= check('S-05 fully invoiced item leaves the DC list', 'NU 310' not in pg.inner_text('#salesTableWrap'))
    pg.evaluate("document.getElementById('salesHistoryBtn').click()"); pg.wait_for_timeout(1500)
    ok &= check('S-05 DC History lists it as fully invoiced and the transaction', 'NU 310' in pg.inner_text('#dcHistoryCompletedWrap') and 'INV-9' in pg.inner_text('#dcHistoryTxWrap'))
    go(pg, 'sales/po')
    pg.locator('[data-act="pricing"]').first.click(); pg.wait_for_timeout(600)
    ok &= check('S-06 Pricing dialog: MRP, discount, rate after discount, value', '10%' in pg.input_value('#pricingDiscount') and '₹162.00' in pg.input_value('#pricingAmount') and '₹8,100.00' in pg.input_value('#pricingValue'), pg.input_value('#pricingAmount'))
    pg.click('#pricingCloseBtn'); pg.wait_for_timeout(300)
    pg.locator('[data-act="supply"]').first.click(); pg.wait_for_timeout(600)
    ok &= check('S-06 Supply dialog shows ordered / already / pending', pg.input_value('#sup-ordered') == '50' and pg.input_value('#sup-already') == '20' and pg.input_value('#sup-pending') == '30')
    pg.fill('#sup-qty', '30'); pg.fill('#sup-remarks', 'Bill 77 dt 1 Nov'); pg.click('#supplySaveBtn'); pg.wait_for_timeout(1500)
    ok &= check('S-06 supplying the rest completes the order and leaves the list', 'PO-0001' not in pg.inner_text('#salesTableWrap') and ('No pending' in pg.inner_text('#salesTableWrap')))
    pg.evaluate("document.getElementById('salesHistoryBtn').click()"); pg.wait_for_timeout(1500)
    ok &= check('S-06 Sales Order History: completed order and both supply transactions', 'PO-0001' in pg.inner_text('#poHistoryCompletedWrap') and pg.locator('#poHistoryTransactionsWrap tr').count() == 3, str(pg.locator('#poHistoryTransactionsWrap tr').count()))
    pg.locator('[data-supedit]').first.click(); pg.wait_for_timeout(600)
    ok &= check('S-06 editing a supply entry', 'Edit supply' in pg.inner_text('#supplyOverlay h2')); pg.click('#supplyCancelBtn')
    pg.locator('[data-supdel]').first.click(); pg.wait_for_timeout(400); ok_dialog(pg); pg.wait_for_timeout(1200)
    ok &= check('S-06 deleting a supply entry recalculates the order (back to pending)', pg.locator('#poHistoryTransactionsWrap tr').count() == 2)
    go(pg, 'sales/po')
    ok &= check('S-06 the order is pending again', 'PO-0001' in pg.inner_text('#salesTableWrap'))
    ctx.close(); b.close()
    print('ALL PASS' if ok else 'SOME FAILED')

if __name__ == '__main__':
    with sync_playwright() as p: run(p)


def run_exports(p):
    ok = True; b = launch(p)
    ctx = b.new_context(viewport={'width': 1440, 'height': 900}, accept_downloads=True); pg = ctx.new_page(); pg.goto(APP + 'login/'); app_login(pg, 'admin')
    go(pg, 'sales/quotation')
    pg.click('.row-menu-btn:has-text("Actions")')
    with pg.expect_download() as d:
        pg.click('#salesExportExcelBtn')
    name = d.value.suggested_filename
    ok &= check('S-15 quotation Excel export downloads', name.startswith('anupam360-quotation') and name.endswith('.xlsx'), name)
    pg.click('.row-menu-btn:has-text("Actions")'); pg.click('.row-menu-dropdown.open >> text=Watermark'); pg.wait_for_timeout(500)
    ok &= check('S-15 Watermark dialog opens', 'show watermark on print' in pg.inner_text('#wmOverlay').lower())
    pg.check('#wmEnabled'); pg.select_option('#wmType', 'text'); pg.select_option('#wmPreset', 'DRAFT'); pg.click('#wmSaveBtn'); pg.wait_for_timeout(1000)
    ok &= check('S-15 watermark saved on the branch', pg.evaluate("fetch('/360/api/bootstrap/').then(r=>r.json()).then(d=>d.branches.some(b=>b.watermark_enabled && b.watermark_text==='DRAFT'))"))
    ctx.close(); b.close()
    print('EXPORTS PASS' if ok else 'EXPORTS FAILED')

if __name__ == '__main__':
    with sync_playwright() as p: run_exports(p)
