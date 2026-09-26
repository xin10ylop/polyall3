# polyall3 — Polymarket liquidity-reward harvester (Jev + Claude)

A bot that earns **Polymarket's CLOB liquidity rewards** by resting small, two-sided, post-only quotes in markets whose
reward pools are thinly contested. A **Jev → Claude Opus 5.5 cascade** filters out markets where resting quotes get
picked off. It is the one edge that survived a day of testing everything else (see [REPORT.md](REPORT.md)).

> **Honest summary.** This is a real, contractual edge. Polymarket pays ~$134k/day to makers by a published formula,
> and real wallets farm it profitably: 76 of 95 active farmers were net positive last week, with a median of ~1%/day
> on capital and the best small accounts at 5–7%/day. It is **not** $100/day on $100 from day one; nothing
> legitimate is. At 1–4%/day you need ≈$2.5k–$10k deployed for $100/day, reached by compounding or adding capital.
> Run it in paper mode, then live with $100, and compare the bot's daily *estimated* rewards with Polymarket's
> *actual* payouts (logged automatically) before scaling.

## How it works

1. **Universe** (every 30 min, background thread): all markets paying liquidity rewards (`/rewards/markets/current`)
   → drop weather, crypto up/down, markets within 72 h of their end date, and mids outside 0.10–0.90 → compute our
   reward share with the exact scoring formula against the live book → keep the best reward-per-$ pools.
2. **Toxicity cascade**:
   * **Jev** (TypeSafe System One via OpenRouter Decisions API, ~$0.00004/market) answers four typed questions. Does
     the outcome track a live public number? Is decisive information due within 72 h? How often does news arrive?
     Could insiders know early?
   * Markets Jev passes (or scores borderline) are re-read in full by **Claude Opus 5.5** (~$0.009/market, cached
     24 h), and the LLM's verdict decides. Failures fail closed.
3. **Allocation**: capital is water-filled to the highest marginal reward per $ locked. When nobody quotes inside a
   pool's band, a minimum-size quote earns the whole pool, which is why $100 is enough to start.
4. **Quoting** (every 20 s): one post-only order per side, joining the best bid/ask but always on the correct side of
   the size-adjusted mid and inside the reward band. Held inventory is sold rather than hedged with the complement,
   so no capital is locked in YES+NO pairs.
5. **Risk**:
   * If the mid ranges ≥ 4¢ within 5 min, the market goes unwind-only for 60 min.
   * After a fill, that side of that market is blocked for 3 min.
   * Max inventory is 1× quote size, and at most 35% of capital goes to one market.
   * A 15% drawdown stop uses trading equity only, never estimated rewards.
   * Heartbeat dead-man switch with a watchdog: if the loop stalls or crashes, the exchange cancels every order
     within ~10–15 s.
   * Any live-loop error triggers cancel-all.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env        # add OPENROUTER_API_KEY (Jev + Claude); live keys only for live mode
set -a; source .env; set +a

# Paper mode: live books + real trade prints, queue-aware simulated fills. No wallet needed.
python -m pmbot.run --mode paper --capital 100 --out runs

# Tests
python -m pytest -q tests
```

### Going live (read all of this first)

1. **Eligibility.** Polymarket's international exchange is close-only for the US, UK, France, Germany, Italy,
   Poland, Australia, Singapore, and others. The bot refuses to start if `https://polymarket.com/api/geoblock`
   reports your IP as blocked. Use it only where you are legally allowed to trade.
2. **Dedicated account** funded with pUSD (Polymarket's USDC-backed collateral). The bot manages and cancels
   *every* open order on the account.
3. `.env`:
   * `PM_PRIVATE_KEY`: the key that signs orders.
   * `PM_FUNDER`: your Polymarket deposit/proxy address.
   * `PM_SIGNATURE_TYPE`: 1 for email/Magic, 2 for a browser wallet.
   * `PMBOT_CAPITAL=100`.
4. `python -m pmbot.run --mode live --capital 100 --out runs`
5. **Verify before scaling.** At each UTC midnight the log gains a line
   `{"reconcile_day": ..., "estimated_rewards": X, "actual_rewards": {...}}`, which compares the model's estimate
   with what Polymarket actually paid. Scale up only after several days of actual payouts net of fills.

## Scaling plan (evidence-based, not a promise)

| Capital deployed | Net/day at 1%/day (median farmer) | at 2.8%/day (top quartile) | at 4.4%/day (top decile) |
|---|---|---|---|
| $100 | $1 | $2.80 | $4.40 |
| $1,000 | $10 | $28 | $44 |
| $3,500 | $35 | $98 | $154 |
| $10,000 | $100 | $280 | $440 |

Compounding at 2%/day takes $100 to $3,500 in ~180 days; at 4%/day, ~90 days. Capacity per bot is set by the
number of acceptable, thinly contested pools (currently ~40 markets and ~$1k of quotes). Beyond that, more capital
means bigger quotes in contested pools and a lower return per dollar.

## Repository

* `pmbot/`: the bot (`run.py` main loop, `selection.py` universe/allocation, `engine.py` quoting, `scoring.py`
  reward formula, `paper.py`/`live.py` brokers, `jev.py` Jev + LLM cascade, `config.py` parameters)
* `research/`: every study script behind [REPORT.md](REPORT.md)
* `tests/`: regression tests, including reproductions of the audit findings
