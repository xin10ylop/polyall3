"""Why are $64k/day of reward pools empty? Break the empty pools down by the reason the bot would skip them."""
import json, sys, re, datetime as dt, collections
sys.path.insert(0, '/home/user/polyall3')
from pmbot import api, scoring
from pmbot.config import CFG
S = './'   # run from the directory that holds live/payout_check.jsonl
snap = [json.loads(l) for l in open(S + 'live/payout_check.jsonl') if '"pools"' in l][-1]
rm = {r['condition_id']: r for r in api.rewarded_markets()}
empty = [(cid, rate) for cid, rate, q, qs, sh in snap['pools'] if qs <= 0]
info = api.clob_markets([c for c, _ in empty], workers=12)
bk = api.books([m['tokens'][0]['token_id'] for m in info.values() if m and m.get('tokens') and len(m['tokens']) == 2])
rx = re.compile(CFG['exclude_regex'], re.I)
now = dt.datetime.now(dt.timezone.utc)
why = collections.Counter(); n = collections.Counter(); samples = collections.defaultdict(list)
for cid, rate in empty:
    m, r = info.get(cid), rm.get(cid)
    if not m or not r:
        k = 'gone'
    elif m.get('closed') or not m.get('accepting_orders'):
        k = 'closed/not accepting'
    elif rx.search(m.get('question') or ''):
        k = 'weather/up-down'
    else:
        try:
            hrs = (dt.datetime.fromisoformat(m['end_date_iso'].replace('Z', '+00:00')) - now).total_seconds() / 3600
        except Exception:
            hrs = 1e9
        b = bk.get(m['tokens'][0]['token_id'])
        if hrs < 72:
            k = 'ends <72h'
        elif not b:
            k = 'no book'
        else:
            ms = float(r['rewards_min_size'])
            st = scoring.book_state(b, max(ms, 5), float(r['rewards_max_spread']))
            if not st:
                k = 'one-sided/empty book'
            elif not (0.10 <= st['mid'] <= 0.90):
                k = 'mid outside 0.10-0.90'
            else:
                k = 'addressable (bot filters next: roi/activity)'
                samples[k].append((rate, m.get('question', '')[:70], round(st['mid'], 3), ms))
    why[k] += rate; n[k] += 1
for k, v in why.most_common():
    print(f"{k:45s} ${v:9.0f}/day  {n[k]:5d} pools")
for s in sorted(samples['addressable (bot filters next: roi/activity)'], reverse=True)[:15]:
    print(s)
