# Out-of-sample analysis: frozen rules on Jan 2023 – Aug 2025

Run date: 24 Oct 2026. Rules, sizing and costs loaded from `frozen/rules_v1.json` (commit c10d7a4). Before running, the
current code's rules, sizing, config and costs were checked against the snapshot and are identical, so nothing was
re-fitted. Full output is in `report.md`; trades, daily equity and stats are in the CSVs alongside it.

## Summary

Over 2 Jan 2023 – 29 Aug 2025 (654 trading days, none skipped) the combined book made **+8.1%** in total
(CAGR **+3.0%**), with a Sharpe of **0.24** and an **18.6%** max drawdown. In-sample (Sep 2025 – Oct 2026) the same
rules made a CAGR of 37.6% with a Sharpe of 2.31. The 95% confidence interval on the Sharpe (-0.89 to 1.37)
includes zero comfortably.

The small positive result is **one day**: 20 Dec 2023 made ₹6.67 lakh across the three strategies. The whole
32-month book made ₹2.42 lakh, so without that single day it lost about ₹4.25 lakh. Take out the five best trades and
it loses ₹6.29 lakh.

| | CAGR | Sharpe | Max DD | Profit factor | In-sample CAGR | In-sample Sharpe |
| --- | --- | --- | --- | --- | --- | --- |
| Mean Reversion | +4.9% | 0.30 | -26.9% | 1.03 | 52.7% | 1.74 |
| Directional | +4.0% | 0.27 | -31.0% | 1.03 | 33.2% | 1.58 |
| Semi-Directional | -0.1% | 0.04 | -14.9% | 1.00 | 26.8% | 2.26 |
| **Combined** | **+3.0%** | **0.24** | **-18.6%** | **1.03** | **37.6%** | **2.31** |

## By year: getting worse over time

| | 2023 | 2024 | Jan–Aug 2025 |
| --- | --- | --- | --- |
| Combined return | +17.4% | +2.3% | -10.0% |
| Combined Sharpe | 0.73 | 0.22 | -1.29 |
| Mean Reversion | +36.9% | -1.2% | -16.0% |
| Directional | +16.3% | +8.8% | -12.4% |
| Semi-Directional | -1.0% | -0.6% | +1.2% |

2023 was the only good year, and most of it came from August and December 2023 (Mean Reversion +32% and +30% in those
two months). The trend runs the wrong way: the further from the in-sample period, the better it looks, and the year
right before the in-sample period (2025) was the worst.

(2024 figures differ slightly from the earlier 2024–2025 holdout in `out_of_sample/` because sizing is a share of
current equity, and here 2024 starts from the equity built up in 2023.)

## By day type

Net P&L, ₹:

| | 2023 | 2024 | 2025 | Total |
| --- | --- | --- | --- | --- |
| DTE 1 | +8,49,035 | +1,96,716 | -19,133 | **+10,26,617** |
| Expiry (DTE 0) | -1,69,094 | -1,33,670 | -1,84,079 | **-4,86,843** |
| Far (2+ days) | -1,57,162 | +17,055 | -1,58,023 | **-2,98,130** |

- **Expiry-day rules lose every single year** in total. Mean Reversion (-₹1.19L, -₹0.80L, -₹1.50L) and
  Semi-Directional (-₹0.56L, -₹0.21L, -₹0.49L) lost in each year; Directional's 1-lot expiry trade was roughly flat. These are the rules that ranked worst in the
  old 2023–2025 search (Mean Reversion's expiry debit spread 1,636th of 2,046; Semi-Directional's expiry credit spread
  1,367th). Three years of consistent losses is strong evidence they are not real edges.
- **Far-day rules** lose overall and add nothing.
- **DTE 1** carries the whole book, but it faded from +₹8.5 lakh in 2023 to slightly negative in 2025, and the 2023
  number is dominated by 20 Dec 2023 (Directional +₹2.35 lakh, plus three Mean Reversion entries of +₹1.2–1.5 lakh
  each). Semi-Directional's DTE 1 credit spread is the steadiest piece: +₹1.78 lakh over the window, with a 56% win
  rate, and it was also positive in the earlier holdout and in-sample.

## Risk

- **Stops are expensive:** Mean Reversion's 95 stopped trades cost ₹11.2 lakh and Directional's 27 cost ₹6.6 lakh,
  wiping out most of what the square-off trades made.
- **Long drawdowns:** 359 trading days (about 17 months) for the combined book; 453 for Semi-Directional.
- **Payoff depends on rare big days:** Mean Reversion's best day was +39.5% of its capital, while only 44% of months
  were positive. That shape can look good or bad on any given year depending on whether one or two big moves turn up.
- **Correlation is higher than in-sample:** Mean Reversion correlates 0.45–0.46 with the other two, so the combined
  book is less diversified than the in-sample results suggested.

## Market differences from in-sample

Lot size was 50 → 25 (Q2 2024) → 75 (Q4 2024); expiries were mostly Thursday (some Wednesdays, and Tuesdays from Sep
2025). Sizing is based on the risk budget, so it adjusts to lot size. Costs use the frozen assumptions (slippage
max(0.25 pts, 0.5% of premium) per fill); `out_of_sample/sensitivity/report.md` shows the near-expiry results get
much worse with wider slippage, so these numbers are if anything optimistic.

## How clean the test is

The rules were frozen before this run and not changed. But the old rule search (`data/dhan_2023_2025/search/scores.csv`)
was run on this same 2023–2025 data, and the earlier 2024–Aug 2025 holdout has already been looked at. So 2023 is the
only part of this window that is new relative to the last test. The window stops at 31 Aug 2025 because the in-sample
period starts on 1 Sep 2025.

## Conclusion

Adding 2023 makes the headline number positive, but it doesn't change the verdict: the frozen rules don't show a
reliable edge outside the period they were fitted on. A profit factor of 1.03, a Sharpe interval that includes zero,
and a result that goes negative without one day all mean it can't be told apart from luck.

What the data does support:

1. **Drop the expiry-day (DTE 0) rules**: they lost in every year in total, and in every year for Mean Reversion and Semi-Directional.
2. **Drop or re-examine the far-day rules**: they lost overall and add nothing.
3. **Keep the DTE 1 rules on the watch list**, especially Semi-Directional's DTE 1 credit spread, the only piece that
   was positive in every period tested. Mean Reversion and Directional DTE 1 rely on a few big days and faded in 2025.
4. Any rule changes based on this should be frozen as a new version (`rules_v2.json`) and judged only on data after the
   freeze (forward / paper trading), because all of 2023–2026 has now been looked at.
