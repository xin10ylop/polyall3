# Polymarket edge search: full research report

All measurements were taken on live Polymarket data (public APIs) on 2026-09-26. Trading venue: **Polymarket only**.
Weather markets are excluded, as required. Every major claim was checked by an independent auditor agent (§5), and the
corrections are incorporated below.

## 0. Bottom line

| | |
|---|---|
| **Candidate edge** | **Liquidity-reward harvesting in quiet, uncontested pools.** Polymarket pays makers a daily reward per market by a published formula, split by each maker's share of qualifying resting liquidity. The bot rests minimum-size, two-sided, post-only quotes inside the reward band of pools where nobody else quotes and almost nothing trades. |
| **Verified** | Rewards are real and paid on-chain; an auditor matched payouts to pUSD inflows to the cent in 16/16 wallets. Uncontested, quiet pools exist in quantity. In one 2.25-h window (Sat 17:55–20:10 UTC), **302 pools worth $8.3k/day stayed uncontested throughout**, and **189 of them ($5.1k/day) pass the bot's own filters**. Their median activity is 1 trade and ~$1 traded per 24 h. A pessimistic-on-fill-count 7-day replay shows fill losses of **≈3–4% of those pools' rewards**. |
| **Not verified, and it decides everything** | Whether Polymarket actually pays a *lone* minimum-size quoter what the formula implies. No public data answers this, and an attempted natural experiment was inconclusive (§2.4). Experienced farmers leave these pools alone, which is a warning sign. |
| **What typical farmers actually earn (audited)** | Pooled across all farmers: ≈0.5–0.7%/day at mid marks and ≈0.15–0.2%/day at liquidation marks. **Non-weather farmers (n = 5–6 survivors):** ≈0.2–0.3%/day at mid; over the latest 7 days, **−0.24%/day at liquidation marks**. Fill losses eat 60–85% of rewards. |
| **Executable?** | Yes. Post-only limit orders, no latency race, requoting every 20 s. Two code audits; details and remaining gaps in §5. |
| **Small capital?** | Yes, *if* the payout holds. A 20-share two-sided quote needs ≈$19 of collateral, so $100 covers ≈5 pools. |
| **$100/day?** | **Not established.** At the audited non-weather rate (≈0.25%/day) it would take ≈$40k. It is reachable with small capital **only if** lone quoters are paid as the formula says. The bot's paper estimate for $100 across 5 pools is ≈$215–265/day, but that number *assumes* the unverified payout. |
| **Decisive next step** | A **$100 live pilot, at least 3 full UTC days** (§7). Within the first hour, the bot logs Polymarket's own per-market reward percentage for our orders, and at 01:30 and 06:00 UTC each day it logs actual versus estimated payout. |

## 1. What was tested and rejected (with evidence)

| # | Idea | Data | Result |
|---|---|---|---|
| 1 | Soccer 1X2: Polymarket vs Pinnacle/Betfair closing line | 3,653 matches, 16 leagues, 2025/26, minute price history | 5 min before kickoff, Polymarket is **as accurate as** the sharp close. 11/16 leagues have lower log-loss on PM; the other 5 are within 0.0065. English leagues: 1.0178 vs 1.0197. Mean \|PM−sharp\| is 0.3–0.8 pp. No significant betting edge. **Efficient.** |
| 2 | Live sports: PM ask vs Pinnacle fair, all sports | Recorder all session, ~300 matched events per snapshot (Jev did the event matching) | Median edge −1.7% (spread + fee); 95th percentile +0.07%. CLV vs Pinnacle's close shrank from +2.3¢ (64 events) to **+1.0¢** (81 events, edge >1%); soccer negative; esports edge >2% +4.6¢ on only 10 events. **Marginal / inconclusive.** |
| 3 | Neg-risk bundle arbitrage | Live scan of 7,360 multi-outcome events / 116k books | Essentially none: only a handful of complete-outcome events were positive, all illiquid (3–5 shares) or year-long lockups. The large "arbs" were augmented events with unlisted outcomes, which are not arbitrage. **Efficient.** |
| 4 | Favorite/longshot bias in sports | 600k real taker fills, 1,500 moneyline markets, $111M | No bucket reliably mispriced; effective sample is markets, not fills. **No edge.** |
| 5 | Post-game "endgame" buying | 250 games; leaderboard sample of 58,480 buys ≥0.95 | ≈+0.5–0.6% per $ with rare total losses; politics at 0.95–0.97 lost 6.2%/$. **Thin carry, fat tails.** |
| 6 | Longshot/favorite bias outside sports | 10,257 resolved markets, 125k fixed-time snapshots, SEs clustered by market | Longshots won **more** than priced (0.10–0.20 bucket: priced 14.7%, won 18.0%); buying NO on longshots loses (t = −6). Other categories fair after costs. **No edge.** |
| 7 | Crypto "above $X on date" favorites | 2,421 strike markets, ~320k real fills | Looked like +6.5%/$ (t = 9). Real fills showed "above" won at every price level and "below" lost at every level: **the crypto rally (a regime), not an edge.** |
| 8 | Crypto 5/15-min up/down | Fee schedule + leaderboard | 7% fee rate (3.5% of stake at 50¢) plus a latency race; 5-min takers pooled −5.3%/$. Violates "no millisecond strategies". **Rejected.** |
| 9 | Copy the leaderboard | 3,102 wallets, 339 analysed, 506 copied entries | PnL is concentrated: 144/287 winners got ≥20% of PnL from one market. The steadiest wallets are speed bots. Copying at +60 s kept ~half the edge (6.2→3.2¢), at +180 s ~20%. **Not viable.** |

Leaderboard P&L counts trading P&L only, not rewards. For example, farmer `hfv` shows −$18.3k all-time on the
leaderboard while having collected $24.3k in rewards. So reward farmers never show up on P&L leaderboards.

## 2. The candidate: liquidity-reward harvesting

### 2.1 Mechanics (Polymarket docs, checked against live data)
* Each rewarded market has a daily pool. The total varies intraday because of sponsored pools: **$134.7k/day across
  16,430 markets at ~14:40 UTC; $182.6k/day across 16,242 at ~20:00 UTC**.
* The book is sampled once a minute. Each order within `v` cents of the size-cutoff-adjusted midpoint scores
  `S = ((v−s)/v)² × size`. Then `Q_min = max(min(Q1,Q2), max(Q1,Q2)/3)` for mids in 0.10–0.90, else
  `min(Q1,Q2)`. Payout = pool × your share of all makers' `Q_min`, credited at 00:00 UTC ($1 minimum). Some sponsored
  pools pay in USDC.e instead of pUSD.
* The NO-token book is an exact mirror of the YES book (verified 70/70 across two checks), so only the YES book is read.
* Makers pay no fees and also receive maker rebates (15–25% of the taker fees they absorb).

### 2.2 What real farmers earn (on-chain; independently audited)
* **Population:** 95 wallets active in thin rewarded markets that were paid rewards in the latest 7 days.
  * My first computation (76/95 profitable, ~1%/day) was **overstated**: a 30k-fill pagination cap dropped the oldest,
    worst fills; open inventory was marked at mid; carry-in losses were ignored; takers and a 12-wallet sibling
    cluster were counted as farmers.
  * **Audited:** ~55–65/95 profitable. Pooled return 0.5–0.7%/day at mid, 0.15–0.2%/day at liquidation marks.
  * Only 29 wallets are true reward farmers (≥70% maker, ≥$50/week rewards): 24/29 profitable at mid, 18/29 at
    liquidation marks.
  * Surviving farmers over 30–90 days: 0.43–0.62%/day, with fill losses ≈37–43% of rewards.
  * **Non-weather farmers (n = 5–6, survivors only): ≈0.2–0.3%/day at mid; −0.24%/day at liquidation marks over the
    latest 7 days (1/6 profitable); fill losses ≈60–85% of rewards.** Weather-heavy farmers did best (1.06%/day at
    mid), but weather is excluded here.
  * Mid-marking flatters makers: losses roughly double as fills age (−71 bp for fills under 3 days vs −142 bp for
    3–7 days).
* **Two hand-picked small non-weather farmers.** These are not audited, were selected after the fact, and are marked at
  mid. **Illustration only, not a planning basis.**
  * `0x1ef01de8…` farms ~300 long-dated markets with 20-share quotes: 30-day net +$3,604 on a ≈$1.1k end-of-window
    balance, with fills eating 79% of rewards.
  * `T22222222222`: +$3,057 on ≈$2.4k, fills eating 49%.
  * `hfv` (61% maker, mostly non-weather by $): the auditor's on-chain 7-day equity net was **+$2,106** (≈$300/day)
    on ≈$13.5k.

### 2.3 Supply of uncontested, quiet pools (`research/pool_tracker.py`, `research/quiet_pools.py`)
One window only: Saturday 2026-09-26, 17:55–20:10 UTC (2.25 h, 28 snapshots). **Persistence over days or weekdays is
not measured.**
* At any single moment, $13.3k–27.9k/day of non-weather pools (median $20.7k) had no competing liquidity inside the
  band.
* **302 pools ($8.3k/day) stayed uncontested in every snapshot.** Of the pools uncontested at the start, 68% were
  still uncontested 1.25 h later, while new ones appeared. Polymarket's own `market_competitiveness` for them is 0.
* Their 24 h activity: median 1 taker trade and ~$1 traded (p75: 2 trades / $26; p90: 8 / $120).
* **209 pools ($5.7k/day) are quiet**: ≤3 trades and <3¢ price range in 24 h.
* **189 pools ($5.1k/day) pass the bot's own filters**: end date >72 h, mid 0.10–0.90, ≤$1k traded and ≤10¢ range in
  24 h, no weather. Min size is 20 shares at the median, 40 at p90. Collateral to cover all of them is roughly $2–4k.
* Pool sizes are small: $10–65/day (median ≈$25). Topics include AI model release dates and API prices
  (insider-prone), elections, awards, crypto/finance, geopolitics and sports.
* Why would farmers leave these pools alone? Possible reasons:
  1. They are small ($25/day) and not worth big farmers' attention.
  2. Insider-prone topics.
  3. An undocumented payout rule.
  The pilot tests (3) on ~5 pools over a few days. It does not test persistence, competitor response, or tail events.

### 2.4 Risk backtest, and the payout question
* **Replay** (`research/quiet_risk_bt.py`): for each of 315 pools that were uncontested over 1.75 h ($8,725/day),
  the last 7 days of real taker trades are replayed as if our 20-share quote sat at the top of the book and absorbed
  every trade. Each fill is marked 24 h later, or at the current mid.
  * Net fill losses: **$247/day** (gross $350/day before $103/day of simulated gains). The auditor's sensitivity
    re-run, pricing fills at the bot's own quote, gave $263–346/day. So losses are **≈3–4% of the pools' rewards**.
  * Median 0.57 fills per pool per day (mean 2.2; p90 5.4). 1–6 of 315 pools lost more than their reward.
  * This is pessimistic on *fill count* only. It uses a 7-day window, 24 h marks, and no resolution events, so insider
    and resolution tail risk is under-sampled. For contrast, real non-weather farmers lose 49–85% of rewards to fills;
    the difference comes entirely from the quiet-pool selection.
* **Payout:** an attempted natural experiment was **inconclusive**. It looked at 172 makers that traded ≤5 markets and
  were paid rewards. Its one striking case, `qingkes`, turned out to be a ~$9.7k round trip in a game-day sports pool
  with a 1,000-share minimum; that pool was $50/day and contested most of the day. There is **no public evidence either
  way** on lone-quoter payouts.

### 2.5 Does a Jev → Claude toxicity screen help? Tested three ways; it does not pay for itself
| Test | Result |
|---|---|
| Jev on real farmer fills (`0x1ef0` + `T222`, 30 days, 46,489 fills, 9,001 markets) | Markets Jev passed lost 4.41%/$ filled; markets it rejected lost 4.16%/$. \|ρ\| ≤ 0.05 for every Jev score vs loss per $ (2,313 markets with ≥$50 filled). |
| Claude Opus 5.5 on the 30 worst vs 30 best of those markets | AUC 0.49 (p = 0.56). No discrimination. |
| Jev **inside** uncontested quiet pools (7-day risk replay; the out-of-sample case) | Rejected pools lost more per $ of reward (2.5% vs 1.1%), but the gate would forgo **$2,589/day** of reward to avoid **$64/day** of fill losses. Insider-prone pools lost *less* in this window, though announcement tails are not captured. |
* The earlier 3-hour simulator suggested the opposite. That was small-sample noise, and the simulator also read a
  cached trade feed (audit N6).
* **Decision: the gate is off by default** (`PMBOT_USE_JEV=1` enables it). It screens only for live-tracked outcomes,
  news due within 72 h, and news frequency; it does not use the insider score.
* Fill losses per market are small in absolute terms (≈$1.6–2.5 per market per 30 days at minimum size; 5.1% per $
  filled in the thinnest markets vs 2.8% in the busiest). But for real farmers in contested pools they still consumed
  49–85% of rewards: breadth helps, it does not remove fill losses.
* Controls that bound losses mechanically:
  * no quoting within 72 h of a market's end date;
  * an activity filter (skip >$1k traded or >10¢ range in 24 h) and an expected-fill-loss charge
    (`0.05 × 0.5 × min(24 h taker $, 2 × min_size)` per day, so ≤ ~$1–2.5 per pool);
  * a jump guard: mid ranges ≥4¢ within 5 min **and** a trade or one of our fills occurred → unwind-only for 60 min;
  * a 3-min block on a side after it fills;
  * max inventory of 1× quote size, and ≤35% of capital per market;
  * post-only orders, an exchange heartbeat watchdog, and a 15% drawdown stop on trading equity.

## 3. Jev + LLM: where they helped and where they did not
| Use | Result |
|---|---|
| Event matching Polymarket ↔ Pinnacle (sports research) | **Useful.** True matches score 0.96–0.98; women's/reserve-team traps score 0.05. $0.00002/call, ~0.4 s. |
| Toxicity screen for reward markets (Jev, and Opus as escalation) | **No economic value** in three tests (§2.5); kept as an opt-in. Opus does catch individual hazards qualitatively, e.g. "Super Bowl headliners are usually announced in September" and "FlixPatrol is a live proxy for Netflix rankings". |
| Claude (this research) | Strategy search (10 hypotheses), bot design, coordinating the audits, and the fixes. |

## 4. Forward test (paper mode on live books and real trade prints)
See §6 for results. Only runs after audit #2's fixes count: the corrected fill feed and the queue-position model. The
earlier simulator (`research/rw_sim.py`) and the first paper runs read a CDN-cached trade feed, so their fill P&L is
optimistic and is **not** used.

## 5. Independent audits
| Audit | Scope | Result |
|---|---|---|
| Code audit #1 | Whole bot vs py-clob-client-v2 source, docs, live endpoints | Verified correct: client usage, post-only (no taker path), YES/NO conversions, scoring formula, mirrored books, no secret logging. Found 2 CRITICAL (the geoblock check did not check geoblock; the heartbeat kept stale quotes alive during stalls), 7 HIGH, 10 MEDIUM. Fixed. |
| Code audit #2 (verification) | The rewrite | Confirmed both CRITICALs and most HIGH/MEDIUM fixed. H2/H3/H6 and M2/M3/M7/M8/M9 were only partially fixed at that point. Found 3 new HIGH: equity double-counted reserved collateral; fills inferred from vanished orders; paper feed cached for 300 s. These and the partial items were then fixed with tests (19 passing). **The fixes after audit #2 (including the activity filter and the trade-gated jump guard) have not been re-audited independently.** |
| Farmer-profitability audit | Independent re-derivation, including on-chain equity accounting for 16 wallets via archive RPC | **Partially supported**; corrected numbers adopted in §0/§2.2. |
| Report audit | Every claim in README/REPORT vs the evidence files | Found 13 issues, including gate-default inconsistency, the invalid `qingkes` example, unwindowed pool figures, the unaudited "$100/day on $1–2.5k" row, and missing scripts. All addressed in this version. |
| Leaderboard forensics | 3,102 wallets | See §1, rows 5, 8 and 9. |

## 6. Forward-test results
_Filled in at the end of the session._

## 7. The decisive test: a $100 live pilot (procedure and pre-committed decision rule)
Every main public-data check has been done. The question that decides between a small edge (≈0.2–0.3%/day, like
typical non-weather farmers) and a large one is whether Polymarket pays a lone minimum-size quoter what the formula
says. Only a live account can answer it.

1. **Eligibility:** run only where Polymarket permits trading. The bot exits if `polymarket.com/api/geoblock` reports
   your IP as blocked.
2. **Account:** use a fresh account for the bot only, with $100 pUSD.
   * `PM_FUNDER` = its deposit (proxy) address.
   * `PM_PRIVATE_KEY` = the exported signing key, kept in `.env` only.
   * `PM_SIGNATURE_TYPE` = 1 for email login, 2 for a browser wallet.
3. **Run continuously:** `python -m pmbot.run --mode live --capital 100 --out runs`.
4. **First hour (fast signal):** every 30 min the log records `scoring_snapshot`, which holds Polymarket's own reward
   percentage for our markets (`/rewards/user/percentages`) and how many of our orders are scoring.
   * **If our uncontested pools show ~100%, the payout thesis is very likely right.**
   * If our orders are not scoring, or our share is small, the thesis fails early.
5. **Daily:** at 01:30 and again at 06:00 UTC, the log records
   `{"reconcile_day": D, "estimated_rewards": E, "actual_rewards": A}`. If `A` is empty or 0, check the Polymarket UI
   and your USDC.e balance (sponsored pools) before concluding anything.
6. **Decision rule** (commit to it in advance; needs at least 3 full UTC days):
   * `A ≥ 0.5·E` for 3 consecutive days **and** the trading-equity drawdown is below cumulative `A`: scale stepwise
     (e.g. ×2 every 3 days), watching `A/E` and fill losses as competition arrives.
   * `A < 0.2·E`: lone quoters are not paid as modelled. **Stop.** At ≈0.2–0.3%/day it is not worth running small.
   * In between: run a week at $100, then decide.
7. **Risks you accept:**
   * inventory from fills (≤1 quote size per market);
   * jumps against a resting quote (bounded by quote size), including insider announcements;
   * resolution/dispute risk on held inventory;
   * Polymarket changing the reward program at any time.
