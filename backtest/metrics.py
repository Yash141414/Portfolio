import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def inr(x, decimals: int = 0) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not np.isfinite(x):
        return str(x)
    s = f"{x:.{decimals}f}"
    neg = s.startswith("-") and float(s) != 0
    whole, _, frac = s.lstrip("-").partition(".")
    if len(whole) > 3:
        head, groups = whole[:-3], [whole[-3:]]
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(([head] if head else []) + groups)
    return ("-" if neg else "") + whole + (f".{frac}" if frac else "")


def trades_frame(trades) -> pd.DataFrame:
    df = pd.DataFrame([t.__dict__ for t in trades])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df


def daily_equity(trades: pd.DataFrame, dates: pd.DatetimeIndex, capital: float) -> pd.DataFrame:
    pnl = (trades.groupby("date")["pnl"].sum() if len(trades) else pd.Series(dtype=float))
    pnl = pnl.reindex(dates, fill_value=0.0)
    equity = capital + pnl.cumsum()
    prev = equity.shift(1).fillna(capital)
    return pd.DataFrame({"pnl": pnl, "equity": equity, "ret": pnl / prev})


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def sharpe_stats(ret: pd.Series) -> dict:
    r = ret.to_numpy()
    n = len(r)
    sd = r.std(ddof=1)
    if n < 3 or sd == 0:
        return {"sharpe": np.nan, "sharpe_lo": np.nan, "sharpe_hi": np.nan, "psr": np.nan}
    sr = r.mean() / sd
    z = (r - r.mean()) / sd
    skew, kurt = (z ** 3).mean(), (z ** 4).mean()
    se = math.sqrt(max(1e-12, (1 - skew * sr + (kurt - 1) / 4 * sr ** 2) / (n - 1)))
    a = math.sqrt(TRADING_DAYS)
    return {"sharpe": sr * a, "sharpe_lo": (sr - 1.96 * se) * a, "sharpe_hi": (sr + 1.96 * se) * a,
            "psr": _norm_cdf(sr / se)}


def drawdown(equity: pd.Series) -> pd.Series:
    return equity / equity.cummax() - 1


def summary(eq: pd.DataFrame, trades: pd.DataFrame, capital: float) -> dict:
    e, r = eq["equity"], eq["ret"]
    years = max((e.index[-1] - e.index[0]).days, 1) / 365.25
    cagr = (e.iloc[-1] / capital) ** (1 / years) - 1
    dd = drawdown(pd.concat([pd.Series([capital], index=[e.index[0] - pd.Timedelta(days=1)]), e]))
    mdd = dd.min()
    under = dd < 0
    runs = under.groupby((~under).cumsum()).sum()
    downside = r[r < 0]
    monthly = eq["pnl"].resample("ME").sum()
    out = {
        "start": e.index[0].date(), "end": e.index[-1].date(), "trading_days": len(e),
        "final_equity": e.iloc[-1], "total_return": e.iloc[-1] / capital - 1, "cagr": cagr,
        "ann_vol": r.std() * math.sqrt(TRADING_DAYS),
        **sharpe_stats(r),
        "sortino": r.mean() / downside.std() * math.sqrt(TRADING_DAYS) if len(downside) > 1 else np.nan,
        "mdd": mdd, "mdd_days": int(runs.max()) if len(runs) else 0,
        "calmar": cagr / abs(mdd) if mdd < 0 else np.inf,
        "worst_day": r.min(), "best_day": r.max(),
        "pct_days_traded": (eq["pnl"] != 0).mean(),
        "pct_months_positive": (monthly > 0).mean(),
    }
    if len(trades):
        p = trades["pnl"]
        wins, losses = p[p > 0], p[p <= 0]
        streak = (p <= 0).astype(int)
        out.update({
            "trades": len(p), "win_rate": (p > 0).mean(),
            "avg_pnl": p.mean(), "avg_win": wins.mean() if len(wins) else 0.0,
            "avg_loss": losses.mean() if len(losses) else 0.0,
            "payoff": wins.mean() / -losses.mean() if len(wins) and len(losses) and losses.mean() < 0 else np.nan,
            "profit_factor": wins.sum() / -losses.sum() if losses.sum() < 0 else np.inf,
            "best_trade": p.max(), "worst_trade": p.min(),
            "max_consec_losses": int(streak.groupby((streak == 0).cumsum()).sum().max()),
            "avg_bars_held": trades["bars_held"].mean(),
            "gross_pnl": trades["gross_pnl"].sum(), "costs": trades["costs"].sum(),
            "costs_pct_gross": trades["costs"].sum() / trades["gross_pnl"].clip(lower=0).sum()
            if trades["gross_pnl"].clip(lower=0).sum() > 0 else np.nan,
        })
    return out


def RS(v) -> str:
    return f"Rs {inr(v)}"


FORMATS = {  
    "final_equity": RS, "total_return": "{:.1%}", "cagr": "{:.1%}", "ann_vol": "{:.1%}",
    "sharpe": "{:.2f}", "sharpe_lo": "{:.2f}", "sharpe_hi": "{:.2f}", "psr": "{:.1%}", "sortino": "{:.2f}",
    "mdd": "{:.1%}", "calmar": "{:.2f}", "worst_day": "{:.2%}", "best_day": "{:.2%}",
    "pct_days_traded": "{:.0%}", "pct_months_positive": "{:.0%}", "win_rate": "{:.1%}",
    "avg_pnl": RS, "avg_win": RS, "avg_loss": RS, "payoff": "{:.2f}",
    "profit_factor": "{:.2f}", "best_trade": RS, "worst_trade": RS,
    "avg_bars_held": "{:.0f} min", "gross_pnl": RS, "costs": RS, "costs_pct_gross": "{:.0%}",
}
LABELS = {
    "start": "Start", "end": "End", "trading_days": "Trading days", "final_equity": "Final equity",
    "total_return": "Total return", "cagr": "CAGR", "ann_vol": "Annual volatility", "sharpe": "Sharpe",
    "sharpe_lo": "Sharpe 95% CI low", "sharpe_hi": "Sharpe 95% CI high", "psr": "P(true Sharpe > 0)",
    "sortino": "Sortino", "mdd": "Max drawdown", "mdd_days": "Longest drawdown (days)", "calmar": "Calmar",
    "worst_day": "Worst day", "best_day": "Best day", "pct_days_traded": "Days with a trade",
    "pct_months_positive": "Positive months", "trades": "Trades", "win_rate": "Win rate",
    "avg_pnl": "Avg P&L / trade", "avg_win": "Avg win", "avg_loss": "Avg loss", "payoff": "Avg win / avg loss",
    "profit_factor": "Profit factor", "best_trade": "Best trade", "worst_trade": "Worst trade",
    "max_consec_losses": "Max consecutive losses", "avg_bars_held": "Avg holding time",
    "gross_pnl": "Gross P&L (after slippage)", "costs": "Charges", "costs_pct_gross": "Charges / gross profits",
}


def fmt(key: str, v) -> str:
    if isinstance(v, float) and not np.isfinite(v):
        return "n/a" if np.isnan(v) else "inf"
    f = FORMATS.get(key, "{}")
    return f(v) if callable(f) else f.format(v)


def table(stats: dict[str, dict]) -> pd.DataFrame:
    """Side-by-side formatted stats: rows = metrics, columns = strategies."""
    keys = [k for k in LABELS if any(k in s for s in stats.values())]
    return pd.DataFrame({name: [fmt(k, s[k]) if k in s else "" for k in keys] for name, s in stats.items()},
                        index=[LABELS[k] for k in keys])
