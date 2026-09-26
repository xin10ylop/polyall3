"""Backtest: Polymarket soccer 1X2 prices before kickoff vs Pinnacle closing (devigged)."""
import json, glob, csv, re, difflib, datetime as dt, math, sys, os
import numpy as np, pandas as pd
FEE_RATE=0.05
ALIAS={"nott'm forest":"nottingham forest","man city":"manchester city","man united":"manchester united","wolves":"wolverhampton",
 "sheffield weds":"sheffield wednesday","sheffield united":"sheffield united","qpr":"queens park rangers","west brom":"west bromwich",
 "ath madrid":"atletico madrid","ath bilbao":"athletic bilbao","betis":"real betis","sociedad":"real sociedad","celta":"celta vigo",
 "espanol":"espanyol","vallecano":"rayo vallecano","m'gladbach":"monchengladbach","ein frankfurt":"eintracht frankfurt",
 "fc koln":"koln","bayern munich":"bayern","leverkusen":"bayer leverkusen","paris sg":"paris saint germain","psg":"paris saint germain",
 "st etienne":"saint etienne","inter":"inter milan","milan":"ac milan","verona":"hellas verona","spal":"spal","sp lisbon":"sporting",
 "sp braga":"braga","st truiden":"sint truiden","st. gilloise":"union saint gilloise","ad. demirspor":"adana demirspor",
 "man utd":"manchester united","newcastle":"newcastle united","tottenham":"tottenham hotspur","brighton":"brighton",
 "leicester":"leicester city","ipswich":"ipswich town","luton":"luton town","hull":"hull city","stoke":"stoke city",
 "cardiff":"cardiff city","swansea":"swansea city","norwich":"norwich city","coventry":"coventry city","derby":"derby county",
 "oxford":"oxford united","plymouth":"plymouth argyle","preston":"preston north end","blackburn":"blackburn rovers","bristol city":"bristol city"}
STOP={'fc','afc','cf','sc','ac','ssc','sv','vfb','vfl','tsg','bv','1.','fk','sk','cd','ud','rcd','club','de','calcio','the','as','us','rc','ogc','losc','stade','olympique','sporting','cp','hsc','sd','ca','city','united','town'}
def norm(s):
    s=s.lower().replace('ü','u').replace('ö','o').replace('ä','a').replace('é','e').replace('á','a').replace('í','i').replace('ó','o').replace('ç','c').replace('ñ','n').replace('ã','a').replace('ş','s').replace('ı','i').replace('ğ','g')
    s=ALIAS.get(s.strip(),s)
    s=re.sub(r"[^a-z0-9 ]"," ",s)
    return ' '.join(w for w in s.split() if w not in STOP) or s
def sim(a,b):
    a,b=norm(a),norm(b)
    if a==b: return 1.0
    if a in b or b in a: return 0.9
    return difflib.SequenceMatcher(None,a,b).ratio()
def load_fd(L):
    rows=list(csv.DictReader(open(f'data/fd/2526_{L}.csv',encoding='utf-8-sig')))
    out=[]
    for r in rows:
        try: d=dt.datetime.strptime(r['Date'],'%d/%m/%Y').date()
        except Exception: continue
        o=None; src=None
        try: o=[float(r['PSCH']),float(r['PSCD']),float(r['PSCA'])]; src='PIN'
        except Exception:
            try: o=[float(r['BFECH']),float(r['BFECD']),float(r['BFECA'])]; src='BFE'
            except Exception: continue
        op=None
        try: op=[float(r['PSH']),float(r['PSD']),float(r['PSA'])]
        except Exception: pass
        bf=None
        try: bf=[float(r['BFECH']),float(r['BFECD']),float(r['BFECA'])]
        except Exception: pass
        out.append(dict(date=d,home=r['HomeTeam'],away=r['AwayTeam'],ftr=r['FTR'],psc=o,src=src,pso=op,bfc=bf))
    return out
def devig_mult(o):
    ip=[1/x for x in o]; s=sum(ip); return [x/s for x in ip]
def devig_power(o):
    ip=np.array([1/x for x in o]); lo,hi=0.5,2.0
    for _ in range(60):
        k=(lo+hi)/2; s=(ip**k).sum()
        if s>1: lo=k
        else: hi=k
    return list(ip**k/ (ip**k).sum())
def price_at(hist,t):
    best=None
    for h in hist:
        if h['t']<=t: best=h['p']
        else: break
    return best
def match(L):
    recs=json.load(open(f'data/soccer/{L}.json')); fd=load_fd(L)
    out=[]; miss=0
    for r in recs:
        ko=dt.datetime.fromisoformat(r['kickoff'].replace('Z','+00:00'))
        parts=r['title'].split(' vs. ')
        if len(parts)!=2: miss+=1; continue
        H,A=parts
        cands=[f for f in fd if abs((f['date']-ko.date()).days)<=1]
        best=None;bs=0
        for f in cands:
            s=min(sim(H,f['home']),sim(A,f['away']))
            if s>bs: bs,best=s,f
        if not best or bs<0.6: miss+=1; continue
        # identify markets
        mk={}
        for m in r['markets']:
            if 'draw' in m['q']: mk['D']=m
            elif sim(m['q'].replace('Will ','').split(' win on')[0],H)>=sim(m['q'].replace('Will ','').split(' win on')[0],A): mk['H']=m
            else: mk['A']=m
        if len(mk)!=3: miss+=1; continue
        out.append(dict(L=L,slug=r['slug'],ko=r['ko'],H=H,A=A,fd=best,score=bs,mk=mk))
    return out,miss
if __name__=='__main__':
    allm=[]
    for f in sorted(glob.glob('data/soccer/*.json')):
        L=os.path.basename(f)[:-5]
        ms,miss=match(L); allm+=ms
        print(L,'matched',len(ms),'missed',miss)
    import pickle; pickle.dump(allm,open('data/soccer_matched.pkl','wb'))
