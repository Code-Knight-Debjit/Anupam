"""Print Label flows (L-01..): the custom label panel, the options dialog, the server-built PDF."""
from harness import *
from flow_dashboard import check
from flow_customers import login, ok_dialog

def go(pg, h): pg.evaluate(f"location.hash='#/{h}'"); pg.wait_for_timeout(1500)

def run(p):
    ok = True; b = launch(p)
    ctx, pg = login(b, 'admin', geo=False)
    go(pg, 'labels')
    ok &= check('L page has the panel fields', all(pg.locator(f'#{i}').count() == 1 for i in ('lc-cust', 'lc-person', 'lc-name', 'lc-attn', 'lc-phone', 'lc-addr', 'lc-area', 'lc-city', 'lc-pin', 'lc-transport', 'lc-branch', 'lcPrintBtn', 'lcPdfBtn')))
    pg.click('#lcPdfBtn'); pg.wait_for_timeout(400)
    ok &= check('L name is required', 'Enter who the label is for.' in pg.inner_text('body')); ok_dialog(pg)
    pg.select_option('#lc-cust', label='Sundaram Fasteners Ltd, Plant 3, Peenya Industrial Area'); pg.wait_for_timeout(1000)
    ok &= check('L picking a customer fills name, address, area, "city, state", PIN', pg.input_value('#lc-name') == 'Sundaram Fasteners Ltd' and pg.input_value('#lc-area') == 'Peenya Industrial Area' and pg.input_value('#lc-city') == 'Bengaluru, Karnataka' and pg.input_value('#lc-pin') == '560058', pg.input_value('#lc-city'))
    ok &= check('L ...but not the person or phone', pg.input_value('#lc-attn') == '' and pg.input_value('#lc-phone') == '')
    ok &= check('L people list loaded', pg.locator('#lc-person option').count() > 1)
    pg.select_option('#lc-person', index=1); pg.wait_for_timeout(300); person = pg.input_value('#lc-attn')
    ok &= check('L picking a person fills Attn and phone', pg.input_value('#lc-attn') != '' and pg.input_value('#lc-phone') != '')
    pg.click('#lcPdfBtn'); pg.wait_for_timeout(600)
    ok &= check('L options dialog (PDF mode) defaults: A5, A4 sheet, 150 %, 1 box', pg.inner_text('#lblOptTitle') == 'Download label PDF' and pg.input_value('#lblSizeSel') == 'a5' and pg.input_value('#lblPaper') == 'a4' and pg.input_value('#lblFrom') == '1.5' and pg.input_value('#lblBoxes') == '1')
    ok &= check('L four label sizes offered', pg.locator('#lblSizeSel option').count() == 4)
    pg.click('#lblOptCancel'); pg.wait_for_timeout(300)
    pg.click('#lcPrintBtn'); pg.wait_for_timeout(500)
    ok &= check('L print mode title', pg.inner_text('#lblOptTitle') == 'Print label' and pg.inner_text('#lblOptGo') == 'Print'); pg.click('#lblOptCancel')
    pg.click('#lcPdfBtn'); pg.wait_for_timeout(400)
    pg.fill('#lblBoxes', '3'); pg.check('#lblShowAttn')
    with pg.expect_download() as dl: pg.click('#lblOptGo')
    d = dl.value; path = d.path(); data = open(path, 'rb').read()
    ok &= check('L Download PDF gives a PDF', data[:4] == b'%PDF', d.suggested_filename)
    # the PDF text: customer, area and (checked) Attn are printed, phone is not
    import subprocess
    try:
        txt = subprocess.run(['pdftotext', '-layout', path, '-'], capture_output=True, text=True).stdout
        ok &= check('L PDF prints the deliver-to name, area, PIN and the person', 'Sundaram Fasteners Ltd' in txt and 'Peenya Industrial Area' in txt and '560058' in txt and ('Attn: ' + person) in txt, txt[:900])
        ok &= check('L unchecked phone is not printed', '9840000' not in txt)
        ok &= check('L one label per box (3)', txt.count('Sundaram Fasteners Ltd') == 3, str(txt.count('Sundaram Fasteners Ltd')))
    except FileNotFoundError:
        print('SKIP pdftotext not installed')
    ctx.close()
    ctx, pg = login(b, 'sales', geo=False)
    ok &= check('L Sales Manager has no Print Label entry', not pg.is_visible('#navLabels')); ctx.close()
    b.close()
    print('LABELS PASS' if ok else 'LABELS FAILED')

if __name__ == '__main__':
    with sync_playwright() as p: run(p)
