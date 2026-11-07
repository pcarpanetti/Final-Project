"""Compare metrics with the limit schedule. Pure function of its inputs, so the verifier can re-run it."""
from __future__ import annotations


def evaluate_limits(metrics: dict[str, dict], limits: list[dict]) -> list[dict]:
    rows = []
    for lim in limits:
        value = float(metrics[lim["metric"]]["value"])
        status = "ok"
        if value >= lim["hard"]:
            status = "breach"
        elif value >= lim["warn"]:
            status = "warning"
        rows.append({
            "limit_id": lim["id"],
            "metric": lim["metric"],
            "label": lim["label"],
            "value": value,
            "warn": lim["warn"],
            "hard": lim["hard"],
            "status": status,
        })
    return rows
