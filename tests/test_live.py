"""Live broker with a fake CLOB client (no network): equity (N1), trade-based fills (N2), cancel races,
heartbeat-before-post (N14)."""
import sys, time, types
import pytest

stub = types.ModuleType("py_clob_client_v2")


class _A:
    def __init__(s, *a, **k):
        s.args, s.__dict__ = a, {**s.__dict__, **k}


stub.BalanceAllowanceParams = stub.OrderArgs = stub.PartialCreateOrderOptions = stub.PostOrdersV2Args = _A
stub.TradeParams = stub.OrdersScoringParams = _A
stub.AssetType = types.SimpleNamespace(COLLATERAL="COLLATERAL", CONDITIONAL="CONDITIONAL")
stub.OrderType = types.SimpleNamespace(GTC="GTC")


@pytest.fixture(autouse=True)
def _stub_client(monkeypatch):
    monkeypatch.setitem(sys.modules, "py_clob_client_v2", stub)


from pmbot.live import LiveBroker   # noqa: E402
from pmbot.engine import Order      # noqa: E402
from pmbot.config import CFG        # noqa: E402

ME = "0xme"
CFGS = {"c": {"cid": "c", "q": "q", "yes": "Y", "no": "N", "tick": 0.01, "neg_risk": False, "v": 4.5, "min_size": 20}}


class FakeClient:
    def __init__(s):
        s.oo, s.balance, s.cancel_resp, s.trades, s.posted, s.hb = [], 100.0, None, [], [], 0

    def get_open_orders(s): return list(s.oo)
    def get_balance_allowance(s, p): return {"balance": str(int(s.balance * 1e6))}
    def update_balance_allowance(s, p): return {}
    def cancel_orders(s, ids): return s.cancel_resp or {"canceled": ids, "not_canceled": {}}
    def cancel_all(s): s.oo = []; return {}
    def get_trades(s, params): return list(s.trades)
    def create_order(s, a, o): return a
    def post_orders(s, posts, post_only=False):
        s.posted += posts
        return [{"success": True, "orderID": f"o{len(s.posted)}"} for _ in posts]
    def get_reward_percentages(s): return {"c": 100.0}
    def get_total_earnings_for_user_for_day(s, d): return [{"date": d, "earnings": 3.5}]
    def get_earnings_for_user_for_day(s, d):
        return [{"condition_id": "c", "earnings": 2.0, "asset_rate": 1.0},
                {"condition_id": "d", "earnings": [{"earnings": 1.5, "asset_rate": 1.0}]}]
    def are_orders_scoring(s, p): return {i: True for i in p.orderIds}
    def post_heartbeat(s, hid):
        s.hb += 1
        return {"heartbeat_id": f"h{s.hb}"}


def mk():
    b = LiveBroker.__new__(LiveBroker)
    b.cfg, b.log, b.client, b.user = dict(CFG), (lambda *a: None), FakeClient(), ME
    b.client.creds = types.SimpleNamespace(api_key="KEY")
    b.open_orders, b.inv, b.inv_stale, b.fills = [], {}, False, []
    b.seen_trades, b.last_trade_ts, b.allowed_tokens, b._last_hb_ok = {}, time.time() - 300, set(), time.time()
    b._cash, b._cash_t, b._hb_id = 100.0, time.time(), ""
    return b


def oo(i, tok, side, p, sz, m=0):
    return {"id": i, "asset_id": tok, "side": side, "price": str(p), "original_size": str(sz), "size_matched": str(m)}


def test_n1_equity_not_double_counting_reserved_collateral(monkeypatch):
    monkeypatch.setattr("pmbot.live.api.positions", lambda u: [])
    b = mk()
    b.client.oo = [oo("a", "Y", "BUY", 0.49, 100), oo("b", "N", "BUY", 0.49, 100)]
    b.refresh_open(CFGS)
    e1 = b.trading_equity({"c": 0.5})
    b.client.oo = []
    b.refresh_open(CFGS)
    assert e1 == b.trading_equity({"c": 0.5}) == 100.0


def test_n2a_exchange_cancel_is_not_a_fill():
    b = mk()
    b.client.oo = [oo("a", "Y", "BUY", 0.49, 50)]
    b.refresh_open(CFGS)
    b.client.oo = []                    # vanished (heartbeat lapse) but no trade record
    assert b.refresh_open(CFGS) == []


def test_n2b_fill_from_trade_record_even_during_cancel_race():
    b = mk()
    b.client.oo = [oo("a", "Y", "BUY", 0.49, 50)]
    b.refresh_open(CFGS)
    b.client.cancel_resp = {"canceled": [], "not_canceled": {"a": "order already matched"}}
    failed = b.sync({"c": []}, CFGS)
    assert "c" not in failed            # 'matched' is not a cancel failure
    b.client.oo = []
    b.client.trades = [{"id": "t1", "status": "MATCHED", "match_time": str(int(time.time())), "trader_side": "TAKER",
                        "maker_orders": [{"maker_address": ME, "asset_id": "Y", "side": "BUY", "matched_amount": "50",
                                          "price": "0.49"}]}]
    ev = b.refresh_open(CFGS)
    assert [(e[1], e[2], e[3]) for e in ev] == [("c", "bid", 50.0)]
    assert b.refresh_open(CFGS) == []   # de-duplicated


def test_no_token_maker_fill_maps_to_ask_side():
    b = mk()
    b.client.trades = [{"id": "t2", "status": "MATCHED", "match_time": str(int(time.time())), "trader_side": "TAKER",
                        "maker_orders": [{"maker_address": ME, "asset_id": "N", "side": "BUY", "matched_amount": "20",
                                          "price": "0.49"},
                                         {"maker_address": "0xother", "asset_id": "N", "side": "BUY",
                                          "matched_amount": "99", "price": "0.49"}]}]
    ev = b.refresh_open(CFGS)
    assert [(e[2], e[3]) for e in ev] == [("ask", 20.0)]


def test_n14_heartbeat_sent_before_posting_after_lapse():
    b = mk()
    b._last_hb_ok = time.time() - 60
    b.sync({"c": [Order("c", "Y", "BUY", 0.49, 20, "bid", 0.49)]}, CFGS)
    assert b.client.hb >= 1 and len(b.client.posted) == 1


def test_keep_matching_open_order_no_churn():
    b = mk()
    b.client.oo = [oo("a", "Y", "BUY", 0.49, 20)]
    b.refresh_open(CFGS)
    b.sync({"c": [Order("c", "Y", "BUY", 0.49, 20, "bid", 0.49)]}, CFGS)
    assert b.client.posted == []


def test_scoring_snapshot_reports_share_and_scoring_orders():
    b = mk()
    b.client.oo = [oo("a", "Y", "BUY", 0.49, 20), oo("b", "N", "BUY", 0.49, 20)]
    b.refresh_open(CFGS)
    snap = b.scoring_snapshot()
    assert snap["reward_percentages"] == {"c": 100.0}
    assert snap["orders_scoring"] == 2 and snap["orders_total"] == 2


def test_m2_leg_matched_by_owner_and_derived_from_taker_fields():
    b = mk()
    logs = []
    b.log = logs.append
    now = str(int(time.time()))
    b.client.trades = [
        # maker leg without maker_address/side/asset_id: matched by API-key owner, same outcome -> opposite side
        {"id": "t1", "status": "MATCHED", "match_time": now, "trader_side": "MAKER", "asset_id": "Y", "side": "SELL",
         "outcome": "Yes", "maker_orders": [{"owner": "KEY", "matched_amount": "20", "price": "0.49", "outcome": "Yes"}]},
        # other outcome (mint): same side on the complement token -> BUY N -> ask
        {"id": "t2", "status": "MATCHED", "match_time": now, "trader_side": "MAKER", "asset_id": "Y", "side": "BUY",
         "outcome": "Yes", "maker_orders": [{"owner": "KEY", "matched_amount": "15", "price": "0.49", "outcome": "No"}]},
        # a MAKER row with no leg of ours is flagged, not silently dropped
        {"id": "t3", "status": "MATCHED", "match_time": now, "trader_side": "MAKER", "asset_id": "Y", "side": "BUY",
         "maker_orders": [{"owner": "OTHER", "matched_amount": "5", "price": "0.49"}]},
    ]
    ev = b.refresh_open(CFGS)
    assert [(e[2], e[3]) for e in ev] == [("bid", 20.0), ("ask", 15.0)]
    assert any("WARNING" in m for m in logs)


def test_m5_old_fill_not_re_emitted_after_a_long_lull():
    b = mk()
    old = time.time() - 25 * 3600                       # last (only) fill was 25 h ago
    b.last_trade_ts = old
    b.client.trades = [{"id": "t1", "status": "MATCHED", "match_time": str(int(old)), "trader_side": "TAKER",
                        "maker_orders": [{"maker_address": ME, "asset_id": "Y", "side": "BUY", "matched_amount": "20",
                                          "price": "0.49"}]}]
    first = b.refresh_open(CFGS)
    assert len(first) == 1
    for _ in range(3):
        assert b.refresh_open(CFGS) == []


def test_m4_redeemable_winner_stays_in_equity(monkeypatch):
    b = mk()
    pos = [{"conditionId": "c", "outcomeIndex": 0, "size": 40, "currentValue": 38.8, "redeemable": False}]
    monkeypatch.setattr("pmbot.live.api.positions", lambda u: pos)
    e1 = b.trading_equity({"c": 0.97})
    pos[0].update(redeemable=True, currentValue=40.0)
    e2 = b.trading_equity({"c": 0.97})
    assert abs(e1 - 138.8) < 1e-9 and abs(e2 - 140.0) < 1e-9


def test_m3_equity_reads_positions_and_cash_together(monkeypatch):
    b = mk()
    state = {"pos": [{"conditionId": "c", "outcomeIndex": 0, "size": 40, "currentValue": 20.8}]}
    monkeypatch.setattr("pmbot.live.api.positions", lambda u: state["pos"])
    b.client.balance = 80.0
    e1 = b.trading_equity({"c": 0.52})
    b.inv = {"c": __import__("pmbot.engine", fromlist=["Inv"]).Inv(yes=40)}   # stale cycle-start inventory
    state["pos"], b.client.balance = [], 100.8          # SELL 40 @ 0.52 lands between cycle start and equity read
    e2 = b.trading_equity({"c": 0.52})
    assert abs(e1 - 100.8) < 1e-9 and abs(e2 - 100.8) < 1e-9     # no fake spike


def test_l1_already_gone_cancel_is_not_a_failure():
    b = mk()
    b.client.oo = [oo("a", "Y", "BUY", 0.49, 50), oo("b", "N", "BUY", 0.49, 50)]
    b.refresh_open(CFGS)
    b.client.cancel_resp = {"canceled": [], "not_canceled": {"a": "order not found or already canceled",
                                                             "b": "order can't be found - already canceled"}}
    assert "c" not in b.sync({"c": []}, CFGS)


def test_n4_real_cancel_failure_is_a_failure():
    b = mk()
    b.client.oo = [oo("a", "Y", "BUY", 0.49, 50)]
    b.refresh_open(CFGS)
    b.client.cancel_resp = {"canceled": [], "not_canceled": {"a": "failed to cancel order: context canceled"}}
    assert "c" in b.sync({"c": []}, CFGS)


def test_rewards_for_day_per_market_breakdown():
    b = mk()
    r = b.rewards_for_day("2026-09-26")
    assert r["by_market"] == {"c": 2.0, "d": 1.5} and "total" in r
