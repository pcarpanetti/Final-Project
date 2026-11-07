"""Point-in-time reads, data quality decisions and scheduling triggers."""
import json
from pathlib import Path

import pytest
import yaml

from conftest import eod
from riskwatch.config import ROOT
from riskwatch.controller import Controller
from riskwatch.improve.leakage import negative_control, perturbation_test
from riskwatch.scheduler import circuit_open, tick


def test_snapshot_shows_the_original_value_until_the_correction_is_published(store):
    before = store.snapshot("2020-01-16", "2020-01-16T20:00")
    after = store.snapshot("2020-01-16", "2020-01-17T10:00")
    assert before.returns.at["2020-01-16", "Telcm"] == pytest.approx(0.187)
    assert after.returns.at["2020-01-16", "Telcm"] == pytest.approx(0.0072)


def test_snapshot_contains_nothing_after_the_as_of_date_or_cutoff(store):
    snap = store.snapshot("2020-03-16", "2020-03-16T20:00")
    assert snap.returns.index.max() == "2020-03-16"
    assert snap.max_published_at <= "2020-03-16T20:00"
    assert snap.weights.index.max() == "2020-03-16"


def test_future_perturbation_leaves_every_artifact_identical(bundle, store):
    result = perturbation_test(bundle, "t", ROOT, store, ["2020-03-16"])
    assert result["passed"] and result["days"][0]["files"] > 10


def test_negative_control_proves_the_leak_test_can_fail(bundle, store):
    assert negative_control(bundle, "t", ROOT, store, "2020-03-16")["leak_detected"]


def test_production_code_never_reads_the_fault_labels():
    src = ROOT / "src" / "riskwatch"
    offenders = [p.name for p in src.rglob("*.py") if "faults.yaml" in p.read_text(encoding="utf-8")
                 and p.parent.name != "improve"]
    assert offenders == []


def test_all_market_data_goes_through_the_point_in_time_store():
    src = ROOT / "src" / "riskwatch"
    offenders = [p.name for p in src.rglob("*.py") if p.name != "pit.py"
                 and any(name in p.read_text(encoding="utf-8") for name in ("market.csv", "positions.csv"))]
    assert offenders == []


def dq_items(paths, day):
    path = paths.artifacts / f"eod-{day}" / "dq_summary.json"
    return {i["id"]: i for i in json.loads(path.read_text(encoding="utf-8"))["items"]}


def test_bad_tick_is_zeroed(make_env, paths):
    eod(make_env(), "2020-01-16")
    assert dq_items(paths, "2020-01-16")["outlier:Telcm"]["action"] == "zero_return"


def test_real_sector_collapse_is_escalated_and_never_overwritten(make_env, paths):
    """Regression: the first replay zeroed the genuine -19.7% energy move of 2020-03-09."""
    eod(make_env(), "2020-03-09")
    assert dq_items(paths, "2020-03-09")["outlier:Enrgy"]["action"] == "escalate"
    clean = (paths.artifacts / "eod-2020-03-09" / "clean_returns.csv").read_text(encoding="utf-8")
    assert "-0.1968" in clean.rstrip().rsplit("\n", 1)[-1]


def test_stale_repeat_is_never_silently_accepted(make_env, paths):
    """Regression: a resent value looks plausible, so plausibility must not clear it."""
    eod(make_env(), "2020-02-19")
    assert dq_items(paths, "2020-02-19")["stale_repeat:Utils"]["action"] == "escalate"


def test_override_stands_until_the_vendor_corrects_the_record(make_env, paths):
    env = make_env()
    ctl, run_id, _ = eod(env, "2020-01-16")
    ctl.decide(run_id, "approve", "t")
    same_day = paths.artifacts / run_id / "clean_returns.csv"
    assert ",0," in same_day.read_text(encoding="utf-8").rstrip().rsplit("\n", 1)[-1]
    _, nxt, _ = eod(env, "2020-01-17")
    manifest = json.loads((paths.artifacts / nxt / "inputs" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["overrides_applied"] == []  # the 09:30 correction replaced the judged record


def replay_day(env, day, times=("09:30", "20:00", "22:00")):
    ctl = Controller(env)
    for t in times:
        tick(env, f"{day}T{t}")
        for row in env.state.q("SELECT run_id FROM runs WHERE status = 'awaiting_approval'"):
            ctl.decide(row["run_id"], "approve", "t")


def test_late_file_blocks_then_extends_the_cutoff_with_a_record(make_env):
    env = make_env()
    env.state.set_kv("book_start", "2020-03-04")
    tick(env, "2020-03-04T20:00")
    assert env.state.run("eod-2020-03-04")["status"] == "blocked_input"
    replay_day(env, "2020-03-04", ("22:00",))
    run = env.state.run("eod-2020-03-04")
    assert run["status"] == "completed" and run["cutoff"] == "2020-03-04T22:00"
    assert env.state.q("SELECT 1 FROM events WHERE type = 'cutoff_extended'")


def test_data_never_arriving_stops_at_the_deadline_and_escalates(make_env):
    env = make_env()
    env.state.set_kv("book_start", "2020-03-04")
    tick(env, "2020-03-04T20:00")
    tick(env, "2020-03-04T23:45")
    assert env.state.run("eod-2020-03-04")["status"] == "halted_no_input"
    assert env.state.one("SELECT severity FROM escalations")["severity"] == "critical"


def test_positions_that_do_not_reconcile_block_the_run(make_env):
    env = make_env()
    env.state.set_kv("book_start", "2020-06-02")
    tick(env, "2020-06-02T20:00")
    run = env.state.run("eod-2020-06-02")
    assert run["status"] == "blocked_input" and "reconciliation" in run["halted_reason"]


def test_vendor_correction_triggers_exactly_one_restatement(make_env, paths):
    env = make_env()
    env.state.set_kv("book_start", "2020-01-16")
    replay_day(env, "2020-01-16")
    replay_day(env, "2020-01-17")
    tick(env, "2020-01-17T22:30")
    runs = env.state.q("SELECT run_id, status FROM runs WHERE workflow = 'restate'")
    assert len(runs) == 1 and runs[0]["status"] == "completed"
    assert (paths.artifacts / runs[0]["run_id"] / "restatement.json").exists()


def test_scheduler_catches_up_after_downtime_with_original_cutoffs(make_env):
    env = make_env()
    env.state.set_kv("book_start", "2019-11-04")
    tick(env, "2019-11-07T21:00")
    rows = env.state.q("SELECT run_id, cutoff FROM runs WHERE workflow = 'eod' ORDER BY as_of")
    assert [r["run_id"] for r in rows] == ["eod-2019-11-04", "eod-2019-11-05", "eod-2019-11-06", "eod-2019-11-07"]
    assert rows[0]["cutoff"] == "2019-11-04T20:00"


def test_ticks_are_idempotent(make_env):
    env = make_env()
    env.state.set_kv("book_start", "2019-11-05")
    tick(env, "2019-11-05T20:00")
    tick(env, "2019-11-05T20:00")
    assert len(env.state.q("SELECT 1 FROM runs")) == 1
    assert len(env.state.q("SELECT 1 FROM outbox")) == 1


def test_later_run_waits_for_the_register_of_the_day_before(make_env):
    env = make_env()
    ctl = Controller(env)
    ctl.create_run("eod-2020-03-16", "eod", "2020-03-16", "2020-03-16T20:00", "t")
    ctl.create_run("eod-2020-03-17", "eod", "2020-03-17", "2020-03-17T20:00", "t")
    assert ctl.drive("eod-2020-03-17") == "blocked_dependency"


def test_pending_approval_does_not_block_the_next_day(make_env):
    env = make_env()
    eod(env, "2020-03-16")
    _, _, status = eod(env, "2020-03-17")
    assert status == "awaiting_approval"
    assert len(env.state.q("SELECT 1 FROM approvals WHERE decision IS NULL")) == 2


def test_unanswered_approval_escalates_after_the_sla(make_env):
    env = make_env()
    env.state.set_kv("book_start", "2020-03-16")
    tick(env, "2020-03-16T20:00")
    tick(env, "2020-03-17T11:00")
    assert any("backup approver" in r["reason"] for r in env.state.q("SELECT reason FROM escalations"))


def test_circuit_breaker_opens_after_repeated_halts(make_env):
    env = make_env()
    for i in range(3):
        env.state.create_run(f"eod-2020-01-0{i + 2}", "eod", f"2020-01-0{i + 2}", "x", "v", "t")
        env.state.set_run(f"eod-2020-01-0{i + 2}", status="halted_error")
    assert circuit_open(env)
    result = tick(env, "2020-01-06T20:00")
    assert result["circuit"] == "open" and result["runs"] == {}


def test_workflow_files_are_valid_and_every_stage_has_code(bundle):
    from riskwatch.config import validate_workflows
    from riskwatch.stages.pipeline import PREDICATES, STAGES
    validate_workflows(bundle)
    for wf in bundle["workflows"].values():
        for stage in wf["stages"]:
            assert stage["kind"] == "gate" or stage["name"] in STAGES
            assert stage.get("when") is None or stage["when"] in PREDICATES


def test_no_role_has_a_tool_that_writes(bundle):
    from riskwatch.agents.tools import Tools
    available = {n for n in dir(Tools) if n.startswith("get_")}
    for spec in bundle["agents"]["roles"].values():
        assert set(spec["tools"]) <= available
