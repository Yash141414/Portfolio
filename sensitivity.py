"""How much do the results depend on slippage and fill assumptions, by day type?

    python sensitivity.py

Runs the frozen rules on the in-sample period and the holdout under a range of slippage and fill
assumptions, and reports net P&L per strategy and day type (far / DTE 1 / expiry). Also finds each
strategy's break-even slippage for its DTE 0 + DTE 1 trades, where the risk multipliers put most of the book.
"""
import argparse
from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from backtest import variant_log  # noqa: E402
from backtest.data import load_days  # noqa: E402
from backtest.frozen import load_frozen  # noqa: E402
from backtest.metrics import inr, summary  # noqa: E402
from backtest.report import COLORS, _md  # noqa: E402
from run_backtest import evaluate  # noqa: E402

PERIODS = {
    "in-sample": ("data/nifty_opt_1min_2y.parquet", "2025-09-01", "2026-10-16"),
    "holdout": ("data/dhan_2023_2025/nifty_opt_1min.parquet", "2024-01-01", "2025-08-31"),
}
SLIP_PCT = [0.0, 0.0025, 0.005, 0.01, 0.015, 0.02]
SLIP_PTS = [0.25, 0.5, 1.0, 2.0]
FILLS = [("next open", "open", 0), ("next close", "close", 0), ("open +1 bar", "open", 1), ("open +2 bars", "open", 2)]
BASE = ("slippage", "max(0.25 pts, 0.50%)")
DT = {0: "expiry", 1: "DTE 1"}


def fresh(s):
    """A new copy of a strategy: RuleStrategy keeps the previous day's close between days, so reusing an
    object across runs would carry the last run's final close into the next run's first day."""
    return type(s)(**s.rules)


def scenarios(cfg):
    """(group, label, config) for every assumption tested; each group varies one thing from the base."""
    c = cfg.costs
    for p in SLIP_PCT:
        yield "slippage %", f"max(0.25 pts, {p:.2%})", replace(cfg, costs=replace(c, slippage_pct=p))
    for p in SLIP_PTS:
        yield "slippage floor", f"max({p} pts, 0.50%)", replace(cfg, costs=replace(c, slippage_pts=p))
    for label, field, delay in FILLS:
        yield "fill", label, replace(cfg, fill_field=field, fill_delay=delay)


def run_all(strategies, days, dates, cfg) -> pd.DataFrame:
    """Net P&L per strategy and day type, plus overall Sharpe, under one set of assumptions."""
    rows = []
    for s in strategies:
        tr, eq = evaluate(fresh(s), days, dates, cfg)
        st = summary(eq, tr, cfg.capital_per_strategy)
        dt = tr["dte"].map(lambda d: DT.get(d, "far")) if len(tr) else pd.Series(dtype=str)
        pnl = tr.groupby(dt)["pnl"].sum() if len(tr) else pd.Series(dtype=float)
        rows.append({"strategy": s.name, "expiry": pnl.get("expiry", 0.0), "DTE 1": pnl.get("DTE 1", 0.0),
                     "far": pnl.get("far", 0.0), "total": tr["pnl"].sum() if len(tr) else 0.0,
                     "sharpe": st["sharpe"], "cagr": st["cagr"], "mdd": st["mdd"]})
    return pd.DataFrame(rows)


def breakeven(strategy, days, dates, cfg, hi=0.05, tol=0.0005) -> float | None:
    """Slippage % (with the 0.25-pt floor) at which the strategy's DTE 0 + DTE 1 net P&L reaches zero."""
    def near_expiry(p):
        tr, _ = evaluate(fresh(strategy), days, dates, replace(cfg, costs=replace(cfg.costs, slippage_pct=p)))
        return tr.loc[tr["dte"] <= 1, "pnl"].sum()
    if near_expiry(0.0) <= 0:
        return 0.0
    lo = 0.0
    if near_expiry(hi) > 0:
        return None
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if near_expiry(mid) > 0 else (lo, mid)
    return (lo + hi) / 2


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frozen", default="frozen/rules_v1.json")
    ap.add_argument("--out", default="out_of_sample/sensitivity")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    strategies, cfg, _ = load_frozen(a.frozen)

    results, bes = [], []
    for period, (data, start, end) in PERIODS.items():
        days = load_days(Path(data), start, end)
        dates = pd.DatetimeIndex([d.date for d in days])
        print(f"{period}: {len(days)} days")
        variant_log.set_context(purpose="sensitivity", data=data, note=period)
        for group, label, c in scenarios(cfg):
            df = run_all(strategies, days, dates, c)
            df.insert(0, "assumption", label)
            df.insert(0, "group", group)
            df.insert(0, "period", period)
            results.append(df)
            print(f"  {group:15s} {label:22s} near-expiry P&L "
                  f"{inr(df['expiry'].sum() + df['DTE 1'].sum()):>12s}")
        for s in strategies:
            be = breakeven(s, days, dates, cfg)
            bes.append({"period": period, "strategy": s.name,
                        "break-even slippage (DTE 0 + DTE 1)": "already negative at 0%" if be == 0.0 else
                        ("above 5%" if be is None else f"{be:.2%} of premium per fill")})
    res = pd.concat(results, ignore_index=True)
    res.to_csv(out / "sensitivity.csv", index=False)
    be = pd.DataFrame(bes)
    be.to_csv(out / "breakeven.csv", index=False)

    # chart: DTE 0 + DTE 1 net P&L against slippage %, per strategy, both periods
    sl = res[res["group"] == "slippage %"].copy()
    sl["pct"] = sl["assumption"].str.extract(r"([\d.]+)%\)").astype(float)
    sl["near"] = (sl["expiry"] + sl["DTE 1"]) / 1e5
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, (period, g) in zip(axes, sl.groupby("period", sort=False)):
        for name, h in g.groupby("strategy", sort=False):
            ax.plot(h["pct"], h["near"], marker="o", color=COLORS.get(name), label=name)
        ax.axhline(0, color="#999", lw=0.8)
        ax.axvline(0.5, color="#bbb", lw=0.8, ls="--")
        ax.set_title(f"{period}: DTE 0 + DTE 1 net P&L")
        ax.set_xlabel("slippage, % of premium per fill (base 0.5%)")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Rs lakh")
    axes[0].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out / "slippage_near_expiry.png", dpi=130)
    plt.close(fig)

    s = ["# Slippage and fill sensitivity\n",
         "Frozen rules (`frozen/rules_v1.json`). Each group changes one assumption from the base "
         "(slippage max(0.25 pts, 0.5%) per fill, fill at the next bar's open). Net P&L in Rs; "
         "'expiry' = DTE 0, 'far' = 2+ days to expiry.\n",
         "![Near-expiry P&L vs slippage](slippage_near_expiry.png)\n",
         "## Break-even slippage for DTE 0 + DTE 1 trades\n", _md(be.set_index("period"))]
    for period in PERIODS:
        for group in res["group"].unique():
            g = res[(res["period"] == period) & (res["group"] == group)].copy()
            g["near expiry"] = g["expiry"] + g["DTE 1"]
            tbl = g.pivot_table(index="assumption", columns="strategy", values="near expiry", sort=False)
            tbl["Combined"] = tbl.sum(axis=1)
            sh = g.pivot_table(index="assumption", columns="strategy", values="sharpe", sort=False)
            s += [f"\n## {period}: {group}\n", "DTE 0 + DTE 1 net P&L (Rs)\n", _md(tbl.map(inr)),
                  "\nOverall Sharpe (all day types)\n", _md(sh.round(2))]
    s += ["\n## Full detail\n", "Every scenario, strategy and day type is in `sensitivity.csv`.\n"]
    (out / "report.md").write_text("\n".join(s), encoding="utf-8")
    print(f"report -> {out / 'report.md'}")


if __name__ == "__main__":
    main()
