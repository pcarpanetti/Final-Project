"""Any period from 1986 to 2026: the data range, the history each run keeps, the fund launch, the scheduler."""
import json

import pandas as pd
import pytest

from conftest import eod
from riskwatch.config import ROOT
from riskwatch.scheduler import tick
from riskwatch.stages.pipeline import LAUNCH_NAV, history_days


def inputs(paths, run_id, name):
    return pd.read_csv(paths.artifacts / run_id / "inputs" / name, index_col=0)


def test_feed_runs_from_1984_and_runs_may_start_in_1986(store):
    assert store.calendar[0] == "1984-01-03" and store.calendar[-1] == "2026-09-30"
    assert store.meta["first_run_day"] == "1986-01-02"
    assert store.calendar.index("1986-01-02") >= 501


def test_book_is_anchored_at_100m_on_the_eve_of_the_test_window(store):
    """Adding earlier history must not move the fixed evaluation window."""
    nav = store.positions[store.positions.vendor_seq == 1].groupby("as_of").nav.first()
    assert nav.loc["2019-06-28"] == 100_000_000.0
    assert nav.index[0] == "1984-01-31"


def test_a_run_keeps_only_the_history_its_risk_model_uses(make_env, paths, bundle):
    _, run_id, _ = eod(make_env(), "2020-03-16")
    returns = inputs(paths, run_id, "returns.csv")
    assert len(returns) == history_days(bundle["risk_model"]) == 501
    assert returns.index[-1] == "2020-03-16"
    assert list(inputs(paths, run_id, "weights.csv").index) == ["2020-03-13", "2020-03-16"]


def test_fund_launches_at_100m_the_day_before_the_workspace_starts(make_env, paths):
    env = make_env()
    env.state.set_kv("book_start", "2020-03-16")
    _, run_id, _ = eod(env, "2020-03-16")
    nav = inputs(paths, run_id, "nav.csv").iloc[:, 0]
    assert nav.index[0] == "2020-03-13" and nav.iloc[0] == LAUNCH_NAV
    metrics = json.loads((paths.artifacts / run_id / "metrics.json").read_text(encoding="utf-8"))
    # Drawdown is from the launch, not from the February 2020 peak a year-long book would have seen.
    assert metrics["drawdown"]["value"] == pytest.approx(-metrics["daily_return"]["value"], abs=0.002)
    assert metrics["nav_usd"]["value"] == pytest.approx(LAUNCH_NAV * (1 + metrics["daily_return"]["value"]), rel=0.002)


def test_black_monday_1987_runs_end_to_end(make_env, paths):
    env = make_env()
    env.state.set_kv("book_start", "1987-10-19")
    _, run_id, status = eod(env, "1987-10-19")
    metrics = json.loads((paths.artifacts / run_id / "metrics.json").read_text(encoding="utf-8"))
    limits = json.loads((paths.artifacts / run_id / "limit_status.json").read_text(encoding="utf-8"))
    assert metrics["daily_return"]["value"] < -0.15
    assert limits["status"] == "BREACH" and status == "awaiting_approval"
    assert (paths.artifacts / run_id / "memo_final.md").read_text(encoding="utf-8").startswith("# Daily Risk Memo: 1987-10-19")


def test_scheduler_resumes_from_its_cursor_and_still_creates_month_end_reviews(make_env):
    env = make_env()
    env.state.set_kv("book_start", "2020-01-30")
    for now in ("2020-01-30T20:00", "2020-01-31T20:00", "2020-02-03T09:30"):
        tick(env, now)
    assert env.state.get_kv("scheduled_to") == "2020-01-31"
    runs = [r["run_id"] for r in env.state.q("SELECT run_id FROM runs ORDER BY run_id")]
    assert runs == ["eod-2020-01-30", "eod-2020-01-31", "monthly-2020-01"]


def test_an_override_older_than_the_history_window_is_ignored_not_added(make_env, paths):
    env = make_env()
    env.state.x("INSERT INTO dq_overrides VALUES(?,?,?,?,?)", "2015-06-01", "Telcm", "zero_return", "", "old")
    _, run_id, _ = eod(env, "2020-03-16")
    returns = inputs(paths, run_id, "returns.csv")
    assert "2015-06-01" not in returns.index and returns.index.is_monotonic_increasing


def test_feed_rebuild_is_reproducible():
    """build_feed.py must give the committed files exactly, so the data can be checked from the source."""
    import hashlib
    import subprocess
    import sys
    feed = ROOT / "data" / "feed"
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(feed.iterdir())}
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_feed.py")], check=True, capture_output=True)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(feed.iterdir())}
    assert before == after
