"""Summarise live/payout_check.jsonl: predicted payable reward rate (all pools with a scoring quote, strict and loose)
vs the lone-quoter-like subset, and actual on-chain payouts per UTC day."""
import json, sys, datetime as dt, collections

f = sys.argv[1] if len(sys.argv) > 1 else 'live/payout_check.jsonl'
snaps, paid = [], {}
for line in open(f):
    x = json.loads(line)
    if 'paid' in x:
        paid[x['paid']['day']] = x['paid']
    elif x.get('pools') and len(x['pools'][0]) >= 5:
        snaps.append(x)


def lone(shape):
    """In-band book looks like a single maker: at most one level per side, each <= 2x min size."""
    if not shape:
        return False
    nb, sb, na, sa, ms = shape
    return nb <= 1 and na <= 1 and sb <= 2 * ms and sa <= 2 * ms


by_day = collections.defaultdict(list)
for s in snaps:
    listed = sum(p[1] for p in s['pools'])
    loose = sum(p[1] for p in s['pools'] if p[2] > 0)
    strict = sum(p[1] for p in s['pools'] if p[3] > 0)
    lone_r = sum(p[1] for p in s['pools'] if p[3] > 0 and lone(p[4]))
    day = dt.datetime.utcfromtimestamp(s['ts']).date().isoformat()
    by_day[day].append((s['ts'], listed, loose, strict, lone_r))
    print(dt.datetime.utcfromtimestamp(s['ts']).strftime('%m-%d %H:%M'), f"listed {listed:9.0f}  payable loose {loose:9.0f}"
          f"  strict {strict:9.0f}  lone-like {lone_r:8.0f} ({lone_r / max(strict, 1):.0%} of strict)")
for day, rows in sorted(by_day.items()):
    span = (rows[-1][0] - rows[0][0]) / 3600
    avg = [sum(r[i] for r in rows) / len(rows) for i in range(1, 5)]
    p = paid.get(day, {}).get('paid_usd')
    print(f"{day}: {len(rows)} snapshots over {span:.1f} h | avg listed {avg[0]:.0f} loose {avg[1]:.0f} strict {avg[2]:.0f}"
          f" lone-like {avg[3]:.0f} | paid {p}")
    if p:
        print(f"   paid / strict = {p / avg[2]:.3f}; paid / (strict - lone-like) = {p / max(avg[2] - avg[3], 1):.3f}")
