"""Universe selection: own quotes are not competition (audit #3 M6), incumbent hysteresis, consistent fill-loss
charge (L2), truncated activity pages (L3)."""
import time
from pmbot import selection, api
from pmbot.config import CFG


def _book(bids, asks):
    return {"bids": [{"price": str(p), "size": str(s)} for p, s in bids],
            "asks": [{"price": str(p), "size": str(s)} for p, s in asks], "tick_size": "0.01"}


def _patch(monkeypatch, books, usd24=0.0):
    rm = [{"condition_id": cid, "total_daily_rate": 20, "rewards_max_spread": 4.5, "rewards_min_size": 20}
          for cid in books]
    info = {cid: {"active": True, "accepting_orders": True, "question": f"Will {cid} happen?", "neg_risk": False,
                  "end_date_iso": "2027-12-31T00:00:00Z", "minimum_tick_size": 0.01,
                  "tokens": [{"token_id": cid + "Y"}, {"token_id": cid + "N"}]} for cid in books}
    monkeypatch.setattr(api, "rewarded_markets", lambda: rm)
    monkeypatch.setattr(api, "clob_markets", lambda cids: info)
    monkeypatch.setattr(api, "books", lambda toks: {cid + "Y": b for cid, b in books.items()})
    monkeypatch.setattr(api, "activity_24h", lambda cid: (usd24, 0.0))


CF = dict(CFG, use_jev=False, max_markets=1)


def test_m6_own_quotes_are_not_competition_and_incumbent_is_kept(monkeypatch):
    # market A: only our own 20-share quotes rest in the band (uncontested); B: identical but empty of us
    a = _book([(0.49, 20), (0.30, 500)], [(0.51, 20), (0.70, 500)])
    b = _book([(0.49, 20), (0.30, 500)], [(0.51, 20), (0.70, 500)])
    _patch(monkeypatch, {"A": a, "B": b})
    own = lambda c: {"bids": [(0.49, 20)], "asks": [(0.51, 20)]} if c["cid"] == "A" else None
    out = selection.build_candidates(CF, None, lambda *x: None, own=own, incumbents={"A"})
    assert [c["cid"] for c in out] == ["A"]
    # without the exclusion A looked contested by ourselves and ranked no better than B
    out2 = {c["cid"]: c["est_roi"] for c in selection.build_candidates(dict(CF, max_markets=2), None, lambda *x: None)}
    out3 = {c["cid"]: c["est_roi"] for c in selection.build_candidates(dict(CF, max_markets=2), None, lambda *x: None,
                                                                      own=own)}
    assert out3["A"] > out2["A"]


def test_l2_adverse_charge_in_dollars_capped_by_notional():
    c = {"usd24": 400.0}
    assert selection.adverse_usd_day(c, CFG, notional=19.6) == CFG["adverse_rate"] * 19.6
    assert selection.adverse_usd_day(c, CFG, notional=1e6) == CFG["adverse_rate"] * CFG["fill_share"] * 400.0
    assert selection.adverse_usd_day({}, CFG, notional=50) == 0.0


def test_l2_allocate_prefers_quiet_pool_for_extra_size():
    from pmbot import scoring
    bk = _book([(0.49, 500)], [(0.51, 500)])
    st = scoring.book_state(bk, 20, 4.5)
    quiet = {"cid": "q", "v": 4.5, "min_size": 20, "rate": 50, "tick": 0.01, "usd24": 0.0}
    busy = dict(quiet, cid="b", usd24=900.0)
    al = selection.allocate([quiet, busy], dict(CFG, capital_usd=1000), {"q": st, "b": st}, 1000)
    assert al.get("q", 0) >= al.get("b", 0)


def test_l3_truncated_activity_page_counts_as_active(monkeypatch):
    now = time.time()
    rows = [{"timestamp": now - i, "size": "1", "price": "0.5", "outcomeIndex": 0} for i in range(500)]
    monkeypatch.setattr(api, "market_trades", lambda cid, limit=500, taker_only=True: rows)
    usd, _ = api.activity_24h("x")
    assert usd == float("inf")
