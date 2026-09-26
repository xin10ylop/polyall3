"""Compare on-chain sponsored-reward payouts per market with the per-minute books from sponsored_recorder.py.

Usage: python sponsored_check.py YYYY-MM-DD   (the UTC day whose rewards were paid at ~00:20 UTC the next day)
Keyed payouts: sponsor contract event 0xed9899d2 (topic1 = conditionId, topic2 = recipient, data = amount).
Prediction per pool: sponsored rate x (minutes with a scoring quote / minutes recorded). A pool paid to a single
wallet with a single in-band quote structure is the lone-quoter case.
"""
import sys, json, requests, datetime as dt, collections

RPC = "https://polygon-bor-rpc.publicnode.com"
SPONSOR = "0xdd8db71ce3be8d71ff148b2163d64da181a29e8b"
KEYED = "0xed9899d2f5991ab401db3fd79f595fad984d6d1ab33d32552b733b9df116b1ae"


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
paid = collections.defaultdict(list)
b = b0
while b < b1:
    e = min(b1, b + 1000)
    for l in rpc("eth_getLogs", [{"fromBlock": hex(b), "toBlock": hex(e), "address": SPONSOR, "topics": [KEYED]}]):
        paid[l["topics"][1]].append(("0x" + l["topics"][2][-40:], int(l["data"], 16) / 1e6))
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
print(f"{day}: {n_snap} per-minute snapshots; {len(paid)} markets with keyed payouts")
print("paid  recipients  rate   pred(rate x scoring-minutes share)  lone-like share  cid")
for c in sorted(set(paid) | {c for c, m in mins.items() if m[1]}, key=lambda c: -sum(a for _, a in paid.get(c, []))):
    m = mins.get(c, [0, 0, 0, 0.0])
    p = sum(a for _, a in paid.get(c, []))
    pred = m[3] * m[1] / m[0] if m[0] else None
    print(f"{p:7.3f}  {len(paid.get(c, [])):3d}  {m[3]:7.3f}  {pred if pred is None else round(pred, 3)!s:>8}  "
          f"{(m[2] / m[1]) if m[1] else 0:5.2f}  {c[:18]}")
