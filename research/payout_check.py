"""Aggregate payout check: does Polymarket pay out the listed reward pools where someone quotes?

1. On-chain: sum every reward transfer (pUSD, from the rewards distributor) for recent UTC days.
2. Every 15 min: for EVERY rewarded market (all categories), compute the pool's total Q_min from the live book
   (formula: S(v,s) = ((v-s)/v)^2 x size, single-sided at 1/3 inside [0.10, 0.90]). The formula predicts that a pool
   pays out in full if Q_min > 0 and nothing otherwise.
3. Compare the predicted payable rate with what was actually paid. This is an aggregate consistency check of the
   formula; it cannot identify individual (e.g. lone) quoters.
Output: live/payout_check.jsonl
"""
import sys, json, time, datetime as dt, requests, traceback
sys.path.insert(0, '/home/user/polyall3')
from pmbot import api, scoring

RPC = "https://polygon-bor-rpc.publicnode.com"
TR = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
DISTRIBUTOR = "0x2c2795ea295d5eb51f9121b728ed2ea4e936a709"      # sender of all REWARD transfers (data-api tx hashes)
PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
OUT = 'live/payout_check.jsonl'


def rpc(m, p):
    r = requests.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": m, "params": p}, timeout=60).json()
    if "error" in r:
        raise Exception(r["error"])
    return r["result"]


def block_at(ts):
    hi = int(rpc("eth_blockNumber", []), 16)
    lo = hi - 400000
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if int(rpc("eth_getBlockByNumber", [hex(mid), False])["timestamp"], 16) < ts:
            lo = mid
        else:
            hi = mid
    return hi


def paid_for_day(day):
    """Rewards for UTC day D are paid shortly after 00:00 UTC of D+1: sum distributor transfers in [00:00, 03:00]."""
    t0 = int(dt.datetime.combine(day + dt.timedelta(days=1), dt.time(), dt.timezone.utc).timestamp())
    b0, b1 = block_at(t0 - 600), block_at(t0 + 3 * 3600)
    tot, n, b, step, errs = 0.0, 0, b0, 2000, 0
    while b < b1:
        e = min(b1, b + step)
        try:
            lg = rpc("eth_getLogs", [{"fromBlock": hex(b), "toBlock": hex(e), "address": PUSD,
                                      "topics": [TR, "0x" + "0" * 24 + DISTRIBUTOR[2:]]}])
        except Exception as ex:
            errs += 1
            if "pruned" in str(ex) or errs > 20:      # the public RPC keeps logs for ~1 day only
                raise
            step = max(100, step // 2)
            time.sleep(1)
            continue
        tot += sum(int(l["data"], 16) / 1e6 for l in lg)
        n += len(lg)
        b = e + 1
    return {"day": day.isoformat(), "paid_usd": round(tot, 2), "recipients": n}


def snapshot(info):
    rm = api.rewarded_markets()
    new = [r['condition_id'] for r in rm if r['condition_id'] not in info]
    if new:
        info.update({k: v for k, v in api.clob_markets(new, workers=12).items() if v})
    toks = {}
    for r in rm:
        m = info.get(r['condition_id'])
        if m and m.get('tokens') and len(m['tokens']) == 2 and not m.get('closed'):
            toks[r['condition_id']] = m['tokens'][0]['token_id']
    bk = api.books(list(toks.values()))
    listed = payable = 0.0
    n_pay = n_empty = 0
    rows = []
    for r in rm:
        rate = float(r.get('total_daily_rate') or 0)
        listed += rate
        b = bk.get(toks.get(r['condition_id']))
        qmin, qstrict, shape = 0.0, 0.0, None
        if b:
            v, ms = float(r['rewards_max_spread']), float(r['rewards_min_size'])
            bids, asks = scoring.levels(b, 'bids'), scoring.levels(b, 'asks')
            ab = scoring.adjusted_best(bids, ms) if bids else None
            aa = scoring.adjusted_best(asks, ms) if asks else None
            if ab is not None and aa is not None and aa > ab:
                mid = (ab + aa) / 2
                q1, q2 = scoring.side_q(bids, mid, v, True), scoring.side_q(asks, mid, v, False)
                qmin = scoring.q_min(q1, q2, mid)
                # strict: a price level smaller than min_size cannot hold a qualifying order
                fb, fa = [x for x in bids if x[1] >= ms], [x for x in asks if x[1] >= ms]
                qstrict = scoring.q_min(scoring.side_q(fb, mid, v, True), scoring.side_q(fa, mid, v, False), mid)
                lb = [(p, s) for p, s in bids if 0 <= (mid - p) * 100 < v]
                la = [(p, s) for p, s in asks if 0 <= (p - mid) * 100 < v]
                # book shape inside the band: (#levels, total size) per side, and min size -> lone-quoter proxy
                shape = (len(lb), round(sum(s for _, s in lb), 1), len(la), round(sum(s for _, s in la), 1), ms)
        if qmin > 0:
            payable += rate
            n_pay += 1
        else:
            n_empty += 1
        rows.append((r['condition_id'], rate, round(qmin, 2), round(qstrict, 2), shape))
    return {"ts": int(time.time()), "n": len(rm), "listed_usd_day": round(listed, 2), "payable_usd_day": round(payable, 2),
            "n_payable": n_pay, "n_empty": n_empty, "pools": rows}


if __name__ == '__main__':
    info = {}
    done_days = set()
    today = dt.datetime.utcnow().date()
    for k in (1,):
        d = today - dt.timedelta(days=k)
        try:
            rec = paid_for_day(d)
            done_days.add(d)
            open(OUT, 'a').write(json.dumps({"paid": rec}) + '\n')
            print(rec, flush=True)
        except Exception:
            traceback.print_exc()
    while True:
        t0 = time.time()
        try:
            s = snapshot(info)
            open(OUT, 'a').write(json.dumps(s) + '\n')
            print(dt.datetime.utcnow().isoformat(timespec='seconds'), {k: v for k, v in s.items() if k != 'pools'},
                  flush=True)
            y = dt.datetime.utcnow().date() - dt.timedelta(days=1)
            if y not in done_days and dt.datetime.utcnow().hour >= 1:
                rec = paid_for_day(y)
                done_days.add(y)
                open(OUT, 'a').write(json.dumps({"paid": rec}) + '\n')
                print(rec, flush=True)
        except Exception:
            traceback.print_exc()
        time.sleep(max(10, 900 - (time.time() - t0)))
