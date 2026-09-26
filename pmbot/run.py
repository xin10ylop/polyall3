"""Main loop (identical decision logic for paper and live).

  python -m pmbot.run --mode paper --capital 100      # forward test: live books + real trade prints, simulated fills
  python -m pmbot.run --mode live  --capital 100      # real orders (see README: eligibility, wallet, env vars)
"""
import argparse, json, os, signal, sys, time, threading, traceback, datetime as dt
from collections import deque
from . import api, scoring
from .config import CFG
from .engine import target_orders, ys_orders, Inv, MIN_ORDER
from .selection import build_candidates, allocate
from .jev import ToxicityCache, SPENT


class Universe:
    """Background refresher: the (slow) market selection never blocks the quoting loop."""

    def __init__(self, cfg, tox, log):
        self.cfg, self.tox, self.log = cfg, tox, log
        self.lock, self.markets, self.version, self.error = threading.Lock(), [], 0, None

    def refresh_once(self):
        try:
            m = build_candidates(self.cfg, self.tox, self.log)
            with self.lock:
                self.markets, self.version = m, self.version + 1
            self.log(f"universe v{self.version}: {len(m)} markets; jev+llm ${SPENT['usd']:.4f}")
        except Exception as e:
            self.error = e
            self.log(f"universe refresh failed: {e}")

    def loop(self):
        while True:
            time.sleep(self.cfg["universe_refresh_min"] * 60)
            self.refresh_once()

    def get(self):
        with self.lock:
            return list(self.markets), self.version


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
    # breadth scales with capital (~$8 per min-size two-sided quote); keeps LLM review cost small for small accounts
    cfg["max_markets"] = min(cfg["max_markets"], max(10, int(cfg["capital_usd"] / 8)))
    os.makedirs(a.out, exist_ok=True)
    tag = f"{a.mode}_{int(cfg['capital_usd'])}_{dt.datetime.utcnow().strftime('%Y%m%dT%H%M')}"
    logf = open(os.path.join(a.out, tag + ".jsonl"), "a")

    def log(msg):
        print(f"{dt.datetime.utcnow().isoformat(timespec='seconds')} {msg}", flush=True)

    def _term(*_):
        raise SystemExit("SIGTERM")
    signal.signal(signal.SIGTERM, _term)

    if cfg["use_jev"] and not os.environ.get("OPENROUTER_API_KEY"):
        log("WARNING: OPENROUTER_API_KEY not set -> Jev/LLM toxicity gate is OFF")
    if a.mode == "live":
        from .live import LiveBroker
        broker = LiveBroker(cfg, log)
    else:
        from .paper import PaperBroker
        broker = PaperBroker(log)
    tox = ToxicityCache(os.path.join(a.out, "jev_toxicity.json")) if cfg["use_jev"] else None
    uni = Universe(cfg, tox, log)
    uni.refresh_once()
    threading.Thread(target=uni.loop, daemon=True).start()

    cfgs = {}
    if a.mode == "live":   # never forget positions from earlier runs (unwind them)
        for cid in broker.all_position_cids():
            m = api.clob_market(cid)
            if m and m.get("tokens") and len(m["tokens"]) == 2:
                cfgs[cid] = {"cid": cid, "q": m.get("question", ""), "yes": m["tokens"][0]["token_id"],
                             "no": m["tokens"][1]["token_id"], "neg_risk": bool(m.get("neg_risk")), "v": 4.5,
                             "min_size": 5.0, "rate": 0.0, "tick": float(m.get("minimum_tick_size") or 0.01),
                             "end": m.get("end_date_iso")}
    mids_hist, last_mid, cooldown, side_block, fill_seen = {}, {}, {}, {}, {}
    rew = {"cons": 0.0, "cent": 0.0}
    day_est, cur_day, pending = 0.0, dt.datetime.utcnow().date(), []
    state_f = os.path.join(a.out, f"state_{a.mode}_{int(cfg['capital_usd'])}.json")
    try:   # survive restarts: today's running reward estimate and days awaiting reconciliation
        stt = json.load(open(state_f))
        if stt.get("day") == cur_day.isoformat():
            day_est = float(stt.get("day_est", 0.0))
        pending = [(dt.date.fromisoformat(d), e, n) for d, e, n in stt.get("pending", [])]
    except Exception:
        pass
    last_score_t = 0.0
    peak_eq, start, last_t, last_eq_t, eq = None, time.time(), None, 0.0, None
    try:
        while time.time() - start < a.hours * 3600:
            t0 = time.time()
            try:
                universe, _ = uni.get()
                for c in universe:
                    cfgs.setdefault(c["cid"], c).update(c)
                in_u = {c["cid"] for c in universe}
                # 1) order state + fills against what rested since last cycle
                if a.mode == "live":
                    ev = broker.refresh_open(cfgs)
                    if ev is None:                           # cannot see our orders -> pull everything
                        broker.cancel_all()
                        time.sleep(5)
                        continue
                    broker.refresh_inventory(cfgs)
                else:
                    ev = broker.poll_fills(cfgs, in_u)
                for (_, cid, ys_side, qty) in [(e[0], e[1], e[2], e[-1]) for e in ev]:
                    side_block[(cid, ys_side)] = t0 + cfg["fill_guard_sec"]
                    fill_seen[(cid, ys_side)] = t0
                    log(f"FILL {ys_side} {qty:.1f} | {cfgs.get(cid, {}).get('q', cid)[:60]}")
                inv_cids = [cid for cid in cfgs if _has_inv(broker.inventory(cid))]
                active = in_u | set(inv_cids)
                # 2) books (fresh, after our own-order snapshot)
                bk = api.books([cfgs[cid]["yes"] for cid in active])
                states = {}
                for cid in active:
                    c = cfgs[cid]
                    if cid not in in_u:          # unwind-only market: relax reward constraints so it can always exit
                        c = cfgs[cid] = dict(c, min_size=MIN_ORDER, v=max(c["v"], 10.0), rate=0.0)
                    st = scoring.book_state(bk.get(c["yes"]), c["min_size"], c["v"], exclude=broker.own_orders(c))
                    if not st:
                        continue
                    c["tick"] = st["tick"]
                    states[cid] = st
                    last_mid[cid] = st["mid"]
                    ltp = (bk.get(c["yes"]) or {}).get("last_trade_price")
                    h = mids_hist.setdefault(cid, deque())
                    h.append((t0, st["mid"], ltp))
                    while h and t0 - h[0][0] > cfg["jump_window_sec"]:
                        h.popleft()
                    lo, hi = min(x[1] for x in h), max(x[1] for x in h)
                    # A mid move in a thin book with no trade is order flicker (we requote around the new mid anyway);
                    # only a move accompanied by actual trading, or by our own fill, counts as information.
                    traded = len({x[2] for x in h}) > 1 or any(k[0] == cid and v > t0 - cfg["jump_window_sec"]
                                                                for k, v in fill_seen.items())
                    if (hi - lo) * 100 >= cfg["jump_cents"] and traded and cooldown.get(cid, 0) < t0:
                        cooldown[cid] = t0 + cfg["cooldown_min"] * 60
                        log(f"jump {(hi - lo) * 100:.1f}c/{cfg['jump_window_sec']}s -> cooldown: {c['q'][:60]}")
                # 3) capital actually available = capital - collateral tied up in inventory
                avail = cfg["capital_usd"] - broker.inventory_cost()
                if a.mode == "live":
                    avail = min(avail, broker.cash_cached())
                eligible = [c for c in universe if c["cid"] in states and cooldown.get(c["cid"], 0) < t0]
                alloc = allocate(eligible, cfg, states, avail)
                # 4) desired orders
                desired = {}
                for cid in active:
                    c, st = cfgs[cid], states.get(cid)
                    if st is None:
                        desired[cid] = []
                        continue
                    inv = broker.inventory(cid)
                    block = {s for s in ("bid", "ask") if side_block.get((cid, s), 0) > t0}
                    size = alloc.get(cid, 0.0)
                    unwind = size <= 0 or cooldown.get(cid, 0) >= t0
                    orders = target_orders(c, st, inv, size, cfg, unwind_only=unwind, block=block)
                    if a.mode == "live" and (broker.inv_stale or not broker.hb_ok):
                        orders = [o for o in orders if o.side == "SELL"]   # never add exposure blind
                    desired[cid] = orders
                # 5) execute
                if a.mode == "live":
                    failed = broker.sync(desired, cfgs)
                    if not failed:
                        broker.mark_ok()      # heartbeats continue only while cycles fully succeed
                else:
                    broker.sync(desired, states)
                # 6) reward estimate from orders actually resting (live: exchange snapshot; paper: desired)
                rate_c = rate_m = 0.0
                for cid, st in states.items():
                    c = cfgs[cid]
                    if cid not in in_u or c.get("rate", 0) <= 0:
                        continue
                    ol = broker.resting_ys_orders(c) if a.mode == "live" else ys_orders(desired.get(cid, []))
                    if not ol:
                        continue
                    _, shc, shm = scoring.our_share(st, c["v"], c["min_size"], ol)
                    rate_c += c["rate"] * shc
                    rate_m += c["rate"] * shm
                el = 0.0 if last_t is None else min(120.0, t0 - last_t)
                last_t = t0
                rew["cons"] += rate_c * el / 86400
                rew["cent"] += rate_m * el / 86400
                day_est += rate_c * el / 86400
                now_utc = dt.datetime.utcnow()
                if now_utc.date() != cur_day:          # day rolled: remember yesterday's estimate
                    pending.append((cur_day, day_est, 0))
                    day_est, cur_day = 0.0, now_utc.date()
                # rewards are paid ~00:00 UTC but can post late: check at 01:30 and again at 06:00 UTC
                mins = now_utc.hour * 60 + now_utc.minute
                still = []
                for d, est, n in pending:
                    if (n == 0 and mins >= 90) or (n == 1 and mins >= 360):
                        rec = {"reconcile_day": d.isoformat(), "check": n + 1, "estimated_rewards": round(est, 4)}
                        if a.mode == "live":
                            rec["actual_rewards"] = broker.rewards_for_day(d.isoformat())
                        logf.write(json.dumps(rec) + "\n"); logf.flush(); log(json.dumps(rec))
                        n += 1
                    if n < 2:
                        still.append((d, est, n))
                pending = still
                json.dump({"day": cur_day.isoformat(), "day_est": day_est,
                           "pending": [(d.isoformat(), e, n) for d, e, n in pending]}, open(state_f, "w"))
                if a.mode == "live" and t0 - last_score_t > 1800:   # fast signal: are we actually being credited?
                    snap = broker.scoring_snapshot()
                    logf.write(json.dumps({"ts": int(t0), "scoring_snapshot": snap}) + "\n"); logf.flush()
                    log(f"scoring snapshot: {str(snap)[:300]}")
                    last_score_t = t0
                # 7) trading equity (excludes estimated rewards) + drawdown stop
                if a.mode == "paper":
                    eq = broker.trading_equity(last_mid)
                elif t0 - last_eq_t > 60:
                    eq, last_eq_t = broker.trading_equity(last_mid), t0
                if eq is not None:
                    peak_eq = eq if peak_eq is None else max(peak_eq, eq)
                    if peak_eq - eq > cfg["max_drawdown_frac"] * cfg["capital_usd"]:
                        log(f"max drawdown hit (peak {peak_eq:.2f} -> {eq:.2f}) -> stopping")
                        break
                rec = {"ts": int(t0), "hrs": round((t0 - start) / 3600, 3), "n_quoted": sum(1 for v in desired.values() if v),
                       "rate_cons_usd_day": round(rate_c, 2), "rew_cons": round(rew["cons"], 4), "rew_cent": round(rew["cent"], 4),
                       "trading_equity": None if eq is None else round(eq, 4), "avail": round(avail, 2),
                       "locked": round(sum(o.price * o.size for ol in desired.values() for o in ol if o.side == "BUY"), 2),
                       "n_fills": len(broker.fills), "cooldowns": sum(1 for v in cooldown.values() if v > t0),
                       "jev_llm_usd": round(SPENT["usd"], 4)}
                logf.write(json.dumps(rec) + "\n"); logf.flush()
                log(json.dumps(rec))
            except Exception:
                traceback.print_exc()
                if a.mode == "live":
                    broker.cancel_all()            # any unexpected error -> no stale quotes left behind
            time.sleep(max(1.0, cfg["cycle_seconds"] - (time.time() - t0)))
    finally:
        if a.mode == "live":
            broker.shutdown()
        else:
            json.dump({"fills": broker.fills, "inv": {k: v.__dict__ for k, v in broker.inv.items()}, "cash": broker.cash},
                      open(os.path.join(a.out, tag + "_final.json"), "w"))


def _has_inv(inv):
    return inv.yes >= MIN_ORDER or inv.no >= MIN_ORDER


if __name__ == "__main__":
    main()
