"""Per-market test on sponsored pools: earned fraction (on-chain) vs fraction of minutes with a scoring quote.

Usage: python sponsored_check.py YYYY-MM-DD   (the UTC day; refunds for it are sent at ~00:20 UTC the next day)
Sponsor contract 0xdd8db71c...a29e8b (verified ABI on Sourcify):
  SponsorRefunded(bytes32 marketId, address sponsor, uint256 amount)  topic0 0xed9899d2...  unearned part, per market
  DistributedRewards(address user, uint256 amount)                    topic0 0x0be93415...  maker payouts, NO market id
  Sponsored(bytes32 marketId, address sponsor, uint256 amount, uint32 start, uint32 end, uint256 ratePerMinute)
Earned(pool, day) = sponsored daily rate - refund. Prediction: rate x (minutes with a scoring quote / minutes
recorded). If pools whose recorded in-band book is a single maker are earned in proportion to their scoring
minutes, lone quoters are being paid.
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
t_day0 = t_pay - 86400
mins = collections.defaultdict(lambda: [0, 0, 0, 0.0])      # recorded, scoring, lone-like scoring, rate
n_snap = 0
for line in open('live/sponsored_books.jsonl'):
    x = json.loads(line)
    if not t_day0 <= x['ts'] < t_pay:
        continue
    n_snap += 1
    for c, (rate, v, ms, mid, q, shape) in x['pools'].items():
        m = mins[c]
        m[0] += 1
        m[3] = rate
        if q > 0:
            m[1] += 1
            if shape and shape[0] <= 1 and shape[2] <= 1:
                m[2] += 1
print(f"{day}: {n_snap} per-minute snapshots; {len(refund)} markets with sponsor refunds")
print("rate    refund  earned_frac  pred_frac(scoring minutes)  lone-like share of scoring minutes  cid")
for c in sorted(mins, key=lambda c: -mins[c][3]):
    m = mins[c]
    if not m[0] or m[3] <= 0:
        continue
    ref = sum(a for _, a in refund.get(c, []))
    earned = max(0.0, 1 - ref / m[3])
    print(f"{m[3]:7.3f} {ref:7.3f}  {earned:5.2f}  {m[1] / m[0]:5.2f}  {(m[2] / m[1]) if m[1] else 0:5.2f}  {c[:18]}")
