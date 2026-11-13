"""The portfolio: target weights per sleeve, a rebalancing rule, and the daily holdings that follow from them.

The shared feed holds the default book. A workspace may instead run its own book, chosen before its first run.
Here this module plays the fund administrator, as `scripts/build_feed.py` does for the default book: it writes the
workspace's positions file before any run starts, valuing the book from the true sleeve returns. Runs still read
that file only through the point-in-time store, so each day sees only the holdings published by its cutoff.
"""
from __future__ import annotations

import bisect
import csv
import json
import math
import re
import shutil

import numpy as np

from .pit import PointInTimeStore, write_positions

ASSETS = ["NoDur", "Durbl", "Manuf", "Enrgy", "HiTec", "Telcm", "Shops", "Hlth", "Utils", "Other"]
LABELS = dict(zip(ASSETS, ["Consumer non-durables", "Consumer durables", "Manufacturing", "Energy", "Business equipment",
                           "Telecoms", "Retail and wholesale", "Healthcare", "Utilities", "Other"]))
DEFAULT_TARGET = dict(zip(ASSETS, [0.09, 0.04, 0.11, 0.06, 0.24, 0.05, 0.12, 0.13, 0.04, 0.12]))
DEFAULT_NAV = 100_000_000.0
REBALANCE = ("monthly", "quarterly", "none")
DEFAULT = {"targets": DEFAULT_TARGET, "nav": DEFAULT_NAV, "rebalance": "monthly", "changes": []}
POSITIONS_TIME = "18:30"    # the administrator publishes after the 18:00 vendor file
RAW_RETURNS = "ff_industry10_vw_daily_pct.csv"
SUM_TOLERANCE = 1e-6
MAX_NAV = 1e12


class BookError(ValueError):
    """A portfolio that cannot be run, with a message fit to show the user."""


def is_month_end(dates: list[str], i: int) -> bool:
    return i + 1 == len(dates) or dates[i + 1][:7] != dates[i][:7]


def is_rebalance_day(dates: list[str], i: int, rule: str) -> bool:
    if rule == "none" or not is_month_end(dates, i):
        return False
    return rule == "monthly" or dates[i][5:7] in ("03", "06", "09", "12")


def simulate(dates, rets, first: str, nav: float, target, rebalance: str = "monthly", changes: dict | None = None,
             stop: str | None = None) -> list[tuple]:
    """Drift weights daily and trade back to target on each rebalance day. On a change date the book trades to the
    new target at that day's close, and later rebalances use it. Rows are (date, weights after trading, NAV)."""
    changes = changes or {}
    start = dates.index(first)
    weights = target.copy()
    rows = [(first, weights.copy(), nav)]
    for i in range(start + 1, len(dates) if stop is None else dates.index(stop) + 1):
        gross = weights * (1.0 + rets[i])
        nav *= float(gross.sum())
        weights = gross / gross.sum()
        if dates[i] in changes:
            target = changes[dates[i]]
            weights = target.copy()
        elif is_rebalance_day(dates, i, rebalance):
            weights = target.copy()
        rows.append((dates[i], weights.copy(), nav))
    return rows


def vector(targets: dict) -> np.ndarray:
    return np.array([targets[a] for a in ASSETS])


def _weights(raw, what: str) -> dict:
    if not isinstance(raw, dict) or set(raw) != set(ASSETS):
        raise BookError(f"{what} need a weight for each of the ten sleeves.")
    out = {}
    for a in ASSETS:
        w = raw[a]
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w):
            raise BookError(f"{what}: the weight for {LABELS[a]} is not a number.")
        if w < 0:
            raise BookError(f"{what}: the weight for {LABELS[a]} is negative. Short positions are not supported.")
        out[a] = round(float(w), 10)
    total = sum(out.values())
    if abs(total - 1.0) > SUM_TOLERANCE:
        raise BookError(f"{what} add up to {total:.2%}, not 100%.")
    return out


def validate(spec, calendar: list[str], start: str) -> dict | None:
    """Check a book and put it in standard form. Returns None for the default book, which the shared feed holds."""
    if not isinstance(spec, dict):
        raise BookError("The portfolio is missing or malformed.")
    targets = _weights(spec.get("targets"), "The target weights")
    nav = spec.get("nav", DEFAULT_NAV)
    if isinstance(nav, bool) or not isinstance(nav, (int, float)) or not 0 < nav <= MAX_NAV:
        raise BookError("The starting NAV must be a positive amount, at most $1 trillion.")
    rebalance = spec.get("rebalance", "monthly")
    if rebalance not in REBALANCE:
        raise BookError(f"Rebalancing must be one of {', '.join(REBALANCE)}.")
    changes = {}
    for change in spec.get("changes") or []:
        given = change.get("from") if isinstance(change, dict) else None
        if not isinstance(given, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", given):
            raise BookError("Each change of targets needs a date.")
        i = bisect.bisect_left(calendar, given)  # a weekend or holiday moves to the next trading day
        if i == len(calendar):
            raise BookError(f"The change of targets on {given} is after the last day of data, {calendar[-1]}.")
        day = calendar[i]
        if day <= start:
            raise BookError(f"The change of targets on {given} must come after the first day, {start}.")
        if day in changes:
            raise BookError(f"Two changes of targets fall on {day}.")
        changes[day] = _weights(change.get("targets"), f"The targets from {day}")
    out = {"targets": targets, "nav": float(nav), "rebalance": rebalance,
           "changes": [{"from": d, "targets": changes[d]} for d in sorted(changes)]}
    return None if out == DEFAULT else out


def describe(spec: dict | None) -> list[str]:
    """Markdown lines saying which book a workspace ran: its targets, size, rebalancing and changes."""
    own = spec is not None
    spec = spec or DEFAULT
    every = {"monthly": "each month end", "quarterly": "each quarter end", "none": "never"}[spec["rebalance"]]
    lines = [f"{'Own portfolio' if own else 'Default portfolio'}: ${spec['nav'] / 1e6:,.1f}m at launch, rebalanced to target {every}.",
             "", "| Sleeve | Target |" + "".join(f" From {c['from']} |" for c in spec["changes"]),
             "|---|---|" + "---|" * len(spec["changes"])]
    lines += [f"| {LABELS[a]} | {spec['targets'][a]:.1%} |" + "".join(f" {c['targets'][a]:.1%} |" for c in spec["changes"])
              for a in ASSETS]
    return lines


def load(paths) -> dict | None:
    """The workspace's own book, or None when it runs the default book."""
    path = paths.book / "book.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def read_returns(root, dates: list[str]) -> np.ndarray:
    with open(root / "data" / "raw" / RAW_RETURNS, newline="") as f:
        rows = list(csv.reader(f))
    if rows[0][1:] != ASSETS or [f"{r[0][:4]}-{r[0][4:6]}-{r[0][6:]}" for r in rows[1:]] != dates:
        raise BookError("The raw return file does not match the feed calendar. Rebuild the feed.")
    return np.array([[float(x) for x in r[1:]] for r in rows[1:]]) / 100.0


def adopt(env, spec, start: str) -> None:
    """Give a fresh workspace its book. A workspace keeps the book it began with: changing it means starting over."""
    begun = env.state.get_kv("book_start")
    spec = validate(spec, env.store.calendar, begun or start)
    if begun:
        if spec != load(env.paths):
            raise BookError("This workspace already runs a different portfolio. Start over to change it.")
        return
    shutil.rmtree(env.paths.book, ignore_errors=True)
    env.state.set_kv("launch_nav", "")
    if spec is None:
        env.store = PointInTimeStore(env.paths.data)
        return
    launch = env.store.previous_day(start)
    if launch is None:
        raise BookError(f"There is no trading day before {start} to launch the book.")
    dates = env.store.calendar
    changes = {c["from"]: vector(c["targets"]) for c in spec["changes"]}
    rows = simulate(dates, read_returns(env.paths.root, dates), launch, spec["nav"], vector(spec["targets"]),
                    spec["rebalance"], changes)
    write_positions(env.paths.book, [(d, a, f"{w:.8f}", f"{nav:.2f}", f"{d}T{POSITIONS_TIME}", 1)
                                     for d, ws, nav in rows for a, w in zip(ASSETS, ws)])
    (env.paths.book / "book.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
    env.state.set_kv("launch_nav", repr(spec["nav"]))
    env.store = PointInTimeStore(env.paths.data, env.paths.book)
