"""Per-minute books of every sponsored reward pool, for a direct public test of lone-quoter payouts.

Sponsored pools are scored like native pools. The sponsor contract (0xdd8db71c...a29e8b) refunds the unearned part
of each pool per market on-chain (SponsorRefunded, ~00:20 UTC), so each pool's earned fraction is public. With
per-minute books we can compare it with the fraction of minutes that had a scoring quote, and check whether pools
whose only quoter is a single maker are earned (i.e. paid out) for those minutes (see sponsored_check.py).
Output: live/sponsored_books.jsonl  (one line per minute: {ts, pools: {cid: [rate, v, min_size, mid, q_min, shape]}})
"""
import sys, json, time, traceback
sys.path.insert(0, '/home/user/polyall3')
from pmbot import api, scoring

OUT = 'live/sponsored_books.jsonl'
pools, tokens, last_list = {}, {}, 0
while True:
    t0 = time.time()
    try:
        if t0 - last_list > 1800:          # sponsored set changes slowly
            rm = [r for r in api.rewarded_markets() if float(r.get('sponsored_daily_rate') or 0) > 0]
            pools = {r['condition_id']: r for r in rm}
            new = [c for c in pools if c not in tokens]
            for c, m in api.clob_markets(new).items():
                if m and m.get('tokens') and len(m['tokens']) == 2:
                    tokens[c] = m['tokens'][0]['token_id']
            last_list = t0
        bk = api.books([tokens[c] for c in pools if c in tokens])
        out = {}
        for c, r in pools.items():
            b = bk.get(tokens.get(c))
            v, ms = float(r['rewards_max_spread']), float(r['rewards_min_size'])
            rate = float(r.get('sponsored_daily_rate') or 0)
            if not b:
                out[c] = [rate, v, ms, None, 0.0, None]
                continue
            bids, asks = scoring.levels(b, 'bids'), scoring.levels(b, 'asks')
            ab = scoring.adjusted_best(bids, ms) if bids else None
            aa = scoring.adjusted_best(asks, ms) if asks else None
            if ab is None or aa is None or aa <= ab:
                out[c] = [rate, v, ms, None, 0.0, None]
                continue
            mid = (ab + aa) / 2
            fb, fa = [x for x in bids if x[1] >= ms], [x for x in asks if x[1] >= ms]
            q = scoring.q_min(scoring.side_q(fb, mid, v, True), scoring.side_q(fa, mid, v, False), mid)
            lb = [(p, s) for p, s in fb if 0 <= (mid - p) * 100 < v]
            la = [(p, s) for p, s in fa if 0 <= (p - mid) * 100 < v]
            out[c] = [rate, v, ms, round(mid, 4), round(q, 2), [len(lb), round(sum(s for _, s in lb), 1),
                                                                 len(la), round(sum(s for _, s in la), 1)]]
        with open(OUT, 'a') as f:
            f.write(json.dumps({'ts': int(t0), 'pools': out}) + '\n')
    except Exception:
        traceback.print_exc()
    time.sleep(max(5, 60 - (time.time() - t0)))
