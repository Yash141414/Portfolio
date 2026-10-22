import argparse
import itertools
import time as clock
from dataclasses import replace
from datetime import datetime, time
from pathlib import Path

import pandas as pd

from backtest.config import DEFAULT
from backtest.data import DATA, load_days
from backtest.engine import run
from backtest.metrics import daily_equity, inr, summary, table, trades_frame
from backtest.report import plot_equity, plot_single, write_report
from backtest.strategies import Directional, MeanReversion, SemiDirectional, default_strategies

GRID = {"shift_min": [-10, 0, 10], "risk_scale": [0.5, 1.0, 1.5]}   # applied to every rule of a strategy
SPLIT = "2026-04-01"   # boundary between the two halves reported separately


def perturbed(cls, shift_min: int, risk_scale: float):
    """The strategy with every rule's signal time shifted and risk multiplier scaled."""
    def move(t: time) -> time:
        m = t.hour * 60 + t.minute + shift_min
        return time(m // 60, m % 60)
    def one(r):
        return replace(r, sig_t=move(r.sig_t), risk=r.risk * risk_scale)
    return cls(**{dt: tuple(map(one, spec)) if isinstance(spec, tuple) else one(spec)
                  for dt, spec in cls.rules.items()})


def evaluate(strategy, days, dates, cfg):
    """Run one strategy over all days; return (trades DataFrame, daily equity DataFrame)."""
    tr = trades_frame(run(strategy, days, cfg))
    eq = daily_equity(tr, dates, cfg.capital_per_strategy)
    return tr, eq


def robustness(days, dates, cfg) -> pd.DataFrame:
    """Re-run each strategy on the GRID (signal times +-10 min x risk x0.5/1/1.5); summarise and save robustness.csv."""
    rows = []
    for cls in (MeanReversion, Directional, SemiDirectional):
        keys = list(GRID)
        for vals in itertools.product(*GRID.values()):
            params = dict(zip(keys, vals))
            tr, eq = evaluate(perturbed(cls, **params), days, dates, cfg)
            st = summary(eq, tr, cfg.capital_per_strategy)
            rows.append({"strategy": cls.name, **{"params": ", ".join(f"{k}={v}" for k, v in params.items())},
                         "trades": st.get("trades", 0), "sharpe": st["sharpe"], "cagr": st["cagr"],
                         "mdd": st["mdd"], "calmar": st["calmar"]})
            print(f"  {cls.name:17s} {rows[-1]['params']:32s} sharpe {st['sharpe']:6.2f}")
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "robustness.csv", index=False)
    agg = df.groupby("strategy").agg(configs=("sharpe", "size"),
                                     sharpe_min=("sharpe", "min"), sharpe_median=("sharpe", "median"),
                                     sharpe_max=("sharpe", "max"),
                                     pct_positive=("sharpe", lambda s: (s > 0).mean()),
                                     calmar_median=("calmar", "median"))
    agg["pct_positive"] = agg["pct_positive"].map("{:.0%}".format)
    return agg.round(2)


def _shift(t: time, m: int) -> time:
    x = min(max(t.hour * 60 + t.minute + m, 9 * 60 + 16), 15 * 60 + 15)
    return time(x // 60, x % 60)


def stress_variants(cls):
    """One-at-a-time perturbations of each day type's rule(s): signal time +-10/20 min, exit
    time +-30/60 min, each alternative stop, each alternative option structure."""
    def rep(spec, f):
        return tuple(f(x) for x in spec) if isinstance(spec, tuple) else f(spec)
    first = lambda spec: spec[0] if isinstance(spec, tuple) else spec
    for dt, spec in cls.rules.items():
        r0 = first(spec)
        mods = [lambda x, m=m: replace(x, sig_t=_shift(x.sig_t, m)) for m in (-20, -10, 10, 20)]
        mods += [lambda x, m=m: replace(x, exit_t=_shift(x.exit_t, m)) for m in (-60, -30, 30, 60)]
        mods += [lambda x, s=s: replace(x, stop=s) for s in (0.0, 0.5, 1.0, 1.5) if s != r0.stop]
        kinds = ("long", "long_otm1", "debit3", "debit6") if r0.kind in ("long", "long_otm1", "debit3", "debit6") \
            else ("credit3", "credit5", "otmcredit3")
        mods += [lambda x, k=k: replace(x, kind=k) for k in kinds if k != r0.kind]
        for f in mods:
            yield cls(**{dt: rep(spec, f)})


def stress_test(days, dates, cfg, mid) -> pd.DataFrame:
    """Re-run each strategy with one setting changed at a time (stress_variants) and summarise:
    worst and median Sharpe, and how many variants stay profitable in both halves."""
    rows = []
    for cls in (MeanReversion, Directional, SemiDirectional):
        sh, both = [], []
        for v in stress_variants(cls):
            tr, eq = evaluate(v, days, dates, cfg)
            sh.append(summary(eq, tr, cfg.capital_per_strategy)["sharpe"])
            both.append(eq["pnl"][eq.index < mid].sum() > 0 and eq["pnl"][eq.index >= mid].sum() > 0)
        rows.append({"strategy": cls.name, "variants": len(sh), "sharpe_min": round(min(sh), 2),
                     "sharpe_median": round(float(pd.Series(sh).median()), 2),
                     "profitable_both_halves": f"{sum(both)} of {len(both)}"})
        print(f"  {cls.name:17s} stress variants {len(sh)}  sharpe min {min(sh):.2f}")
    df = pd.DataFrame(rows).set_index("strategy")
    df.to_csv(OUT / "stress_test.csv")
    return df


def main():
    """Parse arguments, run the three strategies and the portfolio, and write everything to --out."""
    global OUT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--start", help="YYYY-MM-DD (default: 1 year before the last date)")
    ap.add_argument("--end", help="YYYY-MM-DD (default: last date in the data)")
    ap.add_argument("--out", default="results")
    ap.add_argument("--robustness", action="store_true")
    ap.add_argument("--split", default=SPLIT,
                    help=f"date splitting the first and second half tables, YYYY-MM-DD (default {SPLIT})")
    a = ap.parse_args()
    OUT = Path(a.out)
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = DEFAULT

    t0 = clock.time()
    start = a.start
    if not start:
        last = pd.read_parquet(a.data, columns=["date"])["date"].max()
        start = (last - pd.DateOffset(years=1) + pd.Timedelta(days=1)).date()
    days = load_days(Path(a.data), start, a.end)
    dates = pd.DatetimeIndex([d.date for d in days])
    print(f"{len(days)} days loaded ({dates[0].date()} -> {dates[-1].date()}) in {clock.time() - t0:.1f}s")

    curves, stats, capitals, all_trades = {}, {}, {}, []
    for strat in default_strategies():
        tr, eq = evaluate(strat, days, dates, cfg)
        curves[strat.name], capitals[strat.name] = eq, cfg.capital_per_strategy
        stats[strat.name] = summary(eq, tr, cfg.capital_per_strategy)
        all_trades.append(tr)
        print(f"{strat.name:17s} trades {len(tr):4d}  sharpe {stats[strat.name]['sharpe']:6.2f}  "
              f"calmar {stats[strat.name]['calmar']:6.2f}")

    trades = pd.concat(all_trades, ignore_index=True)
    cap = cfg.capital_per_strategy * len(curves)
    combined = daily_equity(trades, dates, cap)
    curves["Combined"], capitals["Combined"] = combined, cap
    stats["Combined"] = summary(combined, trades, cap)
    print(f"{'Combined':17s} trades {len(trades):4d}  sharpe {stats['Combined']['sharpe']:6.2f}  "
          f"calmar {stats['Combined']['calmar']:6.2f}")

    # first half vs second half, same parameters
    mid = pd.Timestamp(a.split)
    if not dates[0] < mid <= dates[-1]:
        mid = dates[len(dates) // 2]
    halves = {}
    for name, eq in curves.items():
        tr = trades if name == "Combined" else trades[trades["strategy"] == name]
        for label, mask in (("first half", eq.index < mid), ("second half", eq.index >= mid)):
            e = eq[mask].copy()
            base = capitals[name] if label == "first half" else eq["equity"][~mask].iloc[-1]
            e = daily_equity(tr[tr["date"].isin(e.index)], e.index, base)
            st = summary(e, tr[tr["date"].isin(e.index)], base)
            halves[f"{name} {label}"] = {k: st[k] for k in ("cagr", "sharpe", "sharpe_lo", "sharpe_hi", "mdd",
                                                            "calmar") if k in st} | \
                {"trades": st.get("trades", 0), "win_rate": st.get("win_rate", float("nan")),
                 "avg_pnl": st.get("avg_pnl", float("nan"))}
    halves_tbl = table(halves).T
    halves_tbl.index.name = f"split at {mid.date()}"
    for name in curves:
        h = halves[f"{name} second half"]
        print(f"2nd half {name:17s} sharpe {h['sharpe']:6.2f}  calmar {h['calmar']:6.2f}  cagr {h['cagr']:+.1%}")

    corr = pd.DataFrame({n: c["ret"] for n, c in curves.items() if n != "Combined"}).corr()
    robust = None
    if a.robustness:
        print("robustness grid:")
        robust = robustness(days, dates, cfg)

    stress = None
    if a.robustness:
        print("stress test:")
        stress = stress_test(days, dates, cfg, mid)

    plot_equity(curves, capitals, OUT / "equity_curves.png")
    for name, eq in curves.items():
        if name != "Combined":
            plot_single(name, eq, capitals[name], OUT / f"{name.lower().replace(' ', '_').replace('-', '_')}.png")
    trades.to_csv(OUT / "trades.csv", index=False)
    pd.concat({n: c for n, c in curves.items()}, axis=1).to_csv(OUT / "daily_equity.csv")
    table(stats).to_csv(OUT / "stats.csv")

    c = cfg.costs
    setup = (f"- Capital: Rs {inr(cfg.capital_per_strategy)} per strategy, Rs {inr(cap)} combined "
             f"(equal allocation, fixed in advance - not optimised).\n"
             f"- Sizing: lots so that the position's worst-case loss (premium paid, or spread width minus "
             f"credit) is {cfg.risk_per_trade:.0%} of the sleeve's equity; max {cfg.max_lots} lots; "
             f"premium outlay <= 20% of equity. Equity compounds.\n"
             f"- Instrument: nearest weekly NIFTY expiry, 1-minute bars from Dhan's expired-options API "
             f"(ATM+-10 strikes, real strike per bar; expiry from the NSE bhavcopy, weekday rule outside it), "
             f"lot size as per NSE on each date.\n"
             f"- Every strategy trades once every day, with one rule per day type (3+ days to expiry, "
             f"day before expiry, expiry day).\n"
             f"- **IN-SAMPLE:** rules and risk multipliers were selected on this same year to make each "
             f"strategy profitable in both halves and reach a combined Calmar >= 5. An earlier design "
             f"fixed on the first half alone lost money in the second half. Read these results as a "
             f"fitted description of this year, not an estimate of future performance.\n"
             f"- Execution: signal on bar close, fill at next bar open; flat by {cfg.square_off:%H:%M}; "
             f"no entries after {cfg.last_entry:%H:%M}.\n"
             f"- Slippage: max({c.slippage_pts} pts, {c.slippage_pct:.1%} of premium) per fill.\n"
             f"- Charges: Rs {c.brokerage_per_order:.0f}/order brokerage, STT {c.stt_sell:.2%} on sells, "
             f"NSE txn {c.exchange_txn:.5%}, SEBI Rs {c.sebi_per_crore:.0f}/cr, stamp {c.stamp_buy:.3%} on buys, "
             f"GST {c.gst:.0%}.\n"
             f"- Drawdown is measured on daily closing equity (positions are always flat overnight).")
    meta = {"data": a.data, "start": dates[0].date(), "end": dates[-1].date(), "days": len(dates),
            "generated": f"{datetime.now():%Y-%m-%d %H:%M}", "setup": setup,
            "synthetic": "synthetic" in Path(a.data).name}
    path = write_report(OUT, meta, stats, halves_tbl, curves, trades, corr, robust, stress)
    print(f"\nreport -> {path}  ({clock.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
