import json,sys,collections,glob
import numpy as np
def rows(fn):
    for l in open(fn):
        yield json.loads(l)
def edges(r):
    out=[]
    for o in r['outs']:
        if o['fair'] is None: continue
        f=o['fair']; rate=o['fee'] or 0
        if o['asks']:
            a,sz=o['asks'][0]; fee=rate*a*(1-a)
            out.append(dict(side='YES',label=o['label'],fair=f,px=a,size=sz,edge=f-a-fee,ev_roi=(f-a-fee)/a))
        if o['no_asks'] and r['kind']=='3way':
            a,sz=o['no_asks'][0]; fee=rate*a*(1-a)
            out.append(dict(side='NO',label=o['label'],fair=1-f,px=a,size=sz,edge=(1-f)-a-fee,ev_roi=((1-f)-a-fee)/a))
    return out
if __name__=='__main__':
    fn=sys.argv[1] if len(sys.argv)>1 else sorted(glob.glob('live/snap_*.jsonl'))[-1]
    last_ts=max(r['ts'] for r in rows(fn))
    R=[r for r in rows(fn) if r['ts']==last_ts]
    E=[]
    for r in R:
        for e in edges(r): e.update(sport=r['sport'],league=r['league'],title=r['title'][:55],age=r['age'],limit=r['limit'],start=r['start']); E.append(e)
    print('events',len(R),'edges',len(E))
    ed=np.array([e['edge'] for e in E]); print('edge pctiles',np.percentile(ed,[5,25,50,75,90,95,99]).round(4))
    by=collections.defaultdict(list)
    for e in E: by[e['sport']].append(e['edge'])
    for k,v in by.items(): print(k,len(v),'median',round(np.median(v),4),'p90',round(np.percentile(v,90),4),'n>2%',sum(1 for x in v if x>0.02))
    for e in sorted(E,key=lambda x:-x['edge'])[:25]:
        print(f"{e['edge']:+.3f} roi={e['ev_roi']:+.2%} {e['side']:3} {e['label'][:22]:22} fair={e['fair']:.3f} ask={e['px']:.3f} sz={e['size']:>8.0f} lim={e['limit']} age={e['age']} {e['sport']:8} {e['league'][:28]:28} {e['start'][5:16]} | {e['title']}")
