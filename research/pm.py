"""Shared Polymarket data helpers (public endpoints only)."""
import requests, json, time, random

S = requests.Session()
S.headers['User-Agent'] = 'Mozilla/5.0 (research)'
GAMMA = "https://gamma-api.polymarket.com"
DATA = "https://data-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

def get(url, params=None, tries=6):
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(1.5 * (i + 1) + random.random()); continue
            return r.json()
        except Exception as e:
            time.sleep(1.5 * (i + 1))
    return None

KEEP = ['id','question','conditionId','slug','endDate','closedTime','outcomes','outcomePrices','volumeNum',
        'clobTokenIds','negRisk','negRiskMarketID','feeType','feeSchedule','sportsMarketType','umaResolutionStatus',
        'groupItemTitle','gameStartTime','eventStartTime','startDate','createdAt','description','resolutionSource','line','orderPriceMinTickSize']

def slim(m):
    d = {k: m.get(k) for k in KEEP}
    ev = (m.get('events') or [{}])[0]
    d['event_slug'] = ev.get('slug'); d['event_title'] = ev.get('title'); d['event_id'] = ev.get('id')
    d['series'] = (ev.get('seriesSlug') or (ev.get('series') or [{}])[0].get('slug') if ev.get('series') else ev.get('seriesSlug'))
    tags = ev.get('tags') or []
    d['tags'] = [t.get('slug') for t in tags if isinstance(t, dict)]
    return d

def closed_markets(day_lo, day_hi, **extra):
    """All closed markets with endDate in [day_lo, day_hi) via keyset pagination."""
    out = []; cursor = None
    while True:
        p = dict(limit=500, closed='true', end_date_min=day_lo, end_date_max=day_hi, **extra)
        if cursor: p['after_cursor'] = cursor
        r = get(f"{GAMMA}/markets/keyset", p)
        if not r: break
        out += r.get('markets', [])
        cursor = r.get('next_cursor')
        if not cursor or not r.get('markets'): break
    return out

def trades(condition_id, end=None, max_pages=40, limit=500):
    """Taker trades for a market, newest first, paginating backwards via `end`."""
    out = []; seen = set()
    for _ in range(max_pages):
        p = dict(market=condition_id, limit=limit)
        if end: p['end'] = end
        r = get(f"{DATA}/trades", p)
        if not isinstance(r, list) or not r: break
        new = 0
        for t in r:
            k = (t.get('transactionHash'), t.get('asset'), t.get('size'), t.get('price'), t.get('timestamp'))
            if k in seen: continue
            seen.add(k); out.append(t); new += 1
        if len(r) < limit or new == 0: break
        end = r[-1]['timestamp']  # inclusive; dedupe handles overlap
    return out

def price_history(token_id, fidelity=1):
    r = get(f"{CLOB}/prices-history", dict(market=token_id, interval='max', fidelity=fidelity))
    return (r or {}).get('history', [])

def winner_index(m):
    try:
        p = [float(x) for x in json.loads(m['outcomePrices'])]
    except Exception:
        return None
    if max(p) >= 0.99 and min(p) <= 0.01: return p.index(max(p))
    return None
