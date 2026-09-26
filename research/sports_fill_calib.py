"""Calibration of actual taker BUY fills in sports moneyline markets, by price bucket (net of current fees)."""
from pm import *
import json, glob, datetime as dt, collections, random, numpy as np, os, pickle
from concurrent.futures import ThreadPoolExecutor
ms=[]
for f in sorted(glob.glob('data/census_2026-09-0*.json'))+sorted(glob.glob('data/census_2026-09-1*.json'))+sorted(glob.glob('data/census_2026-09-2*.json')):
    for m in json.load(open(f)):
        if m.get('sportsMarketType') in ('moneyline',) and float(m.get('volumeNum') or 0)>5000 and winner_index(m) is not None:
            ms.append(m)
random.seed(7); ms=random.sample(ms,min(1500,len(ms)))
print('markets',len(ms))
def get_tr(m):
    fn=f"data/tr_{m['id']}.pkl"
    if os.path.exists(fn): return m,pickle.load(open(fn,'rb'))
    tr=trades(m['conditionId'],max_pages=25)
    pickle.dump(tr,open(fn,'wb')); return m,tr
rows=[]
with ThreadPoolExecutor(8) as ex:
    for m,tr in ex.map(get_tr,ms):
        toks=json.loads(m['clobTokenIds']); w=winner_index(m)
        rate=m.get('feeRate') or 0
        gst=m.get('gameStartTime') or m.get('eventStartTime')
        try: gs=dt.datetime.fromisoformat(gst.replace('Z','+00:00').replace(' ','T')).timestamp() if gst else None
        except Exception: gs=None
        for t in tr:
            if t['side']!='BUY' or t['asset'] not in toks: continue
            won=1 if toks.index(t['asset'])==w else 0
            p=t['price']; fee=rate*p*(1-p)
            rows.append((m['id'],m.get('feeType'),p,t['size'],won,fee,(t['timestamp']-gs)/60 if gs else None, m.get('event_slug','').split('-')[0]))
import pandas as pd
df=pd.DataFrame(rows,columns=['mid','ft','p','size','won','fee','min_from_start','lg'])
df['usd']=df.p*df['size']; df['pnl']=df['size']*(df.won-df.p-df.fee)
df.to_pickle('data/sports_fills.pkl')
bins=[0,0.05,0.1,0.2,0.35,0.5,0.65,0.8,0.9,0.95,0.97,0.98,0.99,0.995,1.0]
df['b']=pd.cut(df.p,bins)
df['phase']=np.where(df.min_from_start.isna(),'?',np.where(df.min_from_start<0,'pre','live'))
for ph in ['pre','live']:
    d=df[df.phase==ph]
    print(f'\n=== {ph}-game taker BUY fills: n={len(d)} usd={d.usd.sum():,.0f}')
    g=d.groupby('b',observed=True).agg(n=('p','size'),usd=('usd','sum'),avg_p=('p','mean'),winrate=('won','mean'),pnl=('pnl','sum'),mk=('mid','nunique'))
    g['roi']=g.pnl/g.usd
    print(g.round(4).to_string())
