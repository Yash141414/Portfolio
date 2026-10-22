from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path("data/final/nifty_opt_1min.parquet")   # Dhan, built by build_dhan_backtest_data.py
BHAVCOPY = Path("data/nifty_opt_bhavcopy.parquet")
MIN_BARS = 300          # skip days with badly incomplete data (a full session is 375)


@dataclass
class Day:

    date: pd.Timestamp
    expiry: pd.Timestamp
    dte: int
    lot: int
    ts: pd.DatetimeIndex            # bar timestamps
    spot: np.ndarray                # spot per bar
    strikes: dict                   # opt_type -> np.ndarray of strikes (columns)
    close: dict                     # opt_type -> [bars, strikes] close, ffilled
    open: dict                      # opt_type -> [bars, strikes] open, falls back to prior close
    offsets: np.ndarray             # offset values, e.g. -10..10
    offset_strike: dict             # opt_type -> [bars, offsets] strike at that offset
    oi: dict | None = None          # opt_type -> [bars, strikes] open interest, ffilled (if the data has it)

    @property
    def n(self) -> int:
        """Number of 1-minute bars in the day."""
        return len(self.ts)

    def pcr(self, i: int, k: float, n: int = 5, step: int = 50) -> float:
        if self.oi is None:
            return np.nan
        tot = {}
        for opt in ("CE", "PE"):
            cols = [self.col(opt, k + j * step) for j in range(-n, n + 1)]
            v = np.array([self.oi[opt][i, c] for c in cols if c >= 0], dtype=float)
            tot[opt] = np.nansum(v)
        return tot["PE"] / tot["CE"] if tot["CE"] > 0 else np.nan

    def bar_at(self, t) -> int:
        return int(np.searchsorted(self.ts.time, t)) if len(self.ts) else 0

    def strike(self, i: int, opt: str, offset: int, step: int = 50) -> float:
        k = np.where(self.offsets == offset)[0]
        if len(k):
            s = self.offset_strike[opt][i, k[0]]
            if not np.isnan(s):
                return float(s)
        return float(round(self.spot[i] / step) * step + offset * step)

    def col(self, opt: str, strike: float) -> int:
        j = np.where(self.strikes[opt] == strike)[0]
        return int(j[0]) if len(j) else -1

    def px(self, i: int, opt: str, strike: float, field: str = "close") -> float:
        j = self.col(opt, strike)
        if j < 0:
            return np.nan
        return float((self.close if field == "close" else self.open)[opt][i, j])


def _lot_sizes(bars: pd.DataFrame) -> pd.Series:
    if "lot_size" in bars:
        return bars.groupby("date")["lot_size"].first()
    if not BHAVCOPY.exists():
        raise FileNotFoundError(f"{BHAVCOPY} needed for lot sizes")
    b = pd.read_parquet(BHAVCOPY, columns=["date", "expiry", "lot_size"])
    near = b[b["expiry"] == b.groupby("date")["expiry"].transform("min")]
    return near.groupby("date")["lot_size"].agg(lambda s: s.mode().iat[0])


def load_days(path: Path = DATA, start=None, end=None) -> list[Day]:
    bars = pd.read_parquet(path)
    if start:
        bars = bars[bars["date"] >= pd.Timestamp(start)]
    if end:
        bars = bars[bars["date"] <= pd.Timestamp(end)]
    if bars.empty:
        raise ValueError("no bars in the requested range")
    lots = _lot_sizes(bars)
    has_offset = "offset" in bars.columns
    offsets = np.sort(bars["offset"].unique()) if has_offset else np.array([], dtype=float)
    days = []
    for d, g in bars.groupby("date", sort=True):
        if d not in lots.index:
            print(f"skip {d.date()}: no lot size")
            continue
        ts = pd.DatetimeIndex(np.sort(g["ts"].unique()))
        if len(ts) < MIN_BARS:
            print(f"skip {d.date()}: only {len(ts)} bars")
            continue
        spot = g.groupby("ts")["spot"].median().reindex(ts).ffill().bfill().to_numpy()
        strikes, close, open_, off_k, oi = {}, {}, {}, {}, {}
        for opt in ("CE", "PE"):
            o = g[g["opt_type"] == opt]
            c = o.pivot_table(index="ts", columns="strike", values="close", aggfunc="last").reindex(ts).ffill()
            op = o.pivot_table(index="ts", columns="strike", values="open", aggfunc="last").reindex(ts)
            op = op.fillna(c.shift(1)).fillna(c)          # no bar this minute -> last known close
            strikes[opt] = c.columns.to_numpy(dtype=float)
            close[opt] = c.to_numpy()
            open_[opt] = op[c.columns].to_numpy()
            if "oi" in o:
                oi[opt] = (o.pivot_table(index="ts", columns="strike", values="oi", aggfunc="last")
                           .reindex(index=ts, columns=c.columns).ffill().to_numpy(dtype=float))
            if has_offset:
                off_k[opt] = (o.pivot_table(index="ts", columns="offset", values="strike", aggfunc="last")
                              .reindex(index=ts, columns=offsets).to_numpy(dtype=float))
            else:
                off_k[opt] = np.empty((len(ts), 0), dtype=float)
        days.append(Day(date=d, expiry=g["expiry"].iat[0], dte=int(g["dte"].iat[0]), lot=int(lots[d]),
                        ts=ts, spot=spot, strikes=strikes, close=close, open=open_,
                        offsets=offsets, offset_strike=off_k, oi=oi or None))
    return days
