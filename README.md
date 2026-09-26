# polyall3 — Polymarket liquidity-reward harvester (Jev + Claude)

A bot that earns **Polymarket's CLOB liquidity rewards** by resting minimum-size, two-sided, post-only quotes across
many markets whose reward pools are thinly contested. It is the one edge that survived a day of testing everything
else (see [REPORT.md](REPORT.md)). An optional **Jev → Claude Opus 5.5** toxicity cascade is included, but on
46k real fills it showed **no** power to predict adverse selection, so it is off by default.

> **Honest summary (after independent audits).**
> * **Real:** Polymarket pays ~$134k/day to makers by a published formula, and the payouts are verifiable on-chain.
> * **Thin for typical farmers:** audited non-weather farmers net only ≈0.2–0.3%/day on capital, because fill
>   losses eat 60–85% of rewards.
> * **The upside is unverified.** ≈$6k/day of reward pools sit in *quiet* markets with no competing quote and ~1 trade
>   per day. By the documented formula a lone minimum-size quote collects them at little risk. Whether Polymarket
>   actually pays a lone quoter that way can only be confirmed live.
> * **Next step:** paper mode, then **live with $100 for 1–3 days**. The bot logs Polymarket's actual daily payout
>   next to its own estimate. Scale only if actual ≈ estimate.
> * **Not promised:** $100/day. At the audited rate that needs ≈$40k; at small capital it is possible only if the
>   quiet-pool thesis holds.

## How it works

1. **Universe** (every 30 min, background thread): all markets paying liquidity rewards (`/rewards/markets/current`)
   → drop weather, crypto up/down, markets within 72 h of their end date, and mids outside 0.10–0.90 → compute our
   reward share with the exact scoring formula against the live book → keep the best reward-per-$ pools.
2. **Toxicity cascade (opt-in, `PMBOT_USE_JEV=1`)**:
   * **Jev** (TypeSafe System One via OpenRouter Decisions API, ~$0.00004/market) answers four typed questions. Does
     the outcome track a live public number? Is decisive information due within 72 h? How often does news arrive?
     Could insiders know early?
   * Markets Jev passes (or scores borderline) are re-read in full by **Claude Opus 5.5** (~$0.009/market, cached
     24 h), and the LLM's verdict decides. Failures fail closed.
   * Measured on real farmers' fills, neither Jev nor Opus scores predicted losses (REPORT §2.5), so it is off by
     default.
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

## What to expect (evidence-based, not a promise)

| Scenario | Evidence | Net return on deployed capital | $100/day needs |
|---|---|---|---|
| Typical non-weather farmer (audited) | ~6 wallets, 7–90 days, on-chain | ≈0.2–0.3%/day | ≈$35–50k |
| Surviving maker farmers, all categories | 27 wallets, 30–90 days | ≈0.4–0.6%/day | ≈$17–25k |
| Best small non-weather farmers (mid-marked, optimistic) | 2 wallets, 30 days | ≈4–11%/day | ≈$1–2.5k |
| Quiet uncontested pools (this bot's focus) | formula + live books; **payout unverified** | paper gross is far higher; verify live | unknown until the pilot |

Capacity per bot is set by the number of acceptable, thinly contested pools, not by capital.

## Repository

* `pmbot/`: the bot (`run.py` main loop, `selection.py` universe/allocation, `engine.py` quoting, `scoring.py`
  reward formula, `paper.py`/`live.py` brokers, `jev.py` Jev + LLM cascade, `config.py` parameters)
* `research/`: every study script behind [REPORT.md](REPORT.md)
* `tests/`: regression tests, including reproductions of the audit findings
