"""Estimate liquidity-reward yield per $ of capital for every rewarded market, vs current live competition."""
from pm import *
import json, time, sys, numpy as np
from negrisk_scan import fetch_books
def all_rewarded():
    out=[]; cur=''
    while True:
        r=get(f"{CLOB}/rewards/markets/current",dict(next_cursor=cur) if cur else None)
        if not r: break
        out+=r.get('data',[]); cur=r.get('next_cursor')
        if not cur or cur=='LTE=': break
    return out
def S(v,s): return max(0.0,(v-s)/v)**2
def q_side(levels, mid, v, is_bid):
    """levels: [(price,size)], v in cents. returns sum S*size for orders within v cents of mid"""
    q=0
    for p,sz in levels:
        s=(mid-p)*100 if is_bid else (p-mid)*100
        if 0<=s<v: q+=S(v,s)*sz
    return q
if __name__=='__main__':
    rm=all_rewarded()
    rm=[r for r in rm if float(r.get('total_daily_rate') or r.get('native_daily_rate') or 0)>0]
    print('rewarded markets',len(rm),'total $/day',round(sum(float(r.get('total_daily_rate') or 0) for r in rm)))
    # need token ids: fetch clob market
    cids=[r['condition_id'] for r in rm]
    info={}
    from concurrent.futures import ThreadPoolExecutor
    def mk(c): return c,get(f"{CLOB}/markets/{c}")
    with ThreadPoolExecutor(8) as ex:
        for c,m in ex.map(mk,cids): info[c]=m
    toks=[]
    for c,m in info.items():
        if m and m.get('tokens') and m.get('active') and not m.get('closed'): toks+=[t['token_id'] for t in m['tokens']]
    bk=fetch_books(toks)
    res=[]
    for r in rm:
        m=info.get(r['condition_id'])
        if not m or not m.get('tokens') or m.get('closed'): continue
        ty,tn=m['tokens'][0]['token_id'],m['tokens'][1]['token_id']
        by,bn=bk.get(ty),bk.get(tn)
        if not by or not bn: continue
        bids=[(float(x['price']),float(x['size'])) for x in by['bids']]; asks=[(float(x['price']),float(x['size'])) for x in by['asks']]
        nb=[(float(x['price']),float(x['size'])) for x in bn['bids']]; na=[(float(x['price']),float(x['size'])) for x in bn['asks']]
        if not bids or not asks: continue
        bb=max(p for p,s in bids); ba=min(p for p,s in asks); mid=(bb+ba)/2
        v=float(r['rewards_max_spread']); mins=float(r['rewards_min_size']); rate=float(r.get('total_daily_rate') or r.get('native_daily_rate'))
        tick=float(m.get('minimum_tick_size') or 0.01)
        # competitor Q: side1 = YES bids + NO asks (NO ask at q == YES bid at 1-q); side2 = YES asks + NO bids
        q1=q_side(bids,mid,v,True)+q_side([(1-p,s) for p,s in na],mid,v,True)
        q2=q_side(asks,mid,v,False)+q_side([(1-p,s) for p,s in nb],mid,v,False)
        inrange=0.10<=mid<=0.90
        qc=max(min(q1,q2),max(q1/3,q2/3)) if inrange else min(q1,q2)
        # our order: size X each side at best bid / best ask (join queue, spread = distance of best from mid)
        X=max(mins,100/ max(0.01,1.0))  # 100 shares per side ~ $100 capital two-sided
        X=max(mins,100)
        s_b=(mid-bb)*100; s_a=(ba-mid)*100
        our=min(S(v,s_b)*X,S(v,s_a)*X) if (s_b<v and s_a<v) else 0
        share=our/(qc+our) if our>0 else 0
        cap=X*bb + X*(1-ba)  # bid YES at bb, bid NO at 1-ba
        daily=rate*share
        res.append(dict(q=m.get('question','')[:60],rate=rate,v=v,mins=mins,mid=round(mid,3),spread=round(ba-bb,3),comp_Q=round(qc),our_Q=round(our),
                        share=round(share,4),usd_day=round(daily,3),cap=round(cap,1),roi_day=round(daily/cap,4) if cap>0 else 0,
                        vol24=None,cid=r['condition_id'],end=m.get('end_date_iso')))
    res.sort(key=lambda x:-x['roi_day'])
    json.dump(res,open('data/rewards_scan_%d.json'%int(time.time()),'w'))
    print('evaluated',len(res))
    print('sum over top-20 usd/day with ~$100 each:',round(sum(x['usd_day'] for x in res[:20]),2))
    for x in res[:40]: print(x)
