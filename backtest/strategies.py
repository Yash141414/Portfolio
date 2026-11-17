from dataclasses import dataclass
from datetime import time

import numpy as np

from .config import Config
from .data import Day
from .engine import Leg, Position, Session, Trade, lots_for, slip

MAX_PREMIUM_FRAC = 0.20   # never spend more than 20% of sleeve equity on premium in one trade
MAX_ONE_LOT_RISK = 0.05   # the 1-lot floor applies only if one lot's worst case is under 5% of equity


@dataclass(frozen=True)
class Rule:
    ref: str            # "open" (day's first bar), "pc" (previous close) or "pcr" (put/call OI ratio)
    mode: str           # "fade" or "follow"
    sig_t: time         # decide on the close of the bar before this time, fill at its open
    kind: str
    exit_t: time
    stop: float = 0.0   # 0 = no spot stop; m = stop at the morning range's far edge +- m x range
    risk: float = 1.0   # multiplier on cfg.risk_per_trade


def day_type(day: Day) -> str:
    return "exp" if day.dte == 0 else ("dte1" if day.dte == 1 else "far")


def legs_for(kind: str, sign: int, k: float, step: float) -> list[Leg]:
    up, dn = ("CE", "PE") if sign > 0 else ("PE", "CE")
    if kind == "long":
        return [Leg(up, k, +1)]
    if kind == "long_otm1":
        return [Leg(up, k + sign * step, +1)]
    if kind.startswith("debit"):
        w = int(kind[5:])
        return [Leg(up, k, +1), Leg(up, k + sign * w * step, -1)]
    if kind.startswith("otmcredit"):
        w = int(kind[9:])
        return [Leg(dn, k - sign * 2 * step, -1), Leg(dn, k - sign * (2 + w) * step, +1)]
    if kind.startswith("credit"):
        w = int(kind[6:])
        return [Leg(dn, k, -1), Leg(dn, k - sign * w * step, +1)]
    raise ValueError(f"unknown kind {kind!r}")


def worst_case(day: Day, i: int, legs: list[Leg], cfg: Config) -> tuple[float, float]:
    px = [day.px(i, l.opt, l.strike) for l in legs]
    if not all(np.isfinite(px)):
        return np.nan, np.nan
    net = sum(l.side * p for l, p in zip(legs, px))            # + = debit paid
    slippage = sum(2 * slip(p, cfg.costs) for p in px)
    if net > 0:
        return net + slippage, net
    width = max(abs(a.strike - b.strike) for a in legs for b in legs if a.opt == b.opt) if len(legs) > 1 else np.inf
    return width + net + slippage, 0.0


def size(day: Day, max_loss: float, debit: float, equity: float, cfg: Config, risk: float) -> int:
    if not np.isfinite(max_loss) or max_loss <= 0:
        return 0
    lots = int(min(cfg.max_lots, risk * cfg.risk_per_trade * equity // (max_loss * day.lot)))
    if debit > 0:
        lots = min(lots, int(MAX_PREMIUM_FRAC * equity // (debit * day.lot)))
    if lots == 0 and max_loss * day.lot <= MAX_ONE_LOT_RISK * equity:
        lots = 1
    return lots


def rules_of(spec) -> tuple[Rule, ...]:
    return spec if isinstance(spec, tuple) else (spec,)


class RuleStrategy:
    name = "Rule strategy"
    rules: dict[str, Rule | tuple[Rule, ...]] = {}

    def __init__(self, **overrides):
        self.rules = {**type(self).rules, **overrides}
        self.prev_close = None

    def run_day(self, day: Day, equity: float, cfg: Config) -> list[Trade]:
        prev, self.prev_close = self.prev_close, day.spot[-1]
        trades = []
        for r in rules_of(self.rules[day_type(day)]):
            trades += self._run_rule(day, r, prev, equity, cfg)
        return trades

    def _run_rule(self, day: Day, r: Rule, prev, equity: float, cfg: Config) -> list[Trade]:
        s = Session.of(day, cfg)
        i = day.bar_at(r.sig_t) - 1
        if i < 0 or i >= s.last_entry:      # i == 0 is fine: some days' data starts a few minutes late
            return []
        step = cfg.strike_step
        k = day.strike(i, "CE", 0, step)
        p = day.pcr(i, k) if r.ref == "pcr" else np.nan
        if r.ref == "pcr" and np.isfinite(p):
            move = 1 if p >= 1 else -1          # more put OI than call OI near the money -> bullish
        else:
            ref = day.spot[0] if r.ref in ("open", "pcr") or prev is None else prev
            move = 1 if day.spot[i] >= ref else -1
        sign = move if r.mode == "follow" else -move
        legs = legs_for(r.kind, sign, k, step)
        max_loss, debit = worst_case(day, i, legs, cfg)
        lots = size(day, max_loss, debit, equity, cfg, r.risk)
        pos = Position(day, legs, lots, i + 1, cfg, self.name, "long" if sign > 0 else "short")
        if not pos.valid:
            return []
        i_exit = min(day.bar_at(r.exit_t), s.square_off)
        if r.stop > 0 and debit > 0:
            hi, lo = day.spot[:i + 1].max(), day.spot[:i + 1].min()
            rng = max(hi - lo, 1.0)
            level = lo - r.stop * rng if sign > 0 else hi + r.stop * rng
            for j in range(pos.i_entry, i_exit):
                if sign * (day.spot[j] - level) <= 0:
                    return [pos.close(min(j + 1, i_exit), "stop")]
        return [pos.close(i_exit, "square-off" if i_exit == s.square_off else "time exit")]


T = time


class MeanReversion(RuleStrategy):
    name = "Mean Reversion"
    rules = {
        "far": Rule("open", "fade", T(10, 0), "long", T(15, 15), 0.0, 0.5),
        "dte1": tuple(Rule("pc", "fade", t, "long", T(15, 15), 1.0, 1.0) for t in (T(10, 20), T(10, 35), T(10, 50))),
        "exp": Rule("open", "fade", T(10, 0), "debit6", T(12, 0), 1.0, 1.0),
    }


class Directional(RuleStrategy):
    name = "Directional"
    rules = {
        "far": Rule("pcr", "follow", T(10, 0), "long", T(15, 15), 0.0, 1.0),
        "dte1": Rule("pcr", "follow", T(10, 15), "long", T(15, 15), 1.0, 2.0),
        "exp": Rule("pcr", "follow", T(9, 55), "credit5", T(15, 15), 0.0, 0.5),
    }


class SemiDirectional(RuleStrategy):
    name = "Semi-Directional"
    rules = {
        "far": Rule("pc", "follow", T(9, 30), "otmcredit3", T(12, 0), 0.0, 0.5),
        "dte1": Rule("pc", "fade", T(10, 30), "credit5", T(15, 15), 0.0, 3.0),
        "exp": Rule("open", "fade", T(10, 0), "credit5", T(12, 0), 0.0, 3.0),
    }


def default_strategies():
    return [MeanReversion(), Directional(), SemiDirectional()]
