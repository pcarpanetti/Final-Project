"""Read-only agent tools. They see the run's own frozen artifacts and nothing else, so they cannot
reach past the information cutoff. Dates are shown as T, T-1, ... when masking is on.
"""
from __future__ import annotations

import pandas as pd

from ..risk import backtest


class Tools:
    def __init__(self, ctx):
        self.ctx = ctx

    def call(self, name: str, args: dict):
        return getattr(self, name)(**args)

    def _returns(self) -> pd.DataFrame:
        name = "clean_returns.csv" if self.ctx.exists("clean_returns.csv") else "inputs/returns.csv"
        return pd.read_csv(self.ctx.path(name), index_col=0)

    def get_asset_history(self, asset: str, days: int = 20) -> dict:
        tail = self._returns()[asset].tail(min(int(days), 60))
        n = len(tail)
        return {f"T-{n - 1 - i}" if i < n - 1 else "T": (None if pd.isna(v) else round(float(v), 6))
                for i, v in enumerate(tail)}

    def get_cross_section(self, offset: int = 0) -> dict:
        row = self._returns().iloc[-1 - int(offset)]
        return {a: (None if pd.isna(v) else round(float(v), 6)) for a, v in row.items()}

    def get_metric(self, metric_id: str) -> dict:
        return self.ctx.read_json("metrics.json")[metric_id]

    def get_breach_history(self, limit_id: str) -> list[dict]:
        rows = self.ctx.state.q("SELECT severity, days_open, peak, closed_on IS NOT NULL AS closed FROM breaches "
                                "WHERE limit_id = ? AND opened_on <= ? ORDER BY opened_on DESC LIMIT 5",
                                limit_id, self.ctx.run["as_of"])
        return [dict(r) for r in rows]

    def get_backtest(self) -> dict:
        hits = [r["hit"] for r in self.ctx.state.q(
            "SELECT hit FROM var_ledger WHERE hit IS NOT NULL AND as_of < ? ORDER BY as_of", self.ctx.run["as_of"])]
        return backtest.summarise(hits)
