"""Quoting engine: (market, book state, inventory, target size) -> concrete orders.

Each YES-space side is expressed as ONE order (never split into legs below the reward min size, which would not
score):
  bid side (buy YES exposure):  SELL NO at (1 - bid) if we hold >= min_size NO, else BUY YES at bid
  ask side (sell YES exposure): SELL YES at ask if we hold >= min_size YES, else BUY NO at (1 - ask)
Selling held inventory instead of buying the complement avoids locking capital in YES+NO pairs (no merge needed).
All of these score: a NO ask at q is a YES-space bid at 1-q, a NO bid at q is a YES-space ask at 1-q.
"""
from dataclasses import dataclass
from .selection import quote_prices

MIN_ORDER = 5.0   # exchange minimum order size (shares)


@dataclass
class Inv:
    yes: float = 0.0
    no: float = 0.0
    cost: float = 0.0   # collateral spent acquiring current holdings (for capital accounting)


@dataclass
class Order:
    cid: str
    token: str
    side: str       # 'BUY' | 'SELL'
    price: float
    size: float
    ys_side: str    # 'bid' | 'ask' (YES-space side, for fills and scoring)
    ys_price: float


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def target_orders(c, st, inv, size, cfg, unwind_only=False, block=()):
    """Orders for one market. `block` may contain 'bid'/'ask' to suppress a side (e.g. right after a fill)."""
    if st is None:
        return []
    bid, ask = quote_prices(st, c, cfg["mode"])
    t, ms = st["tick"], c["min_size"]
    net = inv.yes - inv.no
    orders = []
    if unwind_only:
        # sell held inventory at our ask/bid price (never below the adjusted mid), no new exposure
        if inv.yes >= MIN_ORDER and ask is not None and "ask" not in block:
            orders.append(Order(c["cid"], c["yes"], "SELL", _r(ask, t), _s(inv.yes), "ask", ask))
        if inv.no >= MIN_ORDER and bid is not None and "bid" not in block:
            orders.append(Order(c["cid"], c["no"], "SELL", _r(1 - bid, t), _s(inv.no), "bid", bid))
        return orders
    if size <= 0:
        return []
    max_inv = cfg["max_inventory_frac"] * size
    bid_room = _clamp(max_inv - net, 0.0, size)   # more YES exposure allowed
    ask_room = _clamp(max_inv + net, 0.0, size)   # more NO exposure (or YES sold) allowed
    if bid is not None and "bid" not in block:
        if inv.no >= ms:
            n = min(inv.no, max(bid_room, ms if net < 0 else 0.0))
            if n >= ms:
                orders.append(Order(c["cid"], c["no"], "SELL", _r(1 - bid, t), _s(n), "bid", bid))
        elif bid_room >= ms:
            orders.append(Order(c["cid"], c["yes"], "BUY", _r(bid, t), _s(bid_room), "bid", bid))
    if ask is not None and "ask" not in block:
        if inv.yes >= ms:
            n = min(inv.yes, max(ask_room, ms if net > 0 else 0.0))
            if n >= ms:
                orders.append(Order(c["cid"], c["yes"], "SELL", _r(ask, t), _s(n), "ask", ask))
        elif ask_room >= ms:
            orders.append(Order(c["cid"], c["no"], "BUY", _r(1 - ask, t), _s(ask_room), "ask", ask))
    return orders


def ys_orders(orders):
    """[(ys_side, ys_price, size)] for scoring."""
    return [(o.ys_side, o.ys_price, o.size) for o in orders]


def _r(p, tick):
    return round(round(p / tick) * tick, 6)


def _s(x):
    return float(int(x * 100) / 100.0)
