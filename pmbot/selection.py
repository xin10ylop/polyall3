"""Universe selection, quote placement and capital allocation for reward harvesting."""
import re, math, datetime as dt
from . import api, scoring
from .jev import is_safe, borderline, llm_review


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def build_candidates(cfg, tox_cache=None, log=print, own=None, incumbents=()):
    """Rewarded markets that pass static filters, the reward-ROI screen and the Jev -> LLM toxicity cascade.
    own(c) returns our resting orders in market c (excluded from the book, so our own quotes are not counted as
    competition); markets in `incumbents` get a ranking bonus so a 30-min refresh does not churn them out."""
    rx = re.compile(cfg["exclude_regex"], re.I)
    rm = [r for r in api.rewarded_markets()
          if _f(r.get("total_daily_rate") or r.get("native_daily_rate")) >= cfg["min_pool_usd_day"]]
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
        v, ms = _f(r.get("rewards_max_spread")), _f(r.get("rewards_min_size"))
        if v <= 0:
            continue
        cands.append({
            "cid": r["condition_id"], "q": q, "desc": m.get("description") or "", "end": m["end_date_iso"],
            "yes": toks[0]["token_id"], "no": toks[1]["token_id"], "neg_risk": bool(m.get("neg_risk")),
            "v": v, "min_size": max(ms, 5.0), "rate": _f(r.get("total_daily_rate") or r.get("native_daily_rate")),
            "tick": _f(m.get("minimum_tick_size"), 0.01) or 0.01,
        })
    log(f"candidates after static filters: {len(cands)}")
    bk = api.books([c["yes"] for c in cands])
    out = []
    lo, hi = cfg["mid_range"]
    for c in cands:
        st = scoring.book_state(bk.get(c["yes"]), c["min_size"], c["v"], exclude=own(c) if own else None)
        if not st or not (lo <= st["mid"] <= hi):
            continue
        c["tick"] = st["tick"]
        bid, ask = quote_prices(st, c, cfg["mode"])
        if bid is None or ask is None:
            continue
        size = c["min_size"]
        _, sh, _ = scoring.our_share(st, c["v"], c["min_size"], [("bid", bid, size), ("ask", ask, size)])
        cap = size * bid + size * (1 - ask)
        if cap <= 0:
            continue
        c["est_roi"] = c["rate"] * sh / cap
        c["mid"], c["cap"] = st["mid"], cap
        if c["est_roi"] >= cfg["min_est_roi_day"]:
            out.append(c)
    out.sort(key=lambda x: -x["est_roi"])
    # Activity filter: real farmers lose 3-5% per $ filled; fills come from taker flow. Prefer quiet pools and charge
    # expected adverse selection against the reward estimate.
    from concurrent.futures import ThreadPoolExecutor
    top = out[: cfg["activity_top_n"]]
    with ThreadPoolExecutor(8) as ex:
        acts = list(ex.map(lambda c: api.activity_24h(c["cid"]), top))
    kept_a = []
    for c, act in zip(top, acts):
        if act is None:
            continue
        usd24, rng24 = act
        c["usd24"], c["rng24"] = usd24, rng24
        if usd24 > cfg["max_trades_24h_usd"] or rng24 > cfg["max_range_24h"]:
            continue
        c["adverse_usd_day"] = adverse_usd_day(c, cfg, c["cap"])
        c["est_roi"] -= c["adverse_usd_day"] / max(c["cap"], 1e-9)
        if c["est_roi"] >= cfg["min_est_roi_day"]:
            kept_a.append(c)
    log(f"activity filter: {len(kept_a)}/{len(top)} quiet enough")
    inc = set(incumbents)
    out = sorted(kept_a, key=lambda x: -x["est_roi"] * (cfg["incumbent_bonus"] if x["cid"] in inc else 1.0))
    if cfg["use_jev"] and tox_cache is not None:
        kept, reviews = [], 0
        for c in out[: cfg["max_markets"] * 3]:
            t = tox_cache.get(c["cid"], c["q"], c["desc"], c["end"])
            # Cascade: Jev screens everything cheaply; markets Jev passes (or scores borderline) are confirmed by a
            # frontier LLM that reads the full rules, and the LLM's verdict decides. Cached with the Jev score (24 h).
            if t is not None and "llm" not in t and cfg.get("llm_model") and (is_safe(t, cfg) or borderline(t, cfg)) \
                    and reviews < cfg.get("llm_max_reviews_per_refresh", 15):
                r = llm_review(c["q"], c["desc"], c["end"], cfg["llm_model"])
                if r is not None:          # on API failure: leave unreviewed -> skipped below (fail closed)
                    t["llm"] = r
                reviews += 1
            if t is not None and "llm" not in t and cfg.get("llm_model") and is_safe(t, cfg):
                continue  # not yet confirmed by the LLM (review budget exhausted this refresh): don't quote yet
            c["tox"] = t
            if is_safe(t, cfg):
                kept.append(c)
        tox_cache.save()
        log(f"toxicity cascade: {len(kept)}/{min(len(out), cfg['max_markets'] * 3)} pass")
        out = kept
    return out[: cfg["max_markets"]]


def adverse_usd_day(c, cfg, notional):
    """Expected fill loss per day ($): adverse_rate x the $ we expect to be filled, which is our share of the
    market's 24h taker $ but never more than the collateral our quotes put at risk (both in $)."""
    return cfg["adverse_rate"] * min(cfg["fill_share"] * c.get("usd24", 0.0), notional)


def _floor(p, t):
    return round(math.floor(p / t + 1e-9) * t, 6)


def _ceil(p, t):
    return round(math.ceil(p / t - 1e-9) * t, 6)


def quote_prices(st, c, mode):
    """Desired (bid, ask) in YES-price space.

    Rules: never at or through the adjusted mid (bid <= mid - tick, ask >= mid + tick); join the best quote (or one
    tick inside it in 'improve' mode); if the best quote is outside the reward band, step inside the band. A side whose
    price cannot earn any score returns None.
    """
    t, v, mid = st["tick"], c["v"], st["mid"]
    band = v / 100.0
    bid, ask = st["bb"], st["ba"]
    if mode == "improve" and ask - bid > 2 * t + 1e-9:
        bid, ask = bid + t, ask - t
    bid = min(_floor(bid, t), _floor(mid - t, t), _floor(st["ba"] - t, t))   # never cross the raw best ask
    ask = max(_ceil(ask, t), _ceil(mid + t, t), _ceil(st["bb"] + t, t))      # never cross the raw best bid
    bid_cap = min(mid - t, st["ba"] - t)       # stepping into the band must never cross the raw best ask
    ask_floor = max(mid + t, st["bb"] + t)     # ... nor the raw best bid
    while mid - bid >= band - 1e-9 and bid + t <= bid_cap + 1e-9:
        bid = round(bid + t, 6)
    while ask - mid >= band - 1e-9 and ask - t >= ask_floor - 1e-9:
        ask = round(ask - t, 6)
    if bid > st["ba"] - t + 1e-9:
        bid = None
    if ask is not None and ask < st["bb"] + t - 1e-9:
        ask = None
    bid = bid if (bid is not None and 0 < bid < 1 and 0 <= (mid - bid) * 100 < v) else None
    ask = ask if (ask is not None and 0 < ask < 1 and 0 <= (ask - mid) * 100 < v) else None
    return bid, ask


def allocate(cands, cfg, states, available_usd):
    """Water-filling: add size (first chunk = min_size) to the market with the best marginal reward per $ locked,
    spending at most `available_usd` (capital minus what is tied up in inventory)."""
    cap_left = max(0.0, available_usd)
    alloc = {c["cid"]: 0.0 for c in cands}
    spent = {c["cid"]: 0.0 for c in cands}
    per_mkt_cap = cfg["max_frac_per_market"] * cfg["capital_usd"]
    while True:
        best, best_gain, best_cost, best_chunk = None, 0.0, 0.0, 0.0
        for c in cands:
            st = states.get(c["cid"])
            if not st:
                continue
            bid, ask = quote_prices(st, c, cfg["mode"])
            if bid is None or ask is None:
                continue
            s0 = alloc[c["cid"]]
            chunk = c["min_size"] if s0 == 0 else max(5.0, c["min_size"] / 2)
            cost = chunk * (bid + (1 - ask))
            if cost > cap_left + 1e-9 or spent[c["cid"]] + cost > per_mkt_cap + 1e-9:
                continue
            sh0 = scoring.our_share(st, c["v"], c["min_size"], [("bid", bid, s0), ("ask", ask, s0)])[1] if s0 else 0.0
            sh1 = scoring.our_share(st, c["v"], c["min_size"], [("bid", bid, s0 + chunk), ("ask", ask, s0 + chunk)])[1]
            unit = bid + (1 - ask)            # expected fill losses grow with the size at risk
            d_adv = adverse_usd_day(c, cfg, (s0 + chunk) * unit) - adverse_usd_day(c, cfg, s0 * unit)
            gain = (c["rate"] * (sh1 - sh0) - d_adv) / cost
            if gain > best_gain:
                best, best_gain, best_cost, best_chunk = c, gain, cost, chunk
        if best is None or best_gain < cfg["min_est_roi_day"]:
            break
        alloc[best["cid"]] += best_chunk
        spent[best["cid"]] += best_cost
        cap_left -= best_cost
    return {k: v for k, v in alloc.items() if v > 0}
