# NIFTY Intraday Options Backtest

A backtester for three intraday NIFTY weekly-option strategies, run on 1-minute option data. Each strategy uses a different rule depending on how many days are left to expiry. Every position is a defined-risk long option or vertical spread, sized from its worst-case loss and closed by 15:15 every day.

## Strategies

Each strategy has one rule for each of three day types: far from expiry (3+ days), the day before expiry (DTE 1), and expiry day.

| Strategy | Idea | Signal |
| --- | --- | --- |
| Mean Reversion | The morning move overshoots and partly reverses | Fade spot vs the day's open or the previous close; long options or a debit spread |
| Directional | Option positioning near the money points to the day's direction | Follow the put/call open-interest ratio over ATM±5 strikes |
| Semi-Directional | Short premium with a directional tilt earns time decay near expiry | Spot vs previous close or open; sell a defined-risk credit spread |

The full rule set (entry and exit times, structures, stops and risk multipliers) is in [`backtest/strategies.py`](backtest/strategies.py).

## Results

**The strategies looked strong on the year they were fitted on and failed on a frozen out-of-sample test.**

The rules were chosen on 1 Sep 2025 – 16 Oct 2026, then frozen (`frozen/rules_v1.json`) and run unchanged on earlier data. Combined book, ₹30 lakh:

| Period | Trading days | Return | CAGR | Sharpe (95% CI) | Max drawdown |
| --- | --- | --- | --- | --- | --- |
| In-sample (fitted), 1 Sep 2025 – 16 Oct 2026 | 278 | +43.1% | +37.6% | 2.31 (0.71 to 3.90) | -7.3% |
| **Holdout, 1 Jan 2024 – 29 Aug 2025** | **409** | **-9.0%** | **-5.5%** | **-0.36 (-1.94 to 1.22)** | **-17.6%** |
| Holdout extended, 2 Jan 2023 – 29 Aug 2025 | 654 | +8.1% | +3.0% | 0.24 (-0.89 to 1.37) | -18.6% |

- **No contract change explains the gap.** Lot size has no material effect, and the months after SEBI's Nov 2024 reforms were the worst stretch. The Sep 2025 move to Tuesday expiry can't be tested on history because it starts on the first day of the fitted year (`structural_break/`).
- **The extended holdout's profit is one day.** 20 Dec 2023 made ₹6,66,934, against ₹2,41,644 net for all 32 months.
- **One rule held up in every period:** Semi-Directional's DTE 1 credit spread made ₹1,30,016 in-sample, ₹1,11,567 in Jan 2024 – Aug 2025 and ₹1,77,939 in Jan 2023 – Aug 2025 (win rate 56–60%). It was identified after seeing all periods, so it is a lead for new data, not a confirmed edge.
- **Costs decide the result.** Raising the slippage floor from 0.25 to 2 points per fill cuts in-sample DTE 1 + expiry-day profit by 69.2% (₹11,78,798 to ₹3,62,943). The DTE 1 credit spread survives a 1-point floor in both periods but loses ₹22,877 in the holdout at 2 points.

In-sample results by strategy, for reference (₹10 lakh each):

| | CAGR | Sharpe | Max drawdown | Calmar |
| --- | --- | --- | --- | --- |
| Mean Reversion | 52.7% | 1.74 | -9.9% | 5.33 |
| Directional | 33.2% | 1.58 | -12.8% | 2.60 |
| Semi-Directional | 26.8% | 2.26 | -4.4% | 6.12 |
| **Combined (₹30L)** | **37.6%** | **2.31** | **-7.3%** | **5.12** |

The rules were selected on this period, requiring every strategy to be profitable in both halves and a combined Calmar of at least 5, after an earlier search of 6,138 candidates on 2023–2025 data. Full write-up: [project report](NIFTY%20Intraday%20Options%20Three-Strategy%20Backtest%20Report.md); details in `out_of_sample/`, `2023-2025 test/`, `structural_break/` and `paper_trading/`.

## Project layout

```
run_backtest.py          entry point: runs all strategies, the combined book, and writes the report
freeze_rules.py          saves the rules, sizing and costs to frozen/rules_v1.json (never overwritten)
holdout_test.py          runs the frozen rules unchanged on another period
sensitivity.py           slippage and fill-timing sensitivity, in-sample and holdout
structural_break.py      tests whether lot size, SEBI's Nov 2024 rules or Tuesday expiry explain the break
paper_trading.py         replays the frozen rules on days after the fitted period
backtest/
  config.py              capital, sizing limits, session times, brokerage and statutory charges
  data.py                loads the parquet into per-day bar/strike matrices
  engine.py              order fills, slippage, charges, position sizing
  strategies.py          the three rule-based strategies
  metrics.py             equity curves, Sharpe (with confidence interval), drawdown, trade stats
  report.py              charts and the Markdown report
  frozen.py              writes and loads the frozen snapshot, and checks the code against it
  variant_log.py         records every evaluated rule set in experiments/variant_log.csv
data/
  nifty_opt_1min_2y.parquet          1-minute NIFTY option bars, Oct 2024 – Oct 2026
  nifty_opt_bhavcopy.parquet         NSE expiries and lot sizes by date
  sample/nifty_opt_1min_2026-01.parquet   one month, for quick runs
```

## Setup

Python 3.10 or newer.

```
pip install pandas numpy matplotlib pyarrow
```

## Usage

```
python run_backtest.py --data data/nifty_opt_1min_2y.parquet --start 2025-09-01 --end 2026-10-16
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--data` | `data/final/nifty_opt_1min.parquet` | 1-minute option bars to use. That default file isn't in the repo, so pass this. |
| `--start` / `--end` | last year of the data | date range, `YYYY-MM-DD` |
| `--out` | `results` | output folder |
| `--split` | `2026-04-01` | date that splits the first-half / second-half comparison |
| `--robustness` | off | also runs the parameter grid and the stress test (takes about 2 minutes) |

For a quick check, run on the sample month:

```
python run_backtest.py --data data/sample/nifty_opt_1min_2026-01.parquet --start 2026-01-01 --out results_sample
```

The output folder contains:

- `report.md`: setup, performance table, half-split, correlations, breakdowns by exit reason, days to expiry, direction and month, plus the robustness and stress tables if those ran
- `equity_curves.png` and one chart per strategy
- `trades.csv`: every trade with its legs, lots, entry and exit times and prices, costs and P&L
- `daily_equity.csv`, `stats.csv`, and `robustness.csv` / `stress_test.csv` when `--robustness` is set

## Data format

Each row of the 1-minute file is one strike and option type at one minute. Columns:

| Column | Description |
| --- | --- |
| `ts`, `date` | bar timestamp and trading date |
| `strike`, `opt_type` | strike price and `CE` / `PE` |
| `open`, `close` | option prices |
| `spot` | NIFTY spot at that minute |
| `oi` | open interest (used for the put/call ratio) |
| `offset` | strike distance from ATM in steps, -10 to +10 |
| `expiry`, `dte` | nearest weekly expiry and calendar days to it |
| `lot_size` | optional; taken from the bhavcopy file if missing |

Days with fewer than 300 bars are skipped.

## Assumptions

- Signals are read on a bar's close and filled at the next bar's open. No entries after 14:30, and everything is closed at 15:15.
- Slippage is the larger of 0.25 points or 0.5% of premium on every fill.
- Charges: ₹20 brokerage per order, STT, NSE transaction charges, SEBI fees, stamp duty and GST, as set in [`backtest/config.py`](backtest/config.py). Check STT against current rates.
- Each trade risks 2% of the strategy's equity times the rule's risk multiplier, capped at 20 lots, and equity compounds.
- No overnight positions, so drawdowns are measured on daily closing equity.
