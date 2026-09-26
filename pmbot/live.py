"""Live broker (Polymarket CLOB V2 via py-clob-client-v2).

Safety: post-only GTC orders only (never takes liquidity / never pays taker fees), heartbeat dead-man switch
(exchange cancels all our orders if the bot stops sending heartbeats for ~10 s), cancel-all on exit.
Required env: PM_PRIVATE_KEY, PM_FUNDER (proxy/safe wallet address that holds funds), PM_SIGNATURE_TYPE (0=EOA,
1=POLY_PROXY email/magic wallet, 2=GNOSIS_SAFE browser wallet). API creds are derived from the key.
"""
import os, time, threading
from . import api
from .engine import Inv

HOST = os.environ.get("PM_CLOB_HOST", "https://clob.polymarket.com")


class LiveBroker:
    def __init__(self, log=print):
        from py_clob_client_v2 import ClobClient
        self.log = log
        key = os.environ["PM_PRIVATE_KEY"]
        self.funder = os.environ.get("PM_FUNDER")
        sig = int(os.environ.get("PM_SIGNATURE_TYPE", "1"))
        c = ClobClient(host=HOST, chain_id=137, key=key, signature_type=sig, funder=self.funder)
        creds = c.create_or_derive_api_key()
        self.client = ClobClient(host=HOST, chain_id=137, key=key, creds=creds, signature_type=sig, funder=self.funder)
        self.user = self.funder or self.client.get_address()
        ban = self.client.get_closed_only_mode()
        if isinstance(ban, dict) and ban.get("closed_only"):
            raise SystemExit("Account is in closed-only mode (geoblocked jurisdiction). Refusing to run.")
        self._hb_id, self._stop = "", False
        threading.Thread(target=self._heartbeat, daemon=True).start()
        self.inv, self.fills = {}, []
        self.open_orders = []

    def _heartbeat(self):
        while not self._stop:
            try:
                r = self.client.post_heartbeat(self._hb_id)
                if isinstance(r, dict) and r.get("heartbeat_id"):
                    self._hb_id = r["heartbeat_id"]
            except Exception as e:
                self.log(f"heartbeat error: {e}")
            time.sleep(5)

    # --- orders ---
    def _open_orders(self):
        try:
            return self.client.get_open_orders()
        except Exception as e:
            self.log(f"get_open_orders error: {e}")
            return None

    def sync(self, desired, cfgs):
        from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions, PostOrdersV2Args
        open_ = self._open_orders()
        if open_ is None:
            return
        self.open_orders = open_
        want = {}
        for cid, ol in desired.items():
            for o in ol:
                want[(o.token, o.side, round(o.price, 6))] = (o, cid)
        keep, cancel = set(), []
        for oo in open_:
            k = (oo["asset_id"], oo["side"].upper(), round(float(oo["price"]), 6))
            rem = float(oo["original_size"]) - float(oo.get("size_matched") or 0)
            w = want.get(k)
            if w and abs(rem - w[0].size) < max(1.0, 0.2 * w[0].size) and k not in keep:
                keep.add(k)
            else:
                cancel.append(oo["id"])
        if cancel:
            for i in range(0, len(cancel), 500):
                try:
                    self.client.cancel_orders(cancel[i:i + 500])
                except Exception as e:
                    self.log(f"cancel error: {e}")
        posts = []
        for k, (o, cid) in want.items():
            if k in keep:
                continue
            c = cfgs[cid]
            try:
                signed = self.client.create_order(
                    OrderArgs(token_id=o.token, price=o.price, size=o.size, side=o.side),
                    PartialCreateOrderOptions(tick_size=_tick_str(c["tick"]), neg_risk=c["neg_risk"]))
                posts.append(PostOrdersV2Args(order=signed, orderType=OrderType.GTC))
            except Exception as e:
                self.log(f"create_order error {c['q'][:40]}: {e}")
        for i in range(0, len(posts), 15):
            try:
                r = self.client.post_orders(posts[i:i + 15], post_only=True)
                for x in (r or []):
                    if isinstance(x, dict) and x.get("errorMsg"):
                        self.log(f"post error: {x.get('errorMsg')}")
            except Exception as e:
                self.log(f"post_orders error: {e}")

    def own_orders(self, c):
        """Our resting orders for market c in YES-price space (to remove them from the observed book)."""
        bids, asks = [], []
        for oo in self.open_orders:
            rem = float(oo["original_size"]) - float(oo.get("size_matched") or 0)
            p, side, tok = float(oo["price"]), oo["side"].upper(), oo["asset_id"]
            if tok == c["yes"]:
                (bids if side == "BUY" else asks).append((p, rem))
            elif tok == c["no"]:
                (asks if side == "BUY" else bids).append((round(1 - p, 6), rem))
        return {"bids": bids, "asks": asks}

    def poll_fills(self, cfgs):
        """Inventory from public positions endpoint (authoritative)."""
        pos = api.positions(self.user)
        by_token = {p["asset"]: float(p["size"]) for p in pos if float(p.get("size") or 0) > 0}
        for cid, c in cfgs.items():
            self.inv[cid] = Inv(yes=by_token.get(c["yes"], 0.0), no=by_token.get(c["no"], 0.0))
        return []

    def inventory(self, cid):
        return self.inv.get(cid, Inv())

    def cash_balance(self):
        from py_clob_client_v2 import BalanceAllowanceParams, AssetType
        try:
            r = self.client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
            return float(r["balance"]) / 1e6
        except Exception:
            return None

    def rewards_for_day(self, day):
        """Actual liquidity rewards credited by Polymarket for a UTC day (paid at midnight UTC)."""
        try:
            return self.client.get_total_earnings_for_user_for_day(day)
        except Exception as e:
            return {"error": str(e)}

    def shutdown(self):
        self._stop = True
        try:
            self.client.cancel_all()
            self.log("cancelled all orders")
        except Exception as e:
            self.log(f"cancel_all error: {e}")


def _tick_str(t):
    for s in ("0.1", "0.01", "0.005", "0.0025", "0.001", "0.0001"):
        if abs(float(s) - t) < 1e-12:
            return s
    return "0.01"
