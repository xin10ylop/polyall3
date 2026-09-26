"""Per-market test on sponsored pools: earned fraction (on-chain) vs fraction of minutes with a scoring quote.

Usage: python sponsored_check.py YYYY-MM-DD   (the UTC day; refunds for it are sent at ~00:20 UTC the next day)
Sponsor contract 0xdd8db71c...a29e8b (verified ABI on Sourcify):
  SponsorRefunded(bytes32 marketId, address sponsor, uint256 amount)  topic0 0xed9899d2...  unearned part, per market
  DistributedRewards(address user, uint256 amount)                    topic0 0x0be93415...  maker payouts, NO market id
  Sponsored(bytes32 marketId, address sponsor, uint256 amount, uint32 start, uint32 end, uint256 ratePerMinute)
Earned(pool, day) = what the sponsorship funded that day (sponsorInfo: ratePerMinute x funded minutes) - refund.
Prediction: fraction of recorded minutes with a scoring quote. This tests per-minute accrual. It cannot isolate lone
quoters: public books aggregate makers per price level (audit #6).
"""
import sys, json, requests, datetime as dt, collections

RPC = "https://polygon-bor-rpc.publicnode.com"
SPONSOR = "0xdd8db71ce3be8d71ff148b2163d64da181a29e8b"
REFUND = "0xed9899d2f5991ab401db3fd79f595fad984d6d1ab33d32552b733b9df116b1ae"   # SponsorRefunded


def rpc(m, p):
    r = requests.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": m, "params": p}, timeout=60).json()
    if "error" in r:
        raise Exception(r["error"])
    return r["result"]


def block_at(ts):
    hi = int(rpc("eth_blockNumber", []), 16)
    lo = hi - 200000
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if int(rpc("eth_getBlockByNumber", [hex(mid), False])["timestamp"], 16) < ts:
            lo = mid
        else:
            hi = mid
    return hi


day = dt.date.fromisoformat(sys.argv[1])
t_pay = int(dt.datetime.combine(day + dt.timedelta(days=1), dt.time(), dt.timezone.utc).timestamp())
b0, b1 = block_at(t_pay), block_at(t_pay + 2 * 3600)
refund = collections.defaultdict(list)
b = b0
while b < b1:
    e = min(b1, b + 1000)
    for l in rpc("eth_getLogs", [{"fromBlock": hex(b), "toBlock": hex(e), "address": SPONSOR, "topics": [REFUND]}]):
        refund[l["topics"][1]].append(("0x" + l["topics"][2][-40:], int(l["data"], 16) / 1e6))
    b = e + 1


def funded_on_day(market, sponsor, t0, t1):
    """What a sponsorship funded during [t0, t1): ratePerMinute x the funded minutes inside the day.
    sponsorInfo(address,bytes32) -> (deposited, ratePerMinute, consumed, refunded, start, end, active)."""
    data = "0xfd5aa6f0" + "0" * 24 + sponsor[2:] + market[2:]
    r = rpc("eth_call", [{"to": SPONSOR, "data": data}, "latest"])[2:]
    w = [int(r[i * 64:(i + 1) * 64], 16) for i in range(7)]
    rpm, start, end = w[1] / 1e6, w[4], w[5]
    return rpm * max(0, min(end, t1) - max(start, t0)) / 60


t_day0 = t_pay - 86400
mins = collections.defaultdict(lambda: [0, 0, 0, 0.0])      # recorded, scoring, lone-like scoring, rate
n_snap, inrange = 0, collections.Counter()
for line in open('live/sponsored_books.jsonl'):
    x = json.loads(line)
    if not t_day0 <= x['ts'] < t_pay:
        continue
    n_snap += 1
    for c, (rate, v, ms, mid, q, shape) in x['pools'].items():
        if v > 0 and mid is not None and 0.10 <= mid <= 0.90:
            inrange[c] += 1
        m = mins[c]
        m[0] += 1
        m[3] = rate
        if q > 0:
            m[1] += 1
            if shape and shape[0] <= 1 and shape[2] <= 1:
                m[2] += 1
valid = {c for c, k in inrange.items() if k >= 0.9 * n_snap}
print(f"{day}: {n_snap} per-minute snapshots; {len(refund)} markets with sponsor refunds")
print("funded  refund  earned_frac  pred_frac(scoring minutes)  lone-like share  cid   (pred n/a: no band config or"
      " mid outside 0.10-0.90, where two-sided makers are required and books cannot show them)")
for c in sorted(refund, key=lambda c: -sum(a for _, a in refund[c])):
    funded = sum(funded_on_day(c, sp, t_day0, t_pay) for sp in {sp for sp, _ in refund[c]})
    ref = sum(a for _, a in refund[c])
    earned = max(0.0, 1 - ref / funded) if funded > 0 else float("nan")
    m = mins.get(c, [0, 0, 0, 0.0])
    ok = c in valid
    pred = f"{m[1] / m[0]:5.2f}" if m[0] and ok else "  n/a"
    print(f"{funded:7.3f} {ref:7.3f}  {earned:5.2f}  {pred}  {(m[2] / m[1]) if m[1] else 0:5.2f}  {c[:18]}")
# Pools with no SponsorRefunded event were either fully earned or not sponsored that day; list the recorded ones.
print("recorded pools with no refund event (fully earned, or no sponsorship that day):")
for c, m in sorted(mins.items(), key=lambda x: -x[1][3]):
    if c not in refund and m[3] > 0:
        pred = f"{m[1] / m[0]:5.2f}" if m[0] and c in valid else "  n/a"
        print(f"  listed rate {m[3]:7.3f}  pred_frac {pred}  {c[:18]}")
