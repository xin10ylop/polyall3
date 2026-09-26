"""Validate the Jev toxicity gate on REAL farmer fills: per-market 30-day markout for two non-weather farmers,
then Jev-score each market and compare adverse selection for PASS vs FAIL markets."""
import sys, json, time, os, collections
sys.path.insert(0,'/home/user/polyall3')
exec(open('farmer_markout.py').read().split("for w in sys.argv[1].split(','):")[0].replace("DAYS=float(sys.argv[2]) if len(sys.argv)>2 else 7","DAYS=30"))
from pmbot.jev import ToxicityCache, is_safe
from pmbot.config import CFG
os.environ['OPENROUTER_API_KEY']=open('.env').read().split('=',1)[1].strip()
from concurrent.futures import ThreadPoolExecutor
per=collections.defaultdict(lambda:{'pnl':0.0,'vol':0.0,'n':0,'q':''})
for w in ['0x1ef01de817862024966e8242e923a63c61f9e28e','0xea7f65a8fef1f22c99e760a723080f149f8db855']:
    since=int(time.time()-30*86400); tr=user_trades(w,since)
    toks=sorted({t['asset'] for t in tr}); cids=sorted({t['conditionId'] for t in tr})
    res={}
    with ThreadPoolExecutor(8) as ex:
        for x in ex.map(resolution,cids): res.update(x)
    need=[t for t in toks if t not in res]
    with ThreadPoolExecutor(8) as ex: px=dict(zip(need,ex.map(cur_price,need)))
    px.update(res)
    for t in tr:
        v=px.get(t['asset'])
        if v is None: continue
        sz=float(t['size']); p=float(t['price']); sgn=1 if t['side']=='BUY' else -1
        d=per[t['conditionId']]; d['pnl']+=sgn*(v-p)*sz; d['vol']+=p*sz; d['n']+=1; d['q']=t['title']
print('markets',len(per))
json.dump(per,open('data/gate_per_market.json','w'))
tc=ToxicityCache('data/jev_tox_gate.json',max_age_h=1e6)
def score(item):
    cid,d=item
    m=get(f"{CLOB}/markets/{cid}") or {}
    t=tc.get(cid,d['q'],m.get('description',''),m.get('end_date_iso'))
    return cid,t
with ThreadPoolExecutor(8) as ex:
    for cid,t in ex.map(score,list(per.items())): per[cid]['tox']=t
tc.save()
import numpy as np
for lab,sel in [('PASS',lambda t: t is not None and is_safe(t,CFG)),('FAIL',lambda t: t is None or not is_safe(t,CFG))]:
    x=[d for d in per.values() if sel(d.get('tox'))]
    pnl=sum(d['pnl'] for d in x); vol=sum(d['vol'] for d in x)
    print(f"jev {lab}: markets={len(x)} fills={sum(d['n'] for d in x)} fill vol=${vol:,.0f} markout=${pnl:,.0f}  markout per $ filled={pnl/max(vol,1):+.4f}")
worst=sorted(per.values(),key=lambda d:d['pnl'])[:12]
print('\nworst markets:')
for d in worst:
    t=d.get('tox') or {}
    print(f"  {d['pnl']:9.0f}  {'PASS' if t and is_safe(t,CFG) else 'FAIL'} rt={t.get('realtime',0):.2f} rs={t.get('reveal_soon',0):.2f} ns={t.get('news_speed',0):.2f} | {d['q'][:70]}")
import jev as J
