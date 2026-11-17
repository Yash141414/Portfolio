from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .metrics import drawdown, inr, table  # noqa: E402

COLORS = {"Mean Reversion": "#2a78b5", "Directional": "#d9822b", "Semi-Directional": "#3a9e5c",
          "Combined": "#222222"}


def plot_equity(curves: dict[str, pd.DataFrame], capitals: dict[str, float], out: Path) -> None:
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    for name, eq in curves.items():
        ret = eq["equity"] / capitals[name] - 1
        ax.plot(ret.index, ret * 100, label=name, color=COLORS.get(name),
                lw=2.4 if name == "Combined" else 1.4)
    ax.axhline(0, color="#999", lw=0.8)
    ax.set_ylabel("Return on capital (%)")
    ax.set_title("Equity curves - individual strategies and combined portfolio")
    ax.legend(loc="upper left", frameon=False)
    ax.grid(alpha=0.3)
    dd = drawdown(curves["Combined"]["equity"]) * 100
    ax2.fill_between(dd.index, dd, 0, color="#c0392b", alpha=0.4)
    ax2.set_ylabel("Combined DD (%)")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def plot_single(name: str, eq: pd.DataFrame, capital: float, out: Path) -> None:
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    ax.plot(eq.index, eq["equity"] / 1e5, color=COLORS.get(name), lw=1.6)
    ax.axhline(capital / 1e5, color="#999", lw=0.8)
    ax.set_ylabel("Equity (Rs lakh)")
    ax.set_title(f"{name} - equity and drawdown")
    ax.grid(alpha=0.3)
    dd = drawdown(eq["equity"]) * 100
    ax2.fill_between(dd.index, dd, 0, color="#c0392b", alpha=0.4)
    ax2.set_ylabel("DD (%)")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def _md(df: pd.DataFrame) -> str:
    cols = [str(df.index.name or "")] + [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for idx, row in df.iterrows():
        lines.append("| " + " | ".join([str(idx)] + [str(v) for v in row]) + " |")
    return "\n".join(lines)


def monthly_returns(curves: dict[str, pd.DataFrame]) -> pd.DataFrame:
    m = pd.DataFrame({n: (1 + eq["ret"]).resample("ME").prod() - 1 for n, eq in curves.items()})
    m.index = m.index.strftime("%Y-%m")
    m.index.name = "Month"
    return m.map(lambda v: f"{v:+.1%}")


def breakdown(trades: pd.DataFrame, by: str) -> pd.DataFrame:
    g = trades.groupby(["strategy", by])["pnl"]
    df = pd.DataFrame({"trades": g.size(), "win rate": g.apply(lambda p: f"{(p > 0).mean():.0%}"),
                       "avg P&L (Rs)": g.mean().map(inr),
                       "total P&L (Rs)": g.sum().map(inr)})
    df.index = [f"{s} / {k}" for s, k in df.index]
    df.index.name = f"strategy / {by}"
    return df


def write_report(out: Path, meta: dict, stats: dict, halves: dict, curves: dict, trades: pd.DataFrame,
                 corr: pd.DataFrame, robust: pd.DataFrame | None, stress: pd.DataFrame | None = None) -> Path:
    s = []
    s.append("# NIFTY Intraday Options - Three-Strategy Backtest\n")
    s.append(f"Data: {meta['data']} | Period: {meta['start']} to {meta['end']} "
             f"({meta['days']} trading days) | Generated: {meta['generated']}\n")
    if meta.get("synthetic"):
        s.append("> **SYNTHETIC DATA - pipeline test only. These numbers say nothing about real performance.**\n")
    s.append("## Setup\n")
    s.append(meta["setup"] + "\n")
    s.append("## Equity curves\n\n![Equity curves](equity_curves.png)\n")
    for name in stats:
        if name != "Combined":
            s.append(f"![{name}]({name.lower().replace(' ', '_').replace('-', '_')}.png)\n")
    s.append("## Performance statistics\n")
    s.append(_md(table(stats)) + "\n")
    c = stats["Combined"]
    target = "met" if c["calmar"] >= 5 else "**not met**"
    s.append(f"Combined Calmar = {c['calmar']:.2f} (target >= 5: {target}). "
             f"Combined Sharpe {c['sharpe']:.2f}, 95% CI [{c['sharpe_lo']:.2f}, {c['sharpe_hi']:.2f}].\n")
    s.append("## First half vs second half\n")
    s.append("Same parameters throughout. The parameters were selected on the full year (in-sample), "
             "including a requirement to be profitable in both halves, so this table shows stability "
             "within the fitted year, not out-of-sample performance.\n")
    s.append(_md(halves) + "\n")
    s.append("## Correlation of daily returns\n")
    s.append(_md(corr.map(lambda v: f"{v:.2f}")) + "\n")
    if robust is not None:
        s.append("## Parameter robustness\n")
        s.append("Each strategy re-run with its key parameters moved around the defaults. "
                 "Results that collapse when a parameter moves one notch are a sign of overfitting.\n")
        s.append(_md(robust) + "\n")
    if stress is not None:
        s.append("## Stress test\n")
        s.append("Each strategy re-run with one setting changed at a time, for each day type: signal time "
                 "+-10/20 min, exit time +-30/60 min, each alternative stop width and each alternative option "
                 "structure.\n")
        s.append(_md(stress) + "\n")
    s.append("## Breakdown by exit reason\n")
    s.append(_md(breakdown(trades, "reason")) + "\n")
    s.append("## Breakdown by days to expiry\n")
    s.append(_md(breakdown(trades, "dte")) + "\n")
    s.append("## Breakdown by direction\n")
    s.append(_md(breakdown(trades, "direction")) + "\n")
    s.append("## Monthly returns\n")
    s.append(_md(monthly_returns(curves)) + "\n")
    s.append("## Analysis\n\nSee [ANALYSIS.md](ANALYSIS.md) for the written review of each strategy's "
             "strengths and weaknesses.\n")
    path = out / "report.md"
    path.write_text("\n".join(s), encoding="utf-8")
    return path
