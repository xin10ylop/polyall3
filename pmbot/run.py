"""Main loop (identical logic for paper and live).

  python -m pmbot.run --mode paper            # forward test on live books + real trade prints
  python -m pmbot.run --mode live             # real orders (needs PM_PRIVATE_KEY etc., see README)
"""
import argparse, json, os, sys, time, traceback, datetime as dt
from . import api, scoring
from .config import CFG
from .engine import target_orders, Inv
from .select import build_candidates, allocate
from .jev import ToxicityCache, SPENT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["paper", "live"], default="paper")
    ap.add_argument("--capital", type=float, default=None)
    ap.add_argument("--out", default="runs")
    ap.add_argument("--hours", type=float, default=1e9)
    a = ap.parse_args()
    cfg = dict(CFG)
    if a.capital:
        cfg["capital_usd"] = a.capital
    os.makedirs(a.out, exist_ok=True)
    tag = f"{a.mode}_{int(cfg['capital_usd'])}_{dt.datetime.utcnow().strftime('%Y%m%dT%H%M')}"
    logf = open(os.path.join(a.out, tag + ".jsonl"), "a")

    def log(msg):
        print(f"{dt.datetime.utcnow().isoformat(timespec='seconds')} {msg}", flush=True)

    if a.mode == "live":
        from .live import LiveBroker
        broker = LiveBroker(log)
    else:
        from .paper import PaperBroker
        broker = PaperBroker(log)
    tox = ToxicityCache(os.path.join(a.out, "jev_toxicity.json")) if cfg["use_jev"] else None

    cfgs, universe = {}, []
    last_u, last_t = 0.0, None
    prev_mid, cooldown = {}, {}
    rew_est = {"cons": 0.0, "cent": 0.0}
    day_est, cur_day = {"cons": 0.0}, dt.datetime.utcnow().date()
    peak_eq, start = None, time.time()
    try:
        while time.time() - start < a.hours * 3600:
            t0 = time.time()
            try:
                if t0 - last_u > cfg["universe_refresh_min"] * 60:
                    universe = build_candidates(cfg, tox, log)
                    for c in universe:
                        cfgs[c["cid"]] = c
                    last_u = t0
                    log(f"universe: {len(universe)} markets; jev ${SPENT['usd']:.4f}")
                # fills against orders that were resting since last cycle
                broker.poll_fills(cfgs)
                inv_cids = [cid for cid in cfgs if _has_inv(broker.inventory(cid))]
                active = {c["cid"] for c in universe} | set(inv_cids)
                bk = api.books([cfgs[cid]["yes"] for cid in active] + [cfgs[cid]["no"] for cid in active])
                states, mids = {}, {}
                for cid in active:
                    c = cfgs[cid]
                    st = scoring.book_state(bk.get(c["yes"]), bk.get(c["no"]), c["min_size"], c["v"],
                                            exclude=_own(broker, cid, c))
                    if not st:
                        continue
                    pm = prev_mid.get(cid)
                    if pm is not None and abs(st["mid"] - pm) * 100 >= cfg["jump_cents"]:
                        cooldown[cid] = t0 + cfg["cooldown_min"] * 60
                        log(f"jump {abs(st['mid'] - pm) * 100:.1f}c -> cooldown: {c['q'][:60]}")
                    prev_mid[cid] = st["mid"]
                    states[cid], mids[cid] = st, st["mid"]
                eligible = [c for c in universe if c["cid"] in states and cooldown.get(c["cid"], 0) < t0]
                alloc = allocate(eligible, cfg, states)
                desired, now_share_c, now_share_m = {}, 0.0, 0.0
                for cid in active:
                    c, st = cfgs[cid], states.get(cid)
                    if st is None or cooldown.get(cid, 0) >= t0:
                        desired[cid] = []
                        continue
                    inv = broker.inventory(cid)
                    size = alloc.get(cid, 0.0)
                    if size <= 0 and _has_inv(inv):          # unwind-only quoting for dropped markets
                        size = max(abs(inv.yes - inv.no), 5.0)
                        orders, bid, ask, bs, as_ = target_orders(c, st, inv, size, cfg)
                        orders = [o for o in orders if o.side == "SELL"]
                    else:
                        orders, bid, ask, bs, as_ = target_orders(c, st, inv, size, cfg)
                    desired[cid] = orders
                    if orders:
                        _, shc, shm = scoring.our_share(st, c["v"], bid, ask, bs, as_)
                        now_share_c += c["rate"] * shc
                        now_share_m += c["rate"] * shm
                if a.mode == "live":
                    broker.sync(desired, cfgs)
                else:
                    broker.sync(desired)
                el = 0.0 if last_t is None else min(120.0, t0 - last_t)
                last_t = t0
                rew_est["cons"] += now_share_c * el / 86400
                rew_est["cent"] += now_share_m * el / 86400
                day_est["cons"] += now_share_c * el / 86400
                today = dt.datetime.utcnow().date()
                if today != cur_day:
                    # daily reconciliation: model-estimated rewards vs what Polymarket actually paid (live only)
                    rec_d = {"reconcile_day": cur_day.isoformat(), "estimated_rewards": round(day_est["cons"], 4)}
                    if a.mode == "live":
                        rec_d["actual_rewards"] = broker.rewards_for_day(cur_day.isoformat())
                    logf.write(json.dumps(rec_d) + "\n"); logf.flush(); log(json.dumps(rec_d))
                    day_est["cons"], cur_day = 0.0, today
                eq = broker.equity(mids) if a.mode == "paper" else None
                if eq is not None:
                    tot = eq + rew_est["cons"]
                    peak_eq = tot if peak_eq is None else max(peak_eq, tot)
                    if peak_eq - tot > cfg["max_drawdown_frac"] * cfg["capital_usd"]:
                        log("max drawdown hit -> stopping")
                        break
                rec = {"ts": int(t0), "hrs": round((t0 - start) / 3600, 3), "n_quoted": sum(1 for v in desired.values() if v),
                       "rate_cons_usd_day": round(now_share_c, 2), "rew_cons": round(rew_est["cons"], 4),
                       "rew_cent": round(rew_est["cent"], 4), "trade_equity": None if eq is None else round(eq, 4),
                       "locked": round(sum(o.price * o.size for ol in desired.values() for o in ol if o.side == "BUY"), 2),
                       "n_fills": len(getattr(broker, "fills", [])), "jev_usd": round(SPENT["usd"], 4)}
                logf.write(json.dumps(rec) + "\n"); logf.flush()
                log(json.dumps(rec))
            except Exception:
                traceback.print_exc()
            time.sleep(max(1.0, cfg["cycle_seconds"] - (time.time() - t0)))
    finally:
        if a.mode == "live":
            broker.shutdown()
        if a.mode == "paper":
            json.dump({"fills": broker.fills, "inv": {k: v.__dict__ for k, v in broker.inv.items()}, "cash": broker.cash},
                      open(os.path.join(a.out, tag + "_final.json"), "w"))


def _has_inv(inv):
    return inv.yes >= 1 or inv.no >= 1


def _own(broker, cid, c):
    """Live only: our resting orders (YES space) are removed from the observed book so we never compete with, or
    step inside, ourselves. Paper orders are not in the real book, so nothing to remove."""
    if hasattr(broker, "own_orders"):
        return broker.own_orders(c)
    return None


if __name__ == "__main__":
    main()
