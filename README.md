# polyall3: Polymarket liquidity-reward harvester

A bot that rests minimum-size, two-sided, post-only quotes in **quiet, uncontested Polymarket liquidity-reward
pools**. It is the only candidate edge that was not rejected after a day of testing ten strategy families (see
[REPORT.md](REPORT.md)). **Its profitability at small capital is still unverified.**

> **Honest summary** (eight audit passes by separate agents: four of the code, two of the report, one each of the
> farmer data and the payout evidence. The payout audit's sponsored-pool reading was wrong and has been withdrawn.)
> * **Real:** Polymarket pays makers a daily reward per market by a published formula. It paid **$128.5k** for
>   2026-09-25, on-chain, to ≈2,260 wallets.
> * **Thin for typical farmers:** audited non-weather farmers net only ≈0.2–0.3%/day on capital at mid marks, and
>   were negative at liquidation marks in the latest week. Fill losses eat 60–85% of rewards.
> * **The bot's focus.** At any moment ≈$13–28k/day of non-weather pools have no scoring quote inside the reward band.
>   Over 3.6 h, 255 pools (≈$6.8k/day) stayed empty, and 160 of them (≈$4.2k/day) pass the bot's filters. They trade
>   about once a day. A 7-day replay puts fill losses there at ≈3–4% of rewards. Newer markets are over-represented,
>   but 39% of these pools are markets over a week old. 27% of pools empty at 17:55 drew a lasting competitor within
>   3.6 h, and new empty pools keep appearing.
> * **Whether Polymarket pays a lone quoter that way is unverified.** It decides everything. Aggregate on-chain
>   payouts are consistent with the listed rates of pools that have quotes (a ~10–20% haircut cannot be excluded),
>   and sponsored pools appear to be paid per minute scored. No public record isolates a lone quoter, so the $100
>   pilot is the test. A sponsored-pool recorder checks per-minute accrual only.
> * **Next step:** paper mode, then **live with $100 for at least 3 full UTC days**. Within the first hour the bot logs
>   Polymarket's own reward percentage for our orders; each day it logs actual vs estimated payout **per market**.
>   Scale only if they agree.
> * **Not promised:** $100/day. The $100 formula estimate is ≈$200–300/day at a 100% share (≈$100–150/day at 50%),
>   before fill losses. It holds only if lone quoters are paid. The long-run share is unmeasured: 27% of empty pools
>   drew a lasting competitor within 3.6 h, so even 50% is not a floor. At the audited farmer rate, $100/day needs
>   ≈$40k.

## How it works

1. **Universe** (every 30 min, in a background thread):
   * all markets paying liquidity rewards (`/rewards/markets/current`);
   * drop weather, crypto up/down, markets within 72 h of their end date, and mids outside 0.10–0.90;
   * compute our reward share with the exact scoring formula against the live book;
   * **activity filter:** skip markets that traded >$1k or ranged >10¢ in the last 24 h (or have more than 500
     prints), and charge expected fill losses (`0.05 × min(0.5 × 24 h taker $, $ our quotes put at risk)` per day)
     against the reward estimate and in allocation;
   * our own resting orders are removed from the book before scoring, and pools we already quote get a 1.25×
     ranking bonus, so a refresh does not churn them out.
2. **Optional toxicity cascade** (`PMBOT_USE_JEV=1`, off by default):
   * **Jev** (TypeSafe, via OpenRouter Decisions API) scores whether the outcome tracks a live public number, whether
     news is due within 72 h, and how often news arrives.
   * Markets Jev passes (or scores borderline) are confirmed by **Claude Opus 5.5**; failures fail closed when an API
     key is set.
   * In three tests the gate cost far more reward than it saved in fill losses (REPORT §2.5), hence off by default.
3. **Allocation:** capital is water-filled to the highest marginal reward per $ locked. In an uncontested pool, extra
   size adds nothing, so extra capital buys breadth: more pools.
4. **Quoting** (every 20 s): one post-only order per side, joining the best bid/ask but always on the correct side of
   the size-adjusted mid and inside the reward band. A side that could only be placed at or through the opposite
   best quote is skipped. Held inventory is sold rather than
   hedged with the complement token.
5. **Risk controls:**
   * **Jump guard:** if the mid ranges ≥4¢ within 5 min *and* there was a trade (or one of our fills) in that window,
     the market goes unwind-only for 60 min.
   * After a fill, that side of that market is blocked for 3 min.
   * Max inventory is 1× quote size, and at most 35% of capital goes to one market.
   * 15% drawdown stop on trading equity (estimated rewards are excluded). Both the peak and the drawdown must persist
     over 3 consecutive equity samples, so a fill the positions API has not yet indexed cannot trip the stop or
     inflate the peak. Fills do not pause the check.
   * **Heartbeat dead-man switch with watchdog:** the exchange cancels every order ≈15 s after the process dies, or
     ≈65 s after the loop stalls.
   * Any live-loop error triggers cancel-all.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env            # live keys only needed for live mode
set -a; source .env; set +a

# Paper mode: live books + real (cache-busted) trade prints, queue-position fill model. No wallet needed.
python -m pmbot.run --mode paper --capital 100 --out runs     # optional: --hours N

python -m pytest -q tests       # 41 tests
```

Environment variables:
* `PMBOT_CAPITAL`
* `PMBOT_USE_JEV` (0/1), `OPENROUTER_API_KEY`, `PMBOT_LLM_MODEL`, `PMBOT_LLM_MAX_REVIEWS`, `PMBOT_MAX_MARKETS`
* live only: `PM_PRIVATE_KEY`, `PM_FUNDER`, `PM_SIGNATURE_TYPE` (0 = EOA, 1 = email/Magic proxy, 2 = browser-wallet
  Safe), `PM_CLOB_HOST`

### Going live: the $100 pilot (read REPORT §7 first)

1. **Eligibility.** Polymarket's international exchange is close-only in the US, UK, France, Germany, Italy, Poland,
   Australia, Singapore and others. The bot refuses to start if `polymarket.com/api/geoblock` reports your IP as
   blocked. Use it only where you are legally allowed to trade.
2. **Dedicated account** with $100 pUSD. The bot manages and cancels *every* open order on the account.
3. `.env`:
   * `PM_PRIVATE_KEY`
   * `PM_FUNDER` (your Polymarket deposit/proxy address)
   * `PM_SIGNATURE_TYPE`
4. `python -m pmbot.run --mode live --capital 100 --out runs`, and keep it running.
5. **Read the log:**
   * `trade-row sample` at startup: one raw fill record from the exchange. Check that it has `maker_orders`
     entries with our address or API key; fill detection relies on it. Any `WARNING: MAKER trade row` line means a
     fill was not parsed.
   * `scoring_snapshot` every 30 min: Polymarket's own reward percentage per market, and how many of our orders are
     scoring. This is the fastest verdict on the payout question.
   * `reconcile_day` at 01:30 and 06:00 UTC: actual vs estimated rewards, in total and **per market**
     (`per_market`: `est` vs `paid` for every pool we quoted; `paid_not_estimated`: payouts we did not expect).
   * Scale only per the decision rule in REPORT §7.

## What to expect (evidence-based, not a promise)

| Scenario | Evidence | Net return on deployed capital | $100/day needs |
|---|---|---|---|
| Typical non-weather reward farmer | 5–6 survivor wallets, 7–90 days (audited; data-API fills + Polymarket P&L series) | ≈0.2–0.3%/day at mid; −0.24%/day at liquidation marks in the latest week | ≈$35–50k |
| Surviving maker farmers, all categories | 27 wallets, 30–90 days (audited) | ≈0.4–0.6%/day | ≈$17–25k |
| Two hand-picked small non-weather farmers | 2 wallets, 30 days (unaudited, mid-marked, end-of-window capital) | ≈4–11%/day on reported capital; fills ate 49–79% of rewards | **not a planning basis** |
| This bot, quiet uncontested pools | formula + live books + 7-day risk replay; **lone-quoter payout unverified** | formula: ≈240–290%/day of locked collateral at a 100% share, before fill losses and competitor arrival; real: unknown until the pilot | ≈$50–100 *only if* the pilot confirms the payout *and* the bot keeps finding empty pools as competitors arrive (unmeasured). The supply of empty pools (≈$4–7k/day) caps scale. |

Paper "rewards" (e.g. ≈$200–300/day for $100 across 5 pools) are the formula applied to simulated quotes. They
assume a 100% share and the unverified lone-quoter payout. They are not evidence of income. Below ~$2–4k, capital limits how many pools the bot
covers. Above that, the number of acceptable uncontested pools (≈160–189 pools / ≈$4.2–5.1k/day in the measured windows) is the cap.

## Repository

* `pmbot/`: the bot
  * `run.py` main loop
  * `selection.py` universe, activity filter and allocation
  * `engine.py` quoting
  * `scoring.py` reward formula
  * `paper.py` / `live.py` brokers
  * `jev.py` optional Jev + LLM cascade
  * `config.py` parameters
* `research/`: study scripts behind REPORT.md (see `research/README.md`; evidence data is not committed)
* `tests/`: 41 regression tests, including reproductions of the audit findings
