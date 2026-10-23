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

Run on `data/nifty_opt_1min_2y.parquet` from 1 Sep 2025 to 16 Oct 2026 (278 trading days), with ₹10 lakh per strategy:

| | CAGR | Sharpe | Max drawdown | Calmar |
| --- | --- | --- | --- | --- |
| Mean Reversion | 52.7% | 1.74 | -9.9% | 5.33 |
| Directional | 33.2% | 1.58 | -12.8% | 2.60 |
| Semi-Directional | 26.8% | 2.26 | -4.4% | 6.12 |
| **Combined (₹30L)** | **37.6%** | **2.31** | **-7.3%** | **5.12** |

**These results are in-sample.** The rules were chosen on this same period, with the requirement that every strategy is profitable in both halves of the year and the combined Calmar is at least 5. All variants in the robustness grid and stress test stayed profitable. Even so, treat the numbers as a description of this period rather than a forecast. About 91% of the profit came on the last two days of each expiry week.

## Project layout

```
run_backtest.py          entry point: runs all strategies, the combined book, and writes the report
backtest/
  config.py              capital, sizing limits, session times, brokerage and statutory charges
  data.py                loads the parquet into per-day bar/strike matrices
  engine.py              order fills, slippage, charges, position sizing
  strategies.py          the three rule-based strategies
  metrics.py             equity curves, Sharpe (with confidence interval), drawdown, trade stats
  report.py              charts and the Markdown report
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
