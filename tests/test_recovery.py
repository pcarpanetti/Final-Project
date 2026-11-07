"""A crash at any point must lead to the same result as no crash, with no action repeated."""
import pytest

from conftest import eod, tree_digest
from riskwatch import crash
from riskwatch.controller import Controller

DAY = "2020-03-16"          # hard breaches, so the approval gate and breach notice both fire
DQ_DAY = "2020-01-16"       # the injected bad tick, so the data steward runs
CODE_STAGES = ["ingest", "dq_checks", "dq_apply", "risk_engine", "limit_check", "register", "verify",
               "finalise_memo", "gate_policy", "publish"]
AGENT_STAGES = ["analyst", "writer", "reviewer"]
POINTS = ([(DAY, f"{s}:{p}") for s in CODE_STAGES for p in ("started", "work_done", "mid_commit", "committed")]
          + [(DAY, f"{s}:{p}") for s in AGENT_STAGES for p in ("llm_returned", "llm_journaled", "work_done", "committed")]
          + [(DQ_DAY, f"dq_triage:{p}") for p in ("llm_returned", "llm_journaled", "work_done", "committed")]
          + [(DAY, "publish:outbox_written"), (DAY, "publish:delivered")])


def finish(env, run_id):
    """Drive to the end, approving as a human would."""
    ctl = Controller(env)
    status = ctl.drive(run_id)
    if status == "awaiting_approval":
        status = ctl.decide(run_id, "approve", "tester")
    return status


@pytest.fixture(scope="module")
def controls(tmp_path_factory, bundle, store):
    """One uninterrupted run per day, computed once, to compare every crashed run against."""
    from riskwatch.config import ROOT, Paths, bundle_hash
    from riskwatch.controller import Env
    cache = {}

    def get(day):
        if day in cache:
            return cache[day]
        home = tmp_path_factory.mktemp("control")
        env = Env(Paths(ROOT, home, home / "v", ROOT / "data" / "feed"), bundle, bundle_hash(bundle), store=store,
                  mode="replay", sleep=lambda s: None, durable=False)
        _, run_id, _ = eod(env, day)
        assert finish(env, run_id) == "completed"
        cache[day] = {
            "artifacts": tree_digest(home / "artifacts" / run_id),
            "published": tree_digest(home / "published"),
            "llm_calls": env.state.llm_usage(run_id)["calls"],
            "breaches": [tuple(r) for r in env.state.q("SELECT * FROM breaches ORDER BY breach_id")],
            "ledger": [tuple(r) for r in env.state.q("SELECT * FROM var_ledger ORDER BY as_of")],
        }
        env.close()
        return cache[day]

    return get


@pytest.mark.parametrize("day,point", POINTS)
def test_crash_at_any_point_resumes_to_the_identical_result(day, point, monkeypatch, make_env, paths, controls):
    control = controls(day)
    env = make_env()
    monkeypatch.setenv("RISKWATCH_CRASH_AT", point)
    monkeypatch.setenv("RISKWATCH_CRASH_MODE", "raise")
    run_id = f"eod-{day}"
    with pytest.raises(crash.SimulatedCrash):
        _, _, status = eod(env, day)
        if status == "awaiting_approval":
            Controller(env).decide(run_id, "approve", "tester")
    monkeypatch.delenv("RISKWATCH_CRASH_AT")
    env.close()

    env = make_env()  # a new process would reconnect to the same state
    assert finish(env, run_id) == "completed"
    assert tree_digest(paths.artifacts / run_id) == control["artifacts"]
    assert tree_digest(paths.published) == control["published"]
    assert env.state.llm_usage(run_id)["calls"] == control["llm_calls"]
    assert [tuple(r) for r in env.state.q("SELECT * FROM breaches ORDER BY breach_id")] == control["breaches"]
    assert [tuple(r) for r in env.state.q("SELECT * FROM var_ledger ORDER BY as_of")] == control["ledger"]


def test_finished_llm_calls_are_replayed_not_repaid(monkeypatch, make_env):
    env = make_env()
    monkeypatch.setenv("RISKWATCH_CRASH_AT", "reviewer:work_done")
    monkeypatch.setenv("RISKWATCH_CRASH_MODE", "raise")
    with pytest.raises(crash.SimulatedCrash):
        eod(env, DAY)
    monkeypatch.delenv("RISKWATCH_CRASH_AT")
    run_id = f"eod-{DAY}"
    before = env.state.llm_usage(run_id)["calls"]
    finish(env, run_id)
    assert env.state.llm_usage(run_id)["calls"] == before
    assert env.state.q("SELECT 1 FROM events WHERE type = 'llm_replayed'")


def test_publish_crash_does_not_deliver_twice(monkeypatch, make_env, paths):
    env = make_env()
    _, run_id, _ = eod(env, DAY)
    monkeypatch.setenv("RISKWATCH_CRASH_AT", "publish:delivered")
    monkeypatch.setenv("RISKWATCH_CRASH_MODE", "raise")
    with pytest.raises(crash.SimulatedCrash):
        Controller(env).decide(run_id, "approve", "tester")
    monkeypatch.delenv("RISKWATCH_CRASH_AT")
    assert finish(env, run_id) == "completed"
    delivered = env.state.q("SELECT * FROM events WHERE type = 'delivered' AND run_id = ?", run_id)
    assert len([e for e in delivered if "memo:" in e["detail"]]) == 1
    assert env.state.q("SELECT 1 FROM events WHERE type = 'delivery_suppressed'")


def test_corrupt_artifact_is_detected_and_rebuilt(make_env, paths):
    env = make_env()
    _, run_id, status = eod(env, DAY)
    assert status == "awaiting_approval"
    memo = paths.artifacts / run_id / "memo_final.md"
    original = memo.read_text(encoding="utf-8")
    memo.write_text("tampered", encoding="utf-8")
    Controller(env).drive(run_id)
    assert memo.read_text(encoding="utf-8") == original
    assert env.state.q("SELECT 1 FROM events WHERE type = 'artifact_corrupt'")


def test_corruption_upstream_of_a_side_effect_halts_instead_of_redoing_it(make_env, paths):
    env = make_env()
    _, run_id, _ = eod(env, DAY)
    (paths.artifacts / run_id / "metrics.json").write_text("{}", encoding="utf-8")
    assert Controller(env).drive(run_id) == "halted_error"
    assert env.state.q("SELECT 1 FROM escalations WHERE run_id = ?", run_id)


def test_second_controller_is_refused_until_takeover(make_env):
    from riskwatch.state import LeaseHeld
    first, second = make_env(), make_env()
    first.state.acquire_lease(300)
    with pytest.raises(LeaseHeld):
        second.state.acquire_lease(300)
    second.state.acquire_lease(300, takeover=True)
    assert second.state.q("SELECT 1 FROM events WHERE type = 'lease_takeover'")
