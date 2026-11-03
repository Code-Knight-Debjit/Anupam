"""Compares the geometry and key computed styles of every element that has an id in the active view of BOTH apps
(same data, same viewport) — catches missed inline styles / wrong structure that a text outline cannot.
usage: layout_diff.py <user> <view[:subtab]> [tolerance_px]"""
import sys
from harness import *

JS = """() => {
  const root = document.querySelector('.view.active') || document.body;
  const out = {};
  const vis = e => !!(e.offsetParent || e.getClientRects().length);
  root.querySelectorAll('[id]').forEach(e => {
    if (!vis(e)) return;
    const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
    out[e.id] = {x: Math.round(r.x), y: Math.round(r.y + window.scrollY), w: Math.round(r.width), h: Math.round(r.height),
      fs: cs.fontSize, fw: cs.fontWeight, d: cs.display, c: cs.color, bg: cs.backgroundColor, ls: cs.letterSpacing, tt: cs.textTransform};
  });
  return out;
}"""

def collect(p, which, user, view, w=1440, h=900):
    if which == 'ref':
        b, ctx, pg = ref_open(p, user, w, h)
        sel = f".nav-item[data-view={view.split(':')[0]}]" + (f"[data-subtab={view.split(':')[1]}]" if ':' in view else '')
        pg.click(sel)
    else:
        b = launch(p); ctx, pg = app_page(b, w=w, h=h); app_login(pg, user)
        pg.evaluate(f"location.hash='#/{view.replace(':', '/')}'")
    pg.wait_for_timeout(1500)
    data = pg.evaluate(JS); b.close(); return data

if __name__ == '__main__':
    user, view = sys.argv[1], sys.argv[2]
    tol = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    with sync_playwright() as p:
        R = collect(p, 'ref', user, view); A = collect(p, 'app', user, view)
    bad = 0
    # theme fonts make the hero banner a few px taller; compare vertical positions relative to that constant shift
    shifts = sorted(A[k]['y'] - R[k]['y'] for k in R if k in A)
    base = shifts[len(shifts) // 2] if shifts else 0
    for k in R:
        if k not in A: print(f'MISSING id #{k}'); bad += 1; continue
        r, a = R[k], A[k]; d = []
        for f in ('x', 'y', 'w', 'h'):
            delta = (a[f] - r[f]) - (base if f == 'y' else 0)
            if abs(delta) > tol: d.append(f'{f}:{r[f]}->{a[f]}')
        for f in ('fs', 'fw', 'd', 'ls', 'tt'):
            if r[f] != a[f]: d.append(f'{f}:{r[f]}->{a[f]}')
        if d: print(f'#{k}: ' + ', '.join(d)); bad += 1
    extra = [k for k in A if k not in R]
    print(f'{len(R)} ids in reference, {bad} differ' + (f'; extra ids in 360: {extra}' if extra else ''))
