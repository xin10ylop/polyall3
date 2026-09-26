"""Census of closed markets per day (slim, no descriptions). Usage: census.py START_DAY N_DAYS"""
from pm import *
import json, sys, os, datetime as dt
from concurrent.futures import ThreadPoolExecutor
F=['id','question','conditionId','slug','endDate','closedTime','outcomes','outcomePrices','volumeNum','clobTokenIds',
   'negRisk','negRiskMarketID','feeType','sportsMarketType','umaResolutionStatus','groupItemTitle','gameStartTime',
   'eventStartTime','startDate','createdAt','line','orderPriceMinTickSize','resolutionSource']
def slim2(m):
    d={k:m.get(k) for k in F}
    fs=m.get('feeSchedule') or {}; d['feeRate']=fs.get('rate'); d['rebateRate']=fs.get('rebateRate')
    ev=(m.get('events') or [{}])[0]
    d['event_slug']=ev.get('slug'); d['event_title']=ev.get('title'); d['event_id']=ev.get('id')
    d['seriesSlug']=ev.get('seriesSlug')
    return d
def do_day(day):
    fn=f'data/census_{day}.json'
    if os.path.exists(fn): return day, -1
    nxt=(dt.date.fromisoformat(day)+dt.timedelta(days=1)).isoformat()
    out=[]; cursor=None; seen=set()
    while True:
        p=dict(limit=100, closed='true', end_date_min=day+'T00:00:00Z', end_date_max=nxt+'T00:00:00Z')
        if cursor: p['after_cursor']=cursor
        r=get(f"{GAMMA}/markets/keyset",p)
        if not r or not r.get('markets'): break
        for m in r['markets']:
            if m['id'] in seen: continue
            seen.add(m['id']); out.append(slim2(m))
        cursor=r.get('next_cursor')
        if not cursor: break
    json.dump(out,open(fn,'w'))
    return day,len(out)
start=dt.date.fromisoformat(sys.argv[1]); n=int(sys.argv[2])
days=[(start+dt.timedelta(days=i)).isoformat() for i in range(n)]
with ThreadPoolExecutor(4) as ex:
    for day,c in ex.map(do_day,days): print(day,c,flush=True)
