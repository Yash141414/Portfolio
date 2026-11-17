"""Is there a structural reason the frozen rules work in-sample (Sep 2025 - Oct 2026) but not before?

    python structural_break.py

The in-sample period starts exactly when NIFTY weekly expiry moved from Thursday to Tuesday (Sep 2025), and lot
sizes changed from 25 to 75 (Nov-Dec 2024) and 75 to 65 (Dec 2025). This script checks which of these, if any,
explains the break:

1. contract specs by period (expiry weekday, weekday of DTE 1, lot size)
2. the frozen rules re-run with every day's lot size replaced, to remove the lot-size effect
3. holdout split at SEBI's 20 Nov 2024 F&O changes, and in-sample split at the 75 -> 65 lot change
4. P&L by weekday and day type
5. rule-free: what a long ATM straddle bought at the DTE 1 / expiry signal times made in each period, i.e. whether
   options near expiry were cheap or dear relative to the moves that followed
6. realised volatility and overnight gaps by quarter

Rules, sizing and costs come from frozen/rules_v1.json.
"""
import argparse
from dataclasses import replace
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import variant_log
from backtest.data import load_days
from backtest.frozen import load_frozen
from backtest.metrics import daily_equity, inr, summary
from backtest.report import _md
from holdout_test import DAY_TYPE, period_stats
from run_backtest import evaluate

PERIODS = {
    "holdout": ("data/dhan_2023_2025/nifty_opt_1min.parquet", "2023-01-01", "2025-08-31"),
    "in-sample": ("data/nifty_opt_1min_2y.parquet", "2025-09-01", "2026-10-16"),
}
WD = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def run_book(frozen, days, lot=None):
    """Frozen rules over days (optionally with every day's lot size replaced); returns trades and curves."""
    strategies, cfg, _ = load_frozen(frozen)
    if lot:
        days = [replace(d, lot=lot) for d in days]
    dates = pd.DatetimeIndex([d.date for d in days])
    curves, all_tr = {}, []
    for s in strategies:
        tr, eq = evaluate(s, days, dates, cfg)
        curves[s.name] = eq
        all_tr.append(tr)
    tr = pd.concat(all_tr, ignore_index=True)
    tr["day_type"] = tr["dte"].map(lambda x: DAY_TYPE["exp" if x == 0 else "dte1" if x == 1 else "far"])
    cap = cfg.capital_per_strategy * len(strategies)
    curves["Combined"] = daily_equity(tr, dates, cap)
    return tr, curves, cfg


def headline(tr, curves, cfg) -> dict:
    out = {}
    for name, eq in curves.items():
        cap = cfg.capital_per_strategy * (3 if name == "Combined" else 1)
        t = tr if name == "Combined" else tr[tr["strategy"] == name]
        st = summary(eq, t, cap)
        out[name] = f"{st['cagr']:+.1%} / {st['sharpe']:.2f}"
    return out


def specs(days) -> pd.DataFrame:
    d = pd.DataFrame({"date": [x.date for x in days], "expiry": [x.expiry for x in days],
                      "dte": [x.dte for x in days], "lot": [x.lot for x in days]})
    d["q"] = d["date"].dt.to_period("Q").astype(str)
    g = d.groupby("q")
    dte1 = d[d.dte == 1]
    return pd.DataFrame({
        "days": g.size(),
        "lot size": g["lot"].agg(lambda s: "/".join(map(str, sorted(s.unique())))),
        "expiry weekday (most common)": g["expiry"].agg(lambda s: s.drop_duplicates().dt.day_name().mode().iat[0][:3]),
        "DTE 1 days": dte1.groupby("q").size(),
        "DTE 1 weekday": dte1.groupby("q")["date"].agg(lambda s: ", ".join(
            f"{k} {v}" for k, v in s.dt.day_name().str[:3].value_counts().items())),
    }).fillna({"DTE 1 days": 0})


def straddles(days, label) -> pd.DataFrame:
    """Long ATM straddle bought at the DTE 1 / expiry signal time and sold at the rule's exit, per day, rule-free.

    ret = value at exit / cost - 1. Positive on average means options were cheap for the move that followed
    (good for the long-option rules, bad for the credit spreads)."""
    windows = {1: (time(10, 20), time(15, 15)), 0: (time(10, 0), time(12, 0))}
    rows, prev = [], None
    for d in days:
        pc, prev = prev, d.spot[-1]
        if d.dte not in windows:
            continue
        a, b = windows[d.dte]
        i, j = d.bar_at(a) - 1, min(d.bar_at(b), d.n - 1)
        if i < 0:
            continue
        k = d.strike(i, "CE", 0, 50)
        cost = d.px(i, "CE", k) + d.px(i, "PE", k)
        val = d.px(j, "CE", k) + d.px(j, "PE", k)
        if not (np.isfinite(cost) and np.isfinite(val)) or cost <= 0:
            continue
        rows.append({"period": label, "date": d.date, "dte": d.dte, "weekday": WD[d.date.weekday()],
                     "straddle % spot": cost / d.spot[i], "ret": val / cost - 1,
                     "move / straddle": abs(d.spot[j] - d.spot[i]) / cost,
                     "gap %": abs(d.spot[0] / pc - 1) if pc else np.nan})
    return pd.DataFrame(rows)


def vol_by_quarter(days, tr) -> pd.DataFrame:
    close = pd.Series([d.spot[-1] for d in days], index=pd.DatetimeIndex([d.date for d in days]))
    opn = pd.Series([d.spot[0] for d in days], index=close.index)
    rng = pd.Series([(d.spot.max() - d.spot.min()) / d.spot[0] for d in days], index=close.index)
    r = np.log(close).diff()
    q = close.index.to_period("Q").astype(str)
    pnl = tr.groupby(tr["date"].dt.to_period("Q").astype(str))["pnl"].sum()
    df = pd.DataFrame({"realised vol (ann.)": r.groupby(q).std() * np.sqrt(250),
                       "avg intraday range": rng.groupby(q).mean(),
                       "avg overnight gap (abs)": (opn / close.shift(1) - 1).abs().groupby(q).mean()})
    df["combined P&L (Rs)"] = pnl
    return df


def flat(df: pd.DataFrame) -> pd.DataFrame:
    """Readable row labels for Markdown: ('holdout', 'DTE 1') -> 'holdout / DTE 1'."""
    if isinstance(df.index, pd.MultiIndex):
        df = df.copy()
        df.index = [" / ".join(map(str, i)) for i in df.index]
    return df


def pct(x):
    return f"{x:+.1%}" if np.isfinite(x) else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frozen", default="frozen/rules_v1.json")
    ap.add_argument("--out", default="structural_break")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    variant_log.set_context(purpose="structural-break", data="holdout+in-sample", note=f"frozen {a.frozen}")

    days, base = {}, {}
    for p, (path, s, e) in PERIODS.items():
        days[p] = load_days(Path(path), s, e)
        base[p] = run_book(a.frozen, days[p])
        print(f"{p}: {len(days[p])} days, {len(base[p][0])} trades")

    # 1. specs
    spec = pd.concat({p: specs(days[p]) for p in PERIODS})

    # 2. lot-size counterfactual
    lot_rows = {}
    for p in PERIODS:
        lot_rows[f"{p}, actual lot sizes"] = headline(*base[p])
        for lot in (25, 50, 65, 75):
            lot_rows[f"{p}, all days lot {lot}"] = headline(*run_book(a.frozen, days[p], lot))
            print(f"  {p} lot {lot} done")
    lots = pd.DataFrame(lot_rows).T
    lots.index.name = "CAGR / Sharpe"

    # 3. sub-periods at the spec changes
    subs = {
        "holdout": {"2023-01 to 2024-11-19 (before SEBI changes)": ("2023-01-01", "2024-11-19"),
                    "2024-11-20 to 2025-08 (after SEBI changes, lot 75, Thu expiry)": ("2024-11-20", "2025-08-31")},
        "in-sample": {"2025-09 to 2025-12 (lot 75, Tue expiry)": ("2025-09-01", "2025-12-31"),
                      "2026-01 to 2026-10 (lot 65, Tue expiry)": ("2026-01-01", "2026-10-16")},
    }
    sub_tables = []
    for p, per in subs.items():
        tr, curves, cfg = base[p]
        caps = {n: cfg.capital_per_strategy * (3 if n == "Combined" else 1) for n in curves}
        ps = period_stats(curves, tr, caps, {k: tuple(map(pd.Timestamp, v)) for k, v in per.items()})
        sub_tables.append(ps[[c for c in ps.columns if c in ("CAGR", "Sharpe", "Max drawdown", "Trades")]])
    sub = pd.concat(sub_tables)

    # 4. weekday x day type
    wd_tables = {}
    for p in PERIODS:
        tr = base[p][0].copy()
        tr["weekday"] = tr["date"].dt.weekday.map(dict(enumerate(WD)))
        wd_tables[p] = tr.pivot_table(index="day_type", columns="weekday", values="pnl", aggfunc="sum").reindex(
            columns=[w for w in WD if w in set(tr["weekday"])]).map(lambda v: inr(v) if pd.notna(v) else "")
    by_wd = pd.concat(wd_tables)

    # 5. rule-free straddle test
    st = pd.concat([straddles(days[p], p) for p in PERIODS], ignore_index=True)
    st.to_csv(out / "straddles.csv", index=False)
    st["regime"] = np.where(st["date"] >= "2025-09-01", "Tue expiry", "Thu expiry")
    st["day"] = st["dte"].map({1: "DTE 1 (10:20 -> 15:15)", 0: "expiry (10:00 -> 12:00)"})
    g = st.groupby(["day", "period", st["date"].dt.year.rename("year")])
    strad = pd.DataFrame({"days": g.size(), "straddle % of spot": g["straddle % spot"].mean().map("{:.2%}".format),
                          "avg long-straddle return": g["ret"].mean().map(pct),
                          "median": g["ret"].median().map(pct),
                          "share of days > 0": g["ret"].apply(lambda s: (s > 0).mean()).map("{:.0%}".format),
                          "move / straddle cost": g["move / straddle"].mean().round(2)})
    gap = st[st.dte == 1].groupby(["period", "weekday"]).agg(days=("ret", "size"),
                                                              avg_gap=("gap %", "mean"),
                                                              straddle_ret=("ret", "mean"))
    gap["avg_gap"] = gap["avg_gap"].map("{:.2%}".format)
    gap["straddle_ret"] = gap["straddle_ret"].map(pct)
    gap.columns = ["DTE 1 days", "avg overnight gap (abs)", "avg long-straddle return"]

    # 6. volatility by quarter
    vol = pd.concat({p: vol_by_quarter(days[p], base[p][0]) for p in PERIODS})
    vol = vol.assign(**{c: vol[c].map("{:.1%}".format) for c in vol.columns[:1]},
                     **{c: vol[c].map("{:.2%}".format) for c in vol.columns[1:3]},
                     **{"combined P&L (Rs)": vol["combined P&L (Rs)"].map(inr)})

    for name, df in {"specs": spec, "lot_counterfactual": lots, "subperiods": sub, "pnl_by_weekday": by_wd,
                     "straddle_test": strad, "dte1_gap": gap, "vol_by_quarter": vol}.items():
        df.to_csv(out / f"{name}.csv")
    s = ["# Structural-break checks: frozen rules, holdout (Jan 2023 - Aug 2025) vs in-sample (Sep 2025 - Oct 2026)\n",
         "Generated by `structural_break.py`. Interpretation is in `ANALYSIS.md`.\n",
         "## 1. Contract specs by quarter\n", _md(flat(spec)),
         "\n## 2. Lot-size counterfactual (CAGR / Sharpe)\n",
         "Every day's lot size replaced with the one shown; rules, sizing and costs otherwise unchanged.\n", _md(lots),
         "\n## 3. Sub-periods at the spec changes\n", _md(sub),
         "\n## 4. Net P&L by weekday and day type (Rs)\n", _md(flat(by_wd)),
         "\n## 5. Rule-free test: long ATM straddle at the signal times\n",
         "Bought at the close of the bar before the signal time, sold at the exit time, no costs. A positive "
         "average means options were cheap for the move that followed.\n", _md(flat(strad)),
         "\n### DTE 1 days by weekday\n", _md(flat(gap)),
         "\n## 6. Volatility by quarter\n", _md(flat(vol))]
    (out / "report.md").write_text("\n".join(s), encoding="utf-8")
    print(f"report -> {out / 'report.md'}")


if __name__ == "__main__":
    main()
