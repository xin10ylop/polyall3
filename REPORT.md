# Polymarket edge search: full research report

All measurements were taken on live Polymarket data (public APIs) on 2026-09-26. Trading venue: **Polymarket only**.
Weather markets are excluded, as required. Most major claims were checked by an independent auditor agent (§5), and the
corrections are incorporated below. Everything in §2.3–§2.4 has been through audit #6, and its corrections are applied.
The final forward-test numbers in §6 and the last documentation edits have not been re-audited.

## 0. Bottom line

| | |
|---|---|
| **Candidate edge** | **Liquidity-reward harvesting in quiet, uncontested pools.** Polymarket pays makers a daily reward per market by a published formula, split by each maker's share of qualifying resting liquidity. The bot rests minimum-size, two-sided, post-only quotes inside the reward band of pools where nobody else quotes and almost nothing trades. |
| **Verified** | Rewards are real and paid on-chain; an auditor matched payouts to pUSD inflows to the cent in 16/16 wallets. Uncontested, quiet pools exist in quantity. In a 3.58-h window (Sat 17:55–21:30 UTC), **255 pools worth $6.8k/day stayed uncontested throughout**, and **160 of them ($4.2k/day) pass the bot's own filters** (302 / $8.3k and 189 / $5.1k over the first 2.25 h). Their median activity is 1 trade and ~$1 traded per 24 h. A pessimistic-on-fill-count 7-day replay shows fill losses of **≈3–4% of those pools' rewards**. |
| **Payout evidence (new, audited)** | Polymarket paid **$128.5k** of liquidity rewards for 2026-09-25 (on-chain; $128,287 native + $240 sponsored). That is consistent with the ≈$115–130k/day of listed pools that had a scoring quote at a snapshot, so listed rates look genuinely paid to whoever quotes. It is a cross-day comparison, though, and cannot exclude a ~10–20% haircut. Partial sponsored-pool refunds suggest sponsored pools are paid per minute scored (§2.4). |
| **Not verified, and it decides everything** | Whether a *lone* minimum-size quoter is paid the pool, per minute. No public record attributes payouts to makers per market, so the $100 pilot is the test (§7). Competitors arrive quickly (27% of empty pools drew lasting in-band liquidity within 3.6 h, §2.3), so the long-run share will fall below 100%. |
| **What typical farmers actually earn (audited)** | Pooled across all farmers: ≈0.5–0.7%/day at mid marks and ≈0.15–0.2%/day at liquidation marks. **Non-weather farmers (n = 5–6 survivors):** ≈0.2–0.3%/day at mid; over the latest 7 days, **−0.24%/day at liquidation marks**. Fill losses eat 60–85% of rewards. |
| **Executable?** | Yes. Post-only limit orders, no latency race, requoting every 20 s. Four code audits; audits #3 and #4 re-verified the earlier fixes. The fixes for audit #4 (f0358d2) and the per-market reconciliation (3c0fcff) are covered only by the author's tests and have not been re-audited. 41 regression tests. |
| **Small capital?** | Yes, *if* the payout holds. A 20-share two-sided quote needs ≈$19 of collateral, so $100 covers ≈5 pools. |
| **$100/day?** | **Not established.** The bot's formula estimate for $100 across the 5 largest empty pools (≈$50/day each) is ≈$200–300/day at a 100% share, before fill losses. It holds only if lone quoters are paid as the formula says, which is unverified, and only while pools stay empty. Competitors reached 27% of empty pools within 3.6 h (§2.3), and the long-run share is unmeasured. For contrast, typical contested farming at ≈0.25%/day would need ≈$40k. |
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
Measured on Saturday 2026-09-26 from 17:55 UTC, first over 2.25 h (28 snapshots), then re-run over 3.58 h
(44 snapshots). **Persistence over days or weekdays is not measured.**
* **Re-run over 3.58 h:** 255 pools ($6.8k/day) were uncontested in every snapshot; 178 ($4.7k/day) were quiet; 160
  ($4.2k/day) pass the bot's filters. The stable set shrank from 302 to 255 pools (−16%) in the extra 80 minutes.
  Of the 488 pools empty at 17:55, 255 (52%) stayed empty throughout. New empty pools keep appearing: 120 pools empty
  at 21:30 had not been empty at 17:55.
* **New markets are over-represented among empty pools, but most empty pools are not new** (audit #6).
  * By market listing time (`accepting_order_timestamp`), 43% of the 255 stable-uncontested pools (49% of their $)
    are markets listed in the last 3 days, versus 16% of all tracked pools; 39% were listed more than a week ago.
  * At 17:55, pool dollars were 59–63% contested in markets under 3 days old, 81–86% at 3–30 days and 94% at over
    30 days.
  * The reward config's `start_date` is *not* pool age. It is reset when a config is re-issued: 730 configs moved
    their start_date to 2026-09-26 between 14:05 and 21:27 UTC, half without a rate change, and 46% of all configs
    carry today's date.
* **Competitors arrive quickly, at every market age.**
  * Of the 488 pools empty at 17:55, 86 were contested at 21:25. Another 70 had dropped out of the tracked set: 48
    re-rated below $10/day (a rate cut is itself a risk for the bot), 21 delisted and 1 other.
  * Liquidity that stayed in the band for ≥3 consecutive snapshots appeared within 3.6 h in 27% of them (132/488):
    21–25% for markets under 30 days old and 40% for older ones. Some of this may be a mid move bringing existing
    orders into the band, not a new farmer.
  * For the bot, shares will fall below 100% over time. The universe refresh moves capital to pools that are still
    empty. The realistic long-run share is unmeasured.
* **The original 2.25-h window** (17:55–20:10 UTC):
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
  1. Some are new (43% are markets listed in the last 3 days) and farmers have not arrived yet. But lasting
     competitors appear at similar rates regardless of market age, so novelty explains only part of it.
  2. They are small ($25/day) and not worth big farmers' attention.
  3. Insider-prone topics.
  4. An undocumented payout rule.
  The pilot tests (4) on ~5 pools over a few days. It does not test long-run persistence, competitor response, or
  tail events.

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
* **Payout: what public data shows** (`research/payout_check.py`, `competitiveness_check.py`: on-chain totals and
  the aggregate check, audited in audit #5. `sponsored_recorder.py` / `sponsored_check.py` and the refund analysis:
  checked in audit #6):
  * **Rewards are paid, and precisely.** Native rewards for UTC day D are paid in pUSD by one distributor EOA
    (`0x2c27…a709`, via batch contract `0xd152…`) within ~20 s of 00:00 UTC on D+1. For 2026-09-25 that was
    **$128,287.48 to 2,238 wallets**, and 300/300 sampled recipients have a matching data-api `REWARD` row.
    Sponsored rewards are paid separately by the sponsor contract `0xdd8d…9e8b` (`DistributedRewards`, ~00:16 UTC;
    $240.19 to 176 wallets), for **$128.5k to ≈2,260 wallets** in total. The other $86.87 it sent that night went
    back to sponsors (`SponsorRefunded`, ~00:20 UTC). Holding, rebate and referral payouts come from other senders and
    are excluded.
  * **Aggregate consistency.** On Sat 26 Sep (21:15–21:47 UTC), 64–70% of the listed $181–194k/day sat in pools where
    someone was scoring:
    * $115–130k/day by our formula, depending on how the minimum size is applied;
    * $122.7k/day by Polymarket's own `market_competitiveness`, which agrees pool-by-pool with our formula on 91% of
      dollars.

    This is *consistent with* listed rates being paid to whoever scores, with no large haircut. It compares one
    moment with a different day's payout, though. The listing moves by ±$50k within a day and daily payouts over 30
    days ranged $96k–200k, so a ~10–20% haircut cannot be excluded.
  * **Sponsored pools: a per-market test becomes possible, but no lone-quoter evidence yet.** The sponsor contract
    `0xdd8d…9e8b` (verified ABI on Sourcify) emits three kinds of event:
    * `Sponsored(market, sponsor, amount, start, end, ratePerMinute)`;
    * `DistributedRewards(user, amount)`: payouts to makers, **with no market id**;
    * `SponsorRefunded(market, sponsor, amount)`: the **unearned** part of each day, returned to the sponsor.

    The earned amount per pool and day can be derived: what the sponsorship funded that day
    (`sponsorInfo(sponsor, market)`: start, end, ratePerMinute) minus the refund. For 2026-09-25, in the 15 pools with
    one sponsor, measured against the minutes each sponsorship actually covered that day:
    * 7 pools were ≥99% refunded, i.e. effectively unearned;
    * 5 were 88–98% refunded (2–12% earned);
    * 3 were 4–14% refunded (86–96% earned).

    Partial refunds in 8 pools fit payment per minute that someone scores. Most sponsored pools earned almost
    nothing. Taken as a share of the *current* listed rate, the refunds span 4%–99.7%. That overstates partial
    earning, because 11 of the 15 sponsorships started or ended during that day.

    **Correction.** An earlier version of this report read these refunds as payouts to single makers. That reading was
    wrong. `sponsored_recorder.py` / `sponsored_check.py` test per-minute accrual but cannot isolate lone quoters:
    * Public books aggregate makers per price level. In the first hour of recording, no sponsored pool was
      consistently at ≤1 level per side while scoring; 2 pools ($4/day) were at times.
    * A further 34 pools ($68/day) have no reward config.
    * 10 pools ($32/day) have mids outside 0.10–0.90, where scoring needs two-sided makers that books cannot show.

    A direct public lone-quoter test would be to quote one empty sponsored pool from the pilot account, then read
    that pool's next `SponsorRefunded` and the `DistributedRewards` to our address.
  * **Per-minute, not per-day (sponsored pools).** The sponsor help page says the unearned part of each day is
    refunded. On 2026-09-25 some pools were only partly earned over the minutes they were funded (e.g. 12%, 85% and
    96% earned). Sponsored pools are therefore paid for the minutes someone scores, not in full once anyone scores, as
    the documentation's day-level normalisation would suggest. Native pools have no refund record, so it is plausible
    but unverified that they work the same way. The bot quotes continuously, and its estimate accrues per elapsed
    time, so it does not depend on this.
  * An earlier natural experiment on native payouts (172 makers in ≤5 markets) was inconclusive. Its one striking
    case, `qingkes`, was a contested sports pool.

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
    (`0.05 × min(0.5 × 24 h taker $, $ our quotes put at risk)` per day, i.e. at most 5% of a pool's quote
    collateral per day), applied both in ranking and in allocation;
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
| Code audit #2 (verification) | The rewrite | Confirmed both CRITICALs and most HIGH/MEDIUM fixed. H2/H3/H6 and M2/M3/M7/M8/M9 were only partially fixed at that point. Found 3 new HIGH: equity double-counted reserved collateral; fills inferred from vanished orders; paper feed cached for 300 s. Fixes followed, but audit #3 found several of them incomplete. |
| Code audit #3 (verification) | Fixes after audit #2, activity filter, trade-gated jump guard | No CRITICAL. 1 HIGH: the paper fill model still credited late prints to the wrong order, which is optimistic. 6 MEDIUM: quotes could still cross the raw book in 15 of 551 markets; live fill parsing relied on an unverified row shape; false drawdown stops from cash/position read skew; resolved winners dropped from equity; an old fill re-emitted every cycle after a 24 h lull; universe churn from counting our own quotes as competition. 10 LOW. All fixed in commit e8cb20c with regression tests (31 passing). |
| Code audit #4 (verification) | Fixes for audit #3 | 13 of 15 items FIXED, 2 PARTIAL (drawdown sampling, allowance ordering). A 108k-book fuzz found no crossing quotes. New: 1 MEDIUM (frequent fills could starve the drawdown stop) and 5 LOW (a lagged SELL could inflate the peak; a requote race in paper; an over-broad cancel-reason match; extra data-api time between heartbeats; a stale own-order snapshot in ranking). All but the last fixed in commit f0358d2 with tests. The last is a minor ranking skew and is left as is. |
| Payout audit (#5) | On-chain reward totals, payable-vs-paid, lone-quoter evidence | Paid total SUPPORTED (300/300 recipients match; sponsored rewards add $327). Paid ≈ payable only PARTIALLY SUPPORTED: consistent, but a one-moment, cross-day comparison with low power. The payout looks per-minute, not per-day. The audit's sponsored figure ($327) included $86.87 of sponsor refunds; maker payouts were $240.19. Its per-market sponsored "payouts" turned out, from the contract's verified ABI, to be `SponsorRefunded` events (unearned funds returned to sponsors). The lone-quoter reading built on them was withdrawn, and the per-minute reading now rests on partial refunds in 8 pools (§2.4). |
| Report audit #2 (audit #6) | README/REPORT changes since the first report audit | 4 HIGH, 4 MEDIUM, 8 LOW, all applied here:<br>• refund fractions used the wrong denominator;<br>• reward-config `start_date` is not pool age, so "empty pools are mostly new" was withdrawn;<br>• the sponsored-pool test cannot isolate lone quoters;<br>• the correction was incomplete ($327 included refunds);<br>• a sign error in the §7 fill-loss rule;<br>• overstated audit coverage;<br>• a 50% share presented like a floor;<br>• stale README items. |
| Farmer-profitability audit | Independent re-derivation, including on-chain equity accounting for 16 wallets via archive RPC | **Partially supported**; corrected numbers adopted in §0/§2.2. |
| Report audit | Every claim in README/REPORT vs the evidence files | Found 13 issues, including gate-default inconsistency, the invalid `qingkes` example, unwindowed pool figures, the unaudited "$100/day on $1–2.5k" row, and missing scripts. All were addressed in the version audited then, before §2.3's pool-age and §2.4's payout sections were added. |
| Leaderboard forensics | 3,102 wallets | See §1, rows 5, 8 and 9. |

## 6. Forward-test results
_Filled in at the end of the session._

## 7. The decisive test: a $100 live pilot (procedure and pre-committed decision rule)
The public aggregate checks have been done (§2.4), and no public record isolates a lone quoter. The question that decides between a small edge (≈0.2–0.3%/day, like
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
   `{"reconcile_day": D, "estimated_rewards": E, "actual_rewards": A, "per_market": {...}}`. `per_market` gives
   the estimate and Polymarket's actual payout (`GET /rewards/user`) for every pool we quoted, so `A/E` is measured
   pool by pool. Pools that rotated in or out during the day also show whether a partial-day quoter is paid per
   minute or for the whole day (§2.4). In sponsored pools, part of the estimate is paid by the sponsor contract. If
   `per_market.paid` omits it, check `DistributedRewards` to our address on-chain before reading `A/E`. If `A` is
   empty or 0, check the Polymarket UI before concluding anything.
6. **Decision rule** (commit to it in advance; needs at least 3 full UTC days). `trading_equity` is CLOB cash plus
   positions, so pUSD reward payouts are already inside it. Net P&L = `equity − start equity`. Fill losses =
   `cumulative A − net P&L` (rewards received minus net P&L).
   * `A ≥ 0.5·E` for 3 consecutive days, net P&L > 0, **and** fill losses smaller than half of cumulative `A`: scale
     stepwise (e.g. ×2 every 3 days), watching `A/E` and fill losses as competition arrives.
   * `A < 0.2·E`: lone quoters are not paid as modelled. **Stop.** At ≈0.2–0.3%/day it is not worth running small.
   * In between: run a week at $100, then decide.
7. **Risks you accept:**
   * inventory from fills (≤1 quote size per market);
   * jumps against a resting quote (bounded by quote size), including insider announcements;
   * resolution/dispute risk on held inventory;
   * Polymarket changing the reward program at any time.
