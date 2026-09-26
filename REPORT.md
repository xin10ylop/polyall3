# Polymarket edge search — full research report

Date: 2026-09-26. Everything below was measured on live Polymarket data (public APIs) from this session.
Trading venue: **Polymarket only**. Weather markets excluded as required.

## 0. Bottom line

| | |
|---|---|
| **Edge found** | **Liquidity-reward harvesting**: rest minimum-size, two-sided, post-only quotes inside the reward band of Polymarket markets that pay CLOB liquidity rewards, prioritising **quiet, uncontested pools**. |
| Why it is an edge | Polymarket pays ~$134k/day to makers by a published formula. The income is contractual, not a forecasting bet. |
| What is **verified** (independently audited) | Rewards are paid on-chain; audit matched pUSD inflows to the cent in 16/16 wallets. For surviving maker farmers, rewards exceeded fill losses over 7–90 days. **But the audited return is thin**: ≈0.5–0.7%/day pooled at mid, ≈0.15–0.2%/day at liquidation marks. For **non-weather** farmers (the only kind allowed here) it is ≈0.2–0.3%/day, with fill losses eating 60–85% of rewards. My first, un-audited population numbers (76/95 profitable, ~1%/day) were **overstated** (truncated fills, mid-marking, takers in the sample). See §2.2. |
| What is **promising but unverified** | At any moment **≈$9k/day of non-weather pools have no competing quote inside the band** (325 pools stable for 1.3 h+; Polymarket's own `market_competitiveness` = 0). **222 of them (≈$6k/day) are quiet**: median 1 trade and $2 traded per 24 h. A lone minimum-size quote there should (by the documented formula) collect the pool while almost never being filled. Whether Polymarket actually pays a lone quoter as the formula says **cannot be verified without a live account**. Experienced farmers leave these pools alone, which is a warning sign. |
| Executable? | Yes: post-only limit orders, no latency race, quotes refreshed every 20 s. Audited twice; every critical and high finding was fixed and has a test. |
| Small capital? | Yes. In an uncontested pool, reward share does not depend on size, so ~$10–20 of quotes per market is enough. |
| $100/day? | **Not established.** At the audited non-weather rate (≈0.25%/day) it would need ≈$40k. It is reachable at small capital **only if** the uncontested-pool thesis holds. The cheapest decisive test is a **$100 live pilot for 1–3 days**; the bot logs Polymarket's actual payout against its own estimate every day (§7). |

## 1. What was tested and rejected (with evidence)

| # | Idea | Data | Result |
|---|---|---|---|
| 1 | Soccer 1X2: Polymarket vs Pinnacle/Betfair closing line | 3,653 matches, 16 leagues, 2025/26, minute price history | Polymarket 5 min before kickoff is **as accurate or more accurate** than the sharp close (log-loss 1.0178 vs 1.0197 on English leagues; 11/16 leagues PM ≤ sharp). Mean |PM−sharp| 0.3–0.8 pp. No significant betting edge at T−120/60 min; T−5/15 "edges" were ~100 bets/season (t≈2.3 on 1 of 16 tried cells): noise/look-ahead. **Efficient.** |
| 2 | Live sports: PM ask vs Pinnacle fair (all sports) | ~300 matched events per snapshot, recorded all session | Median edge −1.7% (spread+fee), 95th pct +0.07%. Only thin leagues with low Pinnacle limits show +3–5%. CLV vs Pinnacle's close: after 64 events, +2.3¢ for edge>1%. After 81 events this shrank to **+1.0¢** (28 events); soccer negative; esports edge>2% +4.6¢ on only 10 events. **Marginal / inconclusive.** |
| 3 | Neg-risk bundle arbitrage | Live scan of 7,360 multi-outcome events / 116k books | 8 of 8,085 complete-outcome events positive, all illiquid (3–5 shares) or year-long lockups. The other "arbs" are augmented events with unlisted outcomes (not arbitrage). **Efficient.** |
| 4 | Favorite/longshot bias in sports | 600k real taker fills, 1,500 moneyline markets, $111M | No bucket reliably mispriced; effective sample = markets, not fills. **No edge.** |
| 5 | Post-game "endgame" (buy winner at 0.99 before resolution) | 250 games | Liquidity exists ($2.3M below 0.99 post-decision), but live-fill calibration at 0.99–0.995 returns ≈+0.5% with rare total losses; competitive. **Thin.** |
| 6 | Longshot/favorite bias outside sports | 10,257 resolved markets, 125k fixed-time snapshots, clustered SE | Longshots won **more** than priced (0.10–0.20 bucket priced 14.7%, won 18.0%); buying NO on longshots loses (t=−6). Politics, economics, tech, culture, mentions, and fee-free geopolitics are fair after costs. **No edge.** |
| 7 | Crypto "above $X on date" favorites | 2,421 strike markets, 300k real fills | Looked like +6.5%/$ (t=9). Real fills show "above" bets won at **every** price level and "below" bets lost at every level: the crypto rally, **regime not edge**. |
| 8 | Crypto 5/15-min up/down | fee schedule + market structure | 7% fee rate (3.5% of stake at 50¢) + latency race vs bots. Violates "no millisecond strategies". **Rejected.** |

| 9 | Copy the leaderboard | 3,102 leaderboard wallets, 339 analysed in depth, 506 copied entries | Most leaderboard PnL is concentrated (144/287 winners got ≥20% of PnL from one market). The steadiest wallets are crypto 5-min speed bots; similar bots lost as a group (−5.3%/$ pooled for 5-min takers), so they are excluded. Copying at +60 s keeps about half the edge, at +180 s about 20%. Maker edges can't be copied. **Not viable.** |
| 10 | Endgame buying at ≥0.95 | 58,480 resolved buys by 272 wallets | +0.59%/$ pooled; politics at 0.95–0.97 lost 6.2%/$ (18% loss rate); one geopolitics tail event cost three wallets $400k. **Thin carry with fat tails.** |

**Why the leaderboard hides the best small-capital edge:** leaderboard P&L counts trading P&L only, not liquidity
rewards. Example: farmer `hfv` shows −$18.3k all-time on the leaderboard while having collected $24.3k in rewards,
so reward farmers never rank on P&L leaderboards.

## 2. The edge: liquidity-reward harvesting

### 2.1 Mechanics (Polymarket docs, verified against live data)
* Each rewarded market has a daily pool `rate_per_day` (total ≈ **$134.7k/day** across 16,430 markets; ≈ $104k/day in non-weather, non-sports "other").
* Every minute a random sample is scored: `S(v,s) = ((v−s)/v)² × size` for each resting order within `v` cents of the size-cutoff-adjusted midpoint. `Q_min = max(min(Q1,Q2), max(Q1,Q2)/3)` when 0.10 ≤ mid ≤ 0.90 (else `min(Q1,Q2)`). Your daily reward is `pool × Σ(your Q_min / all Q_min)` / samples, paid at midnight UTC in pUSD.
* Verified: the NO-token book is an exact mirror of the YES book (40/40 markets), so competition is read from the YES book only.
* Makers pay **no fees** and additionally receive maker rebates (15–25% of the taker fees they absorb).

### 2.2 Evidence it pays, from real wallets (on-chain)
* `REWARD` payouts appear in account activity. Example farmers (7-day window, fills marked to resolution or current mid):

| wallet | capital (pUSD + positions) | 7-day rewards | 7-day rebates | fill markout | **net/day** | **net ROI/day** | market mix |
|---|---|---|---|---|---|---|---|
| hfv | ~$13.5k | $6,503 | $156 | −$3,906 | **$393** | **2.9%** | 88% non-weather by $ |
| LongTry | ~$614 | $851 | $52 | −$621 | $40 | 6.6% | weather |
| 0x2b27… | ~$975 | $279 | $23 | −$127 | $25 | 2.6% | weather |

* **The closest real analogues to this bot (non-weather, long-dated markets, 20-share quotes = the reward minimum):**

| wallet | capital | markets farmed | reward history | 30-day rewards+rebates | 30-day fill markout | **30-day net** |
|---|---|---|---|---|---|---|
| `0x1ef01de8…` | ~$1.1k | House/Senate races, Gemini release date, Prague mayor (~300 markets) | 41 straight days since Aug 15, $170/day → $1.1–1.6k/day | $16,930 | −$13,326 | **+$3,604 (≈$120/day)** |
| `T22222222222` | ~$2.4k | midterm vote totals, GPU-price index, governor races, jobs data | 28 days, ramping to $400–700/day | $6,006 | −$2,949 | **+$3,057 (≈$102/day)** |

  At mid marks both clear ~$100/day net on $1–2.5k over 30 days. **Caveat from the audit:** mid-marking flatters
  farmers. Maker losses roughly double as fills age (−71 bp for fills under 3 days vs −142 bp for 3–7 days), and
  many of these positions resolve in Nov 2026. Treat these two as optimistic best cases, not typical results.
* **Population, as first computed (overstated):** 95 wallets that received rewards in the last 7 days. The claim was
  76/95 net profitable, +$110.2k/week, ~1%/day median.
* **Population, corrected by the independent audit:**
  * ~55–65/95 profitable; +$40–65k/week at mid, less at liquidation marks.
  * Pooled 0.5–0.7%/day at mid, 0.15–0.2%/day at liquidation marks.
  * 53 of the "profitable" wallets were profitable *before* rewards (takers, plus a 12-wallet sibling cluster). Only 29
    were true reward farmers: 24/29 profitable at mid, 18/29 at liquidation.
  * Surviving farmers over 30–90 days: 0.43–0.62%/day, with trading losses ≈37–43% of rewards.
  * **Non-weather farmers: ≈0.2–0.3%/day**, losses ≈60–85% of rewards. The largest non-weather farmer (0x21ffd2b7,
    $310k) was ≈0.2%/day over 30 days and negative last week.
  * Weather-heavy farmers did best (1.06%/day pooled at mid), but weather is excluded here.
* Sign convention verified (40/40 maker fills: the user's row carries the user's own side).

### 2.3 Supply of uncontested pools (pool tracker, every 5 min)
* Across ~2,080 rewarded non-weather markets, $16k–21k/day of reward pools have **no** competing liquidity inside
  the band at any moment.
* **325 pools ($9.0k/day) stayed uncontested in every snapshot over 1.3 h.** Polymarket's own
  `market_competitiveness` for them is 0.
* Their 24 h activity: median **1** taker trade and **$2** traded; 75th percentile 3 trades / $30.
* **222 pools ($6.0k/day) are "quiet"** (≤3 trades and <3¢ price range in 24 h). 72 ($2.2k/day) are busy or
  volatile and are excluded by the bot's activity filter.
* Why would farmers leave them? Possible reasons:
  1. insider-prone topics (e.g. "Will the next Claude Sonnet be released on Sep 29?");
  2. new pools that farmers' bots have not picked up yet;
  3. an undocumented payout rule.
  Only (3) would break the thesis; a live pilot settles it.
* Some pools pay in USDC.e rather than pUSD (sponsored pools).
* **Topics** of the 219 quiet pools:
  * other: 102 pools, $2.3k/day;
  * **AI model releases and API prices: 39 pools, $1.6k/day, all flagged insider-prone by Jev** (e.g. "Will GPT
    Sol's output price be ≥ $20 in 2026?");
  * elections: 23, $0.56k/day;
  * awards: 19, $0.54k/day;
  * crypto/finance: 14; geopolitics: 10; sports: 12.
* **Risk backtest** (`research/quiet_risk_bt.py`), deliberately pessimistic:
  * Method: replay the last 7 days of real taker trades in 315 stable uncontested pools as if our 20-share quotes sat
    at the top of the book and absorbed every trade; mark each fill 24 h later.
  * Result: median 0.57 fills/day and **$0.11/day of adverse selection per pool** (90th pct $3.22, 99th $9.54).
  * **Total: $247/day of fill losses against $8,725/day of pool rewards (≈3%)**, vs 60–85% for farmers in contested
    pools. Only 1/315 pools lost more than its reward.
  * So on public data, the risk side of the thesis holds. What remains unverified is the payout to a lone quoter.
* **Circumstantial evidence on payouts** (natural experiment: 172 makers that traded in ≤5 markets in the last week
  and received rewards):
  * `qingkes` (`0x1d2b12e5…`) was dormant since April, then from Sep 22 earned
    **$46 → $276 → $342 → $372 → $482/day**. Its recent fills are in a $1,200/day pool that shows no competing
    in-band liquidity. Only ~$16 of positions and no pUSD are visible, so its real capital base is unclear.
  * Single-market makers in heavily contested pools earn amounts consistent with a proportional share: e.g. a
    $1,000/day pool with Q≈193k pays one maker ~$50–76/day, and a $100/day pool with Q≈1.3M pays two makers
    ~$17–43/day each.
  * This is consistent with the formula paying whoever supplies the qualifying liquidity. It is **not** proof for our
    specific quote placement; the live pilot is.

### 2.4 Why a small account can win
* When nobody quotes inside the band, a minimum-size order (20 shares ≈ $10–20 of collateral per side) earns **100%** of the pool. Right now ≈ $16.4k/day of non-weather pools have no competing liquidity inside the band.
* The bot's allocator water-fills capital to the highest marginal reward per $, so $100 goes to ~5 uncontested pools; extra capital only helps once pools are contested.

### 2.5 Where the risk is: adverse selection, and what does (not) predict it
Resting quotes get hit right before prices move. Measured on real farmers (`0x1ef0` + `T222`, 30 days, 46,489 fills
across 9,001 markets, each fill marked to resolution or current mid):
* Loss per $ filled is **≈3–5% everywhere**: 5.1% in the thinnest volume quartile, 2.8% in the busiest. But in
  absolute terms it is small per market, **≈$1.6–2.5 per market per 30 days** at minimum size, while uncontested
  pools pay $10–100/day. The binding constraint is reward share, not adverse selection, so breadth wins:
  min-size quotes across many pools.
* **Does the Jev → Claude toxicity screen predict losses? No.**
  * Jev: markets it passed lost 4.41%/$ filled vs 4.16%/$ for markets it rejected. Spearman correlation of every
    Jev score with loss per $ is between −0.01 and +0.05 (2,313 markets).
  * Claude Opus 5.5, on the 30 worst vs 30 best markets: AUC 0.49 (p = 0.56).
  * The 3-hour simulator had suggested otherwise (Jev-passed markets +$15.7, rejected −$23.1). That was
    small-sample noise, and the simulator also read the cached trade feed (audit N6).
  * **Caveat, selection bias:** this test only covers markets that experienced farmers *chose* to quote. The
    uncontested pools this bot targets are exactly the ones they avoid, and they include insider-prone topics (model
    release dates, award results, halftime headliners). There the gate is out-of-sample and plausibly useful.
  * **Decision:** the gate stays **on by default** (`PMBOT_USE_JEV=0` disables it). Its cost is a few cents a day
    and some forgone pools.
* **Activity filter (data-driven, on by default):** skip pools whose market traded >$1k or ranged >10¢ in 24 h, and
  charge expected fill losses (5% × half the 24 h taker flow) against each pool's reward estimate.
* Controls that **do** bound losses mechanically:
  * no quoting within 72 h of a market's end date;
  * rolling 5-min jump guard (≥ 4¢ → unwind-only for 60 min);
  * a 3-min block on a side after it fills;
  * max inventory of 1× quote size, and at most 35% of capital per market;
  * post-only orders;
  * an exchange heartbeat watchdog;
  * a 15% drawdown stop on trading equity.

## 3. Forward test (live books, real trade prints, paper fills)
_Filled in at the end of the run — see §6._

## 4. Jev + LLM: where they helped and where they did not
| Use | Result |
|---|---|
| Event matching Polymarket ↔ Pinnacle (sports research) | **Useful.** Separates true matches (0.96–0.98) from women's/reserve-team traps (0.05). $0.00002/call, ~0.4 s. |
| Toxicity screen for reward markets (Jev, 9,001 markets on real fills) | **No predictive power** for adverse selection (ρ ≤ 0.05). |
| Escalation to Claude Opus 5.5 (60 extreme markets) | **No predictive power** (AUC 0.49); qualitative catches only. Opt-in. |
| Claude (this research) | Strategy search, 10 hypothesis tests, bot design, audits, fixes. |

## 5. Independent audits
| Audit | Scope | Result |
|---|---|---|
| Code audit #1 | whole bot vs py-clob-client-v2 source, docs, and live endpoints | Verified correct: client API usage, post-only (no taker path), YES/NO conversions, the scoring formula, mirrored books (30/30), no secret logging. Found 2 CRITICAL (geoblock check didn't check geoblock; heartbeat kept stale quotes alive during stalls), 7 HIGH, 10 MEDIUM. **All fixed**, with reproductions added as tests. |
| Code audit #2 (verification) | the rewrite | Confirmed C1, C2, H1, H4, H5, H7, M1, M4, M5, M6, M10, L3, L6, L8 fixed. Found 3 new HIGH: equity double-counted reserved collateral; fill detection inferred fills from vanished orders; the paper feed was CDN-cached for up to 300 s, biasing paper P&L optimistic. **All fixed and tested** (18 tests). |
| Farmer-profitability audit | independent re-derivation, including on-chain equity accounting for 16 wallets via archive RPC | **Partially supported.** Rewards measured correctly (matched on-chain to the cent) and side convention correct (54/54 on-chain). Headline overstated: a 30k-fill pagination cap dropped the oldest (worst) fills; mid-marks flatter farmers; carry-in losses were ignored; takers and a sibling cluster were in the sample. Corrected: pooled 0.5–0.7%/day at mid, 0.15–0.2%/day at liquidation; **non-weather ≈0.2–0.3%/day**. All corrections adopted in §0/§2.2. |
| Leaderboard forensics | 3,102 wallets | See §1 rows 9–10. |

Consequence of audit #2 (N6) for this report: the first simulator (`research/rw_sim.py`) and the first paper runs
read the cached trade feed, so their **fill P&L is optimistic**. Only the corrected paper runs (§6) are used for the
bot's own results. The real-wallet evidence (§2.2) does not depend on this feed.

## 6. Results of the forward test
_Filled in at the end of the run._

## 7. The decisive test: a $100 live pilot (procedure and pre-committed decision rule)
Why this matters: every public-data check has been done. The one question that decides whether this is a small edge
(≈0.2–0.3%/day, like typical non-weather farmers) or a large one (collecting quiet uncontested pools) is **does
Polymarket pay a lone minimum-size quoter what the formula says?** Only a live account can answer it, and $100 is enough.

1. **Eligibility:** run only where Polymarket permits trading. The bot exits if `polymarket.com/api/geoblock`
   reports your IP as blocked.
2. **Account:** create a fresh Polymarket account used only for the bot, and deposit $100 (pUSD).
   * `PM_FUNDER` = the account's deposit (proxy) address.
   * `PM_PRIVATE_KEY` = the exported signing key.
   * `PM_SIGNATURE_TYPE` = 1 for email login, 2 for a browser wallet.
   * Keep the key in `.env` only; never commit it.
3. **Run:** `python -m pmbot.run --mode live --capital 100 --out runs`, then leave it running.
4. **Read the log daily.** At 01:30 UTC a line `{"reconcile_day": D, "estimated_rewards": E, "actual_rewards": A}`
   appears, together with `trading_equity` (fills marked to mid) and the `FILL` lines.
5. **Decision rule (commit to it in advance):**
   * `A ≥ 0.5 × E` for 3 consecutive days, **and** the trading-equity drawdown is smaller than cumulative `A`:
     the thesis holds. Scale capital stepwise (e.g. ×2 every 3 days), watching `A/E` (competition arrives) and
     fill losses.
   * `A < 0.2 × E`: lone quoters are not being paid as modelled. **Stop.** At the audited ≈0.2–0.3%/day the
     strategy is not worth running at small scale.
   * In between: keep running at $100 for a week, then decide.
6. **Risks you accept:**
   * inventory from fills (max 1 quote size per market, at most 35% of capital per market);
   * rare jumps against a resting quote (bounded by the quote size);
   * resolution/dispute risk on inventory held to resolution;
   * Polymarket changing the reward program at any time.
