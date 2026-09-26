"""Uncontested / quiet reward pools from the pool tracker (live/pool_tracker.jsonl), with consistent definitions.
Run from a working directory containing pm.py, live/ and data/ (see research/README.md)."""
import json, time, datetime as dt, re, sys, numpy as np
from pm import *
from concurrent.futures import ThreadPoolExecutor
tr = [json.loads(l) for l in open('live/pool_tracker.jsonl')]
t0, t1 = tr[0]['ts'], tr[-1]['ts']
print(f"window: {dt.datetime.utcfromtimestamp(t0):%Y-%m-%d %H:%M} -> {dt.datetime.utcfromtimestamp(t1):%H:%M} UTC "
      f"({(t1-t0)/3600:.2f} h, {len(tr)} snapshots)")
snap_unc = [sum(m['rate'] for m in s['m'] if m['q1'] + m['q2'] == 0) for s in tr]
print(f"uncontested at a single moment: ${min(snap_unc):,.0f}-${max(snap_unc):,.0f}/day (median ${np.median(snap_unc):,.0f})")
first = {m['cid']: m for m in tr[0]['m']}
stable = [c for c in first if all(any(m['cid'] == c and m['q1'] + m['q2'] == 0 for m in s['m']) for s in tr)]
print(f"uncontested in every snapshot: {len(stable)} pools, ${sum(first[c]['rate'] for c in stable):,.0f}/day")
now = time.time()
def info(c):
    t = get(f"{DATA}/trades", dict(market=c, limit=500, _=time.time_ns()))
    t = [x for x in (t or []) if x['timestamp'] > now - 86400]
    ps = [float(x['price']) if x.get('outcomeIndex', 0) == 0 else 1 - float(x['price']) for x in t]
    m = get(f"{CLOB}/markets/{c}") or {}
    r = (get(f"{CLOB}/rewards/markets/{c}") or {}).get('data') or [{}]
    return c, len(t), sum(float(x['size']) * float(x['price']) for x in t), (max(ps) - min(ps)) if ps else 0.0, m, r[0]
with ThreadPoolExecutor(8) as ex:
    I = list(ex.map(info, stable))
n = np.array([x[1] for x in I]); usd = np.array([x[2] for x in I])
print(f"24h trades per pool p50/p75/p90: {np.percentile(n,[50,75,90])}; 24h $ p50/p75/p90: {np.percentile(usd,[50,75,90]).round(0)}")
quiet = [x for x in I if x[1] <= 3 and x[3] < 0.03]
print(f"quiet (<=3 trades and <3c range in 24h): {len(quiet)} pools, ${sum(first[x[0]]['rate'] for x in quiet):,.0f}/day")
nowdt = dt.datetime.now(dt.timezone.utc)
def addressable(x):
    c, ntr, u, rng, m, r = x
    try:
        end = dt.datetime.fromisoformat(m['end_date_iso'].replace('Z', '+00:00'))
    except Exception:
        return False
    return ((end - nowdt).total_seconds() > 72 * 3600 and 0.10 <= first[c]['mid'] <= 0.90
            and u <= 1000 and rng <= 0.10 and not re.search(r"temperature|precipitation|°|Up or Down", m.get('question', ''), re.I))
A = [x for x in I if addressable(x)]
ms = np.array([float(x[5].get('rewards_min_size') or 20) for x in A])
coll = sum(2 * float(x[5].get('rewards_min_size') or 20) * min(first[x[0]]['mid'], 1 - first[x[0]]['mid']) + 0 for x in A)
print(f"bot-addressable (end >72h, mid 0.10-0.90, <=$1k & <=10c in 24h, no weather): {len(A)} pools, "
      f"${sum(first[x[0]]['rate'] for x in A):,.0f}/day; min_size p50/p90 {np.percentile(ms,[50,90]) if len(ms) else '-'}")
json.dump([{'cid': x[0], 'trades24': x[1], 'usd24': x[2], 'rng24': x[3], 'rate': first[x[0]]['rate'],
            'q': x[4].get('question', ''), 'end': x[4].get('end_date_iso'), 'min_size': x[5].get('rewards_min_size')}
           for x in I], open('data/quiet_pools.json', 'w'))
