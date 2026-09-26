"""Farmer fill losses vs market trading volume (data/gate_per_market.json from gate_validate.py)."""
import json, numpy as np
from pm import S, GAMMA
from concurrent.futures import ThreadPoolExecutor
from scipy.stats import spearmanr
per = json.load(open('data/gate_per_market.json'))
cids = [c for c, d in per.items() if d['vol'] >= 20]
def gm(ch):
    try:
        r = S.get(f"{GAMMA}/markets", params=[('condition_ids', c) for c in ch] + [('limit', len(ch))], timeout=30).json()
        return r if isinstance(r, list) else []
    except Exception:
        return []
vols = {}
with ThreadPoolExecutor(6) as ex:
    for r in ex.map(gm, [cids[i:i+40] for i in range(0, len(cids), 40)]):
        for m in r: vols[m['conditionId']] = float(m.get('volumeNum') or 0)
a = np.array([(per[c]['pnl'], per[c]['vol'], vols[c]) for c in cids if c in vols])
print('markets', len(a), 'spearman(fill $, volume)', round(spearmanr(a[:,1], a[:,2])[0], 3))
q = np.quantile(a[:,2], [0.25, 0.5, 0.75])
for lo, hi in zip([-1]+list(q), list(q)+[1e12]):
    m = (a[:,2] > lo) & (a[:,2] <= hi)
    print(f"volume ({lo:.0f},{hi:.0f}]: n={m.sum()} loss/$filled={-a[m,0].sum()/a[m,1].sum():.4f} loss$/mkt={-a[m,0].mean():.2f}")
