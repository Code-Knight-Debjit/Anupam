import re,sys,glob,os
S=os.environ.get('PARITY_DIR','/tmp/anupam-parity')
def norm(t):
    t=re.sub(r'[^\w\s&/%+.-]','',t.lower()); t=re.sub(r'\b\d+\b','#',t); return re.sub(r'\s+',' ',t).strip()
def load(f):
    s=set()
    for ln in open(f).read().splitlines():
        tag,_,t=ln.partition(' | ')
        if tag in('h1','h2','h3','button','th','label','.section-label','div','span','p','a') or tag.startswith('select') or tag=='input' or tag=='textarea':
            n=norm(t)
            if n: s.add((tag if tag in('h1','h2','h3','button','th','label') else 'f',n))
    return s
tot_m=0
USER=[a for a in sys.argv[1:] if not a.startswith('-')]
USER=USER[0] if USER else 'admin'
for rf in sorted(glob.glob(f'{S}/shots/ref_{USER}_*.txt')):
    name=os.path.basename(rf)[len(USER)+5:-4]; af=f'{S}/shots/app_{USER}_{name}.txt'
    r,a=load(rf),load(af); miss=sorted(r-a); extra=sorted(a-r)
    tot_m+=len(miss)
    print(f'## {name}: ref={len(r)} app={len(a)} missing_in_app={len(miss)} extra_in_app={len(extra)}')
    if '-v' in sys.argv:
        print('  MISSING:', '; '.join(f'{k}:{v}' for k,v in miss)[:900])
        print('  EXTRA  :', '; '.join(f'{k}:{v}' for k,v in extra)[:500])
print('TOTAL missing',tot_m)
