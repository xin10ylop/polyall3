"""Every 5 min: competitor liquidity inside the reward band for every rewarded non-weather market (for pool-age analysis)."""
import sys, json, time, re, datetime as dt, traceback
sys.path.insert(0,'/home/user/polyall3')
from pmbot import api, scoring
RX=re.compile(r"temperature|precipitation|rain|snow|hurricane|weather|°[CF]|Up or Down",re.I)
info={}
while True:
    try:
        t0=time.time()
        rm=[r for r in api.rewarded_markets() if float(r.get('total_daily_rate') or 0)>=10]
        new=[r['condition_id'] for r in rm if r['condition_id'] not in info]
        if new: info.update(api.clob_markets(new))
        cs=[]
        for r in rm:
            m=info.get(r['condition_id'])
            if not m or m.get('closed') or not m.get('tokens') or len(m['tokens'])!=2 or RX.search(m.get('question','')): continue
            cs.append((r,m))
        bk=api.books([m['tokens'][0]['token_id'] for r,m in cs])
        out=[]
        for r,m in cs:
            b=bk.get(m['tokens'][0]['token_id'])
            if not b: continue
            v=float(r['rewards_max_spread']); ms=float(r['rewards_min_size'])
            bids,asks=scoring.levels(b,'bids'),scoring.levels(b,'asks')
            if not bids or not asks: continue
            ab,aa=scoring.adjusted_best(bids,ms),scoring.adjusted_best(asks,ms)
            if ab is None or aa is None: continue
            mid=(ab+aa)/2
            out.append(dict(cid=r['condition_id'],rate=float(r['total_daily_rate']),start=(r.get('rewards_config') or [{}])[0].get('start_date'),
                            mid=round(mid,4),q1=round(scoring.side_q(bids,mid,v,True),2),q2=round(scoring.side_q(asks,mid,v,False),2)))
        with open('live/pool_tracker.jsonl','a') as f: f.write(json.dumps(dict(ts=int(t0),m=out))+'\n')
        print(dt.datetime.utcnow().isoformat(timespec='seconds'),len(out),'markets',round(time.time()-t0),'s',flush=True)
    except Exception: traceback.print_exc()
    time.sleep(max(5,300-(time.time()-t0)))
