import pickle, numpy as np, sys, collections
from soccer_bt import *
def build(allm, mins_before, spread_pen):
    rows=[]
    for m in allm:
        fair=devig_power(m['fd']['psc'])
        res={'H':0,'D':1,'A':2}[m['fd']['ftr']] if m['fd']['ftr'] in ('H','D','A') else None
        if res is None: continue
        t=m['ko']-mins_before*60
        for i,k in enumerate('HDA'):
            h=m['mk'][k]['hist']; p=price_at(h,t)
            if p is None or p<=0.01 or p>=0.99: continue
            won=1 if res==i else 0
            # YES buy
            ask=min(0.99,p+spread_pen); fee=FEE_RATE*ask*(1-ask)
            rows.append(dict(L=m['L'],slug=m['slug'],o=k,side='YES',mid=p,px=ask,fair=fair[i],edge=fair[i]-ask-fee,pnl=won-ask-fee,won=won))
            # NO buy
            nask=min(0.99,(1-p)+spread_pen); fee=FEE_RATE*nask*(1-nask)
            rows.append(dict(L=m['L'],slug=m['slug'],o=k,side='NO',mid=1-p,px=nask,fair=1-fair[i],edge=(1-fair[i])-nask-fee,pnl=(1-won)-nask-fee,won=1-won))
    return pd.DataFrame(rows)
if __name__=='__main__':
    allm=pickle.load(open('data/soccer_matched.pkl','rb'))
    print('matches',len(allm))
    # accuracy: logloss of PM mid vs Pinnacle close
    for mb in [170,60,15,5,1]:
        ll_pm=[];ll_pin=[];ab=[]
        for m in allm:
            if m['fd']['ftr'] not in ('H','D','A'): continue
            res={'H':0,'D':1,'A':2}[m['fd']['ftr']]
            ps=[price_at(m['mk'][k]['hist'],m['ko']-mb*60) for k in 'HDA']
            if None in ps: continue
            s=sum(ps); pn=[x/s for x in ps]; fair=devig_power(m['fd']['psc'])
            ll_pm.append(-math.log(max(1e-6,pn[res]))); ll_pin.append(-math.log(fair[res]))
            ab+= [abs(pn[i]-fair[i]) for i in range(3)]
        print(f'T-{mb:3}m n={len(ll_pm)} logloss PM={np.mean(ll_pm):.4f} PIN={np.mean(ll_pin):.4f}  mean|PM-PIN|={np.mean(ab):.4f} p90={np.percentile(ab,90):.4f}')
    for mb in [60,15,5]:
        for sp in [0.005,0.01]:
            df=build(allm,mb,sp)
            for th in [0.0,0.01,0.02,0.03,0.05]:
                d=df[df.edge>th]
                if len(d)==0: continue
                print(f'T-{mb}m spread+{sp} edge>{th:.2f}: bets={len(d):5} avg_px={d.px.mean():.3f} avg_edge={d.edge.mean():.4f} pnl/bet={d.pnl.mean():+.4f} ROI={d.pnl.sum()/d.px.sum():+.3%} se={d.pnl.std()/np.sqrt(len(d)):.4f}')
