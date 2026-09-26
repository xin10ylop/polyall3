# Polymarket edge search — full research report

Date: 2026-09-26. Everything below was measured on live Polymarket data (public APIs) from this session.
Trading venue: **Polymarket only**. Weather markets excluded as required.

## 0. Bottom line

| | |
|---|---|
| **Edge found** | **Liquidity-reward harvesting**: rest minimum-size, two-sided, post-only quotes inside the reward band of many thinly contested markets that pay Polymarket CLOB liquidity rewards. |
| Why it is an edge | Polymarket pays ~$134k/day to makers. The pool is split by a published formula, so income is contractual rather than a forecasting bet. Many pools have little or no competition inside the band. |
| Is it real? | Yes, on real wallets. Of 95 wallets active in thin rewarded markets that received rewards last week (no cherry-picking), **76 were net profitable after fill losses**. In aggregate: rewards $127.8k + rebates $21.1k − adverse selection $38.7k = **+$110.2k**. The median farmer made **≈1%/day on capital**; the top 10% made ≥4.4%/day; the best small accounts made 6–7%/day on $600–$1,500. |
| Executable? | Yes. Orders are post-only limit orders (never pay taker fees), with a minimum size of 20 shares and no latency race. Quotes are refreshed every 20 s, and income depends on minutes-long resting time, not milliseconds. |
| Small capital? | Yes. Reward share does not depend on size when a pool is uncontested, so minimum-size quotes (~$10–20 per market) capture it. A $100 account can quote 5 markets. |
| $100/day? | **Not from day one with $100. No legitimate edge does 100%/day.** At the evidence-based 1–4%/day, $100/day needs ≈$2.5k–$10k deployed: reached by compounding (e.g., ~4 months at 3%/day from $100) or by adding capital. The live bot logs actual vs estimated rewards daily so this can be verified within days at $100. |

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

  Both clear **$100/day net on $1–2.5k**, sustained over 30 days. Adverse selection took 50–79% of their rewards,
  which is why this bot adds a toxicity cascade and fill guards. Caveat: open positions (many resolve in Nov 2026)
  are marked at the current mid.
* **Population (not cherry-picked)**: the 200 most active wallets in ~40 thin rewarded markets → 95 received rewards in the last 7 days. 76/95 net profitable; aggregate +$110.2k/week; median ≈1.16%/day, 75th pct 2.84%/day, 90th pct 4.44%/day on capital. Farmers keep ~70% of reward+rebate income after adverse selection.
* Sign convention verified (40/40 maker fills: the user's row carries the user's own side).

### 2.3 Supply of uncontested pools (pool tracker, every 5 min)
Across ~2,080 rewarded non-weather markets, $16k–21k/day of reward pools have **no** competing liquidity inside the
band at any moment. Over 15 minutes, 429/488 uncontested pools stayed uncontested, while new ones kept appearing.
(Pool "start dates" are re-stamped daily by Polymarket, so pool age is not observable from the API.)

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
  * **Decision:** the toxicity gate is **opt-in** (`PMBOT_USE_JEV=1`) rather than default. It removes ~40% of pools
    (reward income) without measurably reducing losses. Opus still catches individual obvious hazards (e.g.
    "headliners usually announced in September"), so it is kept as an optional sanity layer.
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
| Farmer-profitability audit | independent re-derivation of the population result | _pending_ |
| Leaderboard forensics | 3,102 wallets | See §1 rows 9–10. |

Consequence of audit #2 (N6) for this report: the first simulator (`research/rw_sim.py`) and the first paper runs
read the cached trade feed, so their **fill P&L is optimistic**. Only the corrected paper runs (§6) are used for the
bot's own results. The real-wallet evidence (§2.2) does not depend on this feed.

## 6. Results of the forward test
_Filled in at the end of the run._
