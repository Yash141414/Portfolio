"""Track the frozen rules on days after the in-sample period, as the data comes in.

    python paper_trading.py
    python paper_trading.py --data data/nifty_opt_1min_merged.parquet --fills paper_trading/fills.csv

Replays the frozen rules (frozen/rules_v1.json) on every day after the last in-sample date (16 Oct 2026) in --data.
The last in-sample day is loaded too, only so the first day has a previous close. Re-run it whenever the data file
is extended: results are rebuilt from scratch each time, so nothing is appended by hand.

If --fills exists (columns: date, strategy, pnl, with pnl net of charges in Rs), the actual paper-trade P&L is
shown next to the replay so that slippage and missed trades show up.
"""
import argparse
from pathlib import Path

import pandas as pd

from backtest import variant_log
from backtest.data import load_days
from backtest.frozen import load_frozen
from backtest.metrics import daily_equity, inr
from backtest.report import _md
from holdout_test import DAY_TYPE
from run_backtest import evaluate


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frozen", default="frozen/rules_v1.json")
    ap.add_argument("--data", default="data/nifty_opt_1min_merged.parquet")
    ap.add_argument("--fills", default="paper_trading/fills.csv")
    ap.add_argument("--out", default="paper_trading")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    strategies, cfg, snap = load_frozen(a.frozen)
    last = pd.Timestamp(snap["last_insample_date"])
    days = load_days(Path(a.data), last)
    live = [d for d in days if d.date > last]
    if not live:
        raise SystemExit(f"no data after {last.date()} in {a.data}")
    dates = pd.DatetimeIndex([d.date for d in live])

    variant_log.set_context(purpose="paper-trading", data=a.data, note=f"frozen {a.frozen}")
    all_tr = []
    for s in strategies:
        tr, _ = evaluate(s, days, pd.DatetimeIndex([d.date for d in days]), cfg)
        all_tr.append(tr[tr["date"] > last])
    tr = pd.concat(all_tr, ignore_index=True)
    tr["day_type"] = tr["dte"].map(lambda x: DAY_TYPE["exp" if x == 0 else "dte1" if x == 1 else "far"])
    tr.to_csv(out / "trades.csv", index=False)
    cap = cfg.capital_per_strategy * len(strategies)
    eq = daily_equity(tr, dates, cap)

    daily = tr.pivot_table(index="date", columns="strategy", values="pnl", aggfunc="sum").reindex(dates).fillna(0)
    daily["Combined"] = daily.sum(axis=1)
    daily.insert(0, "day type", [DAY_TYPE["exp" if d.dte == 0 else "dte1" if d.dte == 1 else "far"] for d in live])
    cum = daily.drop(columns="day type").sum()
    daily.index = daily.index.strftime("%Y-%m-%d (%a)")
    by_type = tr.pivot_table(index="day_type", columns="strategy", values="pnl", aggfunc="sum").fillna(0)
    by_type["Combined"] = by_type.sum(axis=1)
    counts = pd.Series([DAY_TYPE["exp" if d.dte == 0 else "dte1" if d.dte == 1 else "far"] for d in live]).value_counts()

    fills = Path(a.fills)
    vs = None
    if fills.exists():
        f = pd.read_csv(fills, parse_dates=["date"])
        vs = pd.DataFrame({"replay": tr.groupby(["date", "strategy"])["pnl"].sum(),
                           "paper fills": f.groupby(["date", "strategy"])["pnl"].sum()}).fillna(0)
        vs["difference"] = vs["paper fills"] - vs["replay"]
        vs = vs.map(inr)

    fmt = lambda df: df.map(lambda v: inr(v) if isinstance(v, float) else v)  # noqa: E731
    s = [f"# Paper trading: frozen rules from {dates[0].date()} to {dates[-1].date()}\n",
         f"**Preliminary.** {len(live)} trading days ({', '.join(f'{v} {k}' for k, v in counts.items())}). "
         "That is far too few to say anything about the edge; the rules make most of their money on DTE 1 days, "
         "which come once a week. Treat this as a check that the rules run as specified, and keep extending it.\n",
         f"Rules: `{a.frozen}` (frozen {snap['frozen_at']}), unchanged. Data: `{a.data}`. Capital Rs 10 lakh per "
         "strategy, starting fresh on the first day after the in-sample period.\n",
         "## Cumulative net P&L (Rs)\n", _md(fmt(cum.to_frame("net P&L").T)),
         f"\nCombined return so far: {eq['equity'].iloc[-1] / cap - 1:+.2%}\n",
         "\n## By day\n", _md(fmt(daily)),
         "\n## By day type\n", _md(fmt(by_type)),
         "\n## Trades\n", _md(tr[["date", "strategy", "day_type", "legs", "lots", "entry_ts", "exit_ts", "reason",
                                  "pnl"]].assign(pnl=tr["pnl"].map(inr), date=tr["date"].dt.strftime("%Y-%m-%d"))
                               .set_index("date")),
         "\n## Replay vs actual paper fills\n",
         _md(vs) if vs is not None else f"(no `{fills}` yet; add the paper-trade P&L there to compare)", ""]
    (out / "report.md").write_text("\n".join(s), encoding="utf-8")
    print(f"{len(live)} days, {len(tr)} trades, combined {inr(cum['Combined'])} -> {out / 'report.md'}")


if __name__ == "__main__":
    main()
