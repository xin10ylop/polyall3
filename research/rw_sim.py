"""Forward paper-simulation of liquidity-reward farming on live Polymarket books + real trade prints.
Variants: 'join' (quote at best bid/ask) and 'improve' (1 tick inside). Conservative fills: any taker trade at/through our price fills us."""
import json, time, os, sys, traceback, datetime as dt
from rewards_lib import *
from pm import get, DATA
OUT='live/rw3'; os.makedirs(OUT,exist_ok=True)
VARIANTS=['join','improve']
class Book:
    def __init__(s): s.yes=0.0; s.no=0.0; s.cash=0.0; s.rew_c=0.0; s.rew_m=0.0; s.fills=[]
    def mtm(s,mid): return s.cash+s.yes*mid+s.no*(1-mid)
state={v:{} for v in VARIANTS}   # variant -> cid -> Book
last_trade_ts={}; cfgs={}; last_mid={}; LAST={'t':None}
def trades_since(cid,since):
    r=get(f"{DATA}/trades",dict(market=cid,limit=200))
    if not isinstance(r,list): return []
    return [t for t in r if t['timestamp']>since]
def to_yes_space(t,cfg):
    """returns ('sell',p) if taker effectively SOLD YES at p (hits bids), ('buy',p) if taker BOUGHT YES at p (lifts asks)"""
    p=float(t['price'])
    if t['asset']==cfg['yes']: return ('sell',p) if t['side']=='SELL' else ('buy',p)
    if t['asset']==cfg['no']:  return ('buy',round(1-p,6)) if t['side']=='SELL' else ('sell',round(1-p,6))
    return None
def step(universe_refresh):
    now=int(time.time())
    if universe_refresh:
        U=select_universe(60)
        for c in U:
            cfgs[c['cid']]=c
            if c['cid'] not in last_trade_ts: last_trade_ts[c['cid']]=now
        active=set(c['cid'] for c in U)
        for c in list(cfgs):
            cfgs[c]['active']=c in active
    act=[c for c in cfgs.values() if c.get('active')]
    elapsed=60.0 if LAST['t'] is None else min(120.0,time.time()-LAST['t']); LAST['t']=time.time()
    bk=fetch_books([c['yes'] for c in act]+[c['no'] for c in act])
    log=[]
    for c in act:
        st=market_state(c,bk)
        if not st: continue
        last_mid[c['cid']]=st['mid']
        tr=trades_since(c['cid'],last_trade_ts[c['cid']])
        if tr: last_trade_ts[c['cid']]=max(t['timestamp'] for t in tr)
        for v in VARIANTS:
            b=state[v].setdefault(c['cid'],Book())
            bid,ask,sz=our_quote(st,c,v,c['size'])
            net=b.yes-b.no
            q_bid= net < sz      # still room to buy YES
            q_ask= -net < sz     # still room to sell YES (buy NO)
            # reward share this minute
            bb=bid if q_bid else -1; aa=ask if q_ask else 9
            ours,shc,shm=our_share(st,c,bb,aa,sz)
            b.rew_c+=c['rate']/86400*elapsed*shc; b.rew_m+=c['rate']/86400*elapsed*shm
            # fills from trades since last step (quotes assumed resting at these prices)
            rem_b=sz if q_bid else 0; rem_a=sz if q_ask else 0
            for t in sorted(tr,key=lambda x:x['timestamp']):
                x=to_yes_space(t,c)
                if not x: continue
                side,p=x; qty=float(t['size'])
                if side=='sell' and rem_b>0 and p<=bid+1e-9:
                    f=min(rem_b,qty); rem_b-=f; b.yes+=f; b.cash-=f*bid; b.fills.append((t['timestamp'],'B',bid,f,st['mid']))
                elif side=='buy' and rem_a>0 and p>=ask-1e-9:
                    f=min(rem_a,qty); rem_a-=f; b.no+=f; b.cash-=f*(1-ask); b.fills.append((t['timestamp'],'S',ask,f,st['mid']))
            # merge complete sets
            m=min(b.yes,b.no)
            if m>0: b.yes-=m; b.no-=m; b.cash+=m
            log.append(dict(ts=now,v=v,cid=c['cid'],mid=round(st['mid'],4),bid=bid,ask=ask,shc=round(shc,4),shm=round(shm,4),q1=round(st['q1'],1),q2=round(st['q2'],1),
                            ntr=len(tr),yes=b.yes,no=b.no,cash=round(b.cash,4),rc=round(b.rew_c,4)))
    with open(f'{OUT}/steps_{dt.date.today().isoformat()}.jsonl','a') as f:
        for l in log: f.write(json.dumps(l)+'\n')
    # summary
    summ={}
    for v in VARIANTS:
        rc=sum(b.rew_c for b in state[v].values()); rm=sum(b.rew_m for b in state[v].values())
        tp=sum(b.mtm(last_mid.get(cid,0.5)) for cid,b in state[v].items())
        nf=sum(len(b.fills) for b in state[v].values())
        summ[v]=dict(rew_cons=round(rc,2),rew_cent=round(rm,2),trade_pnl=round(tp,2),net_cons=round(rc+tp,2),fills=nf)
    json.dump(dict(ts=now,summ=summ,books={v:{cid:dict(yes=b.yes,no=b.no,cash=b.cash,rew_c=b.rew_c,rew_m=b.rew_m,fills=b.fills) for cid,b in state[v].items()} for v in VARIANTS},
                   cfgs=cfgs,last_mid=last_mid),open(f'{OUT}/state.json','w'))
    return summ,len(act)
if __name__=='__main__':
    t0=time.time(); last_u=0; start=time.time()
    while True:
        try:
            refresh=time.time()-last_u>1800
            if refresh: last_u=time.time()
            ts=time.time(); summ,n=step(refresh)
            hrs=(time.time()-start)/3600
            print(dt.datetime.utcnow().isoformat(timespec='seconds'),f'hrs={hrs:.2f} mkts={n}',json.dumps(summ),f'{time.time()-ts:.1f}s',flush=True)
        except Exception:
            traceback.print_exc()
        time.sleep(max(1,60-(time.time()-ts)))
