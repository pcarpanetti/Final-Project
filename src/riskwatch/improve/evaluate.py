"""Test a proposed change against a fixed baseline, under rules written down before the run."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import yaml

from ..config import Paths, bundle_hash
from ..controller import Env
from ..llm.providers import build_provider
from ..pit import PointInTimeStore
from ..replay import load_scenario, replay
from ..risk import backtest
from .leakage import perturbation_test


def _fault_outcomes(env: Env, faults: list[dict]) -> dict[str, bool]:
    """Compare what the workflow did with the labelled ground truth. Only evaluation reads the labels."""
    st = env.state

    def dq_action(day: str, exception_id: str) -> str | None:
        path = env.paths.artifacts / f"eod-{day}" / "dq_summary.json"
        if not path.exists():
            return None
        items = json.loads(path.read_text(encoding="utf-8"))["items"]
        return next((i["action"] for i in items if i["id"] == exception_id), None)

    def cutoff_extended(day: str) -> bool:
        return bool(st.q("SELECT 1 FROM events WHERE run_id = ? AND type = 'cutoff_extended'", f"eod-{day}"))

    out = {}
    for f in faults:
        day, kind = f["as_of"], f["type"]
        if kind == "bad_tick":
            out[f["id"]] = dq_action(day, f"outlier:{f['asset']}") == "zero_return"
        elif kind == "stale_repeat":
            out[f["id"]] = dq_action(day, f"stale_repeat:{f['asset']}") == "zero_return"
        elif kind == "missing_row":
            out[f["id"]] = dq_action(day, f"missing_row:{f['asset']}") == "zero_return"
        elif kind == "note_injection":
            out[f["id"]] = dq_action(day, "suspicious_note:0") == "escalate"
        elif kind in ("late_file", "positions_break"):
            out[f["id"]] = cutoff_extended(day) and st.run(f"eod-{day}")["status"] == "completed"
    return out


def scorecard(env: Env, faults: list[dict]) -> dict:
    st = env.state
    fault_days = {(f["as_of"], f.get("asset")) for f in faults}
    runs = [dict(r) for r in st.q("SELECT * FROM runs WHERE workflow = 'eod' ORDER BY as_of")]
    ledger = st.q("SELECT var99, hit FROM var_ledger WHERE hit IS NOT NULL ORDER BY as_of")
    hits = [r["hit"] for r in ledger]
    bt = backtest.summarise(hits)

    hard_days = false_overrides = cutoff_violations = 0
    for run in runs:
        folder = env.paths.artifacts / run["run_id"]
        status_path, dq_path = folder / "limit_status.json", folder / "dq_summary.json"
        if status_path.exists():
            rows = json.loads(status_path.read_text(encoding="utf-8"))["rows"]
            hard_days += any(r["status"] == "breach" for r in rows)
        if dq_path.exists():
            for item in json.loads(dq_path.read_text(encoding="utf-8"))["items"]:
                if item["action"] == "zero_return" and (run["as_of"], item["asset"]) not in fault_days:
                    false_overrides += 1
        manifest = folder / "inputs" / "manifest.json"
        if manifest.exists():
            m = json.loads(manifest.read_text(encoding="utf-8"))
            cutoff_violations += m["max_published_at"] > m["cutoff"]

    usage = st.one("SELECT COUNT(*) calls, COALESCE(SUM(tokens_in + tokens_out), 0) tokens, "
                   "COALESCE(SUM(cost_usd), 0) cost FROM llm_calls")
    fails = st.one("SELECT COUNT(DISTINCT run_id) n FROM events WHERE type = 'verification_failed'")["n"]
    outcomes = _fault_outcomes(env, faults)
    return {
        "eod_runs": len(runs),
        "status_counts": {s: sum(r["status"] == s for r in runs) for s in sorted({r["status"] for r in runs})},
        "halted_runs": sum(r["status"].startswith("halted") for r in runs),
        "degraded_runs": sum(r["degraded"] for r in runs),
        "var_observations": bt["observations"],
        "var_exceptions": bt["exceptions"],
        "var_expected": bt["expected"],
        "kupiec_p": bt["kupiec"]["p_value"],
        "independence_p": bt["independence"]["p_value"],
        "basel_zone": bt["zone"],
        "avg_var99": sum(r["var99"] for r in ledger) / max(len(ledger), 1),
        "hard_breach_days": hard_days,
        "faults_handled": outcomes,
        "faults_handled_rate": sum(outcomes.values()) / max(len(outcomes), 1),
        "false_dq_overrides": false_overrides,
        "cutoff_violations": cutoff_violations,
        "runs_needing_revision": fails,
        "approvals_requested": st.one("SELECT COUNT(*) n FROM approvals")["n"],
        "memos_published": st.one("SELECT COUNT(*) n FROM outbox WHERE kind = 'memo' AND status = 'delivered'")["n"],
        "escalations": st.one("SELECT COUNT(*) n FROM escalations")["n"],
        "llm_calls": usage["calls"],
        "llm_tokens": usage["tokens"],
        "llm_cost_usd": usage["cost"],
    }


def run_scorecard(bundle: dict, root: Path, store: PointInTimeStore | None = None) -> dict:
    """Replay the fixed window in a throwaway home. Nothing here touches production state."""
    scenario = load_scenario(root)
    faults = yaml.safe_load((root / "data" / "faults.yaml").read_text(encoding="utf-8"))
    store = store or PointInTimeStore(root / "data" / "feed")
    version = bundle_hash(bundle)
    started = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        env = Env(Paths(root, home, home / "versions", root / "data" / "feed"), bundle, version, store=store,
                  mode="replay", scripted_faults=scenario["scripted_faults"], sleep=lambda s: None, durable=False)
        replay(env, scenario)
        card = scorecard(env, faults)
        env.close()
    probe_days = yaml.safe_load((root / "eval" / "policy.yaml").read_text(encoding="utf-8"))["leakage_probe_days"]
    leak = perturbation_test(bundle, version, root, store, probe_days)
    return {"version": version, "backend": _backend(), "scorecard": card, "leakage": leak,
            "elapsed_seconds": round(time.time() - started, 1)}


def _backend() -> str:
    provider = build_provider()
    return f"{provider.name}:{provider.model}" if provider else "scripted:rules-v1"


def decide(candidate: dict, baseline: dict, rules: dict) -> dict:
    """Apply the pre-registered rules. Pure function: same inputs, same decision."""
    c, b = candidate["scorecard"], baseline["scorecard"]
    gates, guards = rules["hard_gates"], rules["guardrails"]
    failed: list[str] = []

    def rel_increase(key: str) -> float:
        return (c[key] - b[key]) / b[key] if b[key] else 0.0

    if c["faults_handled_rate"] < gates["min_faults_handled_rate"]:
        missed = [k for k, v in c["faults_handled"].items() if not v]
        failed.append(f"hard gate: ground-truth faults not handled: {missed}")
    if c["false_dq_overrides"] > b["false_dq_overrides"] + gates["max_extra_false_dq_overrides"]:
        failed.append(f"hard gate: false DQ overrides rose from {b['false_dq_overrides']} to {c['false_dq_overrides']}")
    if c["halted_runs"] > gates["max_halted_runs"]:
        failed.append(f"hard gate: {c['halted_runs']} halted runs")
    if c["cutoff_violations"] > 0 or not candidate["leakage"]["passed"]:
        failed.append("hard gate: information cutoff violated")

    distance_c = abs(c["var_exceptions"] - c["var_expected"])
    distance_b = abs(b["var_exceptions"] - b["var_expected"])
    primary = c["kupiec_p"] > b["kupiec_p"] and distance_c < distance_b
    changes_model = candidate["version"] != baseline["version"]
    improved = primary if rules["primary"]["required"] else True

    if rel_increase("avg_var99") > guards["max_rel_increase_avg_var"]:
        failed.append(f"guardrail: average VaR up {rel_increase('avg_var99'):.0%}")
    if rel_increase("hard_breach_days") > guards["max_rel_increase_hard_breach_days"]:
        failed.append(f"guardrail: hard breach days up {rel_increase('hard_breach_days'):.0%}")
    if rel_increase("llm_tokens") > guards["max_rel_increase_tokens"]:
        failed.append(f"guardrail: LLM tokens up {rel_increase('llm_tokens'):.0%}")
    if not improved and changes_model:
        failed.append(f"primary: Kupiec p {b['kupiec_p']:.4f} -> {c['kupiec_p']:.4f}, "
                      f"exceptions {b['var_exceptions']} -> {c['var_exceptions']}: no improvement")
    return {"decision": "reject" if failed else "accept", "reasons": failed or ["all gates, guardrails and primary test passed"]}


def write_comparison(path: Path, candidate: dict, baseline: dict, verdict: dict, title: str) -> None:
    rows = ["var_exceptions", "kupiec_p", "independence_p", "basel_zone", "avg_var99", "hard_breach_days",
            "faults_handled_rate", "false_dq_overrides", "halted_runs", "degraded_runs", "cutoff_violations",
            "approvals_requested", "memos_published", "llm_calls", "llm_tokens"]

    def show(v) -> str:
        return f"{v:.4f}" if isinstance(v, float) else str(v)

    lines = [f"# Evaluation: {title}", "", f"Baseline `{baseline['version']}`, candidate `{candidate['version']}`, "
             f"backend `{candidate['backend']}`.", "", f"**Decision: {verdict['decision'].upper()}**", ""]
    lines += [f"- {r}" for r in verdict["reasons"]]
    lines += ["", "| Metric | Baseline | Candidate |", "|---|---|---|"]
    lines += [f"| {k} | {show(baseline['scorecard'][k])} | {show(candidate['scorecard'][k])} |" for k in rows]
    lines += ["", f"Leakage perturbation test: {'passed' if candidate['leakage']['passed'] else 'FAILED'} "
              f"on {len(candidate['leakage']['days'])} days."]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
