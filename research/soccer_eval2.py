import pickle, numpy as np, collections
from soccer_bt import *
from soccer_eval import build
allm=pickle.load(open('data/soccer_matched.pkl','rb'))
print('matches',len(allm), collections.Counter(m['fd']['src'] for m in allm))
# per league accuracy
print('\nLogloss by league at T-5m (PM normalized mid vs sharp close):')
for L in sorted(set(m['L'] for m in allm)):
    ll_pm=[];ll_pin=[];ab=[]
    for m in allm:
        if m['L']!=L or m['fd']['ftr'] not in ('H','D','A'): continue
        res={'H':0,'D':1,'A':2}[m['fd']['ftr']]
        ps=[price_at(m['mk'][k]['hist'],m['ko']-300) for k in 'HDA']
        if None in ps: continue
        s=sum(ps); pn=[x/s for x in ps]; fair=devig_power(m['fd']['psc'])
        ll_pm.append(-math.log(max(1e-6,pn[res]))); ll_pin.append(-math.log(fair[res])); ab+=[abs(pn[i]-fair[i]) for i in range(3)]
    print(f'{L:4} n={len(ll_pm):4} PM={np.mean(ll_pm):.4f} SHARP={np.mean(ll_pin):.4f} diff={np.mean(ll_pm)-np.mean(ll_pin):+.4f} mean|dev|={np.mean(ab):.4f}')
print()
for mb in [120,60,15,5]:
    df=build(allm,mb,0.005)
    for th in [0.0,0.01,0.02,0.03]:
        d=df[df.edge>th]
        print(f'T-{mb:3}m ask=mid+0.5c edge>{th:.2f}: bets={len(d):5} avg_px={d.px.mean():.3f} avg_edge={d.edge.mean():.4f} pnl/bet={d.pnl.mean():+.4f} ROI={d.pnl.sum()/d.px.sum():+.2%} t={d.pnl.mean()/(d.pnl.std()/np.sqrt(len(d))):+.2f}')
