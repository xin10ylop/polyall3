"""Population (not cherry-picked): every wallet active in thin rewarded markets that received REWARD payouts in the
last 7 days -> 7-day markout P&L + rewards + rebates, and on-chain capital."""
from pm import *
import json, time, requests, sys
from concurrent.futures import ThreadPoolExecutor
sys.argv=[sys.argv[0],'x','7']
exec(open('farmer_markout.py').read().split("for w in sys.argv[1].split(','):")[0])
RPC="https://polygon-bor-rpc.publicnode.com"; PUSD='0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'
def pusd(w):
    try:
        d=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":PUSD,"data":'0x70a08231'+w[2:].lower().rjust(64,'0')},"latest"]},timeout=20).json()['result']
        return int(d,16)/1e6
    except Exception: return None
def analyze(w):
    since=int(time.time()-7*86400)
    rw=get(f"{DATA}/activity",dict(user=w,limit=500,type='REWARD')) or []
    rew=sum(float(a.get('usdcSize') or 0) for a in rw if a['timestamp']>=since)
    if rew<1: return None
    rb=get(f"{DATA}/activity",dict(user=w,limit=500,type='MAKER_REBATE')) or []
    reb=sum(float(a.get('usdcSize') or 0) for a in rb if a['timestamp']>=since)
    tr=user_trades(w,since)
    toks=sorted({t['asset'] for t in tr}); cids=sorted({t['conditionId'] for t in tr})
    res={}
    for c in cids: res.update(resolution(c))
    px={t:cur_price(t) for t in toks if t not in res}; px.update(res)
    pnl=0; vol=0
    for t in tr:
        v=px.get(t['asset'])
        if v is None: continue
        sz=float(t['size']); p=float(t['price']); sgn=1 if t['side']=='BUY' else -1
        pnl+=sgn*(v-p)*sz; vol+=p*sz
    val=get(f"{DATA}/value",dict(user=w)); pv=float(val[0]['value']) if isinstance(val,list) and val else 0
    cash=pusd(w) or 0
    return dict(w=w,rew=rew,reb=reb,markout=pnl,vol=vol,net=pnl+rew+reb,capital=cash+pv,fills=len(tr))
W=[w for w,n in json.load(open('data/thin_makers.json'))]
more=json.load(open('data/thin_makers.json'))
print('wallets',len(W),flush=True)
out=[]
with ThreadPoolExecutor(6) as ex:
    for r in ex.map(analyze,W):
        if r: out.append(r); print(json.dumps({k:(round(v,1) if isinstance(v,float) else v) for k,v in r.items()}),flush=True)
json.dump(out,open('data/farmer_population.json','w'))
import numpy as np
net=np.array([r['net'] for r in out]); cap=np.array([max(r['capital'],1) for r in out])
print('\nN farmers',len(out),'net>0:',(net>0).sum(),'median weekly net',np.median(net).round(1),'sum net',net.sum().round(0),'sum rewards',round(sum(r['rew'] for r in out)))
roi=net/7/cap; print('daily ROI pctiles (10,25,50,75,90):',np.percentile(roi,[10,25,50,75,90]).round(4))
