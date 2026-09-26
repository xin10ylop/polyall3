"""Paper broker: orders rest at their prices; real taker trade prints at/through our price fill us (pessimistic:
we assume we are first in the queue at our level, which maximises adverse-selection exposure)."""
import time
from . import api
from .engine import Inv


class PaperBroker:
    def __init__(self, log=print):
        self.orders = {}        # cid -> list[Order]
        self.inv = {}           # cid -> Inv
        self.cash = 0.0
        self.last_ts = {}       # cid -> last trade timestamp seen
        self.fills = []
        self.log = log

    def sync(self, desired):
        self.orders = {cid: list(o) for cid, o in desired.items()}

    def locked_collateral(self):
        return sum(o.price * o.size for ol in self.orders.values() for o in ol if o.side == "BUY")

    def poll_fills(self, cfgs):
        now = int(time.time())
        new = []
        for cid, ol in self.orders.items():
            c = cfgs.get(cid)
            if not c or not ol:
                self.last_ts.setdefault(cid, now)
                continue
            since = self.last_ts.setdefault(cid, now)
            tr = [t for t in api.market_trades(cid) if t["timestamp"] > since]
            if not tr:
                continue
            self.last_ts[cid] = max(t["timestamp"] for t in tr)
            rem = {id(o): o.size for o in ol}
            for t in sorted(tr, key=lambda x: x["timestamp"]):
                ys = _to_yes_space(t, c)
                if not ys:
                    continue
                side, p = ys
                qty = float(t["size"])
                for o in ol:
                    if qty <= 0 or rem[id(o)] <= 0:
                        continue
                    ys_px = o.price if o.token == c["yes"] else round(1 - o.price, 6)
                    hit = (side == "sell" and o.ys_side == "bid" and p <= ys_px + 1e-9) or \
                          (side == "buy" and o.ys_side == "ask" and p >= ys_px - 1e-9)
                    if not hit:
                        continue
                    f = min(rem[id(o)], qty)
                    rem[id(o)] -= f
                    qty -= f
                    self._apply(cid, c, o, f)
                    new.append((t["timestamp"], cid, o.token == c["yes"], o.side, o.price, f))
        self.fills += new
        return new

    def _apply(self, cid, c, o, f):
        inv = self.inv.setdefault(cid, Inv())
        is_yes = o.token == c["yes"]
        if o.side == "BUY":
            self.cash -= o.price * f
            if is_yes:
                inv.yes += f
            else:
                inv.no += f
        else:
            self.cash += o.price * f
            if is_yes:
                inv.yes -= f
            else:
                inv.no -= f
        m = min(inv.yes, inv.no)
        if m > 0:  # a YES+NO pair is worth exactly $1 (merge)
            inv.yes -= m
            inv.no -= m
            self.cash += m

    def inventory(self, cid):
        return self.inv.get(cid, Inv())

    def equity(self, mids):
        v = self.cash
        for cid, inv in self.inv.items():
            m = mids.get(cid)
            if m is None:
                continue
            v += inv.yes * m + inv.no * (1 - m)
        return v


def _to_yes_space(t, c):
    p = float(t["price"])
    if t["asset"] == c["yes"]:
        return ("sell", p) if t["side"] == "SELL" else ("buy", p)
    if t["asset"] == c["no"]:
        return ("buy", round(1 - p, 6)) if t["side"] == "SELL" else ("sell", round(1 - p, 6))
    return None
