"""Agent limits, the revision loop, degradation and human gates, driven through real runs."""
import json
import re

import pytest

from conftest import eod
from riskwatch.agents.runtime import parse_reply, validate
from riskwatch.config import deep_merge
from riskwatch.controller import Controller

DAY = "2020-03-16"


def statuses(env, run_id):
    return {r["stage"]: r["status"] for r in env.state.q("SELECT stage, status FROM stages WHERE run_id = ?", run_id)}


def test_reply_parser_tolerates_fences_and_rejects_prose():
    assert parse_reply('```json\n{"action": "final"}\n```') == {"action": "final"}
    assert parse_reply('Here you go: {"action": "final"}') == {"action": "final"}
    with pytest.raises(ValueError):
        parse_reply("no json here")


def test_schema_validation_reports_each_problem():
    schema = {"type": "object", "required": ["a"], "properties": {"b": {"type": "string", "enum": ["x"]}}}
    assert validate({"a": 1, "b": "x"}, schema) == []
    errors = validate({"b": "y"}, schema)
    assert any("required" in e for e in errors) and any("not in" in e for e in errors)


@pytest.mark.parametrize("fault,check", [
    ("omit_breach", "coverage"),
    ("raw_number", "no_typed_numbers"),
    ("trade_instruction", "no_trade_instructions"),
])
def test_bad_first_draft_is_caught_and_revised(make_env, paths, fault, check):
    env = make_env({DAY: {"memo_writer": fault}})
    _, run_id, status = eod(env, DAY)
    assert status == "awaiting_approval"
    first = json.loads((paths.artifacts / run_id / "verification.r0.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in first["checks"] if not c["passed"]] == [check]
    second = json.loads((paths.artifacts / run_id / "verification.r1.json").read_text(encoding="utf-8"))
    assert second["passed"]
    assert env.state.run(run_id)["degraded"] == 0


def test_false_analyst_claim_is_caught_and_only_then_is_the_analyst_rerun(make_env, paths):
    env = make_env({DAY: {"risk_analyst": "false_claim"}})
    _, run_id, _ = eod(env, DAY)
    first = json.loads((paths.artifacts / run_id / "verification.r0.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in first["checks"] if not c["passed"]] == ["evidence_claims"]
    assert env.state.run(run_id)["round"] == 1 and env.state.run(run_id)["degraded"] == 0


def test_reviewer_revision_is_not_answered_from_the_journal(make_env):
    """Regression: the journal once replayed round 0's verdict, so the loop could never finish."""
    env = make_env({DAY: {"reviewer": "revise_once"}})
    _, run_id, status = eod(env, DAY)
    run = env.state.run(run_id)
    assert (status, run["round"], run["degraded"]) == ("awaiting_approval", 1, 0)


def test_revision_loop_is_bounded_then_falls_back_to_a_template(make_env, paths, bundle):
    env = make_env({DAY: {"memo_writer": "always_bad"}})
    _, run_id, status = eod(env, DAY)
    run = env.state.run(run_id)
    assert status == "awaiting_approval"
    assert run["degraded"] == 1 and run["round"] == bundle["policy"]["revision"]["max_rounds"] - 1
    assert "Degraded memo" in (paths.artifacts / run_id / "memo_final.md").read_text(encoding="utf-8")
    assert "degraded_memo" in json.loads((paths.artifacts / run_id / "gate.json").read_text(encoding="utf-8"))["reasons"]


def test_verified_memo_survives_an_unconvinced_reviewer(make_env, paths):
    """Regression from the first real-model run: a memo passing every check was thrown away."""
    env = make_env({DAY: {"reviewer": "always_revise"}})
    _, run_id, status = eod(env, DAY)
    memo = (paths.artifacts / run_id / "memo_final.md").read_text(encoding="utf-8")
    assert status == "awaiting_approval" and env.state.run(run_id)["degraded"] == 1
    assert "[F:F1]" in memo and "## Open reviewer concerns" in memo
    assert "cause of the drawdown" in memo and "Degraded memo" not in memo
    assert "degraded_memo" in json.loads((paths.artifacts / run_id / "gate.json").read_text(encoding="utf-8"))["reasons"]


def test_reviewer_is_told_what_is_new_and_the_prior_values(make_env):
    """Regression: without these facts the reviewer raised objections nothing could resolve."""
    env = make_env()
    eod(env, "2020-03-13")
    requests = spy_on_requests(env)
    eod(env, "2020-03-16")
    facts = next(json.loads(t)["payload"] for t in requests if '"memo"' in t and t.startswith("{"))
    assert facts["first_day_of_history"] is False and "new" in facts["delta"]
    assert all(row["prior_value"] is not None for row in facts["limits"])


@pytest.mark.parametrize("fault,calls_expected", [("outage", 0), ("bad_key", 0)])
def test_provider_failure_still_delivers_the_numbers_to_a_human(make_env, paths, fault, calls_expected):
    env = make_env({DAY: {"provider": fault}})
    _, run_id, status = eod(env, DAY)
    assert status == "awaiting_approval" and env.state.run(run_id)["degraded"] == 1
    assert env.state.llm_usage(run_id)["calls"] == calls_expected
    memo = (paths.artifacts / run_id / "memo_final.md").read_text(encoding="utf-8")
    assert "[L:var99]" in memo and "breach" in memo


def test_transient_errors_are_retried_and_permanent_ones_are_not(make_env):
    env = make_env({DAY: {"provider": "transient_twice"}})
    _, run_id, _ = eod(env, DAY)
    assert env.state.run(run_id)["degraded"] == 0
    assert env.state.q("SELECT 1 FROM events WHERE type = 'llm_transient_error'")
    env2 = make_env({"2020-03-17": {"provider": "bad_key"}})
    _, run2, _ = eod(env2, "2020-03-17")
    assert len(env2.state.q("SELECT 1 FROM events WHERE run_id = ? AND type = 'llm_permanent_error'", run2)) == 1
    assert not env2.state.q("SELECT 1 FROM events WHERE run_id = ? AND type = 'llm_transient_error'", run2)


def test_malformed_reply_is_repaired(make_env):
    env = make_env({DAY: {"risk_analyst": "bad_schema"}})
    _, run_id, _ = eod(env, DAY)
    assert env.state.q("SELECT 1 FROM events WHERE type = 'agent_invalid_reply'")
    assert env.state.run(run_id)["degraded"] == 0


def test_forbidden_tool_is_denied_and_escalated(make_env):
    env = make_env({DAY: {"risk_analyst": "forbidden_tool"}})
    _, run_id, _ = eod(env, DAY)
    assert env.state.q("SELECT 1 FROM events WHERE type = 'tool_denied'")
    assert any("forbidden tool" in r["reason"] for r in env.state.q("SELECT reason FROM escalations"))


def test_call_budget_stops_the_agents_but_not_the_numbers(make_env, bundle):
    tight = deep_merge(bundle, {"policy": {"budgets": {"per_run": {"max_llm_calls": 1}}}})
    env = make_env(the_bundle=tight)
    _, run_id, status = eod(env, DAY)
    assert status == "awaiting_approval"
    assert env.state.run(run_id)["degraded"] == 1
    assert env.state.llm_usage(run_id)["calls"] == 1


def test_clean_day_auto_publishes_and_breach_day_does_not(make_env, paths):
    env = make_env()
    _, _, status = eod(env, "2019-11-05")
    assert status == "completed"
    assert (paths.published / "memos" / "2019-11-05.md").exists()
    _, _, status = eod(env, DAY)
    assert status == "awaiting_approval"
    assert not (paths.published / "memos" / f"{DAY}.md").exists()


def test_rejection_publishes_nothing_but_keeps_the_facts(make_env, paths):
    env = make_env()
    ctl, run_id, _ = eod(env, DAY)
    assert ctl.decide(run_id, "reject", "cro", "not this one") == "rejected"
    assert not (paths.published / "memos" / f"{DAY}.md").exists()
    assert env.state.q("SELECT 1 FROM breaches")


def test_human_change_request_reaches_the_writer_and_returns_to_the_gate(make_env, paths):
    env = make_env()
    ctl, run_id, _ = eod(env, DAY)
    assert ctl.decide(run_id, "request_changes", "cro", "lead with variance") == "awaiting_approval"
    feedback = json.loads((paths.artifacts / run_id / "feedback.r1.json").read_text(encoding="utf-8"))
    assert feedback[0]["note"] == "lead with variance"
    assert len(env.state.q("SELECT 1 FROM approvals WHERE run_id = ?", run_id)) == 2
    assert ctl.decide(run_id, "approve", "cro") == "completed"


def test_approved_memo_cannot_be_swapped_before_publish(make_env, paths):
    env = make_env()
    ctl, run_id, _ = eod(env, DAY)
    gate = paths.artifacts / run_id / "gate.json"
    data = json.loads(gate.read_text(encoding="utf-8"))
    data["sha256"] = "0" * 64
    gate.write_text(json.dumps(data), encoding="utf-8")
    env.state.x("UPDATE stages SET outputs = '{}' WHERE run_id = ? AND stage = 'gate_policy'", run_id)
    assert ctl.decide(run_id, "approve", "cro") == "halted_error"
    assert not (paths.published / "memos" / f"{DAY}.md").exists()


def spy_on_requests(env) -> list[str]:
    seen = []
    real = env.llm.scripted.complete

    def spy(messages, max_tokens, meta):
        seen.extend(m["content"] for m in messages)
        return real(messages, max_tokens, meta)

    env.llm.scripted.complete = spy
    return seen


def test_quarantined_note_never_reaches_a_model(make_env):
    env = make_env()
    seen = spy_on_requests(env)
    _, run_id, _ = eod(env, "2020-05-12")
    assert env.state.stage(run_id, "dq_triage", 0)["status"] == "done"
    assert seen and not any("ignore all previous" in text.lower() for text in seen)


def test_compromised_writer_cannot_declare_all_clear(make_env, paths):
    env = make_env({"2020-05-12": {"memo_writer": "obey_injection"}})
    _, run_id, status = eod(env, "2020-05-12")
    first = json.loads((paths.artifacts / run_id / "verification.r0.json").read_text(encoding="utf-8"))
    assert not first["passed"]
    assert status == "awaiting_approval"
    memo = (paths.artifacts / run_id / "memo_final.md").read_text(encoding="utf-8")
    assert "All limits passed" not in memo and "BREACH" in memo


def test_agents_never_see_a_calendar_date(make_env, store):
    """Model memory is a leak too, so requests must not reveal which day of history this is."""
    env = make_env()
    seen = spy_on_requests(env)
    eod(env, "2020-01-16")
    assert seen and not any(re.search(r"20\d\d-\d\d-\d\d", text) for text in seen)
