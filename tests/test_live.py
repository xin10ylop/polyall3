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
    def are_orders_scoring(s, p): return {i: True for i in p.orderIds}
    def post_heartbeat(s, hid):
        s.hb += 1
        return {"heartbeat_id": f"h{s.hb}"}


def mk():
    b = LiveBroker.__new__(LiveBroker)
    b.cfg, b.log, b.client, b.user = dict(CFG), (lambda *a: None), FakeClient(), ME
    b.open_orders, b.inv, b.inv_stale, b.fills = [], {}, False, []
    b.seen_trades, b.last_trade_ts, b.allowed_tokens, b._last_hb_ok = {}, time.time() - 300, set(), time.time()
    b._cash, b._cash_t, b._hb_id = 100.0, time.time(), ""
    return b


def oo(i, tok, side, p, sz, m=0):
    return {"id": i, "asset_id": tok, "side": side, "price": str(p), "original_size": str(sz), "size_matched": str(m)}


def test_n1_equity_not_double_counting_reserved_collateral():
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
