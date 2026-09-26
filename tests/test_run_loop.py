"""Drive pmbot.run.main() in live mode with a fake broker, fake books and a virtual clock (adapted from audit #4's
harness): drawdown stop integration and the per-market reward reconciliation across midnight."""
import sys, types, threading, json, glob, os, datetime as _dt
import pytest
import pmbot.run as R
import pmbot.live as L
from pmbot.engine import Inv


class Clock:
    def __init__(self, t):
        self.t = t

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


def universe(n=3):
    return [{"cid": f"c{i}", "q": f"market {i}", "desc": "", "end": "2027-12-31T00:00:00Z", "yes": f"Y{i}",
             "no": f"N{i}", "neg_risk": False, "v": 4.5, "min_size": 20.0, "rate": 20.0, "tick": 0.01, "usd24": 0.0}
            for i in range(n)]


def book():
    return {"bids": [{"price": "0.49", "size": "500"}], "asks": [{"price": "0.51", "size": "500"}],
            "tick_size": "0.01", "last_trade_price": "0.5"}


class FakeLive:
    def __init__(self, clock, eq_fn, fills_fn):
        self.clock, self.eq_fn, self.fills_fn = clock, eq_fn, fills_fn
        self.open_orders, self.inv, self.inv_stale, self.hb_ok, self.fills = [], {}, False, True, []
        self.last_poll = clock.time()

    def all_position_cids(self): return []
    def refresh_inventory(self, cfgs): pass
    def inventory(self, cid): return Inv()
    def inventory_cost(self): return 0.0
    def cash_cached(self): return 100.0
    def own_orders(self, c): return None
    def resting_ys_orders(self, c): return [("bid", 0.49, 20.0), ("ask", 0.51, 20.0)] if c["cid"] == "c0" else []
    def mark_ok(self): pass
    def scoring_snapshot(self): return {}
    def cancel_all(self): pass
    def shutdown(self): pass

    def refresh_open(self, cfgs):
        t = self.clock.time()
        ev = self.fills_fn(self.last_poll, t)
        self.last_poll = t
        self.fills += ev
        return ev

    def sync(self, desired, cfgs):
        self.clock.sleep(2.0)
        return set()

    def trading_equity(self, mids):
        return self.eq_fn(self.clock.time())

    def rewards_for_day(self, d):
        return {"total": 20.0, "by_market": {"c0": 19.5, "zz": 0.5}}


def run(monkeypatch, tmp_path, eq_fn, fills_fn, hours, t0):
    clk = Clock(t0)

    class FDT(_dt.datetime):
        @classmethod
        def utcnow(cls):
            return _dt.datetime.utcfromtimestamp(clk.t)
    monkeypatch.setattr(R, "time", types.SimpleNamespace(time=clk.time, sleep=clk.sleep))
    monkeypatch.setattr(R, "dt", types.SimpleNamespace(datetime=FDT, date=_dt.date))
    monkeypatch.setattr(R, "threading", types.SimpleNamespace(
        Thread=lambda *a, **k: types.SimpleNamespace(start=lambda: None), Lock=threading.Lock))
    monkeypatch.setattr(R, "build_candidates", lambda *a, **k: universe())
    monkeypatch.setattr(R.api, "books", lambda toks, **k: {t: book() for t in toks})
    holder = {}

    def mk(cfg, log):
        holder["b"] = FakeLive(clk, eq_fn, fills_fn)
        return holder["b"]
    monkeypatch.setattr(L, "LiveBroker", mk)
    monkeypatch.setattr(sys, "argv", ["x", "--mode", "live", "--capital", "100", "--out", str(tmp_path),
                                      "--hours", str(hours)])
    R.main()
    recs = [json.loads(l) for f in glob.glob(os.path.join(str(tmp_path), "*.jsonl")) for l in open(f)]
    return clk.t - t0, recs


def test_real_loss_stops_despite_fills_every_100s(monkeypatch, tmp_path):
    t0 = 1_790_000_000.0
    eq = lambda t: 100.0 if t < t0 + 600 else 70.0                        # real $30 loss after 10 min
    fills = lambda a, b: [(int(b), "c1", "bid", 5.0)] if int(b // 100) != int(a // 100) else []
    ran, _ = run(monkeypatch, tmp_path, eq, fills, 1.0, t0)
    assert 600 < ran < 1800                                               # after the loss, well before the hour


def test_no_stop_without_loss_despite_fills(monkeypatch, tmp_path):
    t0 = 1_790_000_000.0
    fills = lambda a, b: [(int(b), "c1", "bid", 5.0)] if int(b // 100) != int(a // 100) else []
    ran, _ = run(monkeypatch, tmp_path, lambda t: 100.0 + (3.0 if int(t // 100) % 2 else 0.0), fills, 0.5, t0)
    assert ran >= 0.5 * 3600 - 30                                         # ran the full half hour


def test_per_market_reconciliation_across_midnight(monkeypatch, tmp_path):
    t0 = _dt.datetime(2026, 9, 26, 23, 30, tzinfo=_dt.timezone.utc).timestamp()
    ran, recs = run(monkeypatch, tmp_path, lambda t: 100.0, lambda a, b: [], 2.2, t0)
    rec = [r for r in recs if r.get("reconcile_day") == "2026-09-26"]
    assert rec, "no reconciliation record"
    pm = rec[0]["per_market"]
    assert set(pm) == {"c0"} and pm["c0"]["est"] > 0 and pm["c0"]["paid"] == 19.5
    assert rec[0]["paid_not_estimated"] == {"zz": 0.5}
