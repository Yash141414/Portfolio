# Paper trading: frozen rules from 2026-10-19 to 2026-10-22

**Preliminary.** 3 trading days (2 far (2+ days), 1 expiry (DTE 0)). That is far too few to say anything about the edge; the rules make most of their money on DTE 1 days, which come once a week. Treat this as a check that the rules run as specified, and keep extending it.

Rules: `frozen/rules_v1.json` (frozen 2026-10-24 00:35:14), unchanged. Data: `data/nifty_opt_1min_merged.parquet`. Capital Rs 10 lakh per strategy, starting fresh on the first day after the in-sample period.

## Cumulative net P&L (Rs)

|  | Directional | Mean Reversion | Semi-Directional | Combined |
|---|---|---|---|---|
| net P&L | 11,887 | -22,371 | -12,669 | -23,153 |

Combined return so far: -0.77%


## By day

|  | day type | Directional | Mean Reversion | Semi-Directional | Combined |
|---|---|---|---|---|---|
| 2026-10-19 (Mon) | expiry (DTE 0) | -10,380 | -12,283 | -9,162 | -31,825 |
| 2026-10-21 (Wed) | far (2+ days) | 22,119 | -7,611 | -3,022 | 11,485 |
| 2026-10-22 (Thu) | far (2+ days) | 148 | -2,477 | -485 | -2,813 |

## By day type

| day_type | Directional | Mean Reversion | Semi-Directional | Combined |
|---|---|---|---|---|
| expiry (DTE 0) | -10,380 | -12,283 | -9,162 | -31,825 |
| far (2+ days) | 22,267 | -10,088 | -3,507 | 8,672 |

## Trades

| date | strategy | day_type | legs | lots | entry_ts | exit_ts | reason | pnl |
|---|---|---|---|---|---|---|---|---|
| 2026-10-19 | Mean Reversion | expiry (DTE 0) | +23050CE -23350CE | 5 | 2026-10-19 10:00:00 | 2026-10-19 12:00:00 | time exit | -12,283 |
| 2026-10-21 | Mean Reversion | far (2+ days) | +23000CE | 1 | 2026-10-21 10:00:00 | 2026-10-21 15:15:00 | square-off | -7,611 |
| 2026-10-22 | Mean Reversion | far (2+ days) | +22650PE | 1 | 2026-10-22 10:00:00 | 2026-10-22 15:15:00 | square-off | -2,477 |
| 2026-10-19 | Directional | expiry (DTE 0) | -23100PE +22850PE | 1 | 2026-10-19 09:55:00 | 2026-10-19 15:15:00 | square-off | -10,380 |
| 2026-10-21 | Directional | far (2+ days) | +23000PE | 2 | 2026-10-21 10:00:00 | 2026-10-21 15:15:00 | square-off | 22,119 |
| 2026-10-22 | Directional | far (2+ days) | +22650CE | 1 | 2026-10-22 10:00:00 | 2026-10-22 15:15:00 | square-off | 148 |
| 2026-10-19 | Semi-Directional | expiry (DTE 0) | -23050PE +22800PE | 5 | 2026-10-19 10:00:00 | 2026-10-19 12:00:00 | time exit | -9,162 |
| 2026-10-21 | Semi-Directional | far (2+ days) | -23000PE +22850PE | 1 | 2026-10-21 09:30:00 | 2026-10-21 12:00:00 | time exit | -3,022 |
| 2026-10-22 | Semi-Directional | far (2+ days) | -22700CE +22850CE | 1 | 2026-10-22 09:30:00 | 2026-10-22 12:00:00 | time exit | -485 |

## Replay vs actual paper fills

(no `paper_trading\fills.csv` yet; add the paper-trade P&L there to compare)
