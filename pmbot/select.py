"""Universe selection and capital allocation for reward harvesting."""
import re, json, datetime as dt
from . import api, scoring
from .jev import ToxicityCache, is_safe


def build_candidates(cfg, tox_cache=None, log=print):
    rx = re.compile(cfg["exclude_regex"], re.I)
    rm = [r for r in api.rewarded_markets()
          if float(r.get("total_daily_rate") or r.get("native_daily_rate") or 0) >= cfg["min_pool_usd_day"]]
    info = api.clob_markets([r["condition_id"] for r in rm])
    now = dt.datetime.now(dt.timezone.utc)
    cands = []
    for r in rm:
        m = info.get(r["condition_id"])
        if not m or m.get("closed") or not m.get("active") or not m.get("accepting_orders"):
            continue
        toks = m.get("tokens") or []
        if len(toks) != 2:
            continue
        q = m.get("question") or ""
        if rx.search(q) or rx.search((m.get("description") or "")[:300]):
            continue
        try:
            end = dt.datetime.fromisoformat(m["end_date_iso"].replace("Z", "+00:00"))
        except Exception:
            continue
        if (end - now).total_seconds() < cfg["min_hours_to_end"] * 3600:
            continue
        cands.append({
            "cid": r["condition_id"], "q": q, "desc": m.get("description") or "", "end": m["end_date_iso"],
            "yes": toks[0]["token_id"], "no": toks[1]["token_id"], "neg_risk": bool(m.get("neg_risk")),
            "v": float(r["rewards_max_spread"]), "min_size": float(r["rewards_min_size"]),
            "rate": float(r.get("total_daily_rate") or r.get("native_daily_rate")),
            "tick": float(m.get("minimum_tick_size") or 0.01),
        })
    log(f"candidates after static filters: {len(cands)}")
    bk = api.books([c["yes"] for c in cands] + [c["no"] for c in cands])
    out = []
    lo, hi = cfg["mid_range"]
    for c in cands:
        st = scoring.book_state(bk.get(c["yes"]), bk.get(c["no"]), c["min_size"], c["v"])
        if not st or not (lo <= st["mid"] <= hi):
            continue
        bid, ask = quote_prices(st, c, cfg["mode"])
        size = max(c["min_size"], 5)
        _, sh, _ = scoring.our_share(st, c["v"], bid, ask, size, size)
        cap = size * bid + size * (1 - ask)
        if cap <= 0:
            continue
        c["est_roi"] = c["rate"] * sh / cap
        c["mid"] = st["mid"]
        if c["est_roi"] >= cfg["min_est_roi_day"]:
            out.append(c)
    out.sort(key=lambda x: -x["est_roi"])
    if cfg["use_jev"] and tox_cache is not None:
        kept = []
        for c in out[: cfg["max_markets"] * 3]:
            t = tox_cache.get(c["cid"], c["q"], c["desc"], c["end"])
            c["tox"] = t
            if is_safe(t, cfg):
                kept.append(c)
        tox_cache.save()
        log(f"jev gate: {len(kept)}/{min(len(out), cfg['max_markets'] * 3)} pass")
        out = kept
    return out[: cfg["max_markets"]]


def quote_prices(st, c, mode):
    """Desired (bid, ask) in YES-price space, kept inside the reward band around the adjusted mid."""
    t, v, mid = c["tick"], c["v"], st["mid"]
    bid, ask = st["bb"], st["ba"]
    if mode == "improve" and ask - bid > 2 * t + 1e-9:
        bid, ask = round(bid + t, 6), round(ask - t, 6)
    # if the best quote sits outside the reward band, step inside it (never cross the book)
    band = v / 100.0
    while (mid - bid) >= band and bid + t < ask - t:
        bid = round(bid + t, 6)
    while (ask - mid) >= band and ask - t > bid + t:
        ask = round(ask - t, 6)
    return bid, ask


def allocate(cands, cfg, books_state):
    """Water-filling: add size in min-size chunks to the market with the best marginal reward per $."""
    cap_left = cfg["capital_usd"]
    alloc = {c["cid"]: 0.0 for c in cands}
    per_cap = {c["cid"]: 0.0 for c in cands}
    while True:
        best, best_gain, best_cost = None, 0.0, 0.0
        for c in cands:
            st = books_state.get(c["cid"])
            if not st:
                continue
            bid, ask = quote_prices(st, c, cfg["mode"])
            chunk = max(c["min_size"], 5) if alloc[c["cid"]] == 0 else max(5.0, c["min_size"] / 2)
            cost = chunk * (bid + (1 - ask))
            if cost > cap_left or per_cap[c["cid"]] + cost > cfg["max_frac_per_market"] * cfg["capital_usd"] + 1e-9:
                continue
            s0 = alloc[c["cid"]]
            _, sh0, _ = scoring.our_share(st, c["v"], bid, ask, s0, s0) if s0 > 0 else (0, 0.0, 0)
            _, sh1, _ = scoring.our_share(st, c["v"], bid, ask, s0 + chunk, s0 + chunk)
            gain = c["rate"] * (sh1 - sh0) / cost
            if gain > best_gain:
                best, best_gain, best_cost, best_chunk = c, gain, cost, chunk
        if best is None or best_gain < cfg["min_est_roi_day"]:
            break
        alloc[best["cid"]] += best_chunk
        per_cap[best["cid"]] += best_cost
        cap_left -= best_cost
    return {k: v for k, v in alloc.items() if v > 0}
