"""Version control of behaviour, and the accept/reject decision."""
import copy

import pytest

from riskwatch.config import bundle_hash, deep_merge
from riskwatch.improve import versions
from riskwatch.improve.evaluate import decide

RULES = {
    "hard_gates": {"min_faults_handled_rate": 1.0, "max_extra_false_dq_overrides": 0, "max_halted_runs": 0},
    "primary": {"required": True},
    "guardrails": {"max_rel_increase_avg_var": 0.25, "max_rel_increase_hard_breach_days": 0.30,
                   "max_rel_increase_tokens": 0.20},
}


def card(**changes):
    base = {"var_exceptions": 10, "var_expected": 2.5, "kupiec_p": 0.001, "avg_var99": 0.04, "hard_breach_days": 100,
            "faults_handled_rate": 1.0, "faults_handled": {"F1": True}, "false_dq_overrides": 0, "halted_runs": 0,
            "cutoff_violations": 0, "llm_tokens": 1000}
    return {"version": "cand", "scorecard": {**base, **changes}, "leakage": {"passed": True}}


BASE = {**card(), "version": "base"}
BETTER = dict(var_exceptions=5, kupiec_p=0.1)


def test_a_real_improvement_is_accepted():
    assert decide(card(**BETTER), BASE, RULES)["decision"] == "accept"


def test_no_improvement_is_rejected():
    assert decide(card(), BASE, RULES)["decision"] == "reject"


@pytest.mark.parametrize("change,text", [
    (dict(faults_handled_rate=0.8, faults_handled={"F1": False}), "ground-truth"),
    (dict(false_dq_overrides=1), "false DQ"),
    (dict(halted_runs=1), "halted"),
    (dict(cutoff_violations=1), "cutoff"),
    (dict(avg_var99=0.06), "average VaR"),
    (dict(hard_breach_days=140), "hard breach days"),
    (dict(llm_tokens=1300), "tokens"),
])
def test_each_gate_can_reject_an_otherwise_better_candidate(change, text):
    verdict = decide(card(**BETTER, **{k: v for k, v in change.items()}), BASE, RULES)
    assert verdict["decision"] == "reject" and any(text in r for r in verdict["reasons"])


def test_leak_rejects_even_with_better_numbers():
    candidate = card(**BETTER)
    candidate["leakage"] = {"passed": False}
    assert decide(candidate, BASE, RULES)["decision"] == "reject"


def test_decision_is_deterministic():
    assert decide(card(**BETTER), BASE, RULES) == decide(card(**BETTER), BASE, RULES)


@pytest.fixture
def registry(paths, bundle):
    v1 = versions.register(paths, bundle, "first")
    versions.activate_first(paths, v1, "tester")
    candidate = deep_merge(bundle, {"risk_model": {"var": {"method": "age_weighted"}}})
    v2 = versions.register(paths, candidate, "second")
    return v1, v2


def test_promotion_requires_a_passing_evaluation_against_the_active_version(paths, registry):
    v1, v2 = registry
    with pytest.raises(versions.VersionError):
        versions.promote(paths, v2, "tester")
    versions.record_evaluation(paths, v2, v1, "reject", ["no"], "r.md")
    with pytest.raises(versions.VersionError):
        versions.promote(paths, v2, "tester")
    versions.record_evaluation(paths, v2, "some-other-baseline", "accept", ["ok"], "r.md")
    with pytest.raises(versions.VersionError):
        versions.promote(paths, v2, "tester")
    versions.record_evaluation(paths, v2, v1, "accept", ["ok"], "r.md")
    versions.promote(paths, v2, "tester")
    assert versions.active(paths) == v2


def test_rollback_restores_the_exact_prior_behaviour(paths, bundle, registry):
    v1, v2 = registry
    versions.record_evaluation(paths, v2, v1, "accept", ["ok"], "r.md")
    versions.promote(paths, v2, "tester")
    assert versions.rollback(paths, "tester", "post-launch issue") == v1
    assert versions.active(paths) == v1
    assert bundle_hash(versions.load_snapshot(paths, v1)) == v1
    assert versions.load_snapshot(paths, v1)["risk_model"]["var"]["method"] == "historical"
    assert [e["event"] for e in versions.history(paths)][-2:] == ["promoted", "rolled_back"]


def test_a_tampered_snapshot_is_refused(paths, registry):
    v1, _ = registry
    path = paths.versions / v1 / "bundle.json"
    path.write_text(path.read_text(encoding="utf-8").replace('"historical"', '"age_weighted"'), encoding="utf-8")
    with pytest.raises(versions.VersionError, match="altered"):
        versions.load_snapshot(paths, v1)


def test_rollback_with_no_history_is_refused(paths, registry):
    with pytest.raises(versions.VersionError):
        versions.rollback(paths, "tester", "nothing to go back to")


def test_prompt_changes_produce_a_new_version(bundle):
    changed = copy.deepcopy(bundle)
    changed["prompts"]["memo_writer.md"] += "\nExtra line."
    assert bundle_hash(changed) != bundle_hash(bundle)


def test_a_running_version_survives_a_rollback(paths, bundle, make_env, registry):
    """A run in flight finishes on the version it started with."""
    from conftest import eod
    from riskwatch.controller import Controller
    v1, v2 = registry
    env = make_env(the_bundle=versions.load_snapshot(paths, v2))
    ctl, run_id, status = eod(env, "2020-03-16")
    assert status == "awaiting_approval" and env.state.run(run_id)["version"] == v2
    env.close()
    env = make_env(the_bundle=versions.load_snapshot(paths, v1))
    assert env.state.run(run_id)["version"] == v2
    assert Controller(env).decide(run_id, "approve", "tester") == "completed"
