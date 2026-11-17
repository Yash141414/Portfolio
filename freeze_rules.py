"""Freeze the current strategy rules, sizing and cost settings to a JSON snapshot.

    python freeze_rules.py                      # writes frozen/rules_v1.json
    python freeze_rules.py --out frozen/rules_v2.json --last-insample 2026-10-16

Out-of-sample and forward tests load the snapshot with backtest.frozen.load_frozen, so later
edits to the code can't change what is being tested.
"""
import argparse
import json
from pathlib import Path

from backtest.config import DEFAULT
from backtest.frozen import snapshot


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="frozen/rules_v1.json")
    ap.add_argument("--last-insample", default="2026-10-16", help="last date the rules were evaluated on")
    ap.add_argument("--note", default="Rules fitted on 2025-09-01 .. 2026-09; frozen before any out-of-sample test.")
    ap.add_argument("--force", action="store_true", help="overwrite an existing snapshot")
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists() and not a.force:
        raise SystemExit(f"{out} exists; a frozen snapshot is never overwritten (use a new version or --force)")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot(DEFAULT, a.last_insample, a.note), indent=2), encoding="utf-8")
    print(f"frozen -> {out}")


if __name__ == "__main__":
    main()
