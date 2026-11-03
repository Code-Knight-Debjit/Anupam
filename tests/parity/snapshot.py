import sys
from harness import *
VIEWS=['dashboard','tasks','callinglist','attendance','customers','map','sales:enquiry','sales:quotation','sales:proforma','sales:dc','sales:po','payments','labels','reports','managelists','import','backup','users','branches']
which=sys.argv[1]; user=sys.argv[2] if len(sys.argv)>2 else 'admin'
if len(sys.argv)>3: VIEWS=sys.argv[3:]
with sync_playwright() as p:
    if which=='ref':
        b,ctx,pg=ref_open(p,user)
    else:
        b=launch(p); ctx,pg=app_page(b); app_login(pg,user)
    for v in VIEWS:
        name=v.replace(':','_')
        if which=='ref':
            sel=f".nav-item[data-view={v.split(':')[0]}]"+(f"[data-subtab={v.split(':')[1]}]" if ':' in v else '')
            pg.click(sel)
        else:
            pg.evaluate(f"location.hash='#/{v.replace(':','/')}'")
        pg.wait_for_timeout(1000)
        pg.screenshot(path=f"{S}/shots/{which}_{user}_{name}.png", full_page=True)
        open(f"{S}/shots/{which}_{user}_{name}.txt",'w').write('\n'.join(outline(pg)))
    b.close()
