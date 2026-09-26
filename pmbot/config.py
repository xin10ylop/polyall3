"""Strategy parameters. Every value here is used identically in paper and live mode."""
import os

CFG = {
    # --- capital & sizing ---
    "capital_usd": float(os.environ.get("PMBOT_CAPITAL", 100)),  # total collateral the bot may lock in quotes
    "max_frac_per_market": 0.35,      # never lock more than this fraction of capital in one market
    "max_markets": int(os.environ.get("PMBOT_MAX_MARKETS", 150)),             # breadth: min-size quotes across many pools (real farmers quote 100-300)
    # --- market selection ---
    "min_pool_usd_day": 10,           # ignore reward pools smaller than this
    "min_hours_to_end": 72,           # stop quoting markets whose scheduled end is closer than this
    "mid_range": (0.10, 0.90),        # single-sided liquidity still scores 1/3 here; outside it both sides are required
    "exclude_regex": r"temperature|precipitation|rain|snow|hurricane|tornado|weather|°[CF]|inches of|Up or Down",
    "min_est_roi_day": 0.01,          # projected reward per $ locked per day (conservative share) to be eligible
    # --- activity filter (quiet pools: few fills -> little adverse selection) ---
    "activity_top_n": 300,            # measure 24h trading for this many top candidates per refresh
    "max_trades_24h_usd": 1000,       # skip pools whose market traded more than this in 24h
    "max_range_24h": 0.10,            # ...or whose traded price ranged more than this in 24h
    "adverse_rate": 0.05,             # expected loss per $ filled (real farmers: 3-5%)
    "fill_share": 0.5,                # assume we absorb this share of a quiet market's 24h taker $ (we'd be top of book)
    # --- Jev toxicity gate ---
    "use_jev": os.environ.get("PMBOT_USE_JEV", "0") == "1",   # off by default: in every test the gate cost far more
                                                               # reward than it saved in fill losses (REPORT §2.5)
    "max_realtime": 0.5,
    "max_reveal_soon": 0.4,
    "max_news_speed": 1.5,            # 0=rarely .. 3=constantly
    "llm_model": os.environ.get("PMBOT_LLM_MODEL", "anthropic/claude-opus-5.5"),  # cascade escalation ('' disables)
    "llm_max_reviews_per_refresh": int(os.environ.get("PMBOT_LLM_MAX_REVIEWS", 25)),
    # --- quoting ---
    "mode": "join",                   # 'join' best bid/ask, or 'improve' one tick inside when spread allows
    "max_inventory_frac": 1.0,        # max net inventory per market, as a multiple of quote size
    # --- risk ---
    "jump_cents": 4,                  # if the adjusted mid ranges >= this many cents within jump_window_sec...
    "jump_window_sec": 300,
    "cooldown_min": 60,               # ...pull quotes (unwind-only) in that market for this long
    "fill_guard_sec": 180,            # after a fill, stop quoting that side of that market for this long
    "max_drawdown_frac": 0.15,        # stop the bot if mark-to-market equity falls this far below its peak
    "cycle_seconds": 20,
    "watchdog_sec": 30,               # live: heartbeats stop (exchange cancels all orders) if no healthy cycle for this long
    "universe_refresh_min": 30,
}
