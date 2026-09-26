from pm import *
import json, glob, datetime as dt, collections, random, numpy as np
from concurrent.futures import ThreadPoolExecutor
def P(s): return dt.datetime.fromisoformat(s.replace('Z','+00:00').replace(' ','T')) if s else None
ms=[]
for f in sorted(glob.glob('data/census_2026-09-1*.json'))+sorted(glob.glob('data/census_2026-09-2*.json')):
    for m in json.load(open(f)):
        if m.get('sportsMarketType')=='moneyline' and float(m.get('volumeNum') or 0)>20000 and winner_index(m) is not None and m.get('closedTime'):
            ms.append(m)
random.seed(1); ms=random.sample(ms,min(250,len(ms)))
print('sample',len(ms))
def probe(m):
    w=winner_index(m); tok=json.loads(m['clobTokenIds'])[w]
    ct=P(m['closedTime'])
    tr=trades(m['conditionId'],end=None,max_pages=6)
    tr=[t for t in tr if t['asset']==tok]
    if not tr: return None
    tr.sort(key=lambda t:t['timestamp'])
    # first time winner trades >=0.97 and never trades below 0.9 afterwards => "decided"
    dec=None
    for i,t in enumerate(tr):
        if t['price']>=0.97 and all(x['price']>=0.90 for x in tr[i:]): dec=t['timestamp']; break
    if dec is None: return None
    post=[t for t in tr if t['timestamp']>=dec]
    buys=[t for t in post if t['side']=='BUY']   # taker bought winner = ask available at that price
    sells=[t for t in post if t['side']=='SELL'] # taker sold winner = someone's bid filled
    def vol(ts,lo,hi): return sum(t['size']*t['price'] for t in ts if lo<=t['price']<hi)
    return dict(q=m['question'][:50],sport=m.get('event_slug','')[:6],hours_to_close=(ct.timestamp()-dec)/3600,
                n_post=len(post),buy_usd_lt99=vol(buys,0,0.99),buy_usd_99_995=vol(buys,0.99,0.995),buy_usd_995p=vol(buys,0.995,1.01),
                sell_usd_lt99=vol(sells,0,0.99),vwap_buy=(sum(t['size']*t['price'] for t in buys)/max(1e-9,sum(t['size'] for t in buys))) if buys else None)
with ThreadPoolExecutor(8) as ex: R=[r for r in ex.map(probe,ms) if r]
print('decided markets',len(R))
h=np.array([r['hours_to_close'] for r in R]); print('hours decided->closed: pctiles',np.percentile(h,[10,25,50,75,90]).round(2))
for k in ['buy_usd_lt99','buy_usd_99_995','buy_usd_995p','sell_usd_lt99']:
    v=np.array([r[k] for r in R]); print(k,'mean',round(v.mean()),'median',round(np.median(v)),'total',round(v.sum()))
vb=[r['vwap_buy'] for r in R if r['vwap_buy']]; print('vwap of post-decision taker buys: pctiles',np.percentile(vb,[10,25,50,75,90]).round(4))
json.dump(R,open('data/endgame_probe.json','w'))
