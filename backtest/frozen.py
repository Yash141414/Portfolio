import hashlib
import json
import subprocess
from dataclasses import asdict, fields
from datetime import datetime, time
from pathlib import Path

from . import strategies as S
from .config import Config, Costs

HASHED = ["backtest/strategies.py", "backtest/config.py", "backtest/engine.py", "backtest/data.py"]
CLASSES = {c.name: c for c in (S.MeanReversion, S.Directional, S.SemiDirectional)}


def _rule_json(r: S.Rule) -> dict:
    d = asdict(r)
    d["sig_t"], d["exit_t"] = f"{r.sig_t:%H:%M}", f"{r.exit_t:%H:%M}"
    return d


def _rule_obj(d: dict) -> S.Rule:
    return S.Rule(**{**d, "sig_t": time.fromisoformat(d["sig_t"]), "exit_t": time.fromisoformat(d["exit_t"])})


def sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(cfg: Config, last_insample: str, note: str = "") -> dict:
    """Everything that defines the strategies' behaviour, as plain JSON."""
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    rules = {name: {dt: [_rule_json(r) for r in S.rules_of(spec)] for dt, spec in cls.rules.items()}
             for name, cls in CLASSES.items()}
    return {"frozen_at": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "git_commit": commit,
            "last_insample_date": last_insample, "note": note, "rules": rules,
            "sizing": {"MAX_PREMIUM_FRAC": S.MAX_PREMIUM_FRAC, "MAX_ONE_LOT_RISK": S.MAX_ONE_LOT_RISK},
            "config": {k: (v.isoformat(timespec="minutes") if isinstance(v, time) else v)
                       for k, v in asdict(cfg).items() if k != "costs"},
            "costs": asdict(cfg.costs), "file_sha256": {p: sha256(p) for p in HASHED}}


def load_frozen(path) -> tuple[list, Config, dict]:
    """Rebuild the frozen strategies and config from a snapshot; warn if the code has drifted since."""
    snap = json.loads(Path(path).read_text(encoding="utf-8"))
    strategies = []
    for name, rules in snap["rules"].items():
        overrides = {dt: tuple(map(_rule_obj, rs)) if len(rs) > 1 else _rule_obj(rs[0]) for dt, rs in rules.items()}
        strategies.append(CLASSES[name](**overrides))
    for k, v in snap["sizing"].items():
        if getattr(S, k) != v:
            raise RuntimeError(f"{k} is {getattr(S, k)} in the code but {v} in the frozen snapshot")
    conf = {f.name: f.type for f in fields(Config)}
    kw = {k: (time.fromisoformat(v) if conf.get(k) is time or k in ("session_open", "last_entry", "square_off") else v)
          for k, v in snap["config"].items()}
    cfg = Config(**kw, costs=Costs(**snap["costs"]))
    changed = [p for p, h in snap["file_sha256"].items() if Path(p).exists() and sha256(p) != h]
    if changed:
        print(f"warning: changed since the freeze: {', '.join(changed)} (frozen rules and config are still used)")
    return strategies, cfg, snap
