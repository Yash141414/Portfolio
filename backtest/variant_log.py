import csv
import hashlib
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

LOG = Path("experiments/variant_log.csv")
FIELDS = ["logged_at", "purpose", "data", "start", "end", "strategy", "day_type", "rule_hash", "rules",
          "costs", "trades", "pnl", "sharpe", "note"]

# set by the script doing the runs; every evaluate() call is logged under it
context = {"purpose": "unspecified", "data": ""}


def set_context(**kw) -> None:
    context.update(kw)


def describe_rules(strategy) -> str:
    """One line per day type, e.g. 'dte1: pc fade 10:20 long exit 15:15 stop 1.0 risk 1.0'."""
    parts = []
    for dt, spec in strategy.rules.items():
        for r in (spec if isinstance(spec, tuple) else (spec,)):
            parts.append(f"{dt}: {r.ref} {r.mode} {r.sig_t:%H:%M} {r.kind} exit {r.exit_t:%H:%M} "
                         f"stop {r.stop} risk {r.risk}")
    return " | ".join(parts)


def describe_costs(cfg) -> str:
    c = cfg.costs
    return (f"slip max({c.slippage_pts} pts, {c.slippage_pct:.2%}); fill {cfg.fill_field} +{cfg.fill_delay} bars; "
            f"risk {cfg.risk_per_trade:.0%}; max lots {cfg.max_lots}")


def rule_hash(rules: str) -> str:
    return hashlib.sha1(rules.encode()).hexdigest()[:12]


def append(rows: list[dict]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    with LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def log_variant(strategy, cfg, dates, trades, stats) -> None:
    """Record one evaluated strategy variant under the current context."""
    rules = describe_rules(strategy)
    append([{"logged_at": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "purpose": context["purpose"],
             "data": context["data"], "start": dates[0].date() if len(dates) else "",
             "end": dates[-1].date() if len(dates) else "", "strategy": strategy.name, "day_type": "all",
             "rule_hash": rule_hash(rules), "rules": rules, "costs": describe_costs(cfg),
             "trades": len(trades), "pnl": round(float(trades["pnl"].sum()), 2) if len(trades) else 0.0,
             "sharpe": round(float(stats["sharpe"]), 3), "note": context.get("note", "")}])
