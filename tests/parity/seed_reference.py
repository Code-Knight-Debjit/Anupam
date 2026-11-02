from harness import *
import json
seed=json.load(open(f'{S}/seed.json'))
with sync_playwright() as p:
    b=launch(p); ctx,pg=ref_page(b)
    pg.evaluate("""async (seed)=>{ const jobs=[]; BACKUP_ITEMS.forEach(([k,get,set,sk])=>{ if(seed[k]===undefined) return; set(seed[k]); jobs.push(setShared(sk,get())); }); await Promise.all(jobs); }""", seed)
    ctx.storage_state(path=f'{S}/ref_state.json'); b.close()
    ctx2,pg=ref_page(launch(p) if False else b) if False else (None,None)
with sync_playwright() as p:
    b=launch(p); ctx,pg=ref_page(b)
    pg.screenshot(path=f'{S}/shots/ref_cust_seeded.png'); print(pg.evaluate("companies.length")); b.close()
