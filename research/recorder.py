"""Forward-test recorder: every cycle snapshot Pinnacle fair odds + Polymarket books for matched pre-game events."""
import json, time, os, sys, datetime as dt, traceback
from sharp import *
import jev
OUT='live'; os.makedirs(OUT,exist_ok=True)
JEVCACHE_F=f'{OUT}/jev_cache.json'
jcache=json.load(open(JEVCACHE_F)) if os.path.exists(JEVCACHE_F) else {}
def verify(pair):
    if pair['score']>=0.85: return 1.0
    k=pair['e']['slug']+'|'+str(pair['pin']['pin_id'])
    if k not in jcache:
        p=pair['pin']
        v=jev.same_event({'title':pair['e']['title'],'start':pair['e']['startTime']},
                         {'league':p['league'],'home':p['home'],'away':p['away'],'start':p['start']})
        jcache[k]=v; json.dump(jcache,open(JEVCACHE_F,'w'))
    return jcache[k]
def label_to_pin(label,kind,pair):
    if label=='draw': return 'draw'
    p=pair['pin']; return 'home' if sim(label,p['home'])>=sim(label,p['away']) else 'away'
def cycle(pm_evs):
    ts=int(time.time())
    pin=pin_snapshot()
    pairs=match_events(pm_evs,pin)
    good=[]
    for pr in pairs:
        v=verify(pr)
        if v is not None and v>=0.8: pr['jev']=v; good.append(pr)
    toks=[o[3] for pr in good for o in pr['outs']]+[o[4] for pr in good for o in pr['outs']]
    bk=fetch_books(list(set(toks)))
    rows=[]
    for pr in good:
        e=pr['e']; p=pr['pin']
        outs=[]
        for kind_lbl,label,m,ty,tn in pr['outs']:
            d=label_to_pin(label,pr['kind'],pr)
            fs=m.get('feeSchedule') or {}
            by=bk.get(ty,{}); bn=bk.get(tn,{})
            outs.append(dict(label=label,pin=d,fair=p['fair'].get(d),cid=m['conditionId'],yes=ty,no=tn,fee=fs.get('rate',0),
                             asks=book_side(by,'asks'),bids=book_side(by,'bids'),no_asks=book_side(bn,'asks'),no_bids=book_side(bn,'bids')))
        # sanity: each pin designation used exactly once
        if len({o['pin'] for o in outs})!=len(outs): continue
        rows.append(dict(ts=ts,slug=e['slug'],title=e['title'],start=e['startTime'],sport=p['sport'],league=p['league'],
                         pin_id=p['pin_id'],pin_start=p['start'],pin_home=p['home'],pin_away=p['away'],limit=p['limit'],
                         age=p['age'],overround=p['overround'],score=pr['score'],jev=pr.get('jev'),kind=pr['kind'],outs=outs))
    with open(f'{OUT}/snap_{dt.date.today().isoformat()}.jsonl','a') as f:
        for r in rows: f.write(json.dumps(r)+'\n')
    return len(pin),len(pairs),len(good),len(rows)
if __name__=='__main__':
    last_ev=0; pm_evs=[]
    while True:
        try:
            if time.time()-last_ev>900:
                pm_evs=pm_sport_events(36); last_ev=time.time()
            t=time.time(); r=cycle(pm_evs)
            print(dt.datetime.utcnow().isoformat(timespec='seconds'),'pin',r[0],'pairs',r[1],'verified',r[2],'rows',r[3],'jev$',round(jev.SPENT['usd'],5),round(time.time()-t,1),'s',flush=True)
        except Exception:
            traceback.print_exc()
        time.sleep(240)
