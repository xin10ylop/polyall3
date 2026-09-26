"""Public Polymarket endpoints (no auth): markets, books, trades, positions, rewards, geoblock."""
import time, random, threading, requests
from concurrent.futures import ThreadPoolExecutor

GAMMA = "https://gamma-api.polymarket.com"
DATA = "https://data-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

_TL = threading.local()


def session():
    """One requests.Session per thread (the universe thread's bursts don't share a pool with the quoting loop)."""
    s = getattr(_TL, "s", None)
    if s is None:
        s = _TL.s = requests.Session()
        s.headers["User-Agent"] = "pmbot/1.2"
    return s


def get(url, params=None, tries=3, timeout=10):
    """GET JSON with bounded retries (worst case ~35 s). Returns None on failure."""
    for i in range(tries):
        try:
            r = session().get(url, params=params, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(1.0 * (i + 1) + random.random())
                continue
            return r.json()
        except Exception:
            time.sleep(1.0 * (i + 1))
    return None


def geoblock():
    """{'blocked': bool, 'country': .., 'region': ..} for this machine's IP, or None if unknown."""
    r = get("https://polymarket.com/api/geoblock", tries=3)
    return r if isinstance(r, dict) and "blocked" in r else None


def rewarded_markets():
    """All markets currently paying CLOB liquidity rewards (one entry per condition id)."""
    out, cur = [], ""
    for _ in range(1000):
        r = get(f"{CLOB}/rewards/markets/current", {"next_cursor": cur} if cur else None)
        if not isinstance(r, dict):
            break
        out += r.get("data") or []
        cur = r.get("next_cursor")
        if not cur or cur == "LTE=":
            break
    return out


def clob_market(condition_id):
    r = get(f"{CLOB}/markets/{condition_id}")
    return r if isinstance(r, dict) else None


def clob_markets(condition_ids, workers=8):
    with ThreadPoolExecutor(workers) as ex:
        return dict(zip(condition_ids, ex.map(clob_market, condition_ids)))


def books(token_ids, workers=6):
    """Order books keyed by token id (POST /books, 100 per request). Missing books are simply absent."""
    out = {}
    chunks = [token_ids[i:i + 100] for i in range(0, len(token_ids), 100)]

    def f(ch):
        for i in range(2):
            try:
                r = session().post(f"{CLOB}/books", json=[{"token_id": t} for t in ch], timeout=10).json()
                if isinstance(r, list):
                    return r
            except Exception:
                pass
            time.sleep(1 + i)
        return []

    with ThreadPoolExecutor(workers) as ex:
        for r in ex.map(f, chunks):
            for b in r:
                if isinstance(b, dict) and "asset_id" in b:
                    out[b["asset_id"]] = b
    return out


def market_trades(condition_id, limit=500, taker_only=True):
    """Most recent trades for a market (newest first). taker_only=False also returns each maker leg.
    The data-api response is CDN-cached for up to 300 s; a unique cache-buster parameter forces a fresh read."""
    r = get(f"{DATA}/trades", {"market": condition_id, "limit": limit, "takerOnly": str(taker_only).lower(),
                               "_": time.time_ns()})
    return r if isinstance(r, list) else None


def activity_24h(condition_id):
    """(taker $ traded, YES-price range) over the last 24h, from fresh (cache-busted) trade prints; None on failure."""
    t = market_trades(condition_id, limit=500, taker_only=True)
    if t is None:
        return None
    cut = time.time() - 86400
    t = [x for x in t if x.get("timestamp", 0) > cut]
    usd = sum(float(x["size"]) * float(x["price"]) for x in t)
    ps = [float(x["price"]) if x.get("outcomeIndex", 0) == 0 else 1 - float(x["price"]) for x in t]
    return usd, (max(ps) - min(ps)) if ps else 0.0


def positions(user, page=500):
    """All positions of a wallet (paginated). Returns None on any failure (callers must keep last known state)."""
    out, off = [], 0
    for _ in range(40):
        r = get(f"{DATA}/positions", {"user": user, "limit": page, "offset": off, "sizeThreshold": 0})
        if not isinstance(r, list):
            return None
        out += r
        if len(r) < page:
            return out
        off += page
    return out
