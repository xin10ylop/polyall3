# research/

Study scripts behind ../REPORT.md. They expect to be run from a working directory that contains `pm.py` (this folder),
`data/` and `live/` (evidence data is **not** committed: it is large and regenerable). Several analyses depend on
earlier outputs:

| Script | Produces / uses |
|---|---|
| `census.py` | `data/census_<day>.json` (closed-market census, 90 days) |
| `soccer_collect.py`, `soccer_bt.py`, `soccer_eval*.py` | soccer 1X2 vs Pinnacle/Betfair closing (football-data.co.uk CSVs in `data/fd/`) |
| `negrisk_scan.py` | live neg-risk bundle arbitrage scan |
| `sports_fill_calib.py`, `endgame_probe.py` | sports taker-fill calibration, post-game window |
| `calib_collect.py`, `calib_eval.py`, `crypto_fills.py` | non-sports calibration; crypto strike-market fills |
| `sharp.py`, `recorder.py`, `live_edges.py`, `sports_clv.py`, `jev.py` | live Pinnacle vs Polymarket recorder (Jev event matching) and CLV |
| `rewards_scan.py`, `rewards_lib.py`, `rw_sim.py` | first reward scans/simulator (fill P&L optimistic: cached feed, see audit N6) |
| `farmer_markout.py`, `farmer_population.py` | real-farmer markouts (see the audit corrections in REPORT §2.2) |
| `gate_validate.py`, `gate_market_volume.py`, `gate_opus_extremes.py`, `gate_uncontested.py`, `jev_tox.py` | toxicity-gate tests |
| `pool_tracker.py`, `quiet_pools.py`, `quiet_risk_bt.py` | uncontested/quiet pool supply and the 7-day risk backtest |
| `payout_check.py`, `payout_analyze.py`, `empty_pools.py`, `competitiveness_check.py` | on-chain daily reward totals vs pools with a scoring quote (aggregate payout check); why empty pools are empty; Polymarket's own per-market competitiveness |
| `sponsored_recorder.py`, `sponsored_check.py` | per-minute books of sponsored pools vs on-chain `SponsorRefunded` (earned fraction per pool; tests per-minute accrual, cannot isolate lone quoters) |
| `lone_maker_check.py` | native pools whose book looks like one maker: identify the maker from fills, compare its next-day on-chain reward with a lone quoter's expected payout |
| `fwd_summary.py` | summary of paper forward-test logs (REPORT §6) |
