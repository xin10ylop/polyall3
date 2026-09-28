"""Paper broker with a queue-position fill model on real trade prints.

* An order keeps its queue position while its (token, side, price) is unchanged and its size is within 20% (the same
  keep-tolerance the live broker uses); a new/changed order joins the back of the queue: queue_ahead = displayed size
  at that price level when it was placed. A trade can only fill orders that were already resting when it happened.
* The trade feed is read with a cache-buster (the data-api CDN caches it for up to 300 s); trades are de-duplicated
  by identity, not by a wall-clock cursor, so late-arriving prints are still applied.
* A trade's legs are only used once the takerOnly=true feed also shows it (the two feeds are indexed separately);
  otherwise the taker's own row could be mistaken for a maker leg.
* The data-api indexes trades 30-90 s late. Orders that were repriced or cancelled are therefore kept for `RETAIN`
  seconds with their [placed, removed] interval, and a late print fills whichever order was resting when it traded
  (a live maker is filled at the moment of the sweep, not when the print shows up in the feed).
* Fills come from MAKER legs of real trades (data-api takerOnly=false minus taker rows), which carry each maker's
  exact level price (taker rows carry a sweep VWAP). A maker fill strictly beyond our price means the level we rest at
  was swept -> we fill first (price priority). A maker fill AT our price consumes queue_ahead first, then us.
* No automatic YES+NO merge (live does not merge either): pairs stay as locked collateral worth $1 at resolution.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from . import api
from .engine import Inv

RETAIN = 300   # seconds a removed paper order can still be filled by late-indexed prints


class PaperBroker:
    def __init__(self, log=print):
        self.log = log
        self.resting = {}      # key -> dict(order, queue_ahead, filled)
        self.inv = {}          # cid -> Inv
        self.cash = 0.0
        self.seen = {}         # trade identity -> timestamp (dedupe)
        self.recent = []       # removed orders: dict(o, queue_ahead, filled, placed, removed)
        self.fills = []

    # ---------- orders ----------
    def sync(self, desired, states):
        new, now = {}, time.time()
        for cid, ol in desired.items():
            st = states.get(cid)
            for o in ol:
                k = (o.token, o.side, round(o.price, 6))
                old = self.resting.get(k)
                if old and abs((old["o"].size - old["filled"]) - o.size) <= max(1.0, 0.2 * o.size):
                    new[k] = old
                else:
                    new[k] = {"o": o, "queue_ahead": _displayed(st, o), "filled": 0.0, "placed": now}
        for k, r in self.resting.items():
            if k not in new or new[k] is not r:
                r["removed"] = now
                self.recent.append(r)
        self.recent = [r for r in self.recent if now - r["removed"] <= RETAIN and r["o"].size - r["filled"] > 1e-9]
        self.resting = new

    def own_orders(self, c):
        return None   # paper orders are not in the real book

    # ---------- fills ----------
    def poll_fills(self, cfgs, tracked_cids=()):
        by_cid = {}
        for r in list(self.resting.values()) + self.recent:
            by_cid.setdefault(r["o"].cid, []).append(r)
        cids = [c for c in by_cid if c in cfgs]

        def fetch(cid):
            return cid, api.market_trades(cid, taker_only=False), api.market_trades(cid, taker_only=True)
        with ThreadPoolExecutor(8) as ex:
            feeds = list(ex.map(fetch, cids))
        key = lambda t: (t["transactionHash"], t["proxyWallet"], t["asset"], t["size"], t["price"])
        events = []
        for cid, allr, tak in feeds:
            if allr is None or tak is None:
                continue
            c, rs = cfgs[cid], by_cid[cid]
            takers = {key(t) for t in tak}
            taker_tx = {t["transactionHash"] for t in tak}
            oldest = min(r["placed"] for r in rs)
            makers = []
            for t in allr:
                k = key(t)
                if k in takers or k in self.seen or t["timestamp"] < oldest - 1:
                    continue
                if t["transactionHash"] not in taker_tx:
                    continue      # taker feed has not indexed this trade yet: its taker row cannot be told apart
                                  # from the maker legs, so wait (do not mark as seen) and retry next cycle
                self.seen[k] = t["timestamp"]
                makers.append(t)
            for t in sorted(makers, key=lambda x: x["timestamp"]):
                ys = _maker_ys(t, c)
                if not ys:
                    continue
                side, p, qty = ys
                ts = t["timestamp"]
                for r in rs:
                    o = r["o"]
                    rem = o.size - r["filled"]
                    if rem <= 1e-9 or qty <= 1e-9 or o.ys_side != side:
                        continue
                    if ts < r["placed"] - 1 or ts > r.get("removed", float("inf")) + 1:
                        continue          # this order was not resting when the print happened
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
                    events.append((ts, cid, o.ys_side, f))
                    break     # we rest one order per side, so one print can fill only one of them (requote races)
        self.resting = {k: r for k, r in self.resting.items() if r["o"].size - r["filled"] > 1e-9}
        # prune dedupe memory only below every order that could still be filled (no replays of old prints)
        live_orders = list(self.resting.values()) + self.recent
        floor = min((r["placed"] for r in live_orders), default=time.time()) - 60
        self.seen = {k: v for k, v in self.seen.items() if v >= floor}
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
