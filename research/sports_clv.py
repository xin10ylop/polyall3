"""CLV test: when PM ask was below Pinnacle fair (after fee), did Pinnacle's CLOSING fair (last snapshot before start) confirm it?"""
import json, glob, collections, numpy as np, datetime as dt, time
rows=[json.loads(l) for f in sorted(glob.glob('live/snap_*.jsonl')) for l in open(f)]
now=time.time()
ev=collections.defaultdict(list)
for r in rows: ev[r['slug']].append(r)
bets=[]
for slug,rs in ev.items():
    rs.sort(key=lambda r:r['ts'])
    st=dt.datetime.fromisoformat(rs[0]['start'].replace('Z','+00:00')).timestamp()
    if st>now: continue
    pre=[r for r in rs if r['ts']<st]
    if len(pre)<2: continue
    close=pre[-1]
    if st-close['ts']>1800: continue   # need a snapshot within 30 min of start
    cf={o['label']:o['fair'] for o in close['outs']}
    for r in pre[:-1]:
        if st-r['ts']<600: continue
        for o in r['outs']:
            if o['fair'] is None or not o['asks'] or cf.get(o['label']) is None: continue
            a,sz=o['asks'][0]; fee=(o['fee'] or 0)*a*(1-a)
            edge=o['fair']-a-fee
            bets.append(dict(slug=slug,sport=r['sport'],edge=edge,clv=cf[o['label']]-a-fee,move=cf[o['label']]-o['fair'],age=r['age'],limit=r['limit'] or 0,hrs=(st-r['ts'])/3600,size=sz))
print('events with closing snapshot:',len({b['slug'] for b in bets}),'bet-snapshots',len(bets))
b=bets
for th in [0.0,0.01,0.02,0.03]:
    x=[z for z in b if z['edge']>th]
    if not x: continue
    ev_=len({z['slug'] for z in x})
    print(f"edge>{th:.2f}: n={len(x)} events={ev_} mean edge={np.mean([z['edge'] for z in x]):+.4f} mean CLV (vs close)={np.mean([z['clv'] for z in x]):+.4f} fair drift={np.mean([z['move'] for z in x]):+.4f}")
    for sp in sorted({z['sport'] for z in x}):
        y=[z for z in x if z['sport']==sp]
        print(f"     {sp:10} n={len(y):4} CLV={np.mean([z['clv'] for z in y]):+.4f}")
