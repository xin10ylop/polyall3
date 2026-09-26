"""Realized returns of ACTUAL taker YES/NO buys in crypto 'above $X on date' markets, by price bucket."""
from pm import *
import json, glob, re, random, os, pickle, numpy as np, pandas as pd, datetime as dt
from concurrent.futures import ThreadPoolExecutor
ms=[]
for f in sorted(glob.glob('data/census_*.json')):
    for m in json.load(open(f)):
        if m.get('feeType')=='crypto_fees_v2' and re.search(r'price of (Bitcoin|Ethereum|Solana|XRP) be above',m['question']) and winner_index(m) is not None and float(m.get('volumeNum') or 0)>1000:
            ms.append(m)
print('strike markets',len(ms))
random.seed(3); ms=random.sample(ms,min(1200,len(ms)))
def gt(m):
    fn=f"data/tr_{m['id']}.pkl"
    if os.path.exists(fn): return m,pickle.load(open(fn,'rb'))
    tr=trades(m['conditionId'],max_pages=20); pickle.dump(tr,open(fn,'wb')); return m,tr
rows=[]
with ThreadPoolExecutor(8) as ex:
    for m,tr in ex.map(gt,ms):
        toks=json.loads(m['clobTokenIds']); w=winner_index(m)
        en=dt.datetime.fromisoformat(m['endDate'].replace('Z','+00:00')).timestamp()
        for t in tr:
            if t['side']!='BUY' or t['asset'] not in toks: continue
            won=1 if toks.index(t['asset'])==w else 0
            p=float(t['price']); fee=0.07*p*(1-p)
            rows.append((m['id'],m['question'][:70],toks.index(t['asset']),p,float(t['size']),won,fee,(en-t['timestamp'])/3600))
df=pd.DataFrame(rows,columns=['mid','q','outcome_idx','p','size','won','fee','hrs_to_end'])
df['ret']=(df.won-df.p-df.fee)/df.p; df['usd']=df.p*df['size']; df['pnl']=df['size']*(df.won-df.p-df.fee)
df.to_pickle('data/crypto_strike_fills.pkl')
df['side']=np.where(df.outcome_idx==0,'YES','NO')
bins=[0,0.05,0.2,0.5,0.8,0.9,0.95,0.97,0.98,0.99,0.995,1]
df['b']=pd.cut(df.p,bins)
for side in ['YES','NO']:
    d=df[df.side==side]
    g=d.groupby('b',observed=True).agg(fills=('p','size'),mk=('mid','nunique'),usd=('usd','sum'),p=('p','mean'),win=('won','mean'),ret_per_fill=('ret','mean'),pnl=('pnl','sum'))
    g['roi_usd']=g.pnl/g.usd
    print(f'\n=== taker {side} buys ===\n',g.round(4).to_string())
# time-to-end profile for favorites
fav=df[(df.p>=0.9)&(df.p<0.99)]
fav['h']=pd.cut(fav.hrs_to_end,[-100,1,6,24,72,1000])
print('\nfavorite buys 0.90-0.99 by hours-to-end:\n',fav.groupby('h',observed=True).agg(n=('p','size'),usd=('usd','sum'),p=('p','mean'),win=('won','mean'),roi=('ret','mean')).round(4).to_string())
