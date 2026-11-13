"""A workspace's own portfolio: checked, simulated, read only through the cutoff, and kept apart from the baseline."""
import json

import numpy as np
import pandas as pd
import pytest

from conftest import eod
from riskwatch import book
from riskwatch.config import ROOT, Paths
from riskwatch.pit import PointInTimeStore

EVEN = {a: 0.1 for a in book.ASSETS}
TWO = {**{a: 0.0 for a in book.ASSETS}, "NoDur": 0.5, "Hlth": 0.5}


def spec(**over):
    return {"targets": dict(EVEN), "nav": 50_000_000, "rebalance": "monthly", "changes": [], **over}


def test_the_default_book_reproduces_the_committed_feed(store):
    """build_feed.py and a workspace book share one simulation, so the shared feed must come out unchanged."""
    dates = store.calendar
    rows = book.simulate(dates, book.read_returns(ROOT, dates), "2019-06-28", book.DEFAULT_NAV, book.vector(book.DEFAULT_TARGET))
    p = store.positions.sort_values("vendor_seq").groupby(["as_of", "asset"]).tail(1)
    weights = p.pivot(index="as_of", columns="asset", values="weight").loc["2019-06-28":, book.ASSETS]
    nav = p.groupby("as_of").nav.last().loc["2019-06-28":]
    assert list(weights.index) == [d for d, _, _ in rows]
    assert np.abs(weights.to_numpy() - np.array([w for _, w, _ in rows])).max() < 1e-8
    assert np.abs(nav.to_numpy() - np.array([n for _, _, n in rows])).max() < 0.01


def test_the_default_book_needs_no_file_of_its_own(store):
    assert book.validate(dict(book.DEFAULT, nav=100_000_000), store.calendar, "2020-03-16") is None


@pytest.mark.parametrize("bad, message", [
    (spec(targets={**EVEN, "NoDur": -0.1, "Durbl": 0.3}), "negative"),
    (spec(targets={**EVEN, "NoDur": 0.2}), "add up to 110.00%"),
    (spec(targets={a: 0.1 for a in book.ASSETS[:9]}), "each of the ten sleeves"),
    (spec(targets={**EVEN, "NoDur": "0.1"}), "not a number"),
    (spec(nav=0), "positive"),
    (spec(rebalance="weekly"), "Rebalancing"),
    (spec(changes=[{"from": "2020-03-16", "targets": TWO}]), "after the first day"),
    (spec(changes=[{"from": "2027-01-04", "targets": TWO}]), "after the last day"),
    (spec(changes=[{"from": "2020-03-21", "targets": TWO}, {"from": "2020-03-23", "targets": EVEN}]), "Two changes"),
    (spec(changes=[{"targets": TWO}]), "needs a date"),
    ("not a book", "missing or malformed"),
])
def test_a_book_that_cannot_run_is_refused_with_a_reason(store, bad, message):
    with pytest.raises(book.BookError, match=message):
        book.validate(bad, store.calendar, "2020-03-16")


def test_a_change_on_a_weekend_moves_to_the_next_trading_day(store):
    out = book.validate(spec(changes=[{"from": "2020-03-21", "targets": TWO}]), store.calendar, "2020-03-16")
    assert out["changes"][0]["from"] == "2020-03-23"


def test_rebalancing_follows_the_rule_and_a_change_trades_on_its_date():
    dates = ["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-28", "2020-03-02", "2020-03-31", "2020-04-01", "2020-04-02", "2020-04-03"]
    rets = np.tile(np.linspace(-0.02, 0.03, 10), (len(dates), 1))
    target = book.vector(EVEN)
    drifted = lambda rows, day: not np.allclose(dict((d, w) for d, w, _ in rows)[day], target)
    quarterly = book.simulate(dates, rets, dates[0], 1.0, target, "quarterly")
    assert drifted(quarterly, "2020-01-31") and drifted(quarterly, "2020-02-28") and not drifted(quarterly, "2020-03-31")
    never = book.simulate(dates, rets, dates[0], 1.0, target, "none")
    assert drifted(never, "2020-03-31")
    changed = book.simulate(dates, rets, dates[0], 1.0, target, "monthly", {"2020-04-01": book.vector(TWO)})
    assert np.allclose(changed[6][1], book.vector(TWO)) and not np.allclose(changed[7][1], book.vector(TWO))
    assert all(abs(w.sum() - 1) < 1e-12 for _, w, _ in changed)


def test_a_workspace_runs_its_own_book_from_its_own_launch_nav(make_env, paths):
    env = make_env()
    book.adopt(env, spec(targets=TWO, nav=50_000_000), "2020-03-16")
    env.state.set_kv("book_start", "2020-03-16")
    _, run_id, status = eod(env, "2020-03-16")
    folder = paths.artifacts / run_id / "inputs"
    weights = pd.read_csv(folder / "weights.csv", index_col=0)
    nav = pd.read_csv(folder / "nav.csv", index_col=0).iloc[:, 0]
    assert weights.loc["2020-03-13", "NoDur"] == 0.5 and weights.loc["2020-03-13", "Hlth"] == 0.5
    assert (weights.sum(axis=1) - 1).abs().max() < 1e-6
    assert nav.loc["2020-03-13"] == 50_000_000
    metrics = json.loads((paths.artifacts / run_id / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["weight_max"]["value"] == pytest.approx(0.5, abs=0.02)
    # Half the book in one sleeve breaks the 25% limit, which the default book never does.
    assert status == "awaiting_approval"


def test_a_book_is_read_only_up_to_the_cutoff(make_env):
    env = make_env()
    book.adopt(env, spec(), "2020-03-16")
    assert env.store.snapshot("2020-03-17", "2020-03-17T20:00").weights.index.max() == "2020-03-17"
    assert "2020-03-17" not in env.store.snapshot("2020-03-17", "2020-03-17T18:00").weights.index


def test_a_workspace_keeps_the_book_it_began_with(make_env):
    env = make_env()
    book.adopt(env, spec(), "2020-03-16")
    env.state.set_kv("book_start", "2020-03-16")
    book.adopt(env, spec(), "2020-03-20")  # the same book continues
    for other in (spec(nav=60_000_000), dict(book.DEFAULT)):
        with pytest.raises(book.BookError, match="Start over"):
            book.adopt(env, other, "2020-03-20")


def test_the_evaluation_home_never_sees_a_workspace_book(make_env, paths, tmp_path, store):
    """Evaluation replays in an empty home, so it always runs the shared feed's default book."""
    env = make_env()
    book.adopt(env, spec(targets=TWO), "2020-03-16")
    assert (paths.book / "book.json").exists()
    fresh = Paths(ROOT, tmp_path / "eval-home", tmp_path / "v", ROOT / "data" / "feed")
    shared = PointInTimeStore(fresh.data, fresh.book)
    assert shared.positions.equals(store.positions)
