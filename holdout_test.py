"""Run the frozen rules, unchanged, on data not used to select them, and report the results separately.

    python holdout_test.py
    python holdout_test.py --data data/dhan_2023_2025/nifty_opt_1min.parquet --start 2024-01-01 --end 2025-08-31

Rules, sizing and costs come from the frozen snapshot (frozen/rules_v1.json), not from the current code.
"""
import argparse
import time as clock
from pathlib import Path

import pandas as pd

from backtest import variant_log
from backtest.data import load_days
from backtest.frozen import load_frozen
from backtest.metrics import daily_equity, inr, summary, table
from backtest.report import _md, breakdown, monthly_returns, plot_equity, plot_single
from backtest.strategies import day_type
from run_backtest import evaluate

SEARCH = Path("data/dhan_2023_2025/search/scores.csv")
INSAMPLE_STATS = Path("results/stats.csv")
DAY_TYPE = {"far": "far (2+ days)", "dte1": "DTE 1", "exp": "expiry (DTE 0)"}


def period_stats(curves, trades, capitals, periods) -> pd.DataFrame:
    """Stats for each strategy over each sub-period, each starting from the equity it had on entering it."""
    rows = {}
    for name, eq in curves.items():
        tr = trades if name == "Combined" else trades[trades["strategy"] == name]
        for label, (a, b) in periods.items():
            mask = (eq.index >= a) & (eq.index <= b)
            if not mask.any():
                continue
            before = eq["equity"][eq.index < a]
            base = before.iloc[-1] if len(before) else capitals[name]
            t = tr[tr["date"].isin(eq.index[mask])]
            e = daily_equity(t, eq.index[mask], base)
            st = summary(e, t, base)
            rows[f"{name} {label}"] = {k: st[k] for k in ("total_return", "cagr", "sharpe", "sharpe_lo", "sharpe_hi",
                                                          "mdd", "calmar")} | \
                {"trades": st.get("trades", 0), "win_rate": st.get("win_rate", float("nan"))}
    return table(rows).T


def search_ranks(strategies) -> pd.DataFrame:
    """Where each frozen rule ranked (by t-stat, within its day type) in the 2023-2025 search."""
    s = pd.read_csv(SEARCH)
    s["rank"] = s.groupby("dtype")["t"].rank(ascending=False, method="min").astype(int)
    size = s.groupby("dtype").size()
    rows = []
    for strat in strategies:
        for dt, spec in strat.rules.items():
            for r in (spec if isinstance(spec, tuple) else (spec,)):
                m = s[(s.dtype == dt) & (s.ref == r.ref) & (s["mode"] == r.mode) & (s.sig == f"{r.sig_t:%H:%M:%S}")
                      & (s.kind == r.kind) & (s.exit == f"{r.exit_t:%H:%M:%S}") & (s.stop == r.stop)]
                rule = f"{r.ref} {r.mode} {r.sig_t:%H:%M} {r.kind} exit {r.exit_t:%H:%M} stop {r.stop}"
                if len(m):
                    x = m.iloc[0]
                    rows.append([strat.name, DAY_TYPE[dt], rule, f"{x['rank']} of {size[dt]}", f"{x.t:.2f}",
                                 inr(x.y2024), inr(x.y2025)])
                else:
                    rows.append([strat.name, DAY_TYPE[dt], rule, "not in search", "", "", ""])
    df = pd.DataFrame(rows, columns=["strategy", "day type", "rule", "rank (by t)", "t-stat",
                                     "search P&L 2024 (Rs)", "search P&L 2025 (Rs)"]).set_index("strategy")
    return df


def compare_insample(stats: dict) -> pd.DataFrame | None:
    if not INSAMPLE_STATS.exists():
        return None
    ins = pd.read_csv(INSAMPLE_STATS, index_col=0)
    out = table(stats)
    keys = ["CAGR", "Sharpe", "Sharpe 95% CI low", "Sharpe 95% CI high", "Max drawdown", "Calmar", "Win rate",
            "Profit factor"]
    rows = {}
    for k in keys:
        if k in ins.index and k in out.index:
            for name in out.columns:
                rows.setdefault(name, {})[f"{k}: in-sample"] = ins.loc[k, name]
                rows[name][f"{k}: holdout"] = out.loc[k, name]
    return pd.DataFrame(rows)


def regime(days) -> pd.DataFrame:
    d = pd.DataFrame({"date": [x.date for x in days], "expiry": [x.expiry for x in days], "lot": [x.lot for x in days]})
    d["period"] = d["date"].dt.to_period("Q").astype(str)
    g = d.groupby("period")
    return pd.DataFrame({"days": g.size(), "lot size": g["lot"].agg(lambda s: "/".join(map(str, sorted(s.unique())))),
                         "expiry weekday": g["expiry"].agg(
                             lambda s: ", ".join(sorted(s.drop_duplicates().dt.day_name().str[:3].unique())))})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frozen", default="frozen/rules_v1.json")
    ap.add_argument("--data", default="data/dhan_2023_2025/nifty_opt_1min.parquet")
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2025-08-31")
    ap.add_argument("--out", default="out_of_sample/holdout_2024-01_2025-08")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    strategies, cfg, snap = load_frozen(a.frozen)
    if pd.Timestamp(a.end) >= pd.Timestamp("2025-09-01"):
        print("warning: the window overlaps the in-sample period (from 2025-09-01)")
    t0 = clock.time()
    days = load_days(Path(a.data), a.start, a.end)
    dates = pd.DatetimeIndex([d.date for d in days])
    all_dates = pd.read_parquet(a.data, columns=["date"])["date"].drop_duplicates()
    all_dates = all_dates[(all_dates >= a.start) & (all_dates <= a.end)].sort_values()
    skipped = sorted(set(all_dates) - set(dates))
    print(f"{len(days)} days loaded ({dates[0].date()} -> {dates[-1].date()}), {len(skipped)} skipped, "
          f"{clock.time() - t0:.0f}s")

    variant_log.set_context(purpose="holdout", data=a.data, note=f"frozen {a.frozen}")
    curves, stats, capitals, all_trades = {}, {}, {}, []
    for strat in strategies:
        tr, eq = evaluate(strat, days, dates, cfg)
        curves[strat.name], capitals[strat.name] = eq, cfg.capital_per_strategy
        stats[strat.name] = summary(eq, tr, cfg.capital_per_strategy)
        all_trades.append(tr)
        print(f"{strat.name:17s} trades {len(tr):4d}  sharpe {stats[strat.name]['sharpe']:6.2f}  "
              f"cagr {stats[strat.name]['cagr']:+.1%}  mdd {stats[strat.name]['mdd']:.1%}")
    trades = pd.concat(all_trades, ignore_index=True)
    trades["day_type"] = trades["dte"].map(lambda x: DAY_TYPE[day_type(type("D", (), {"dte": x})())])
    cap = cfg.capital_per_strategy * len(strategies)
    curves["Combined"], capitals["Combined"] = daily_equity(trades, dates, cap), cap
    stats["Combined"] = summary(curves["Combined"], trades, cap)
    print(f"{'Combined':17s} trades {len(trades):4d}  sharpe {stats['Combined']['sharpe']:6.2f}  "
          f"cagr {stats['Combined']['cagr']:+.1%}  mdd {stats['Combined']['mdd']:.1%}")

    years = {str(y): (pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y}-12-31")) for y in sorted(dates.year.unique())}
    by_year = period_stats(curves, trades, capitals, years)
    by_type = breakdown(trades, "day_type")
    share = trades.pivot_table(index="day_type", columns="strategy", values="pnl", aggfunc="sum")
    share["Combined"] = share.sum(axis=1)
    share = share.map(inr)
    share.index.name = "net P&L by day type (Rs)"
    corr = pd.DataFrame({n: c["ret"] for n, c in curves.items() if n != "Combined"}).corr().round(2)
    ranks = search_ranks(strategies) if SEARCH.exists() else None
    vs = compare_insample(stats)

    plot_equity(curves, capitals, out / "equity_curves.png")
    for name, eq in curves.items():
        if name != "Combined":
            plot_single(name, eq, capitals[name], out / f"{name.lower().replace('-', '_').replace(' ', '_')}.png")
    trades.to_csv(out / "trades.csv", index=False)
    pd.concat(curves, axis=1).to_csv(out / "daily_equity.csv")
    table(stats).to_csv(out / "stats.csv")
    by_year.to_csv(out / "stats_by_year.csv")

    s = [f"# Holdout test: frozen rules on {dates[0].date()} to {dates[-1].date()}\n",
         f"Data: `{a.data}` | {len(days)} trading days | Frozen snapshot: `{a.frozen}` "
         f"(frozen {snap['frozen_at']}, commit {snap['git_commit'][:7]}, last in-sample date "
         f"{snap['last_insample_date']})\n",
         "Rules, sizing and costs are taken from the snapshot and were not changed for this run.\n",
         "## Performance\n", _md(table(stats)), "\n![Equity curves](equity_curves.png)\n",
         "## By calendar year\n", _md(by_year),
         "\n## By day type\n", _md(by_type), "\n", _md(share),
         "\n## Holdout vs in-sample\n",
         _md(vs) if vs is not None else "(results/stats.csv not found)",
         "\n## Correlation of daily returns\n", _md(corr),
         "\n## Monthly returns\n", _md(monthly_returns(curves)),
         "\n## Exit reasons\n", _md(breakdown(trades, "reason")),
         "\n## Where the frozen rules ranked in the 2023-2025 search\n",
         "Rank by t-statistic among the candidates for the same day type in "
         "`data/dhan_2023_2025/search/scores.csv`. That search covered this data, so this window is a holdout "
         "for the final rules but not data nobody has looked at.\n",
         _md(ranks) if ranks is not None else "(search file not found)",
         "\n## Market regime in the window\n", _md(regime(days)),
         f"\n## Skipped days\n{len(skipped)} days with fewer than 300 one-minute bars: "
         f"{', '.join(str(d.date()) for d in skipped) or 'none'}\n"]
    (out / "report.md").write_text("\n".join(s), encoding="utf-8")
    print(f"report -> {out / 'report.md'}")


if __name__ == "__main__":
    main()
