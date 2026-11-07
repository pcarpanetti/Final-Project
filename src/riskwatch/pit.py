"""Point-in-time store: the only way any stage or agent tool reads market data.

Every read takes a cutoff, and a row published after that cutoff does not exist for the caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class Snapshot:
    as_of: str
    cutoff: str
    returns: pd.DataFrame        # dates x assets; NaN where a row is missing
    published: pd.DataFrame      # dates x assets; published_at of the row in use
    factors: pd.DataFrame
    weights: pd.DataFrame        # dates x assets
    nav: pd.Series
    notes: list[dict]
    max_published_at: str


class PointInTimeStore:
    def __init__(self, feed_dir: Path):
        read = lambda name: pd.read_csv(feed_dir / name, dtype={"as_of": str, "published_at": str})
        self.market = read("market.csv")
        self.factors = read("factors.csv")
        self.positions = read("positions.csv")
        self.notes = read("vendor_notes.csv").fillna("")
        self.calendar: list[str] = pd.read_csv(feed_dir / "calendar.csv", dtype=str)["date"].tolist()

    def trading_days(self, start: str, end: str) -> list[str]:
        return [d for d in self.calendar if start <= d <= end]

    def previous_day(self, day: str) -> str | None:
        earlier = [d for d in self.calendar if d < day]
        return earlier[-1] if earlier else None

    def next_day(self, day: str) -> str | None:
        later = [d for d in self.calendar if d > day]
        return later[0] if later else None

    def snapshot(self, as_of: str, cutoff: str) -> Snapshot:
        known = self.market[(self.market.published_at <= cutoff) & (self.market.as_of <= as_of)]
        latest = known.sort_values(["published_at", "vendor_seq"]).groupby(["as_of", "asset"]).tail(1)
        returns = latest.pivot(index="as_of", columns="asset", values="ret").sort_index()
        published = latest.pivot(index="as_of", columns="asset", values="published_at").sort_index()

        f = self.factors[(self.factors.published_at <= cutoff) & (self.factors.as_of <= as_of)]
        factors = f.pivot(index="as_of", columns="factor", values="ret").sort_index()

        p = self.positions[(self.positions.published_at <= cutoff) & (self.positions.as_of <= as_of)]
        p = p.sort_values(["published_at", "vendor_seq"]).groupby(["as_of", "asset"]).tail(1)
        weights = p.pivot(index="as_of", columns="asset", values="weight").sort_index()
        nav = p.groupby("as_of")["nav"].last().sort_index()

        n = self.notes[(self.notes.published_at <= cutoff) & (self.notes.as_of <= as_of)]
        notes = n[n.as_of == as_of].to_dict("records")

        stamps = [known.published_at.max(), f.published_at.max(), p.published_at.max()]
        stamps = [s for s in stamps if isinstance(s, str)]
        return Snapshot(as_of, cutoff, returns, published, factors, weights, nav, notes, max(stamps, default=""))

    def corrections_between(self, after: str, upto: str) -> list[dict]:
        """Market rows that arrived in (after, upto] for a date before the day they were published."""
        m = self.market
        rows = m[(m.published_at > after) & (m.published_at <= upto) & (m.as_of < m.published_at.str[:10])]
        return rows.to_dict("records")
