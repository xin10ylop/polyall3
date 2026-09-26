"""Quoting engine: turns (market, book state, inventory, target size) into concrete orders.

YES-space bid of size n  -> SELL NO at (1 - bid) up to NO held, remainder BUY YES at bid
YES-space ask of size n  -> SELL YES at ask up to YES held, remainder BUY NO at (1 - ask)
Selling held inventory instead of buying the complement avoids locking capital in YES+NO pairs (no merge needed).
All of these orders score for rewards: a NO ask at q is a YES-space bid at 1-q, a NO bid at q is a YES-space ask at 1-q.
"""
from dataclasses import dataclass, field
from .select import quote_prices

MIN_ORDER = 5.0


@dataclass
class Inv:
    yes: float = 0.0
    no: float = 0.0


@dataclass
class Order:
    token: str
    side: str      # 'BUY' | 'SELL'
    price: float
    size: float
    ys_side: str   # 'bid' | 'ask' (YES-space side, for fills and scoring)


def target_orders(c, st, inv, size, cfg):
    """Returns (orders, bid, ask, bid_size, ask_size) for one market."""
    if size <= 0 or st is None:
        return [], None, None, 0.0, 0.0
    bid, ask = quote_prices(st, c, cfg["mode"])
    net = inv.yes - inv.no
    max_inv = cfg["max_inventory_frac"] * size
    orders = []
    bid_sz = size if net < max_inv else 0.0
    ask_sz = size if -net < max_inv else 0.0
    if bid_sz > 0:
        sell_no = min(bid_sz, inv.no)
        if sell_no >= MIN_ORDER:
            orders.append(Order(c["no"], "SELL", _r(1 - bid, c["tick"]), _s(sell_no), "bid"))
        else:
            sell_no = 0.0
        rest = bid_sz - sell_no
        if rest >= MIN_ORDER:
            orders.append(Order(c["yes"], "BUY", _r(bid, c["tick"]), _s(rest), "bid"))
    if ask_sz > 0:
        sell_yes = min(ask_sz, inv.yes)
        if sell_yes >= MIN_ORDER:
            orders.append(Order(c["yes"], "SELL", _r(ask, c["tick"]), _s(sell_yes), "ask"))
        else:
            sell_yes = 0.0
        rest = ask_sz - sell_yes
        if rest >= MIN_ORDER:
            orders.append(Order(c["no"], "BUY", _r(1 - ask, c["tick"]), _s(rest), "ask"))
    eff_bid = sum(o.size for o in orders if o.ys_side == "bid")
    eff_ask = sum(o.size for o in orders if o.ys_side == "ask")
    return orders, bid, ask, eff_bid, eff_ask


def _r(p, tick):
    n = round(p / tick)
    return round(n * tick, 6)


def _s(x):
    return float(int(x * 100) / 100.0)
