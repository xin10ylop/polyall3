"""Risk backtest for lone quoting in uncontested pools: replay 7 days of real taker trades as if our min-size quotes
(inside the band, top of book) absorbed every one, and mark each fill 24h later (or at the current mid)."""
import json, time, numpy as np
from pm import *
from concurrent.futures import ThreadPoolExecutor
tr=[json.loads(l) for l in open('live/pool_tracker.jsonl')]
first={m['cid']:m for m in tr[0]['m']}
stable=[c for c in first if all(any(m['cid']==c and m['q1']+m['q2']==0 for m in s['m']) for s in tr)]
rm={r['condition_id']:r for r in get(f"{CLOB}/rewards/markets/current") and []}
now=time.time()
def bt(c):
    t=get(f"{DATA}/trades",dict(market=c,limit=500,_=time.time_ns()))
    if not isinstance(t,list): return None
    t=[x for x in t if x['timestamp']>now-7*86400]; t.sort(key=lambda x:x['timestamp'])
    m=get(f"{CLOB}/markets/{c}") or {}
    toks=[k['token_id'] for k in m.get('tokens',[])]
    if len(toks)!=2: return None
    mid=get(f"{CLOB}/midpoint",dict(token_id=toks[0])) or {}
    try: mid_now=float(mid.get('mid'))
    except Exception: return None
    ys=[(x['timestamp'], float(x['price']) if x['asset']==toks[0] else 1-float(x['price']), x) for x in t]
    pnl=0.0; fills=0; size=20.0
    for i,(ts,p,x) in enumerate(ys):
        # taker bought YES at p (lifted asks) -> we'd have sold YES (short) ; taker sold YES -> we bought YES
        taker_buys_yes=(x['asset']==toks[0] and x['side']=='BUY') or (x['asset']==toks[1] and x['side']=='SELL')
        later=[q for (t2,q,_) in ys[i+1:] if t2<=ts+86400]
        mark=later[-1] if later and ts+86400<now else (later[-1] if later else mid_now)
        if ts+86400>now: mark=mid_now
        q=min(size,float(x['size']))
        pnl+= (p-mark)*q if taker_buys_yes else (mark-p)*q
        fills+=1
    days=7
    return dict(cid=c,rate=first[c]['rate'],trades7=len(ys),fills_per_day=fills/days,adverse_per_day=-pnl/days,q=m.get('question','')[:70])
with ThreadPoolExecutor(8) as ex: R=[r for r in ex.map(bt,stable) if r]
adv=np.array([r['adverse_per_day'] for r in R]); rate=np.array([r['rate'] for r in R]); fpd=np.array([r['fills_per_day'] for r in R])
print('pools',len(R),'pool $/day total',round(rate.sum()))
print('simulated fills/day per pool pctiles 50/75/90:',np.percentile(fpd,[50,75,90]).round(2))
print('adverse selection $/day per pool pctiles 50/75/90/99:',np.percentile(adv,[50,75,90,99]).round(2),' total $/day',round(adv.sum(),1))
print('pools where adverse > pool reward:',int((adv>rate).sum()),' reward - adverse (sum) $/day:',round((rate-adv).sum()))
for r in sorted(R,key=lambda r:-r['adverse_per_day'])[:8]: print(f"  adv ${r['adverse_per_day']:6.2f}/d vs pool ${r['rate']:5.0f}/d fills/d {r['fills_per_day']:.1f} | {r['q']}")
json.dump(R,open('data/quiet_risk_bt.json','w'))
