"""Liquidity-reward farming: scoring + universe selection (shared by simulator and live bot)."""
import json, time, re, datetime as dt
from pm import S as PMS, get, CLOB, GAMMA
from concurrent.futures import ThreadPoolExecutor
WEATHER=re.compile(r"temperature|precipitation|rain|snow|hurricane|tornado|weather|°[CF]|inches of", re.I)
def all_rewarded():
    out=[]; cur=''
    while True:
        r=get(f"{CLOB}/rewards/markets/current",dict(next_cursor=cur) if cur else None)
        if not r: break
        out+=r.get('data',[]); cur=r.get('next_cursor')
        if not cur or cur=='LTE=': break
    return out
def fetch_books(tokens):
    out={}
    chunks=[tokens[i:i+100] for i in range(0,len(tokens),100)]
    def f(ch):
        for i in range(4):
            try: return PMS.post(f"{CLOB}/books",json=[{"token_id":t} for t in ch],timeout=30).json()
            except Exception: time.sleep(1+i)
        return []
    with ThreadPoolExecutor(6) as ex:
        for r in ex.map(f,chunks):
            for b in (r or []): out[b['asset_id']]=b
    return out
def levels(b,side):
    lv=[(float(x['price']),float(x['size'])) for x in (b.get(side) or [])]
    lv.sort(key=lambda x:x[0],reverse=(side=='bids')); return lv
def adj_best(lv,min_size):
    """price where cumulative depth from top first reaches min_size (size-cutoff-adjusted)"""
    c=0
    for p,s in lv:
        c+=s
        if c>=min_size: return p
    return None
def Sfun(v,s): return max(0.0,(v-s)/v)**2 if s>=0 else 0.0
def side_q(orders,mid,v,is_bid):
    q=0
    for p,sz in orders:
        s=round(((mid-p) if is_bid else (p-mid))*100,6)
        if 0<=s<v: q+=Sfun(v,s)*sz
    return q
def qmin(q1,q2,mid):
    if 0.10<=mid<=0.90: return max(min(q1,q2),max(q1,q2)/3.0)
    return min(q1,q2)
def market_state(cfg, bk):
    """cfg: dict with yes,no,v,min_size,rate,tick. returns book summary incl adjusted mid and competitor Q on both sides"""
    by,bn=bk.get(cfg['yes']),bk.get(cfg['no'])
    if not by or not bn: return None
    yb,ya=levels(by,'bids'),levels(by,'asks'); nb,na=levels(bn,'bids'),levels(bn,'asks')
    # unify into YES-price space: side1 (bids) = YES bids + NO asks(1-p); side2 (asks) = YES asks + NO bids(1-p)
    bids=yb; asks=ya  # NO book mirrors YES book; don't double count
    if not bids or not asks: return None
    bb,ba=bids[0][0],asks[0][0]
    abb,aba=adj_best(bids,cfg['min_size']),adj_best(asks,cfg['min_size'])
    if abb is None or aba is None: return None
    mid=(abb+aba)/2
    v=cfg['v']
    q1=side_q(bids,mid,v,True); q2=side_q(asks,mid,v,False)
    return dict(bb=bb,ba=ba,mid=mid,raw_mid=(bb+ba)/2,q1=q1,q2=q2,bids=bids[:10],asks=asks[:10])
def our_quote(st,cfg,mode='join',size=None):
    """returns (bid_px, ask_px, size) in YES-price space. join = at best bid/ask; improve = one tick inside if spread allows"""
    t=cfg['tick']; size=size or cfg['size']
    bb,ba=st['bb'],st['ba']
    if mode=='improve' and ba-bb>2*t+1e-9: bid,ask=round(bb+t,4),round(ba-t,4)
    else: bid,ask=bb,ba
    # keep within reward band
    return bid,ask,size
def our_share(st,cfg,bid,ask,size):
    v=cfg['v']; mid=st['mid']
    s_b=round((mid-bid)*100,6); s_a=round((ask-mid)*100,6)
    o1=Sfun(v,s_b)*size if 0<=s_b<v else 0.0
    o2=Sfun(v,s_a)*size if 0<=s_a<v else 0.0
    ours=qmin(o1,o2,mid)
    comp_cons=max(st['q1'],st['q2'])            # conservative: competitors fully credited
    comp_cent=qmin(st['q1'],st['q2'],mid)       # central
    sh_cons=ours/(ours+comp_cons) if ours>0 else 0.0
    sh_cent=ours/(ours+comp_cent) if ours>0 else 0.0
    return ours,sh_cons,sh_cent
def select_universe(max_markets=60, min_rate=10, min_hours_left=36, capital_per_mkt=100):
    rm=[r for r in all_rewarded() if float(r.get('total_daily_rate') or r.get('native_daily_rate') or 0)>=min_rate]
    cids=[r['condition_id'] for r in rm]
    info={}
    def mk(c): return c,get(f"{CLOB}/markets/{c}")
    with ThreadPoolExecutor(8) as ex:
        for c,m in ex.map(mk,cids): info[c]=m
    now=dt.datetime.now(dt.timezone.utc)
    cands=[]
    for r in rm:
        m=info.get(r['condition_id'])
        if not m or m.get('closed') or not m.get('active') or not m.get('accepting_orders') or not m.get('tokens') or len(m['tokens'])!=2: continue
        q=m.get('question','')
        if WEATHER.search(q) or WEATHER.search(m.get('description','')[:300]): continue
        end=m.get('end_date_iso')
        try: e=dt.datetime.fromisoformat(end.replace('Z','+00:00'))
        except Exception: continue
        if (e-now).total_seconds()<min_hours_left*3600: continue
        cands.append(dict(cid=r['condition_id'],q=q,yes=m['tokens'][0]['token_id'],no=m['tokens'][1]['token_id'],
                          v=float(r['rewards_max_spread']),min_size=float(r['rewards_min_size']),
                          rate=float(r.get('total_daily_rate') or r.get('native_daily_rate')),tick=float(m.get('minimum_tick_size') or 0.01),
                          end=end,neg_risk=m.get('neg_risk'),slug=m.get('market_slug')))
    bk=fetch_books([c['yes'] for c in cands]+[c['no'] for c in cands])
    scored=[]
    for c in cands:
        st=market_state(c,bk)
        if not st or not (0.04<=st['mid']<=0.96): continue
        c['size']=max(c['min_size'],round(capital_per_mkt/1.0))  # ~$100 two-sided
        bid,ask,sz=our_quote(st,c,'join')
        ours,shc,sh=our_share(st,c,bid,ask,sz)
        cap=sz*bid+sz*(1-ask)
        c['est_usd_day']=c['rate']*shc; c['est_roi']=c['est_usd_day']/cap if cap>0 else 0
        scored.append(c)
    scored.sort(key=lambda x:-x['est_roi'])
    return scored[:max_markets]
