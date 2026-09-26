# Polymarket edge search — full research report

Date: 2026-09-26. Everything below was measured on live Polymarket data (public APIs) from this session.
Trading venue: **Polymarket only**. Weather markets excluded as required.

## 0. Bottom line

| | |
|---|---|
| **Edge found** | **Liquidity-reward harvesting**: rest small two-sided post-only quotes inside the reward band of markets that pay Polymarket CLOB liquidity rewards, in markets a **Jev → Claude Opus cascade** judges low-toxicity. |
| Why it is an edge | Polymarket pays ~$134k/day to makers. The pool is split by a published formula, so income is contractual rather than a forecasting bet. Many pools have little or no competition inside the band. |
| Is it real? | Yes, on real wallets. Of 95 wallets active in thin rewarded markets that received rewards last week (no cherry-picking), **76 were net profitable after fill losses**. In aggregate: rewards $127.8k + rebates $21.1k − adverse selection $38.7k = **+$110.2k**. The median farmer made **≈1%/day on capital**; the top 10% made ≥4.4%/day; the best small accounts made 6–7%/day on $600–$1,500. |
| Executable? | Yes. Orders are post-only limit orders (never pay taker fees), with a minimum size of 20 shares and no latency race. Quotes are refreshed every 20 s, and income depends on minutes-long resting time, not milliseconds. |
| Small capital? | Yes. Reward share does not depend on size when a pool is uncontested, so minimum-size quotes (~$10–20 per market) capture it. A $100 account can quote 5 markets. |
| $100/day? | **Not from day one with $100. No legitimate edge does 100%/day.** At the evidence-based 1–4%/day, $100/day needs ≈$2.5k–$10k deployed: reached by compounding (e.g., ~4 months at 3%/day from $100) or by adding capital. The live bot logs actual vs estimated rewards daily so this can be verified within days at $100. |

## 1. What was tested and rejected (with evidence)

| # | Idea | Data | Result |
|---|---|---|---|
| 1 | Soccer 1X2: Polymarket vs Pinnacle/Betfair closing line | 3,653 matches, 16 leagues, 2025/26, minute price history | Polymarket 5 min before kickoff is **as accurate or more accurate** than the sharp close (log-loss 1.0178 vs 1.0197 on English leagues; 11/16 leagues PM ≤ sharp). Mean |PM−sharp| 0.3–0.8 pp. No significant betting edge at T−120/60 min; T−5/15 "edges" were ~100 bets/season (t≈2.3 on 1 of 16 tried cells): noise/look-ahead. **Efficient.** |
| 2 | Live sports: PM ask vs Pinnacle fair (all sports) | 302 matched events per snapshot, recorder running all session | Median edge −1.7% (spread+fee), 95th pct +0.07%. Only thin leagues with low Pinnacle limits show +3–5%. CLV check (64 events): PM-cheaper-than-Pinnacle bets held vs Pinnacle's close (+2.3¢ for edge>1%, n=21 events, mostly esports). **Promising but small sample; secondary.** |
| 3 | Neg-risk bundle arbitrage | Live scan of 7,360 multi-outcome events / 116k books | 8 of 8,085 complete-outcome events positive, all illiquid (3–5 shares) or year-long lockups. The other "arbs" are augmented events with unlisted outcomes (not arbitrage). **Efficient.** |
| 4 | Favorite/longshot bias in sports | 600k real taker fills, 1,500 moneyline markets, $111M | No bucket reliably mispriced; effective sample = markets, not fills. **No edge.** |
| 5 | Post-game "endgame" (buy winner at 0.99 before resolution) | 250 games | Liquidity exists ($2.3M below 0.99 post-decision), but live-fill calibration at 0.99–0.995 returns ≈+0.5% with rare total losses; competitive. **Thin.** |
| 6 | Longshot/favorite bias outside sports | 10,257 resolved markets, 125k fixed-time snapshots, clustered SE | Longshots won **more** than priced (0.10–0.20 bucket priced 14.7%, won 18.0%); buying NO on longshots loses (t=−6). Politics, economics, tech, culture, mentions, and fee-free geopolitics are fair after costs. **No edge.** |
| 7 | Crypto "above $X on date" favorites | 2,421 strike markets, 300k real fills | Looked like +6.5%/$ (t=9). Real fills show "above" bets won at **every** price level and "below" bets lost at every level: the crypto rally, **regime not edge**. |
| 8 | Crypto 5/15-min up/down | fee schedule + market structure | 7% fee rate (3.5% of stake at 50¢) + latency race vs bots. Violates "no millisecond strategies". **Rejected.** |

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

* **Population (not cherry-picked)**: the 200 most active wallets in ~40 thin rewarded markets → 95 received rewards in the last 7 days. 76/95 net profitable; aggregate +$110.2k/week; median ≈1.16%/day, 75th pct 2.84%/day, 90th pct 4.44%/day on capital. Farmers keep ~70% of reward+rebate income after adverse selection.
* Sign convention verified (40/40 maker fills: the user's row carries the user's own side).

### 2.3 Why a small account can win
* When nobody quotes inside the band, a minimum-size order (20 shares ≈ $10–20 of collateral per side) earns **100%** of the pool. Right now ≈ $16.4k/day of non-weather pools have no competing liquidity inside the band.
* The bot's allocator water-fills capital to the highest marginal reward per $, so $100 goes to ~5 uncontested pools; extra capital only helps once pools are contested.

### 2.4 Where the risk is, and how the bot handles it
Adverse selection: quotes get hit right before information moves the price. The simulator's largest loss (−$39.50, "#2 global Netflix show") came from a market whose ranking is visible in real time.
* **Jev screen** (TypeSafe Jev via OpenRouter Decisions API, ~$0.00004/market): realtime-observable outcome? decisive info within 72 h? news frequency? insider risk?
* **Claude Opus 5.5 confirmation** (cascade): every market Jev passes is re-read in full by Opus before quoting (≈$0.009/market, cached 24 h). Opus caught what Jev missed: FlixPatrol as a live proxy for Netflix rankings; Super Bowl headliners usually announced in September.
* In the 3-hour simulation, markets passing Jev earned $52 in rewards with **+$15.7** fill P&L; markets Jev rejected earned $90 with **−$23.1** fill P&L, including all three largest losses.
* Jump guard (mid moves ≥ 4¢ → pull quotes 60 min), no quoting within 72 h of a market's end, max inventory = 1 quote size, 35% max capital per market, post-only orders, exchange heartbeat dead-man switch, drawdown stop.

## 3. Forward test (live books, real trade prints, paper fills)
_Filled in at the end of the run — see §6._

## 4. Jev usage summary
1. Event matching for the sports recorder (Polymarket ↔ Pinnacle): catches women's/reserve-team mismatches (0.05 vs 0.98 on true matches), $0.00002/call.
2. Toxicity screen for reward markets (above), 1,387 markets scored for $0.05.
3. Cascade escalation to Claude Opus 5.5 for final confirmation.

## 5. Independent audits
_Filled in when the audits complete._

## 6. Results of the forward test
_Filled in at the end of the run._
