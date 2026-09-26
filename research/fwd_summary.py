"""Summarise paper forward-test logs: python fwd_summary.py <run_dir> [...]
Formula rewards assume the (unverified) lone-quoter payout; trading equity is fill P&L marked at the current mid."""
import sys, json, glob, os, statistics as st

for d in sys.argv[1:]:
    recs = []
    for f in sorted(glob.glob(os.path.join(d, '*.jsonl'))):
        recs += [r for r in map(json.loads, open(f)) if 'hrs' in r]
    if not recs:
        continue
    fills = []
    log = os.path.join(d, 'run.log')
    if os.path.exists(log):
        fills = [l.strip()[20:] for l in open(log) if ' FILL ' in l]
        jumps = sum(1 for l in open(log) if ' jump ' in l)
    eq = [r['trading_equity'] for r in recs if r.get('trading_equity') is not None]
    hrs = recs[-1]['hrs']
    print(f"== {os.path.basename(d.rstrip('/'))}: {hrs:.2f} h, {len(recs)} cycles")
    print(f"   pools quoted (median) {st.median(r['n_quoted'] for r in recs):.0f}; collateral locked (median) "
          f"${st.median(r['locked'] for r in recs):.0f}; formula rate (median) ${st.median(r['rate_cons_usd_day'] for r in recs):.0f}/day")
    print(f"   formula rewards accrued ${recs[-1]['rew_cons']:.2f} (= ${recs[-1]['rew_cons'] / max(hrs, 1e-9) * 24:.0f}/day)")
    print(f"   fills {recs[-1]['n_fills']}; jump cooldowns started {jumps if fills is not None else '?'}; "
          f"trading equity (fill P&L at mid): last ${eq[-1]:.2f}, min ${min(eq):.2f}, max ${max(eq):.2f}")
    for f in fills[:30]:
        print('     ', f[:110])
