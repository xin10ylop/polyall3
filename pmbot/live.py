"""Live broker (Polymarket CLOB V2 via py-clob-client-v2).

Safety design
* Refuses to start if polymarket.com/api/geoblock says this IP is blocked, if the account is closed-only, or if a
  proxy/safe signature type is used without PM_FUNDER.
* Post-only GTC orders only: an order that would cross is rejected by the exchange, so the bot never takes
  liquidity and never pays taker fees.
* Dead-man switch with a watchdog: the heartbeat thread only heartbeats while the main loop has completed a fully
  successful sync within `watchdog_sec`. If the loop stalls, errors, or the process dies, heartbeats stop and the
  exchange cancels every order (worst case ~watchdog_sec + 15 s). Heartbeat-id desyncs (HTTP 400 carrying the expected
  id) are recovered; a broken chain is restarted; after a lapse a heartbeat is sent before any new order is posted.
* Fills come from the exchange's own trade records for our maker orders (GET /data/trades?maker_address=...), not from
  inferring vanished orders (which would confuse exchange-side cancels with fills). Inventory comes from the positions
  API and keeps its last known value if that call fails.
Use a dedicated Polymarket account: the bot manages (and cancels) every open order on it.
Env: PM_PRIVATE_KEY, PM_FUNDER, PM_SIGNATURE_TYPE (0=EOA, 1=email/Magic proxy, 2=browser-wallet Safe).
"""
import os, time, threading
from . import api
from .engine import Inv

HOST = os.environ.get("PM_CLOB_HOST", "https://clob.polymarket.com")


class LiveBroker:
    def __init__(self, cfg, log=print):
        from py_clob_client_v2 import ClobClient
        self.cfg, self.log = cfg, log
        gb = api.geoblock()
        if gb is None or gb.get("blocked"):
            raise SystemExit(f"Geoblock check failed or blocked ({gb}). Polymarket does not allow trading from here.")
        key = os.environ["PM_PRIVATE_KEY"]
        sig = int(os.environ.get("PM_SIGNATURE_TYPE", "1"))
        self.funder = os.environ.get("PM_FUNDER") or None
        if sig != 0 and not self.funder:
            raise SystemExit("PM_SIGNATURE_TYPE 1/2 requires PM_FUNDER (the proxy/safe address that holds funds).")
        c0 = ClobClient(host=HOST, chain_id=137, key=key, signature_type=sig, funder=self.funder)
        creds = c0.create_or_derive_api_key()
        self.client = ClobClient(host=HOST, chain_id=137, key=key, creds=creds, signature_type=sig, funder=self.funder)
        self.user = self.funder or self.client.get_address()
        ban = self.client.get_closed_only_mode()
        if isinstance(ban, dict) and ban.get("closed_only"):
            raise SystemExit("Account is in closed-only mode. Refusing to run.")
        cash = self.cash_balance()
        if cash is None:
            raise SystemExit("Could not read collateral balance.")
        log(f"live broker ready: user={self.user[:10]}.. cash=${cash:.2f} geo={gb.get('country')}")
        if cash < cfg["capital_usd"]:
            log(f"WARNING: cash ${cash:.2f} < configured capital ${cfg['capital_usd']:.2f}; allocation uses the lower")
        self.open_orders = []
        self.seen_trades, self.last_trade_ts = {}, time.time() - 300
        self.allowed_tokens, self._last_hb_ok = set(), 0.0
        self._cash, self._cash_t = cash, time.time()
        self._update_allowance(None)
        self.inv, self.inv_stale, self.fills = {}, True, []
        self.last_ok, self.hb_ok, self._hb_id, self._stop = 0.0, True, "", False
        threading.Thread(target=self._heartbeat, daemon=True).start()

    # ---------------- heartbeat + watchdog ----------------
    def mark_ok(self):
        self.last_ok = time.time()

    def _heartbeat(self):
        from py_clob_client_v2.exceptions import PolyApiException
        fails = 0
        while not self._stop:
            t0 = time.time()
            if t0 - self.last_ok < self.cfg["watchdog_sec"]:
                for attempt in range(2):
                    try:
                        r = self.client.post_heartbeat(self._hb_id)
                        if isinstance(r, dict) and r.get("heartbeat_id"):
                            self._hb_id = r["heartbeat_id"]
                        fails, self._last_hb_ok = 0, time.time()
                        break
                    except PolyApiException as e:
                        em = e.error_msg if isinstance(e.error_msg, dict) else {}
                        if em.get("heartbeat_id"):          # desync: adopt the id the server expects, retry now
                            self._hb_id = em["heartbeat_id"]
                            continue
                        fails += 1
                        break
                    except Exception:
                        fails += 1
                        break
                if fails >= 5:
                    self._hb_id = ""          # restart the heartbeat chain
                self.hb_ok = fails < 3
            # else: main loop unhealthy -> deliberately skip; the exchange cancels all orders (dead-man switch)
            time.sleep(max(0.2, 3.0 - (time.time() - t0)))

    # ---------------- order state ----------------
    def ensure_heartbeat(self):
        """After a lapse the exchange may still cancel fresh orders; heartbeat synchronously before posting."""
        if time.time() - self._last_hb_ok > 6:
            try:
                r = self.client.post_heartbeat(self._hb_id)
            except Exception as e:
                em = getattr(e, "error_msg", None)
                hid = em.get("heartbeat_id") if isinstance(em, dict) else None
                try:
                    r = self.client.post_heartbeat(hid or "")
                except Exception:
                    return False
            if isinstance(r, dict) and r.get("heartbeat_id"):
                self._hb_id = r["heartbeat_id"]
            self._last_hb_ok = time.time()
        return True

    def refresh_open(self, cfgs):
        """Fetch open orders right before reading books, then read our maker fills from the exchange's trade records.
        Returns fill events [(ts, cid, ys_side, qty)] or None if our open orders could not be read."""
        try:
            self.open_orders = self.client.get_open_orders()
        except Exception as e:
            self.log(f"get_open_orders error: {e}")
            return None
        return self._poll_fills(cfgs)

    def _poll_fills(self, cfgs):
        from py_clob_client_v2 import TradeParams
        tok = {}
        for cid, c in cfgs.items():
            tok[c["yes"]] = (cid, True)
            tok[c["no"]] = (cid, False)
        try:
            trades = self.client.get_trades(TradeParams(maker_address=self.user, after=int(self.last_trade_ts) - 120))
        except Exception as e:
            self.log(f"get_trades error: {e}")
            return []
        events, me = [], self.user.lower()
        for t in trades or []:
            tid = t.get("id")
            if not tid or tid in self.seen_trades or "FAIL" in str(t.get("status", "")).upper():
                continue
            ts = _ts(t.get("match_time") or t.get("matched_at")) or time.time()
            self.seen_trades[tid] = ts
            self.last_trade_ts = max(self.last_trade_ts, ts)
            legs = [mo for mo in (t.get("maker_orders") or []) if str(mo.get("maker_address", "")).lower() == me]
            if not legs and str(t.get("maker_address", "")).lower() == me and t.get("trader_side") == "TAKER":
                legs = [{"asset_id": t.get("asset_id") or t.get("token_id"), "side": t.get("side"),
                         "matched_amount": t.get("size"), "price": t.get("price")}]
            for mo in legs:
                token = mo.get("asset_id") or mo.get("token_id")
                if token not in tok:
                    continue
                cid, is_yes = tok[token]
                buy = str(mo.get("side", "")).upper() == "BUY"
                ys_side = "bid" if (is_yes and buy) or (not is_yes and not buy) else "ask"
                events.append((int(ts), cid, ys_side, float(mo.get("matched_amount") or 0)))
        for k in [k for k, v in self.seen_trades.items() if time.time() - v > 86400]:
            self.seen_trades.pop(k, None)
        self.fills += events
        return events

    def own_orders(self, c):
        """Our resting orders for market c in YES-price space (fresh snapshot taken this cycle)."""
        bids, asks = [], []
        for oo in self.open_orders:
            rem = float(oo["original_size"]) - float(oo.get("size_matched") or 0)
            p, side, tok = float(oo["price"]), oo["side"].upper(), oo["asset_id"]
            if tok == c["yes"]:
                (bids if side == "BUY" else asks).append((p, rem))
            elif tok == c["no"]:
                (asks if side == "BUY" else bids).append((round(1 - p, 6), rem))
        return {"bids": bids, "asks": asks}

    def resting_ys_orders(self, c):
        """Our live orders on market c as [(ys_side, ys_price, remaining)] for reward estimation."""
        own = self.own_orders(c)
        return [("bid", p, s) for p, s in own["bids"]] + [("ask", p, s) for p, s in own["asks"]]

    def sync(self, desired, cfgs):
        """Cancel orders not desired, post missing ones. Returns set of cids whose orders are in place."""
        from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions, PostOrdersV2Args
        want = {}
        for cid, ol in desired.items():
            for o in ol:
                want[(o.token, o.side, round(o.price, 6))] = o
        keep, cancel = set(), []
        tok2cid = {}
        for cid, c in cfgs.items():
            tok2cid[c["yes"]] = cid
            tok2cid[c["no"]] = cid
        for oo in self.open_orders:
            k = (oo["asset_id"], oo["side"].upper(), round(float(oo["price"]), 6))
            rem = float(oo["original_size"]) - float(oo.get("size_matched") or 0)
            w = want.get(k)
            if w and abs(rem - w.size) < max(1.0, 0.2 * w.size) and k not in keep:
                keep.add(k)
            else:
                cancel.append(oo)
        failed_cids = set()
        for i in range(0, len(cancel), 100):
            chunk = cancel[i:i + 100]
            try:
                r = self.client.cancel_orders([o["id"] for o in chunk])
                nc = (r or {}).get("not_canceled") if isinstance(r, dict) else None
                for oid, why in (nc.items() if isinstance(nc, dict) else []):
                    if "match" in str(why).lower():
                        continue          # already filled: not a failure; the fill arrives via the trades poll
                    o = next((x for x in chunk if x["id"] == oid), None)
                    if o:
                        failed_cids.add(tok2cid.get(o["asset_id"]))
            except Exception as e:
                self.log(f"cancel error: {e}")
                failed_cids |= {tok2cid.get(o["asset_id"]) for o in chunk}
        if not self.ensure_heartbeat():
            self.log("heartbeat not confirmed -> not posting this cycle")
            return failed_cids | {None}
        posts, meta = [], []
        for k, o in want.items():
            if k in keep or o.cid in failed_cids:
                continue
            c = cfgs[o.cid]
            try:
                if o.side == "SELL":
                    self._update_allowance(o.token)
                self._sync_tick(o.token, c["tick"])
                signed = self.client.create_order(
                    OrderArgs(token_id=o.token, price=o.price, size=o.size, side=o.side),
                    PartialCreateOrderOptions(tick_size=_tick_str(c["tick"]), neg_risk=c["neg_risk"]))
                posts.append(PostOrdersV2Args(order=signed, orderType=OrderType.GTC))
                meta.append(o)
            except Exception as e:
                self.log(f"create_order error {c['q'][:40]}: {e}")
        for i in range(0, len(posts), 15):
            try:
                res = self.client.post_orders(posts[i:i + 15], post_only=True)
            except Exception as e:
                self.log(f"post_orders error: {e}")
                continue
            if not isinstance(res, list):
                self.log(f"post_orders unexpected response: {str(res)[:200]}")
                continue
            for o, x in zip(meta[i:i + 15], res):
                if not (isinstance(x, dict) and x.get("success")):
                    self.log(f"order rejected ({o.side} {o.size}@{o.price}): {str(x)[:160]}")
        return failed_cids

    def _sync_tick(self, token, tick):
        """The client caches each token's tick forever and rejects a finer one; keep it in line with the live book."""
        cache = getattr(self.client, "_ClobClient__tick_sizes", None)
        ts = _tick_str(tick)
        if isinstance(cache, dict) and cache.get(token) != ts:
            cache[token] = ts

    def _update_allowance(self, token):
        """Refresh the exchange's view of our collateral (token=None) or conditional-token allowance before selling."""
        from py_clob_client_v2 import BalanceAllowanceParams, AssetType
        if token in self.allowed_tokens:
            return
        try:
            p = (BalanceAllowanceParams(asset_type=AssetType.COLLATERAL) if token is None else
                 BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token))
            self.client.update_balance_allowance(p)
            self.allowed_tokens.add(token)
        except Exception as e:
            self.log(f"update_balance_allowance error: {e}")

    def cancel_all(self):
        try:
            self.client.cancel_all()
        except Exception as e:
            self.log(f"cancel_all error: {e}")

    # ---------------- inventory / equity ----------------
    def refresh_inventory(self, cfgs):
        pos = api.positions(self.user)
        if pos is None:
            self.inv_stale = True
            return
        self._pos = pos
        by_token = {p["asset"]: (float(p.get("size") or 0), float(p.get("initialValue") or 0))
                    for p in pos if not p.get("redeemable")}   # resolved positions: redeem manually in the UI
        for cid, c in cfgs.items():
            y, n = by_token.get(c["yes"], (0.0, 0.0)), by_token.get(c["no"], (0.0, 0.0))
            self.inv[cid] = Inv(yes=y[0], no=n[0], cost=y[1] + n[1])
        self.inv_stale = False

    def all_position_cids(self):
        for _ in range(5):
            pos = api.positions(self.user)
            if pos is not None:
                return sorted({p["conditionId"] for p in pos if float(p.get("size") or 0) >= 1 and not p.get("redeemable")})
            time.sleep(3)
        raise SystemExit("Could not load existing positions at startup; refusing to trade blind.")

    def inventory(self, cid):
        return self.inv.get(cid, Inv())

    def inventory_cost(self):
        return sum(max(0.0, i.cost) for i in self.inv.values())

    def cash_balance(self):
        from py_clob_client_v2 import BalanceAllowanceParams, AssetType
        try:
            r = self.client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
            return float(r["balance"]) / 1e6
        except Exception:
            return None

    def cash_cached(self, max_age=60):
        if time.time() - self._cash_t > max_age:
            c = self.cash_balance()
            if c is not None:
                self._cash, self._cash_t = c, time.time()
        return self._cash

    def trading_equity(self, mids):
        """collateral balance (already includes collateral reserved by our open BUYs) + positions at mid."""
        cash = self.cash_balance()
        if cash is None:
            return None
        self._cash, self._cash_t = cash, time.time()
        pos = 0.0
        for cid, inv in self.inv.items():
            m = mids.get(cid)
            if m is not None:
                pos += inv.yes * m + inv.no * (1 - m)
        return cash + pos

    def rewards_for_day(self, day):
        """Actual liquidity rewards credited by Polymarket for a UTC day (paid at midnight UTC)."""
        try:
            return self.client.get_total_earnings_for_user_for_day(day)
        except Exception as e:
            return {"error": str(e)}

    def shutdown(self):
        self._stop = True
        self.cancel_all()
        self.log("cancelled all orders")


def _ts(x):
    """match_time may be unix seconds (str/int) or ISO-8601."""
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        import datetime as dt
        try:
            return dt.datetime.fromisoformat(str(x).replace("Z", "+00:00")).timestamp()
        except Exception:
            return None


def _tick_str(t):
    for s in ("0.1", "0.01", "0.005", "0.0025", "0.001", "0.0001"):
        if abs(float(s) - t) < 1e-12:
            return s
    return "0.01"
