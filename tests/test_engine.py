"""Regression tests for the audit findings (H5, H7, M6) and core pricing/scoring invariants."""
from pmbot import scoring
from pmbot.engine import target_orders, Inv, ys_orders
from pmbot.selection import quote_prices
from pmbot.config import CFG

CFG_T = dict(CFG, mode="join", max_inventory_frac=1.0)


def mk(min_size=20, v=4.5, tick=0.01):
    return {"cid": "c", "yes": "Y", "no": "N", "v": v, "min_size": min_size, "tick": tick, "neg_risk": False}


def st_from(bids, asks, min_size=20, v=4.5, tick=0.01):
    book = {"bids": [{"price": str(p), "size": str(s)} for p, s in bids],
            "asks": [{"price": str(p), "size": str(s)} for p, s in asks], "tick_size": str(tick)}
    return scoring.book_state(book, min_size, v)


def test_h7_bid_never_above_adjusted_mid():
    # thin 5-share bid at 0.53 above a deep 0.47 bid; adjusted mid 0.505 -> our bid must be <= mid - tick
    st = st_from([(0.53, 5), (0.47, 500)], [(0.54, 500)])
    b, a = quote_prices(st, mk(), "join")
    assert b is not None and b <= st["mid"] - 0.01 + 1e-9
    assert a is not None and a >= st["mid"] + 0.01 - 1e-9


def test_quotes_inside_reward_band():
    st = st_from([(0.14, 160)], [(0.40, 950)])      # wide book, mid 0.27
    b, a = quote_prices(st, mk(), "join")
    assert 0 <= (st["mid"] - b) * 100 < 4.5 and 0 <= (a - st["mid"]) * 100 < 4.5


def test_h5_no_split_legs_below_min_size():
    st = st_from([(0.49, 100)], [(0.51, 100)], min_size=50)
    orders = target_orders(mk(min_size=50), st, Inv(yes=0, no=30), 50, CFG_T)
    for o in orders:
        assert o.size >= 50, o
    # scored share only counts orders >= min size
    _, sh, _ = scoring.our_share(st, 4.5, 50, [("bid", 0.49, 30), ("ask", 0.51, 20)])
    assert sh == 0.0


def test_m6_inventory_cap_exact():
    st = st_from([(0.49, 100)], [(0.51, 100)])
    orders = target_orders(mk(), st, Inv(yes=49.9, no=0), 50, CFG_T)
    bid = sum(o.size for o in orders if o.ys_side == "bid")
    assert 49.9 + bid <= 50 + 1e-6


def test_sell_inventory_instead_of_buying_complement():
    st = st_from([(0.49, 100)], [(0.51, 100)])
    orders = target_orders(mk(), st, Inv(yes=40, no=0), 40, CFG_T)
    ask = [o for o in orders if o.ys_side == "ask"]
    assert ask and ask[0].side == "SELL" and ask[0].token == "Y"


def test_unwind_never_below_mid():
    st = st_from([(0.30, 100), (0.66, 3)], [(0.70, 100)])   # thin 0.66 bid above deep 0.30 bid, adjusted mid 0.50
    orders = target_orders(mk(), st, Inv(yes=0, no=40), 0, CFG_T, unwind_only=True)
    for o in orders:
        assert o.side == "SELL"
        # selling NO at (1 - bid) must be >= NO's mid value (1 - mid)
        assert o.price >= (1 - st["mid"]) - 1e-9


def test_conservative_share_le_central():
    st = st_from([(0.48, 80), (0.47, 50)], [(0.52, 30), (0.53, 200)])
    _, c, m = scoring.our_share(st, 4.5, 20, [("bid", 0.48, 40), ("ask", 0.52, 40)])
    assert 0 < c <= m <= 1


def test_tick_0001_rounding():
    st = st_from([(0.955, 100)], [(0.962, 100)], tick=0.001)
    b, a = quote_prices(st, mk(tick=0.001), "join")
    assert abs(b * 1000 - round(b * 1000)) < 1e-6 and abs(a * 1000 - round(a * 1000)) < 1e-6


def test_m1_band_stepping_never_crosses_raw_book():
    # audit #3 example: thin 0.52 ask below a size-adjusted mid of ~0.57 -> our bid must stay below 0.52
    for v in (2.0, 3.5, 4.5):
        st = st_from([(0.39, 500)], [(0.52, 5), (0.75, 500)], min_size=20, v=v)
        b, a = quote_prices(st, mk(v=v), "join")
        assert b is None or b <= 0.52 - 0.01 + 1e-9
        assert a is None or a >= 0.39 + 0.01 - 1e-9
