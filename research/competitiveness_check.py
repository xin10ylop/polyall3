"""Same-day aggregate payout check from Polymarket's own per-market competitiveness.
GET /rewards/user/markets?date=D (public; no auth) lists every rewarded market with its rate and
market_competitiveness. Predicted payable(D) = sum of rates of markets with competitiveness > 0."""
import sys, json, requests, time
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"


def pull(date, **kw):
    out, cur = [], "MA=="
    while cur != "LTE=":
        for _ in range(4):
            try:
                r = s.get("https://clob.polymarket.com/rewards/user/markets",
                          params={"date": date, "next_cursor": cur, **kw}, timeout=30).json()
                break
            except Exception:
                time.sleep(2)
        out += r.get("data", [])
        cur = r.get("next_cursor", "LTE=")
    return out


if __name__ == "__main__":
    for date in sys.argv[1:]:
        rows = pull(date)
        rate = lambda x: sum(float(c.get("rate_per_day") or 0) for c in x.get("rewards_config") or [])
        tot = sum(rate(x) for x in rows)
        comp = [x for x in rows if float(x.get("market_competitiveness") or 0) > 0]
        by_asset = {}
        for x in rows:
            for c in x.get("rewards_config") or []:
                by_asset[c["asset_address"]] = by_asset.get(c["asset_address"], 0) + float(c.get("rate_per_day") or 0)
        print(json.dumps({"date": date, "markets": len(rows), "listed_usd_day": round(tot, 2),
                          "competitive_markets": len(comp), "payable_usd_day": round(sum(rate(x) for x in comp), 2),
                          "by_asset": {k: round(v) for k, v in by_asset.items()}}))
        json.dump(rows, open(f"comp_{date}.json", "w"))
