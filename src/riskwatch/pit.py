"""Point-in-time store: the only way any stage or agent tool reads market data.

Every read takes a cutoff, and a row published after that cutoff does not exist for the caller.
"""
from __future__ import annotations

import bisect
import csv
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

POSITIONS = "positions.csv"
POSITION_COLUMNS = ["as_of", "asset", "weight", "nav", "published_at", "vendor_seq"]


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


def write_positions(folder: Path, rows: list[tuple]) -> None:
    """Write an administrator's positions file, one row per (as_of, asset), in the feed's format."""
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / POSITIONS, "w", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(POSITION_COLUMNS)
        w.writerows(rows)


class PointInTimeStore:
    def __init__(self, feed_dir: Path, book_dir: Path | None = None):
        """With `book_dir` holding its own positions file, those positions replace the feed's default book."""
        read = lambda folder, name: pd.read_csv(folder / name, dtype={"as_of": str, "published_at": str})
        self.market = read(feed_dir, "market.csv")
        self.factors = read(feed_dir, "factors.csv")
        own = book_dir is not None and (book_dir / POSITIONS).exists()
        self.positions = read(book_dir if own else feed_dir, POSITIONS)
        self.notes = read(feed_dir, "vendor_notes.csv").fillna("")
        self.calendar: list[str] = pd.read_csv(feed_dir / "calendar.csv", dtype=str)["date"].tolist()
        meta = feed_dir / "meta.json"
        self.meta: dict = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
        self._corrections: pd.DataFrame | None = None

    def trading_days(self, start: str, end: str) -> list[str]:
        return self.calendar[bisect.bisect_left(self.calendar, start):bisect.bisect_right(self.calendar, end)]

    def previous_day(self, day: str) -> str | None:
        i = bisect.bisect_left(self.calendar, day)
        return self.calendar[i - 1] if i else None

    def next_day(self, day: str) -> str | None:
        i = bisect.bisect_right(self.calendar, day)
        return self.calendar[i] if i < len(self.calendar) else None

    def snapshot(self, as_of: str, cutoff: str, history: int | None = None) -> Snapshot:
        """With `history`, market rows are limited to the last that many trading days up to as_of."""
        known = self.market[(self.market.published_at <= cutoff) & (self.market.as_of <= as_of)]
        f = self.factors[(self.factors.published_at <= cutoff) & (self.factors.as_of <= as_of)]
        p = self.positions[(self.positions.published_at <= cutoff) & (self.positions.as_of <= as_of)]
        stamps = [known.published_at.max(), f.published_at.max(), p.published_at.max()]
        if history:
            since = self.calendar[max(bisect.bisect_right(self.calendar, as_of) - history, 0)]
            known, f = known[known.as_of >= since], f[f.as_of >= since]

        latest = known.sort_values(["published_at", "vendor_seq"]).groupby(["as_of", "asset"]).tail(1)
        returns = latest.pivot(index="as_of", columns="asset", values="ret").sort_index()
        published = latest.pivot(index="as_of", columns="asset", values="published_at").sort_index()

        factors = f.pivot(index="as_of", columns="factor", values="ret").sort_index()

        p = p.sort_values(["published_at", "vendor_seq"]).groupby(["as_of", "asset"]).tail(1)
        weights = p.pivot(index="as_of", columns="asset", values="weight").sort_index()
        nav = p.groupby("as_of")["nav"].last().sort_index()

        n = self.notes[(self.notes.published_at <= cutoff) & (self.notes.as_of <= as_of)]
        notes = n[n.as_of == as_of].to_dict("records")

        stamps = [s for s in stamps if isinstance(s, str)]
        return Snapshot(as_of, cutoff, returns, published, factors, weights, nav, notes, max(stamps, default=""))

    def corrections_between(self, after: str, upto: str) -> list[dict]:
        """Market rows that arrived in (after, upto] for a date before the day they were published."""
        if self._corrections is None:
            m = self.market
            self._corrections = m[m.as_of < m.published_at.str[:10]]
        c = self._corrections
        return c[(c.published_at > after) & (c.published_at <= upto)].to_dict("records")
