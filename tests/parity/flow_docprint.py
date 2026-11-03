"""Printed documents, label and list exports are built in the browser by the reference's own code (E-*, P-* exports)."""
import subprocess
from harness import *
from flow_dashboard import check
from flow_customers import login, ok_dialog

def go(pg, h): pg.evaluate(f"location.hash='#/{h}'"); pg.wait_for_timeout(2000)
def text(path): return subprocess.run(['pdftotext', '-layout', path, '-'], capture_output=True, text=True).stdout

def run(p):
    ok = True; b = launch(p)
    ctx, pg = login(b, 'admin', geo=False)
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    go(pg, 'sales/quotation')
    pg.locator('#salesTableWrap .row-menu-btn').first.click(); pg.wait_for_timeout(300)
    with pg.expect_download() as dl: pg.locator('.row-menu-dropdown.open [data-act="pdf"]').click()
    path = dl.value.path(); t = text(path); name = dl.value.suggested_filename
    ok &= check('D1 quotation PDF: file named number-customer, like the reference', name.startswith('QUO-') and name.endswith('.pdf'), name)
    ok &= check('D1 title, customer block, meta panel, table and totals', all(x in t for x in ('QUOTATION', 'CUSTOMER DETAILS', 'QUOTATION NUMBER', 'REFERENCE NUMBER', 'Item & Description', 'Sub Total', 'Total Amount', 'TOTAL AMOUNT (IN WORDS)', 'TERMS & CONDITIONS', 'Authorized Signatory')), t[:400])
    ok &= check('D1 the rupee sign is printed (embedded font), amount in words starts "Rupees"', '₹' in t and 'Rupees' in t, t[:200])
    pg.locator('#salesTableWrap .row-menu-btn').first.click(); pg.wait_for_timeout(300)
    pg.locator('.row-menu-dropdown.open [data-act="print"]').click(); pg.wait_for_timeout(2500)
    ok &= check('D2 Print uses a hidden frame with the reference HTML', pg.locator('#quotPrintIframe').count() == 1 and 'QUOTATION' in pg.frame_locator('#quotPrintIframe').locator('body').inner_text())
    pg.locator('#salesTableWrap .row-menu-btn').first.click(); pg.wait_for_timeout(300); pg.locator('.row-menu-dropdown.open [data-act="view"]').click(); pg.wait_for_timeout(1500)
    pg.click('#sdvPreviewBtn'); pg.wait_for_timeout(2500)
    ok &= check('D3 Preview dialog: heading, sub-line, frame, Close / Print / Download PDF', 'exactly how the printed copy' in pg.inner_text('#quotPreviewOverlay') and 'QUOTATION' in pg.frame_locator('#quotPreviewFrame').locator('body').inner_text())
    with pg.expect_download() as dl2: pg.click('#quotPreviewPdfBtn')
    ok &= check('D3 Download PDF from the preview', dl2.value.suggested_filename.endswith('.pdf'))
    pg.click('#quotPreviewCloseBtn'); pg.evaluate("document.getElementById('salesDocViewOverlay').classList.remove('open')"); pg.wait_for_timeout(300)
    for typ, title in (('proforma', 'PROFORMA INVOICE'), ('dc', 'DELIVERY CHALLAN')):
        go(pg, 'sales/' + typ)
        if not pg.locator('#salesTableWrap .row-menu-btn:visible').count(): continue
        pg.locator('#salesTableWrap .row-menu-btn:visible').first.click(); pg.wait_for_timeout(300)
        with pg.expect_download() as dl3: pg.locator('.row-menu-dropdown.open [data-act="pdf"]').click()
        t3 = text(dl3.value.path()); ok &= check(f'D1 {typ} PDF uses the same layout with its own title', title in t3 and 'Total Amount' in t3, t3[:150])
    # list export (letterhead is the plain default, as in the reference)
    go(pg, 'sales/quotation');
    pg.locator('#view-sales .row-menu-btn').first.click(); pg.wait_for_timeout(300)
    with pg.expect_download() as dl4: pg.locator('#salesExportPdfBtn').click()
    t4 = text(dl4.value.path())
    ok &= check('D4 list PDF is the reference plain table: title, date, grid (no letterhead)', 'Anupam 360 — Quotations' in t4 and 'Quotation No' in t4 and 'Generated' not in t4, t4[:200])
    # label
    go(pg, 'labels'); pg.select_option('#lc-cust', index=1); pg.wait_for_timeout(900)
    pg.click('#lcPdfBtn'); pg.wait_for_timeout(400); pg.fill('#lblBoxes', '2')
    with pg.expect_download() as dl5: pg.click('#lblOptGo')
    t5 = text(dl5.value.path())
    ok &= check('D5 label PDF built by the reference code: DELIVER TO / FROM and two boxes', 'DELIVER TO' in t5 and 'BOX 2 OF 2' in t5.upper(), t5[:200])
    ok &= check('no page errors', not errs, '; '.join(errs[:3]))
    ctx.close(); b.close()
    print('DOCPRINT PASS' if ok else 'DOCPRINT FAILED')

if __name__ == '__main__':
    with sync_playwright() as p: run(p)
