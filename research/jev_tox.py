"""Jev classification of rewarded markets by adverse-selection (toxicity) risk."""
import json, os, sys, datetime as dt, time
from concurrent.futures import ThreadPoolExecutor
import jev, threading
LOCK=threading.Lock()
from rewards_lib import all_rewarded, WEATHER
from pm import get, CLOB
CACHE='data/jev_tox.json'
try: cache=json.load(open(CACHE)) if os.path.exists(CACHE) else {}
except Exception: cache={}
def save():
    with LOCK: snap=dict(cache)
    json.dump(snap,open(CACHE+'.tmp','w')); os.replace(CACHE+'.tmp',CACHE)
Q={
 "realtime": {"type":"noul","instructions":"Before this market resolves, is its outcome driven by a quantity that the public can watch update continuously or many times per day (e.g. live counts of posts/tweets/views/streams, asset or commodity prices, live vote counts, live sports scores, chart rankings updated daily)?",
              "criteria":{"true":"Outcome tracks a live, frequently-updated public number or feed","false":"Outcome depends on a discrete future decision, announcement, or event with no live running tally"}},
 "reveal_soon": {"type":"noul","instructions":"Given `now` and `end_date`, is decisive information likely to be revealed within the next 72 hours (e.g. a scheduled announcement, ceremony, release, election, data release, meeting, or the deadline itself)?",
              "criteria":{"true":"Decisive information is scheduled or very likely within 72 hours","false":"No decisive information expected within 72 hours"}},
 "news_speed": {"type":"score","instructions":"How often does new information that could move this market's probability by 5+ percentage points typically arrive?",
              "criteria":["Rarely (weeks or more between relevant news)","Occasionally (every few days)","Often (daily)","Constantly (hourly or real-time)"]},
 "insider": {"type":"noul","instructions":"Could some traders plausibly know the outcome well before the public (e.g. company/lab insiders, award committees, content creators, government officials, organizers)?",
              "criteria":{"true":"Plausible insider knowledge exists","false":"Outcome is not knowable in advance by any identifiable insiders"}},
}
def classify(m):
    k=m['condition_id']
    if k in cache: return k,cache[k]
    st={"question":m['question'],"rules":(m.get('description') or '')[:900],"end_date":m.get('end_date_iso'),"now":dt.datetime.utcnow().isoformat(timespec='minutes')+'Z'}
    a=jev.decide(st,Q)
    if a is None: return k,None
    r=dict(realtime=a['realtime']['noul'],reveal_soon=a['reveal_soon']['noul'],news_speed=a['news_speed']['score'],insider=a['insider']['noul'],q=m['question'])
    with LOCK: cache[k]=r
    return k,r
if __name__=='__main__':
    min_rate=float(sys.argv[1]) if len(sys.argv)>1 else 20
    rm=[r for r in all_rewarded() if float(r.get('total_daily_rate') or 0)>=min_rate]
    print('rewarded >=',min_rate,':',len(rm))
    def mk(r): return get(f"{CLOB}/markets/{r['condition_id']}")
    with ThreadPoolExecutor(8) as ex: ms=[m for m in ex.map(mk,rm) if m and not m.get('closed') and m.get('question')]
    ms=[m for m in ms if not WEATHER.search(m['question'])]
    print('non-weather open',len(ms))
    t=time.time(); n=0
    with ThreadPoolExecutor(8) as ex:
        for k,r in ex.map(classify,ms):
            n+=1
            if n%200==0: save(); print(n,round(time.time()-t),'s $',round(jev.SPENT['usd'],4),flush=True)
    save()
    print('done',len(cache),'spent $',round(jev.SPENT['usd'],4))
