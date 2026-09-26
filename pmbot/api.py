"""Public Polymarket endpoints (no auth): markets, books, trades, rewards."""
import time, random, requests
from concurrent.futures import ThreadPoolExecutor

GAMMA = "https://gamma-api.polymarket.com"
DATA = "https://data-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

S = requests.Session()
S.headers["User-Agent"] = "pmbot/1.0"


def get(url, params=None, tries=6):
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(1.5 * (i + 1) + random.random())
                continue
            return r.json()
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def rewarded_markets():
    """All markets currently paying CLOB liquidity rewards (one entry per condition id)."""
    out, cur = [], ""
    while True:
        r = get(f"{CLOB}/rewards/markets/current", {"next_cursor": cur} if cur else None)
        if not r:
            break
        out += r.get("data", [])
        cur = r.get("next_cursor")
        if not cur or cur == "LTE=":
            break
    return out


def clob_market(condition_id):
    return get(f"{CLOB}/markets/{condition_id}")


def clob_markets(condition_ids, workers=8):
    with ThreadPoolExecutor(workers) as ex:
        return dict(zip(condition_ids, ex.map(clob_market, condition_ids)))


def books(token_ids, workers=6):
    """Order books keyed by token id (POST /books, 100 per request)."""
    out = {}
    chunks = [token_ids[i:i + 100] for i in range(0, len(token_ids), 100)]

    def f(ch):
        for i in range(4):
            try:
                return S.post(f"{CLOB}/books", json=[{"token_id": t} for t in ch], timeout=30).json()
            except Exception:
                time.sleep(1 + i)
        return []

    with ThreadPoolExecutor(workers) as ex:
        for r in ex.map(f, chunks):
            for b in r or []:
                out[b["asset_id"]] = b
    return out


def market_trades(condition_id, limit=200):
    """Most recent taker trades for a market (newest first)."""
    r = get(f"{DATA}/trades", {"market": condition_id, "limit": limit})
    return r if isinstance(r, list) else []


def positions(user, limit=500):
    r = get(f"{DATA}/positions", {"user": user, "limit": limit, "sizeThreshold": 0})
    return r if isinstance(r, list) else []
