"""Playwright helpers for the Anupam 360 <-> contact_management.html parity checks (see docs/360/PARITY_PLAN.md)."""
import os, json
from playwright.sync_api import sync_playwright
S=os.environ.get('PARITY_DIR','/tmp/anupam-parity')
os.makedirs(S+'/shots',exist_ok=True)
REF=os.environ.get('PARITY_REF','http://127.0.0.1:8020/contact_management.html')
APP=os.environ.get('PARITY_APP','http://127.0.0.1:8010/360/')
PW='secret-pw-1'  # password of the 4 test users in the throw-away 360 database
def launch(p):
    return p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox'])
def ref_page(b, w=1440, h=900):
    st=f'{S}/ref_state.json'
    ctx=b.new_context(viewport={'width':w,'height':h}, storage_state=st if os.path.exists(st) else None)
    pg=ctx.new_page(); pg.goto(REF); pg.wait_for_timeout(1200)
    return ctx,pg
def app_page(b, user='admin', w=1440, h=900):
    ctx=b.new_context(viewport={'width':w,'height':h}); pg=ctx.new_page()
    pg.goto(APP+'login/'); pg.wait_for_timeout(500)
    return ctx,pg
def app_login(pg, user='admin'):
    pg.fill('#li-user',user); pg.click('#useridSubmit'); pg.fill('#li-pass',PW); pg.click('#pinSubmit'); pg.wait_for_timeout(2000)
OUTLINE_JS = """() => {
  const vis = e => e.offsetParent !== null || getComputedStyle(e).position==='fixed';
  const root = document.querySelector('.view.active') || document.querySelector('#app-view') || document.body;
  const out = [];
  root.querySelectorAll('h1,h2,h3,.section-label,.brand-eyebrow,label,button,th,select,input,textarea,.stat,.dash-tile,.tag,a.btn').forEach(e=>{
    if(!vis(e)) return;
    let t=(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,60);
    const tag=e.tagName.toLowerCase();
    if(tag==='select') t='[select:'+(e.options.length)+'] '+(e.options[0]?e.options[0].text.slice(0,30):'');
    if(tag==='input') t='[input:'+e.type+'] '+(e.placeholder||'');
    if(tag==='textarea') t='[textarea] '+(e.placeholder||'');
    out.push(tag+' | '+t);
  });
  return out;
}"""
def outline(pg): return pg.evaluate(OUTLINE_JS)
def ref_login(pg, user='admin', pw='secret1'):
    pg.wait_for_timeout(300)
    if not pg.is_visible('#useridInput'):
        who=pg.evaluate("currentUser ? currentUser.userId : ''")
        if who==user: return
        pg.click('#logoutBtn'); pg.wait_for_timeout(300); pg.click('#dlgButtons button:last-child'); pg.wait_for_timeout(500)
    if pg.is_visible('#useridInput'):
        pg.fill('#useridInput',user); pg.click('#useridSubmit'); pg.wait_for_timeout(300)
        pg.fill('#pinInput',pw); pg.click('#pinSubmit'); pg.wait_for_timeout(1200)
def ref_open(p, user='admin', w=1440, h=900):
    b=launch(p); ctx,pg=ref_page(b,w,h); ref_login(pg,user); return b,ctx,pg
