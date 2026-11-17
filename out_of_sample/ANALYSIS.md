# Out-of-sample analysis: frozen rules on 2024 – Aug 2025

Run date: 24 Oct 2026. Rules frozen in `frozen/rules_v1.json` (commit c10d7a4) before this test was run.

## Summary

The frozen rules lose money on the 20 months before the period they were fitted on. Over 1 Jan 2024 – 29 Aug 2025 (409 trading days) the combined book returned **-9.0%** (CAGR -5.5%), with a Sharpe of **-0.36** and a **17.6%** drawdown it never recovered from. In-sample, the same rules made 43.1% with a Sharpe of 2.31.

| | Holdout CAGR | Holdout Sharpe | Holdout max DD | In-sample CAGR | In-sample Sharpe | In-sample max DD |
| --- | --- | --- | --- | --- | --- | --- |
| Mean Reversion | -12.6% | -0.44 | -28.5% | 52.7% | 1.74 | -9.9% |
| Directional | -4.9% | -0.10 | -29.9% | 33.2% | 1.58 | -12.8% |
| Semi-Directional | +0.6% | 0.11 | -9.2% | 26.8% | 2.26 | -4.4% |
| **Combined** | **-5.5%** | **-0.36** | **-17.6%** | **37.6%** | **2.31** | **-7.3%** |

The in-sample result looks like mostly selection on one favourable year. One piece does hold up: the DTE 1 credit spread in Semi-Directional, which made money in both periods. Everything else should be treated as unproven, or as not working.

## How the test was set up

- **Rules:** the nine day-type rules, risk multipliers, sizing limits and cost settings were frozen to JSON and loaded from there. Nothing was tuned on this window.
- **Data:** `data/dhan_2023_2025/nifty_opt_1min.parquet`. Where it overlaps the 2-year file (22 Oct 2024 – 29 Sep 2025, 3.65M rows), prices, open interest, expiries and lot sizes agree exactly, so the result isn't a data artifact.
- **Window:** 1 Jan 2024 to 31 Aug 2025. It stops before September 2025 because that's where the in-sample period begins. All 409 days had complete data.
- **Market differences from in-sample:** expiries were on Thursday (Tuesday from Sep 2025), and lot sizes were 50, then 25, then 75. Sizing is based on the risk budget, so it adjusts to lot size automatically.

**How clean is this holdout?** It isn't fully clean. An earlier rule search (`data/dhan_2023_2025/search/scores.csv`, 6,138 candidates) was run on 2023–2025. The current rules were **not** picked from it: four of the eleven aren't in it at all, and most of the rest ranked poorly. Still, the data had been looked at, so this counts as "not used to select the final rules", not "never seen".

## What happened

**By year:** the book was roughly flat in 2024 (+0.7%, Sharpe 0.12) and lost 9.6% in Jan–Aug 2025 (Sharpe -1.35). Directional made 5.8% in 2024, mostly from three large put trades in Jan–Mar 2024 (best: +₹1.70 lakh on 13 Mar 2024). It then lost 13.1% in 2025. Mean Reversion lost in both years.

**By day type** (net P&L, ₹):

| | DTE 1 | Expiry (DTE 0) | Far (2+ days) |
| --- | --- | --- | --- |
| Mean Reversion | +64,062 | -1,82,910 | -82,014 |
| Directional | -41,422 | -13,285 | -25,768 |
| Semi-Directional | **+1,11,567** | -66,419 | -34,670 |
| Combined | +1,34,207 | -2,62,614 | -1,42,452 |

In-sample, 91% of profit came from DTE 1 and expiry days. In the holdout, **DTE 1 is still positive** but **expiry days are the biggest loser**. The expiry rules are exactly the ones that ranked worst in the old search: Mean Reversion's expiry debit spread was 1,636th of 2,046 and Semi-Directional's expiry credit spread 1,367th of 2,046, and both had already lost money on this data in that search. They were kept because they worked in Sep 2025 – Sep 2026. The holdout says that year was the exception.

**Stops:** Mean Reversion's 52 stopped trades lost ₹4.85 lakh and Directional's 19 lost ₹4.20 lakh. On Mean Reversion's DTE 1 days, all three entries lost on 38 of 79 days, costing ₹8.27 lakh on those days. The rule still came out slightly ahead (+₹64k) only because the other days made it back.

**Diversification:** daily correlations stayed low (Directional vs the others 0.13 and -0.20), but that doesn't help when the parts don't make money on their own.

## How sensitive the near-expiry results are to costs

Full tables are in `sensitivity/report.md`. Each test changes one assumption from the base, which is slippage of max(0.25 pts, 0.5% of premium) per fill, filled at the next bar's open. All figures below are DTE 0 + DTE 1 net P&L, in ₹.

| Assumption | In-sample, combined | Holdout, combined |
| --- | --- | --- |
| Base | 11,78,798 | -1,28,408 |
| Slippage 1% of premium | 9,46,527 | -2,56,859 |
| Slippage 2% of premium | 7,28,225 | -4,21,360 |
| Slippage floor 1 pt | 7,66,495 | -4,26,506 |
| Slippage floor 2 pts | 3,62,943 | -7,02,987 |
| Fill at next bar's close | 10,87,432 | -1,13,537 |
| Fill 2 bars late | 10,79,533 | -72,041 |

- **The points floor matters most.** These trades often use spreads with legs priced around 40–100. A 2-point floor per fill takes away 69% of the in-sample near-expiry profit, and Semi-Directional's in-sample Sharpe falls from 2.26 to -0.15. The 0.25-point base assumes very tight fills. If crossing the bid-ask costs more like 0.5–1 point per leg (worth checking against real fills; the data has no bid-ask), the in-sample numbers should be read at those rows.
- **Percentage slippage does less damage** than you might expect. Sizing includes slippage in each trade's worst-case loss, so higher slippage means fewer lots. In-sample break-even percentage slippage is above 5% for Mean Reversion and Semi-Directional and 4.98% for Directional. In the holdout, Mean Reversion and Directional lose money on DTE 0 + DTE 1 **even with zero slippage**. Semi-Directional breaks even at 1.19% of premium per fill.
- **Fill timing barely matters.** Filling one or two bars later, or at the close instead of the open, cuts in-sample near-expiry P&L by about 8%. The edge, where there is one, isn't a one-minute timing effect.

## How many variants were tried

`experiments/variant_log.csv` now records every evaluated rule set:

| Purpose | Rows | Note |
| --- | --- | --- |
| Historical search, 2023–2025 | 6,138 | single-rule candidates, 2,046 per day type |
| Refit search, Sep 2025 – Sep 2026 | unknown | produced the current rules; not recorded |
| Robustness grids | 54 | 27 on each in-sample dataset |
| Stress tests | 6 rows (244 variants) | aggregate rows, 122 variants on each dataset |
| Baseline / holdout / sensitivity runs | 3 / 6 / 108 | diagnostics, not selection |

At least 6,138 candidates were tried before the refit, and the refit added an unknown number on top. With that many tries, an in-sample Sharpe of 2.3 on one year is well within what selection alone can produce. The holdout result is consistent with that. From now on, every call to `evaluate()` writes to the log automatically.

## What to take from this

1. **Don't trade the current book.** Three of the four results are negative out of sample, and the confidence intervals on the positive one (Semi-Directional, Sharpe 0.11) span -1.4 to 1.7.
2. **Semi-Directional's DTE 1 credit spread is the only piece with support in both periods** (+₹1.30 lakh in-sample, +₹1.12 lakh in the holdout). It's the obvious candidate to research further. It would need to be tested on 2023 and in the live forward period, without being retuned, before it means anything.
3. **Drop the expiry-day rules as they stand.** They lost in the old search and in the holdout, and only worked in the fitted year.
4. **Use a realistic cost floor.** Re-run everything with a 0.5–1 point floor per fill as the base case.
5. **Forward test.** The frozen snapshot is ready. When data after 22 Oct 2026 arrives, run `holdout_test.py --data <new file> --start 2026-10-23 --end <date> --out out_of_sample/forward_...`, unchanged.

## Files

- `holdout_2024-01_2025-08/report.md`: full generated report (performance, per year, day type, months, exit reasons, search ranks, regime)
- `holdout_2024-01_2025-08/trades.csv`, `daily_equity.csv`, `stats.csv`, `stats_by_year.csv`, PNG charts
- `sensitivity/report.md`, `sensitivity.csv`, `breakeven.csv`, `slippage_near_expiry.png`
- To reproduce: `python holdout_test.py` and `python sensitivity.py` (both read `frozen/rules_v1.json`)
