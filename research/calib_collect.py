"""Unbiased calibration dataset for non-sports binary markets: hourly price history over each market's life."""
from pm import *
import json, glob, os, sys, datetime as dt, collections, random
from concurrent.futures import ThreadPoolExecutor
def P(s): return dt.datetime.fromisoformat(s.replace('Z','+00:00').replace(' ','T')) if s else None
def cat(m):
    q=m['question']; ft=m.get('feeType') or 'nofee'
    if 'Up or Down' in q: return 'updown'
    if ft.startswith('sports') or m.get('sportsMarketType') or (ft=='zero_fees'): return 'sports'
    if ft=='weather_fees': return 'weather'
    return ft
U=[]
for f in sorted(glob.glob('data/census_*.json')):
    for m in json.load(open(f)):
        c=cat(m)
        if c in ('updown','sports','weather'): continue
        if float(m.get('volumeNum') or 0)<5000: continue
        try: oc=json.loads(m['outcomes'])
        except Exception: continue
        if oc!=['Yes','No']: continue
        w=winner_index(m)
        if w is None: continue
        m['cat']=c; m['yes_won']=1 if w==0 else 0; U.append(m)
print('universe',len(U),collections.Counter(m['cat'] for m in U).most_common())
os.makedirs('data/calib',exist_ok=True)
def fetch(m):
    fn=f"data/calib/{m['id']}.json"
    if os.path.exists(fn): return 0
    tok=json.loads(m['clobTokenIds'])[0]
    c=P(m.get('createdAt')) or P(m.get('startDate')); e=P(m.get('closedTime')) or P(m['endDate'])
    if not c or not e: return 0
    c=max(c, e-dt.timedelta(days=60))
    h=[]; t=int(c.timestamp())
    while t<e.timestamp():
        t2=min(int(e.timestamp())+3600, t+15*86400)
        r=get(f"{CLOB}/prices-history",dict(market=tok,startTs=t,endTs=t2,fidelity=60))
        h+=(r or {}).get('history',[]); t=t2
    json.dump(dict(m=m,h=h),open(fn,'w')); return 1
with ThreadPoolExecutor(8) as ex:
    n=0
    for i,r in enumerate(ex.map(fetch,U)):
        n+=r
        if i%500==0: print(i,n,flush=True)
print('done')
