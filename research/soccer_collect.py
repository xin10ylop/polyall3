"""Collect Polymarket 3-way soccer markets (2025/26) + minute price history around kickoff."""
from pm import *
import json, os, sys, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor
LEAGUES={'E0':10188,'E1':10355,'E2':11435,'E3':11436,'EC':11445,'SP1':10193,'SP2':10672,'D1':10194,'D2':10670,
         'I1':10203,'I2':10676,'F1':10195,'F2':10675,'N1':10286,'P1':10330,'T1':10292,'B1':12351,'G1':12356}
OUT='data/soccer'; os.makedirs(OUT,exist_ok=True)
def iso(ts): return dt.datetime.fromisoformat(ts.replace('Z','+00:00'))
def events_for(series):
    evs=[]; cursor=None
    while True:
        p=dict(limit=100,series_id=series,closed='true',start_date_min='2025-06-15T00:00:00Z',start_date_max='2026-06-15T00:00:00Z')
        if cursor: p['after_cursor']=cursor
        r=get(f"{GAMMA}/events/keyset",p)
        if not r or not r.get('events'): break
        evs+=r['events']; cursor=r.get('next_cursor')
        if not cursor: break
    return evs
def hist(tok,t0,t1):
    r=get(f"{CLOB}/prices-history",dict(market=tok,startTs=t0,endTs=t1,fidelity=1))
    return (r or {}).get('history',[])
def proc(e):
    ms=e.get('markets',[])
    win=[m for m in ms if ' win on ' in m['question']]; draw=[m for m in ms if 'end in a draw' in m['question']]
    if len(win)!=2 or len(draw)!=1 or not e.get('startTime'): return None
    ko=int(iso(e['startTime']).timestamp())
    rec=dict(slug=e['slug'],title=e['title'],kickoff=e['startTime'],ko=ko,markets=[])
    for m in win+draw:
        toks=json.loads(m['clobTokenIds'])
        rec['markets'].append(dict(q=m['question'],team=m.get('groupItemTitle'),cid=m['conditionId'],yes=toks[0],no=toks[1],
            outcomePrices=m.get('outcomePrices'),vol=m.get('volumeNum'),fee=m.get('feeSchedule'),feeType=m.get('feeType'),
            hist=hist(toks[0],ko-3*3600,ko+600)))
    return rec
if __name__=='__main__':
    for L,series in LEAGUES.items():
        fn=f'{OUT}/{L}.json'
        if os.path.exists(fn): continue
        t=time.time(); evs=events_for(series)
        with ThreadPoolExecutor(8) as ex: recs=[r for r in ex.map(proc,evs) if r]
        json.dump(recs,open(fn,'w'))
        print(L,'events',len(evs),'3way',len(recs),'with hist',sum(1 for r in recs if all(m['hist'] for m in r['markets'])),round(time.time()-t),'s',flush=True)
