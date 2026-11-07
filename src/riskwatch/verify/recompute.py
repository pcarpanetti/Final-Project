"""Second implementation of the headline metrics, in plain Python from the frozen run inputs.

It shares no code with risk/engine.py on purpose. A bug has to appear twice, in two styles, to get through.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path


def _read_table(path: Path) -> tuple[list[str], list[str], list[list[float]]]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[0][1:], [r[0] for r in rows[1:]], [[float(x) for x in r[1:]] for r in rows[1:]]


def _tail_quantile(pnl: list[float], alpha: float, weights: list[float]) -> float:
    total = sum(weights)
    cum = 0.0
    for value, w in sorted(zip(pnl, weights), key=lambda t: t[0]):
        cum += w / total
        if cum >= alpha - 1e-12:
            return value
    return max(pnl)


def recompute(run_dir: Path, as_of: str, var_cfg: dict) -> dict[str, float]:
    assets, dates, returns = _read_table(run_dir / "clean_returns.csv")
    w_assets, w_dates, w_rows = _read_table(run_dir / "inputs" / "weights.csv")
    _, _, nav_rows = _read_table(run_dir / "inputs" / "nav.csv")
    i = w_dates.index(as_of)
    by_name = dict(zip(w_assets, w_rows[i]))
    weights = [by_name[a] for a in assets]

    window = returns[-var_cfg["lookback_days"]:]
    pnl = [sum(w * r for w, r in zip(weights, row)) for row in window]
    n = len(pnl)
    if var_cfg["method"] == "age_weighted":
        obs = [var_cfg["age_decay"] ** (n - 1 - k) for k in range(n)]
    else:
        obs = [1.0] * n

    cut975 = _tail_quantile(pnl, 0.025, obs)
    tail = [(p, o) for p, o in zip(pnl, obs) if p <= cut975]
    prev = dict(zip(w_assets, w_rows[i - 1])) if i else by_name
    navs = [r[0] for r in nav_rows]
    ordered = sorted(weights, reverse=True)
    return {
        "var99_1d": -_tail_quantile(pnl, 0.01, obs),
        "var95_1d": -_tail_quantile(pnl, 0.05, obs),
        "es975_1d": -sum(p * o for p, o in tail) / sum(o for _, o in tail),
        "daily_return": sum(prev[a] * r for a, r in zip(assets, returns[-1])),
        "weight_max": ordered[0],
        "top3_weight": sum(ordered[:3]),
        "drawdown": 1.0 - navs[-1] / max(navs),
        "nav_usd": navs[-1],
    }


def max_abs_error(a: float, b: float) -> float:
    return abs(a - b) if math.isfinite(a) and math.isfinite(b) else math.inf
