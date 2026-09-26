"""Paper broker: queue position and maker-leg fill mapping."""
from pmbot.paper import PaperBroker, _maker_ys
from pmbot.engine import Order


def test_maker_leg_mapping():
    c = {"yes": "Y", "no": "N"}
    assert _maker_ys({"asset": "Y", "side": "BUY", "price": "0.4", "size": "10"}, c) == ("bid", 0.4, 10.0)
    assert _maker_ys({"asset": "Y", "side": "SELL", "price": "0.6", "size": "10"}, c) == ("ask", 0.6, 10.0)
    assert _maker_ys({"asset": "N", "side": "BUY", "price": "0.4", "size": "10"}, c) == ("ask", 0.6, 10.0)
    assert _maker_ys({"asset": "N", "side": "SELL", "price": "0.6", "size": "10"}, c) == ("bid", 0.4, 10.0)


def test_queue_ahead_from_displayed_size():
    pb = PaperBroker(log=lambda *a: None)
    st = {"bids": [(0.40, 120.0)], "asks": [(0.60, 80.0)]}
    o = Order("c", "Y", "BUY", 0.40, 20, "bid", 0.40)
    pb.sync({"c": [o]}, {"c": st})
    r = next(iter(pb.resting.values()))
    assert r["queue_ahead"] == 120.0
    # unchanged order keeps its queue position
    pb.sync({"c": [Order("c", "Y", "BUY", 0.40, 20, "bid", 0.40)]}, {"c": {"bids": [(0.40, 5.0)], "asks": []}})
    assert next(iter(pb.resting.values()))["queue_ahead"] == 120.0


def test_apply_buy_then_sell_cash_and_inventory():
    pb = PaperBroker(log=lambda *a: None)
    pb._apply("c", Order("c", "Y", "BUY", 0.40, 20, "bid", 0.40), 20)
    assert pb.inv["c"].yes == 20 and abs(pb.cash + 8.0) < 1e-9
    pb._apply("c", Order("c", "Y", "SELL", 0.45, 20, "ask", 0.45), 20)
    assert pb.inv["c"].yes == 0 and abs(pb.cash - 1.0) < 1e-9


def test_poll_fills_placed_filter_queue_and_dedupe(monkeypatch):
    import time as _t
    from pmbot import paper as P
    now = int(_t.time())
    pb = PaperBroker(log=lambda *a: None)
    c = {"cid": "c", "yes": "Y", "no": "N"}
    pb.sync({"c": [Order("c", "Y", "BUY", 0.40, 20, "bid", 0.40)]}, {"c": {"bids": [(0.40, 10.0)], "asks": []}})
    old = {"transactionHash": "t0", "proxyWallet": "m0", "asset": "Y", "size": "50", "price": "0.39", "side": "BUY",
           "timestamp": now - 600}                                  # before our order existed -> ignored
    at = {"transactionHash": "t1", "proxyWallet": "m1", "asset": "Y", "size": "15", "price": "0.40", "side": "BUY",
          "timestamp": now + 1}                                     # at our level: 10 ahead of us -> we get 5
    taker = {"transactionHash": "t1", "proxyWallet": "tk", "asset": "Y", "size": "15", "price": "0.40", "side": "SELL",
             "timestamp": now + 1}
    feeds = {False: [at, taker, old], True: [taker]}
    monkeypatch.setattr(P.api, "market_trades", lambda cid, taker_only=True, **k: feeds[taker_only])
    ev = pb.poll_fills({"c": c})
    assert [(e[2], e[3]) for e in ev] == [("bid", 5.0)]
    assert pb.poll_fills({"c": c}) == []                            # same prints are not re-applied



def test_h1_late_print_fills_order_that_was_resting(monkeypatch):
    import time as _t
    from pmbot import paper as P
    pb = PaperBroker(log=lambda *a: None)
    c = {"cid": "c", "yes": "Y", "no": "N"}
    pb.sync({"c": [Order("c", "Y", "BUY", 0.40, 20, "bid", 0.40)]}, {"c": {"bids": [], "asks": []}})
    t_sweep = int(_t.time()) + 1
    # engine reprices to 0.37 before the sweep print is indexed
    pb.sync({"c": [Order("c", "Y", "BUY", 0.37, 20, "bid", 0.37)]}, {"c": {"bids": [], "asks": []}})
    for r in pb.recent:
        r["removed"] = t_sweep + 5
    for r in pb.resting.values():
        r["placed"] = t_sweep + 5
    sweep = {"transactionHash": "s1", "proxyWallet": "m", "asset": "Y", "size": "50", "price": "0.37", "side": "BUY",
             "timestamp": t_sweep}
    monkeypatch.setattr(P.api, "market_trades", lambda cid, taker_only=True, **k: [] if taker_only else [sweep])
    ev = pb.poll_fills({"c": c})
    assert [(e[2], e[3]) for e in ev] == [("bid", 20.0)]          # the 0.40 bid (resting at sweep time) is filled
    assert abs(pb.cash + 8.0) < 1e-9


def test_h1_no_replay_of_old_prints_for_long_resting_orders(monkeypatch):
    import time as _t
    from pmbot import paper as P
    pb = PaperBroker(log=lambda *a: None)
    c = {"cid": "c", "yes": "Y", "no": "N"}
    pb.sync({"c": [Order("c", "Y", "BUY", 0.40, 20, "bid", 0.40)]}, {"c": {"bids": [(0.40, 70.0)], "asks": []}})
    r = next(iter(pb.resting.values()))
    r["placed"] = _t.time() - 5 * 3600                                # order resting for 5 h
    pr = {"transactionHash": "p1", "proxyWallet": "m", "asset": "Y", "size": "30", "price": "0.40", "side": "BUY",
          "timestamp": int(_t.time() - 4 * 3600)}
    monkeypatch.setattr(P.api, "market_trades", lambda cid, taker_only=True, **k: [] if taker_only else [pr])
    for _ in range(5):
        pb.poll_fills({"c": c})
    assert r["queue_ahead"] == 40.0 and pb.fills == []               # applied once, never replayed
