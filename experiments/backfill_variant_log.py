"""One-off: record rule variants evaluated before experiments/variant_log.csv existed.

    python experiments/backfill_variant_log.py

Sources:
- data/dhan_2023_2025/search/scores.csv: the 2023-2025 rule search (one row per single-rule candidate)
- the Sep 2025 - Sep 2026 refit that produced the current rules (count not recorded)
- robustness grids and stress tests run on 23 Oct 2026 (results/, results_options_1min/)
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.variant_log import LOG, append, rule_hash  # noqa: E402

SEARCH = Path("data/dhan_2023_2025/search/scores.csv")
WHEN = "2026-10-23 (backfilled)"


def historical_search() -> list[dict]:
    s = pd.read_csv(SEARCH)
    rows = []
    for _, r in s.iterrows():
        rules = (f"{r.dtype}: {r.ref} {r['mode']} {r.sig[:5]} {r.kind} exit {r.exit[:5]} stop {r.stop} risk fixed")
        rows.append({"logged_at": "2025-10-02 (search file date)", "purpose": "selection (historical search)",
                     "data": "data/dhan_2023_2025/nifty_opt_1min.parquet", "start": "2023-01-02",
                     "end": "2025-09-29", "strategy": "", "day_type": r.dtype, "rule_hash": rule_hash(rules),
                     "rules": rules, "costs": "as in search", "trades": int(r.n), "pnl": round(r.total, 2),
                     "sharpe": "", "note": f"t={r.t:.2f}; y2023={r.y2023:.0f} y2024={r.y2024:.0f} "
                                            f"y2025={r.y2025:.0f}"})
    return rows


def refit_search() -> list[dict]:
    return [{"logged_at": WHEN, "purpose": "selection (refit, unrecorded)",
             "data": "data/nifty_opt_1min_2y.parquet", "start": "2025-09-01", "end": "2026-09",
             "strategy": "all", "day_type": "all", "trades": "", "pnl": "", "sharpe": "",
             "note": "Search that produced the current rules. Number of candidates NOT recorded. Acceptance: "
                     "every strategy profitable in both halves (split 2026-04-01) and combined Calmar >= 5."}]


def session_runs() -> list[dict]:
    rows = []
    for folder, data, end in (("results", "data/nifty_opt_1min_2y.parquet", "2026-10-16"),
                              ("results_options_1min", "data/nifty_options_1min.parquet (converted)",
                               "2026-10-22")):
        rob = Path(folder) / "robustness.csv"
        if rob.exists():
            for _, r in pd.read_csv(rob).iterrows():
                rows.append({"logged_at": WHEN, "purpose": "robustness", "data": data, "start": "2025-09-01",
                             "end": end, "strategy": r.strategy, "day_type": "all",
                             "rules": f"base rules, {r.params}", "trades": r.trades, "sharpe": round(r.sharpe, 3),
                             "note": f"cagr={r.cagr:.3f} mdd={r.mdd:.3f}"})
        st = Path(folder) / "stress_test.csv"
        if st.exists():
            for _, r in pd.read_csv(st).iterrows():
                rows.append({"logged_at": WHEN, "purpose": "stress", "data": data, "start": "2025-09-01",
                             "end": end, "strategy": r.strategy, "day_type": "all", "trades": "",
                             "sharpe": "", "note": f"{r.variants} variants (aggregate row); sharpe min "
                                                   f"{r.sharpe_min}, median {r.sharpe_median}; "
                                                   f"profitable both halves {r.profitable_both_halves}"})
    return rows


def main():
    if LOG.exists() and "backfilled" in LOG.read_text(encoding="utf-8"):
        raise SystemExit("already backfilled")
    rows = historical_search() + refit_search() + session_runs()
    append(rows)
    print(f"appended {len(rows)} rows to {LOG}")


if __name__ == "__main__":
    main()
