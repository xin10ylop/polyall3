"""Public test of lone-quoter payouts on NATIVE pools.

Usage (from the dir holding live/payout_check.jsonl): python lone_maker_check.py YYYY-MM-DD
1. From payout_check snapshots of day D (every 15 min), find pools whose in-band book looks like ONE maker
   (strict Q_min > 0, <= 1 price level per side, each <= 2x min size) in most snapshots.
2. A trade in such a pool identifies the resting maker (data-api maker legs = takerOnly=false rows minus taker rows).
3. For each such maker W, compare its native REWARD paid at ~00:00 UTC on D+1 (distributor batch) with what a lone
   quoter should earn from those pools (rate x lone fraction), and list W's other maker activity on D.
A wallet with no other maker markets whose payout matches the prediction is a paid lone quoter; a payout far below it
is evidence against lone-quoter payment (or that W was not the resting maker for most of the day).
"""
import sys, json, time, datetime as dt, collections, requests
from concurrent.futures import ThreadPoolExecutor

DATA = "https://data-api.polymarket.com"
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"


def get(url, params):
    for i in range(4):
        try:
            r = s.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(1 + i)
    return None


def lone(shape):
    if not shape:
        return False
    nb, sb, na, sa, ms = shape
    return nb <= 1 and na <= 1 and sb <= 2 * ms and sa <= 2 * ms


day = dt.date.fromisoformat(sys.argv[1])
t0 = int(dt.datetime.combine(day, dt.time(), dt.timezone.utc).timestamp())
t1 = t0 + 86400
snaps = [x for x in map(json.loads, open('live/payout_check.jsonl'))
         if 'pools' in x and t0 <= x['ts'] < t1 and len(x['pools'][0]) >= 5]
n = len(snaps)
print(f"{day}: {n} snapshots covering {((snaps[-1]['ts'] - snaps[0]['ts']) / 3600 if n else 0):.1f} h")
cnt, rate = collections.Counter(), {}
for sn in snaps:
    for cid, r, q, qs, sh in sn['pools']:
        rate[cid] = r
        if qs > 0 and lone(sh):
            cnt[cid] += 1
cands = {c: k / n for c, k in cnt.items() if k / n >= 0.6 and rate[c] >= 5}
print(f"pools lone-like in >= 60% of snapshots (rate >= $5): {len(cands)}, ${sum(rate[c] for c in cands):.0f}/day")


def makers(cid):
    a = get(f"{DATA}/trades", {"market": cid, "limit": 500, "takerOnly": "false", "_": time.time_ns()}) or []
    tk = get(f"{DATA}/trades", {"market": cid, "limit": 500, "takerOnly": "true", "_": time.time_ns()}) or []
    key = lambda t: (t["transactionHash"], t["proxyWallet"], t["asset"], t["size"], t["price"])
    tks = {key(t) for t in tk}
    return cid, {t["proxyWallet"].lower() for t in a if key(t) not in tks and t0 <= t["timestamp"] < t1}


with ThreadPoolExecutor(8) as ex:
    mk = dict(ex.map(makers, list(cands)))
by_w = collections.defaultdict(list)
for cid, ws in mk.items():
    for w in ws:
        by_w[w].append(cid)
print(f"maker wallets identified in those pools: {len(by_w)}")


def profile(w):
    rw = get(f"{DATA}/activity", {"user": w, "type": "REWARD", "start": t1 - 60, "end": t1 + 900, "limit": 50}) or []
    native = sum(float(x.get("usdcSize") or 0) for x in rw if x["timestamp"] < t1 + 300)   # distributor ~00:00:15
    a = get(f"{DATA}/trades", {"user": w, "limit": 500, "takerOnly": "false"}) or []
    tk = get(f"{DATA}/trades", {"user": w, "limit": 500, "takerOnly": "true"}) or []
    key = lambda t: (t["transactionHash"], t["asset"], t["size"], t["price"])
    tks = {key(t) for t in tk}
    mm = {t["conditionId"] for t in a if key(t) not in tks and t0 <= t["timestamp"] < t1}
    return w, native, mm


with ThreadPoolExecutor(6) as ex:
    prof = list(ex.map(profile, list(by_w)))
print("native_paid  predicted_lone  other_maker_mkts(rewarded, $/day)  lone pools")
for w, native, mm in sorted(prof, key=lambda x: -sum(rate[c] * cands[c] for c in by_w[x[0]])):
    pred = sum(rate[c] * cands[c] for c in by_w[w])
    other = [c for c in mm if c not in by_w[w]]
    other_r = sum(rate.get(c, 0) for c in other)
    print(f"{native:9.2f}  {pred:9.2f}   {len(other):3d} ({sum(1 for c in other if c in rate)}, ${other_r:.0f})  "
          f"{[(round(rate[c]), round(cands[c], 2), len(mk[c])) for c in by_w[w]]}  {w}")
print("(lone pools: (rate $/day, lone-like fraction of snapshots, maker wallets filled in that pool on D)."
      " Cleanest cases: one maker wallet in the pool and no other maker markets.)")
