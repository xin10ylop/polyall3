"""Paper broker with a queue-position fill model on real trade prints.

* An order keeps its queue position while its (token, side, price, size) is unchanged; a new/changed order joins the
  back of the queue: queue_ahead = displayed size at that price level when it was placed.
* Fills come from MAKER legs of real trades (data-api takerOnly=false minus taker rows), which carry each maker's
  exact level price (taker rows carry a sweep VWAP). A maker fill strictly beyond our price means the level we rest at
  was swept -> we fill first (price priority). A maker fill AT our price consumes queue_ahead first, then us.
* No automatic YES+NO merge (live does not merge either): pairs stay as locked collateral worth $1 at resolution.
"""
import time
from . import api
from .engine import Inv


class PaperBroker:
    def __init__(self, log=print):
        self.log = log
        self.resting = {}      # key -> dict(order, queue_ahead, filled)
        self.inv = {}          # cid -> Inv
        self.cash = 0.0
        self.last_ts = {}      # cid -> last trade timestamp processed
        self.fills = []

    # ---------- orders ----------
    def sync(self, desired, states):
        new = {}
        for cid, ol in desired.items():
            st = states.get(cid)
            for o in ol:
                k = (o.token, o.side, round(o.price, 6), round(o.size, 2))
                if k in self.resting:
                    new[k] = self.resting[k]
                else:
                    new[k] = {"o": o, "queue_ahead": _displayed(st, o), "filled": 0.0}
        self.resting = new

    def own_orders(self, c):
        return None   # paper orders are not in the real book

    # ---------- fills ----------
    def poll_fills(self, cfgs, tracked_cids):
        now = int(time.time())
        by_cid = {}
        for k, r in self.resting.items():
            by_cid.setdefault(r["o"].cid, []).append(r)
        events = []
        for cid in set(tracked_cids) | set(by_cid):
            since = self.last_ts.get(cid)
            if since is None:
                self.last_ts[cid] = now - 2
                continue
            rs = by_cid.get(cid)
            if not rs:
                self.last_ts[cid] = now      # advance even when not quoting (no replay after cooldowns)
                continue
            allr = api.market_trades(cid, taker_only=False)
            tak = api.market_trades(cid, taker_only=True)
            if allr is None or tak is None:
                continue                      # retry next cycle; last_ts not advanced
            takers = {(t["transactionHash"], t["proxyWallet"], t["asset"], t["size"], t["price"]) for t in tak}
            makers = [t for t in allr if t["timestamp"] > since and
                      (t["transactionHash"], t["proxyWallet"], t["asset"], t["size"], t["price"]) not in takers]
            if allr:
                self.last_ts[cid] = max(since, max(t["timestamp"] for t in allr))
            c = cfgs.get(cid)
            if not c:
                continue
            for t in sorted(makers, key=lambda x: x["timestamp"]):
                ys = _maker_ys(t, c)
                if not ys:
                    continue
                side, p, qty = ys
                for r in rs:
                    o = r["o"]
                    rem = o.size - r["filled"]
                    if rem <= 1e-9 or qty <= 1e-9 or o.ys_side != side:
                        continue
                    if side == "bid":
                        through, at = p < o.ys_price - 1e-9, abs(p - o.ys_price) < 1e-9
                    else:
                        through, at = p > o.ys_price + 1e-9, abs(p - o.ys_price) < 1e-9
                    if not (through or at):
                        continue
                    if at and r["queue_ahead"] > 0:
                        eat = min(r["queue_ahead"], qty)
                        r["queue_ahead"] -= eat
                        qty -= eat
                        if qty <= 1e-9:
                            continue
                    f = min(rem, qty)
                    qty -= f
                    r["filled"] += f
                    self._apply(cid, o, f)
                    events.append((t["timestamp"], cid, o.ys_side, o.token == c["yes"], o.side, o.price, f))
        # drop fully filled orders
        self.resting = {k: r for k, r in self.resting.items() if r["o"].size - r["filled"] > 1e-9}
        self.fills += events
        return events

    def _apply(self, cid, o, f):
        inv = self.inv.setdefault(cid, Inv())
        # token identity from ys_side/side: bid+BUY = YES token, bid+SELL = NO token, ask+SELL = YES, ask+BUY = NO
        is_yes = (o.ys_side == "bid" and o.side == "BUY") or (o.ys_side == "ask" and o.side == "SELL")
        if o.side == "BUY":
            self.cash -= o.price * f
            inv.cost += o.price * f
            if is_yes:
                inv.yes += f
            else:
                inv.no += f
        else:
            held = inv.yes if is_yes else inv.no
            if held > 1e-9:
                inv.cost -= inv.cost * min(1.0, f / (inv.yes + inv.no))
            self.cash += o.price * f
            if is_yes:
                inv.yes -= f
            else:
                inv.no -= f

    # ---------- state ----------
    def inventory(self, cid):
        return self.inv.get(cid, Inv())

    def inventory_cost(self):
        return sum(max(0.0, i.cost) for i in self.inv.values())

    def locked(self):
        return sum(r["o"].price * (r["o"].size - r["filled"]) for r in self.resting.values() if r["o"].side == "BUY")

    def trading_equity(self, mids):
        v = self.cash
        for cid, inv in self.inv.items():
            m = mids.get(cid)
            if m is None:
                continue
            v += inv.yes * m + inv.no * (1 - m)
        return v


def _displayed(st, o):
    """Displayed size already resting at our YES-space price on our side (we join behind it)."""
    if not st:
        return 0.0
    lv = st["bids"] if o.ys_side == "bid" else st["asks"]
    return sum(s for p, s in lv if abs(p - o.ys_price) < 1e-9)


def _maker_ys(t, c):
    """A maker leg -> (ys_side, ys_price, size): which YES-space side of the book was filled, at what level."""
    p, s = float(t["price"]), float(t["size"])
    if t["asset"] == c["yes"]:
        return ("bid", p, s) if t["side"] == "BUY" else ("ask", p, s)
    if t["asset"] == c["no"]:
        return ("ask", round(1 - p, 6), s) if t["side"] == "BUY" else ("bid", round(1 - p, 6), s)
    return None
