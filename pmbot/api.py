"""Public Polymarket endpoints (no auth): markets, books, trades, positions, rewards, geoblock."""
import time, random, requests
from concurrent.futures import ThreadPoolExecutor

GAMMA = "https://gamma-api.polymarket.com"
DATA = "https://data-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

S = requests.Session()
S.headers["User-Agent"] = "pmbot/1.1"


def get(url, params=None, tries=4, timeout=15):
    """GET JSON with bounded retries (worst case ~1 min). Returns None on failure."""
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=timeout)
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
        for i in range(3):
            try:
                r = S.post(f"{CLOB}/books", json=[{"token_id": t} for t in ch], timeout=20).json()
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
    """Most recent trades for a market (newest first). taker_only=False also returns each maker leg."""
    r = get(f"{DATA}/trades", {"market": condition_id, "limit": limit, "takerOnly": str(taker_only).lower()})
    return r if isinstance(r, list) else None


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
