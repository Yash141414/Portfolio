"""Charts for the structural-break findings PDF.

    python structural_break/make_charts.py

Reads the daily equity of the frozen rules (holdout run and in-sample run) and the quarterly table written by
structural_break.py; writes equity_timeline.png and quarterly_pnl.png next to this file.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).parent
HOLDOUT, INSAMPLE = "#2a78d6", "#eb6834"     # categorical slots 1 and 2
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
EVENTS = [("2024-11-20", "SEBI F&O changes\n(lot 75 from 2 Dec)"), ("2025-09-01", "Expiry moves\nThu → Tue"),
          ("2025-12-31", "Lot 75 → 65")]


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def combined(path):
    eq = pd.read_csv(path, header=[0, 1], index_col=0, parse_dates=True)[("Combined", "equity")]
    return (eq / 3_000_000 - 1) * 100


def equity_timeline():
    ho, ins = combined("2023-2025 test/daily_equity.csv"), combined("results/daily_equity.csv")
    fig, ax = plt.subplots(figsize=(9, 3.6), facecolor=SURFACE)
    style(ax)
    ax.plot(ho.index, ho, color=HOLDOUT, lw=2, label="Before the fitted year (holdout)")
    ax.plot(ins.index, ins, color=INSAMPLE, lw=2, label="Fitted year (in-sample)")
    ax.axhline(0, color=MUTED, lw=0.8)
    top = max(ho.max(), ins.max())
    for (d, txt), y in zip(EVENTS, (top * 1.02, top * 1.02, -7)):     # staggered so the labels don't collide
        x = pd.Timestamp(d)
        ax.axvline(x, color=MUTED, lw=0.8, ls=(0, (3, 3)))
        ax.text(x + pd.Timedelta(days=6), y, txt, fontsize=7.5, color=MUTED, va="top")
    spike = pd.Timestamp("2023-12-20")
    ax.annotate("20 Dec 2023: +₹6.67 lakh\nin one day", (spike, ho[spike]), xytext=(pd.Timestamp("2023-04-01"),
                ho[spike] + 2), fontsize=7.5, color=INK, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    ax.text(ho.index[-1], ho.iloc[-1] - 2.5, f"{ho.iloc[-1]:+.0f}%", color=INK, fontsize=8, ha="right", va="top")
    ax.text(ins.index[-1] + pd.Timedelta(days=8), ins.iloc[-1], f"{ins.iloc[-1]:+.0f}%", color=INK, fontsize=8,
            va="center")
    ax.set_xlim(right=ins.index[-1] + pd.Timedelta(days=60))
    ax.set_ylabel("Combined return on ₹30 lakh (%)", color=MUTED, fontsize=8)
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.legend(loc="upper left", frameon=False, fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(HERE / "equity_timeline.png", dpi=200, facecolor=SURFACE)


def quarterly_pnl():
    q = pd.read_csv(HERE / "vol_by_quarter.csv", index_col=0)
    pnl = q["combined P&L (Rs)"].str.replace(",", "").astype(float) / 1e5
    labels = list(q.index)
    # the table lists holdout quarters first; 2025Q3 appears twice (end of holdout, start of in-sample)
    split = labels.index("2025Q3") + 1
    colors = [HOLDOUT] * split + [INSAMPLE] * (len(labels) - split)
    names = [f"{x}\n(part)" if x == "2025Q3" else x for x in labels]
    fig, ax = plt.subplots(figsize=(9, 3.2), facecolor=SURFACE)
    style(ax)
    x = range(len(pnl))
    ax.bar(x, pnl, color=colors, width=0.72, edgecolor=SURFACE, linewidth=1)
    ax.axhline(0, color=MUTED, lw=0.8)
    for i, v in zip(x, pnl):
        if abs(v) >= 3:
            ax.text(i, v + (0.25 if v > 0 else -0.25), f"{v:+.1f}", ha="center", va="bottom" if v > 0 else "top",
                    fontsize=7.5, color=INK)
    ax.set_xticks(list(x), names, fontsize=7)
    ax.set_ylabel("Combined net P&L (₹ lakh)", color=MUTED, fontsize=8)
    ax.bar([0], [0], color=HOLDOUT, label="Holdout")
    ax.bar([0], [0], color=INSAMPLE, label="Fitted year (in-sample)")
    ax.legend(loc="upper left", frameon=False, fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(HERE / "quarterly_pnl.png", dpi=200, facecolor=SURFACE)


if __name__ == "__main__":
    equity_timeline()
    quarterly_pnl()
    print(f"charts -> {HERE}")
