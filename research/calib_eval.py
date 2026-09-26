"""Unbiased calibration of non-sports markets using fixed daily snapshots; clustered by market."""
import json, glob, datetime as dt, numpy as np, pandas as pd, sys
def P(s): return dt.datetime.fromisoformat(s.replace('Z','+00:00').replace(' ','T')) if s else None
RATES={'crypto_fees_v2':0.07,'crypto_fees':0.07,'culture_fees':0.05,'nofee':0.0,'politics_fees':0.04,'finance_prices_fees':0.04,'tech_fees':0.04,'economics_fees':0.05,'mentions_fees':0.04,'general_fees':0.05}
rows=[]
start=dt.datetime(2026,6,28,tzinfo=dt.timezone.utc)
snaps=[start+dt.timedelta(days=i) for i in range(0,89)]
for f in glob.glob('data/calib/*.json'):
    d=json.load(open(f)); m=d['m']; h=d['h']
    if len(h)<3: continue
    h.sort(key=lambda x:x['t'])
    ts=np.array([x['t'] for x in h]); ps=np.array([x['p'] for x in h])
    c=P(m.get('createdAt')) or P(m.get('startDate')); cl=P(m.get('closedTime')); en=P(m['endDate'])
    if not c or not cl or not en: continue
    rate=RATES.get(m['cat'],0.05) if m.get('feeRate') is None else float(m.get('feeRate') or 0)
    for S in snaps:
        if not (c+dt.timedelta(days=1) < S < cl): continue
        dte=(en-S).total_seconds()/86400
        if not (0 < dte <= 60): continue
        i=np.searchsorted(ts,S.timestamp(),side='right')-1
        if i<0 or S.timestamp()-ts[i]>6*3600: continue
        p=float(ps[i])
        if p<=0.001 or p>=0.999: continue
        rows.append((m['id'],m['cat'],S.date().isoformat(),p,dte,(cl-S).total_seconds()/86400,m['yes_won'],rate,float(m.get('volumeNum') or 0),m['question'][:80]))
df=pd.DataFrame(rows,columns=['mid','cat','snap','p','dte','dtr','won','rate','vol','q'])
df.to_pickle('data/calib_df.pkl')
print('rows',len(df),'markets',df.mid.nunique())
def clustered(x,g):
    """mean and cluster-robust SE of x grouped by g"""
    d=pd.DataFrame({'x':x,'g':g}); mu=d.x.mean()
    s=d.assign(r=d.x-mu).groupby('g').r.sum()
    se=np.sqrt((s**2).sum())/len(d); return mu,se
bins=[0,0.02,0.05,0.1,0.2,0.35,0.5,0.65,0.8,0.9,0.95,0.98,1]
df['b']=pd.cut(df.p,bins)
print('\nCalibration (all non-sports):')
g=df.groupby('b',observed=True).agg(n=('p','size'),mk=('mid','nunique'),p=('p','mean'),won=('won','mean'))
print(g.round(4).to_string())
# strategies: buy NO at price (1-p)+spread when p<=x ; buy YES when p>=y
SPREAD=0.01
def strat(d,side):
    if side=='NO':
        px=np.minimum(0.999,(1-d.p)+SPREAD); pay=1-d.won
    else:
        px=np.minimum(0.999,d.p+SPREAD); pay=d.won
    fee=d.rate*px*(1-px); ret=(pay-px-fee)/px
    return ret, px
print('\nStrategy returns (per $ staked, net of 1c spread + fee), clustered SE by market:')
for cat in ['ALL']+sorted(df.cat.unique()):
    d0=df if cat=='ALL' else df[df.cat==cat]
    for side,lo,hi in [('NO',0.0,0.05),('NO',0.05,0.15),('NO',0.15,0.3),('YES',0.85,0.95),('YES',0.95,0.99)]:
        d=d0[(d0.p>lo)&(d0.p<=hi)] if side=='NO' else d0[(d0.p>=lo)&(d0.p<hi)]
        if d.mid.nunique()<30: continue
        r,px=strat(d,side); mu,se=clustered(r.values,d.mid.values)
        hold=d.dtr.median()
        print(f'{cat:20} {side} p in ({lo},{hi}]: n={len(d):6} mk={d.mid.nunique():5} ret/$={mu:+.4f} se={se:.4f} t={mu/se:+.2f} med_hold_days={hold:5.1f} ret/day≈{mu/max(hold,0.5):+.5f}')
