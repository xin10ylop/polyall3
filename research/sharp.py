"""Pinnacle (sharp reference) <-> Polymarket sports matcher + snapshot recorder."""
import requests, json, time, re, difflib, datetime as dt, os, sys, math
from concurrent.futures import ThreadPoolExecutor
from pm import S as PMS, get, GAMMA, CLOB
PIN="https://guest.api.arcadia.pinnacle.com/0.1"
PS=requests.Session(); PS.headers['User-Agent']='Mozilla/5.0'
PIN_SPORTS={29:'soccer',33:'tennis',12:'esports',3:'baseball',4:'basketball',15:'football',19:'hockey',22:'mma'}
def am2dec(a): return 1+a/100 if a>0 else 1+100/(-a)
def devig_power(dec):
    ip=[1/x for x in dec]; lo,hi=0.3,3.0
    for _ in range(60):
        k=(lo+hi)/2; s=sum(x**k for x in ip)
        if s>1: lo=k
        else: hi=k
    v=[x**k for x in ip]; s=sum(v); return [x/s for x in v]
def pin_snapshot():
    """returns list of dict(matchup, start, home, away, league, sport, probs{home,away,draw}, limit, age)"""
    out=[]
    def one(sid):
        try:
            r=PS.get(f"{PIN}/sports/{sid}/matchups",params=dict(withSpecials='false'),timeout=60)
            r2=PS.get(f"{PIN}/sports/{sid}/markets/straight",params=dict(primaryOnly='false',withSpecials='false'),timeout=60)
            if r.status_code!=200 or r2.status_code!=200: return []
            age=max(int(r.headers.get('age') or 0),int(r2.headers.get('age') or 0))
            mu={m['id']:m for m in r.json() if not m.get('parentId') and m.get('type')=='matchup'}
            res=[]
            for k in r2.json():
                if k.get('type')!='moneyline' or k.get('period')!=0 or k.get('status')!='open': continue
                m=mu.get(k['matchupId'])
                if not m or m.get('isLive'): continue
                pr={p['designation']:am2dec(p['price']) for p in k['prices'] if 'designation' in p}
                des=[d for d in ('home','away','draw') if d in pr]
                if len(des)<2: continue
                fair=devig_power([pr[d] for d in des])
                parts={p['alignment']:p['name'] for p in m['participants']}
                res.append(dict(pin_id=m['id'],sport=PIN_SPORTS[sid],league=m['league']['name'],start=m['startTime'],
                                home=parts.get('home'),away=parts.get('away'),dec=pr,fair=dict(zip(des,fair)),
                                overround=sum(1/pr[d] for d in des)-1,limit=(k.get('limits') or [{}])[0].get('amount'),age=age))
            return res
        except Exception as e:
            print('pin err',sid,e,file=sys.stderr); return []
    with ThreadPoolExecutor(8) as ex:
        for r in ex.map(one,PIN_SPORTS): out+=r
    return out
# ---------- name matching ----------
STOP={'fc','afc','cf','sc','ac','ssc','sv','vfb','vfl','tsg','bv','fk','sk','cd','ud','rcd','club','de','calcio','the','as','us','rc','ogc',
      'cp','sd','ca','team','esports','esport','gaming','academy','u21','u23','ii','b','w','women','(w)','clube','sporting','fútbol','futbol','de'}
def norm(s):
    import unicodedata
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
    s=re.sub(r"[^a-z0-9 ]"," ",s)
    return ' '.join(w for w in s.split() if w not in STOP)
def sim(a,b):
    a,b=norm(a),norm(b)
    if not a or not b: return 0
    if a==b: return 1.0
    ta,tb=set(a.split()),set(b.split())
    if ta and tb and (ta<=tb or tb<=ta): return 0.92
    # surname match for tennis/mma
    if a.split()[-1]==b.split()[-1] and len(a.split()[-1])>3: s0=0.85
    else: s0=0
    return max(s0,difflib.SequenceMatcher(None,a,b).ratio())
def pm_sides(e):
    """extract (A,B) participant names from a Polymarket event title"""
    t=e['title']
    t=re.sub(r"^[^:]*:\s*","",t) if ':' in t.split(' vs')[0] else t
    t=re.sub(r"\s*\((BO\d|Bantamweight|[^)]*weight|Main Card|Prelims)[^)]*\).*$","",t)
    t=re.sub(r"\s+-\s+.*$","",t)
    parts=re.split(r"\s+vs\.?\s+",t)
    return (parts[0].strip(),parts[1].strip()) if len(parts)==2 else None
def pm_sport_events(hours_ahead=36):
    now=dt.datetime.now(dt.timezone.utc); evs=[]; cursor=None
    while True:
        p=dict(limit=100,active='true',closed='false',tag_id=1,start_date_min=(now-dt.timedelta(days=30)).isoformat())
        if cursor: p['after_cursor']=cursor
        r=get(f"{GAMMA}/events/keyset",p)
        if not r or not r.get('events'): break
        evs+=r['events']; cursor=r.get('next_cursor')
        if not cursor: break
    out=[]
    for e in evs:
        st=e.get('startTime')
        if not st: continue
        s=dt.datetime.fromisoformat(st.replace('Z','+00:00'))
        if not (now < s < now+dt.timedelta(hours=hours_ahead)): continue
        out.append(e)
    return out
def pm_moneyline(e):
    """returns list of (label, market, token_yes) for moneyline outcomes; soccer=3 markets, others=1 market 2 outcomes"""
    ms=[m for m in e.get('markets',[]) if m.get('active') and not m.get('closed') and m.get('clobTokenIds')]
    win=[m for m in ms if ' win on ' in m['question']]; draw=[m for m in ms if 'end in a draw' in m['question']]
    if len(win)==2 and len(draw)==1:
        out=[]
        for m in win: out.append(('team',m['question'].replace('Will ','').split(' win on')[0],m,json.loads(m['clobTokenIds'])[0],json.loads(m['clobTokenIds'])[1]))
        out.append(('draw','draw',draw[0],json.loads(draw[0]['clobTokenIds'])[0],json.loads(draw[0]['clobTokenIds'])[1]))
        return '3way',out
    ml=[m for m in ms if m.get('sportsMarketType')=='moneyline']
    if len(ml)==1:
        m=ml[0]; oc=json.loads(m['outcomes']); tk=json.loads(m['clobTokenIds'])
        if len(oc)==2 and 'Yes' not in oc: return '2way',[('team',oc[0],m,tk[0],tk[1]),('team',oc[1],m,tk[1],tk[0])]
    return None,None
def match_events(pm_evs, pin):
    pairs=[]
    for e in pm_evs:
        sides=pm_sides(e)
        kind,outs=pm_moneyline(e)
        if not sides or not kind: continue
        st=dt.datetime.fromisoformat(e['startTime'].replace('Z','+00:00'))
        best=None;bs=0;flip=False
        for p in pin:
            ps=dt.datetime.fromisoformat(p['start'].replace('Z','+00:00'))
            if abs((ps-st).total_seconds())>3600*1.5: continue
            if kind=='3way' and 'draw' not in p['fair']: continue
            if kind=='2way' and 'draw' in p['fair']: continue
            s1=min(sim(sides[0],p['home']),sim(sides[1],p['away'])); s2=min(sim(sides[0],p['away']),sim(sides[1],p['home']))
            s=max(s1,s2)
            if s>bs: bs,best,flip=s,p,(s2>s1)
        if best and bs>=0.6: pairs.append(dict(e=e,kind=kind,outs=outs,pin=best,score=bs,flip=flip,sides=sides))
    return pairs
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
def book_side(b,side):
    lv=[(float(x['price']),float(x['size'])) for x in (b.get(side) or [])]
    lv.sort(key=lambda x: x[0], reverse=(side=='bids'))
    return lv[:5]
