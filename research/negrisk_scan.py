"""Live scan: neg-risk events where buying every YES (or every NO) costs < payout after taker fees."""
from pm import *
import json, time, sys
from concurrent.futures import ThreadPoolExecutor
def active_events():
    evs=[]; cursor=None
    while True:
        p=dict(limit=100,active='true',closed='false')
        if cursor: p['after_cursor']=cursor
        r=get(f"{GAMMA}/events/keyset",p)
        if not r or not r.get('events'): break
        evs+=r['events']; cursor=r.get('next_cursor')
        if not cursor: break
    return evs
def fetch_books(tokens):
    out={}
    chunks=[tokens[i:i+100] for i in range(0,len(tokens),100)]
    def f(ch):
        for i in range(4):
            try: return S.post(f"{CLOB}/books",json=[{"token_id":t} for t in ch],timeout=30).json()
            except Exception: time.sleep(1+i)
        return []
    with ThreadPoolExecutor(6) as ex:
        for r in ex.map(f,chunks):
            for b in (r or []): out[b['asset_id']]=b
    return out
if __name__=='__main__':
    t0=time.time()
    evs=active_events()
    groups=[]
    for e in evs:
        if not e.get('negRisk'): continue
        ms=[m for m in e.get('markets',[]) if m.get('active') and not m.get('closed') and m.get('clobTokenIds') and m.get('enableOrderBook')]
        if len(ms)<2: continue
        groups.append((e,ms))
    toks=[t for e,ms in groups for m in ms for t in json.loads(m['clobTokenIds'])]
    print('events',len(evs),'negrisk groups',len(groups),'tokens',len(toks),round(time.time()-t0,1),flush=True)
    bk=fetch_books(toks)
    print('books',len(bk),round(time.time()-t0,1),flush=True)
    res=[]
    for e,ms in groups:
        rate=float(((ms[0].get('feeSchedule') or {}).get('rate')) or 0)
        tk=[json.loads(m['clobTokenIds']) for m in ms]
        aug=bool(e.get('negRiskAugmented') or e.get('enableNegRisk') and any('other' in (m.get('groupItemTitle') or '').lower() for m in ms))
        for side,idx,payout in (('YES',0,1),('NO',1,len(ms)-1)):
            asks=[]
            for t in tk:
                b=bk.get(t[idx])
                if not b or not b.get('asks'): asks=None; break
                asks.append(min((float(x['price']),float(x['size'])) for x in b['asks']))
            if not asks: continue
            cost=sum(p for p,s in asks); fee=sum(rate*p*(1-p) for p,s in asks)
            res.append(dict(side=side,title=e['title'][:60],slug=e.get('slug'),n=len(ms),cost=round(cost,4),fee=round(fee,4),
                            edge=round(payout-cost-fee,4),depth=round(min(s for p,s in asks),1),rate=rate,aug=aug,
                            augflag=e.get('negRiskAugmented'),end=e.get('endDate')))
    res.sort(key=lambda x:-x['edge'])
    print('scanned',len(res),'in',round(time.time()-t0,1),'s; positive-edge:',sum(1 for r in res if r['edge']>0))
    for r in res[:30]: print(r)
    json.dump(res,open('data/negrisk_scan_%d.json'%int(time.time()),'w'))
