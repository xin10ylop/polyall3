"""Trading P&L of real reward farmers over the last N days (fills marked to current price / resolution) vs rewards."""
from pm import *
import json, sys, time, collections, datetime as dt
from concurrent.futures import ThreadPoolExecutor
DAYS=float(sys.argv[2]) if len(sys.argv)>2 else 7
def user_trades(w, since):
    out=[]; end=None
    for _ in range(60):
        p=dict(user=w,limit=500,takerOnly='false')
        if end: p['end']=end
        r=get(f"{DATA}/trades",p)
        if not isinstance(r,list) or not r: break
        out+=r
        if r[-1]['timestamp']<since or len(r)<500: break
        end=r[-1]['timestamp']-1
    return [t for t in out if t['timestamp']>=since]
def cur_price(token):
    r=get(f"{CLOB}/last-trade-price",dict(token_id=token))
    m=get(f"{CLOB}/midpoint",dict(token_id=token))
    try: return float(m['mid'])
    except Exception:
        try: return float(r['price'])
        except Exception: return None
def resolution(cid):
    m=get(f"{CLOB}/markets/{cid}")
    if not m: return {}
    out={}
    for t in m.get('tokens',[]):
        if m.get('closed') and t.get('winner') is not None: out[t['token_id']]=1.0 if t['winner'] else 0.0
    return out
for w in sys.argv[1].split(','):
    since=int(time.time()-DAYS*86400)
    tr=user_trades(w,since)
    toks=sorted({t['asset'] for t in tr}); cids=sorted({t['conditionId'] for t in tr})
    with ThreadPoolExecutor(8) as ex: res={}; [res.update(x) for x in ex.map(resolution,cids)]
    need=[t for t in toks if t not in res]
    with ThreadPoolExecutor(8) as ex: px=dict(zip(need,ex.map(cur_price,need)))
    px.update(res)
    pnl=0; vol=0; n=0; miss=0
    for t in tr:
        v=px.get(t['asset'])
        if v is None: miss+=1; continue
        sz=float(t['size']); p=float(t['price'])
        # the user's side: for takerOnly=false rows, 'side' is the user's side? (data-api returns user's own side for user queries)
        sgn=1 if t['side']=='BUY' else -1
        pnl+=sgn*(v-p)*sz; vol+=p*sz; n+=1
    rw=get(f"{DATA}/activity",dict(user=w,limit=500,type='REWARD')) or []
    rb=get(f"{DATA}/activity",dict(user=w,limit=500,type='MAKER_REBATE')) or []
    rew=sum(float(a.get('usdcSize') or 0) for a in rw if a['timestamp']>=since)
    reb=sum(float(a.get('usdcSize') or 0) for a in rb if a['timestamp']>=since)
    print(f"{w} days={DAYS} fills={n} miss={miss} vol=${vol:,.0f} markout_pnl=${pnl:,.0f}  rewards=${rew:,.0f} rebates=${reb:,.0f}  NET=${pnl+rew+reb:,.0f} ({(pnl+rew+reb)/DAYS:,.0f}/day)",flush=True)
