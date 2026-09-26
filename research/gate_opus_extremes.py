"""Claude Opus toxicity scores on the 30 worst vs 30 best markets (by farmer fill loss per $, >= $100 filled).
Needs data/gate_per_market.json (from gate_validate.py) and OPENROUTER_API_KEY. ~$0.55."""
import json, sys, numpy as np
sys.path.insert(0, '..')
from pmbot.jev import llm_review, SPENT
from pm import get, CLOB
from concurrent.futures import ThreadPoolExecutor
from scipy.stats import mannwhitneyu
per = json.load(open('data/gate_per_market.json'))
c = sorted([(k, d) for k, d in per.items() if d['vol'] >= 100], key=lambda x: x[1]['pnl'] / x[1]['vol'])
worst, best = c[:30], c[-30:]
def rev(item):
    k, d = item; m = get(f"{CLOB}/markets/{k}") or {}
    return llm_review(d['q'], m.get('description', ''), m.get('end_date_iso'), 'anthropic/claude-opus-5.5')
with ThreadPoolExecutor(6) as ex:
    W = list(ex.map(rev, worst)); B = list(ex.map(rev, best))
sc = lambda r: r['realtime'] + r['reveal_soon'] + r['news_speed'] / 3 + r['insider']
sw = [sc(r) for r in W if r]; sb = [sc(r) for r in B if r]
u, p = mannwhitneyu(sw, sb, alternative='greater')
print(f"AUC={u/(len(sw)*len(sb)):.3f} p={p:.3f} n={len(sw)}/{len(sb)} cost=${SPENT['usd']:.3f}")
