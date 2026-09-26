"""Does the Jev gate reduce fill losses INSIDE uncontested quiet pools? Joins the 7-day risk backtest
(data/quiet_risk_bt.json from quiet_risk_bt.py) with Jev scores (data/jev_tox_quiet.json)."""
import json, sys, numpy as np
sys.path.insert(0, '..')
from pmbot.config import CFG
from pmbot.jev import is_safe
bt = {r['cid']: r for r in json.load(open('data/quiet_risk_bt.json'))}
tox = json.load(open('data/jev_tox_quiet.json'))
rows = [(bt[c], t) for c, t in tox.items() if c in bt and t]
for lab, f in [('PASS', lambda t: is_safe(t, CFG)), ('FAIL', lambda t: not is_safe(t, CFG)),
               ('insider>0.6', lambda t: t['insider'] > 0.6), ('insider<=0.6', lambda t: t['insider'] <= 0.6)]:
    x = [(b, t) for b, t in rows if f(t)]
    adv = sum(b['adverse_per_day'] for b, t in x); rew = sum(b['rate'] for b, t in x)
    print(f"{lab:13} pools={len(x):3} reward ${rew:6.0f}/d adverse ${adv:6.1f}/d adverse/reward={adv/max(rew,1):.3f}")
