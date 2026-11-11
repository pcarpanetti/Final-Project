"""Build the bitemporal vendor feed in data/feed/ from data/raw/ and data/faults.yaml.

Deterministic: running it twice produces byte-identical files.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW, FEED = ROOT / "data" / "raw", ROOT / "data" / "feed"

ASSETS = ["NoDur", "Durbl", "Manuf", "Enrgy", "HiTec", "Telcm", "Shops", "Hlth", "Utils", "Other"]
TARGET = dict(zip(ASSETS, [0.09, 0.04, 0.11, 0.06, 0.24, 0.05, 0.12, 0.13, 0.04, 0.12]))
# The book is anchored at $100m on this date, the eve of the fixed evaluation window, so every row from here
# on is unchanged by adding earlier history. Earlier rows run the same book backwards to the first month end.
BOOK_START = "2019-06-28"
START_NAV = 100_000_000.0
FIRST_RUN_YEAR = "1986"
MIN_HISTORY_DAYS = 501
FEED_TIME, POSITIONS_TIME = "18:00", "18:30"


def iso(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"


def read_raw(name: str) -> tuple[list[str], list[str], np.ndarray]:
    with open(RAW / name, newline="") as f:
        rows = list(csv.reader(f))
    cols = rows[0][1:]
    dates = [iso(r[0]) for r in rows[1:]]
    return dates, cols, np.array([[float(x) for x in r[1:]] for r in rows[1:]]) / 100.0


def market_records(dates, rets, faults):
    """One row per (as_of, asset); corrections are extra rows with a higher vendor_seq."""
    index = {d: i for i, d in enumerate(dates)}
    by_day = {f["as_of"]: f for f in faults}
    out = []
    for d in dates:
        fault = by_day.get(d)
        ftype = fault["type"] if fault else None
        for j, asset in enumerate(ASSETS):
            true_ret = float(rets[index[d], j])
            published = f"{d}T{FEED_TIME}"
            hit = fault is not None and fault.get("asset") == asset
            if ftype == "late_file":
                published = fault["published_at"]
            if hit and ftype == "missing_row":
                out.append((d, asset, true_ret, fault["corrected_at"], 1))
                continue
            if hit and ftype in ("bad_tick", "stale_repeat"):
                prev = float(rets[index[d] - 1, j])
                shown = fault["reported_ret"] if ftype == "bad_tick" else prev
                out.append((d, asset, shown, published, 1))
                out.append((d, asset, true_ret, fault["corrected_at"], 2))
                continue
            out.append((d, asset, true_ret, published, 1))
    return out


def is_month_end(dates, i: int) -> bool:
    return i + 1 == len(dates) or dates[i + 1][:7] != dates[i][:7]


def simulate_book(dates, rets, first: str = BOOK_START, nav: float = START_NAV, stop: str | None = None):
    """Drift weights daily and rebalance to target on the last trading day of each month."""
    start = dates.index(first)
    target = np.array([TARGET[a] for a in ASSETS])
    weights = target.copy()
    rows = [(first, weights.copy(), nav)]
    for i in range(start + 1, len(dates) if stop is None else dates.index(stop) + 1):
        gross = weights * (1.0 + rets[i])
        nav *= float(gross.sum())
        weights = gross / gross.sum()
        if is_month_end(dates, i):
            weights = target.copy()
        rows.append((dates[i], weights.copy(), nav))
    return rows


def full_book(dates, rets):
    """The same book over all of history, scaled so it joins the anchored book at BOOK_START exactly."""
    first = next(d for i, d in enumerate(dates) if is_month_end(dates, i))
    early = simulate_book(dates, rets, first, 1.0, stop=BOOK_START)
    scale = START_NAV / early[-1][2]
    return [(d, w, nav * scale) for d, w, nav in early if d < BOOK_START] + simulate_book(dates, rets)


def write_csv(path: Path, header: list[str], rows) -> None:
    with open(path, "w", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main() -> None:
    faults = yaml.safe_load((ROOT / "data" / "faults.yaml").read_text(encoding="utf-8"))
    dates, cols, rets = read_raw("ff_industry10_vw_daily_pct.csv")
    assert cols == ASSETS
    FEED.mkdir(exist_ok=True)

    records = market_records(dates, rets, faults)
    write_csv(FEED / "market.csv", ["as_of", "asset", "ret", "published_at", "vendor_seq"],
              [(d, a, f"{r:.6f}", p, s) for d, a, r, p, s in records])

    fdates, fcols, frets = read_raw("ff_factors_daily_pct.csv")
    assert fdates == dates
    late = {f["as_of"]: f["published_at"] for f in faults if f["type"] == "late_file"}
    write_csv(FEED / "factors.csv", ["as_of", "factor", "ret", "published_at"],
              [(d, c, f"{frets[i, j]:.6f}", late.get(d, f"{d}T{FEED_TIME}"))
               for i, d in enumerate(fdates) for j, c in enumerate(fcols)])

    breaks = {f["as_of"]: f for f in faults if f["type"] == "positions_break"}
    prows = []
    for d, w, nav in full_book(dates, rets):
        published = f"{d}T{POSITIONS_TIME}"
        fault = breaks.get(d)
        for a, weight in zip(ASSETS, w):
            if fault:
                prows.append((d, a, f"{weight * fault['bad_weight_scale']:.8f}", f"{nav:.2f}", published, 1))
                prows.append((d, a, f"{weight:.8f}", f"{nav:.2f}", fault["corrected_at"], 2))
            else:
                prows.append((d, a, f"{weight:.8f}", f"{nav:.2f}", published, 1))
    write_csv(FEED / "positions.csv", ["as_of", "asset", "weight", "nav", "published_at", "vendor_seq"], prows)

    notes = [(f["as_of"], f"{f['as_of']}T{FEED_TIME}", f["asset"], " ".join(f["note"].split()))
             for f in faults if f["type"] == "note_injection"]
    for f in faults:
        if "corrected_at" in f and f["type"] != "positions_break":
            notes.append((f["as_of"], f["corrected_at"], f.get("asset", ""),
                          "Vendor correction issued for this date."))
    write_csv(FEED / "vendor_notes.csv", ["as_of", "published_at", "asset", "note"], sorted(notes))

    write_csv(FEED / "calendar.csv", ["date"], [(d,) for d in dates])
    first_run = next(d for d in dates if d.startswith(FIRST_RUN_YEAR))
    assert dates.index(first_run) >= MIN_HISTORY_DAYS, "not enough history before the first run day"
    meta = {"first_run_day": first_run, "last_day": dates[-1], "history_from": dates[0],
            "source": "Kenneth R. French Data Library, CRSP vintage 202609"}
    (FEED / "meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"market rows {len(records)}, position rows {len(prows)}, notes {len(notes)}, days {len(dates)}")


if __name__ == "__main__":
    main()
