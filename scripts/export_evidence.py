"""Copy a curated, shareable slice of a finished replay into evidence/ and examples/.

Usage: RISKWATCH_HOME=<replay home> python scripts/export_evidence.py
Runtime state itself stays out of the repository; it can be regenerated with `riskwatch replay`.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = Path(os.environ.get("RISKWATCH_HOME", ROOT / "runtime"))
EVIDENCE, EXAMPLES = ROOT / "evidence" / "replay", ROOT / "examples"

SAMPLES = {
    "clean_day": ("eod-2019-11-05", ["memo_final.md", "limit_status.json", "gate.json", "verification.r0.json"]),
    "hard_breach_day": ("eod-2020-03-16", ["memo_final.md", "metrics.json", "limit_status.json", "breach_delta.json",
                                           "backtest.json", "analysis.r0.json", "verification.r0.json", "review.r0.json",
                                           "gate.json", "published.json"]),
    "bad_tick_caught": ("eod-2020-01-16", ["dq_report.json", "dq_decisions.json", "dq_summary.json", "memo_final.md"]),
    "real_move_escalated": ("eod-2020-03-09", ["dq_report.json", "dq_decisions.json", "dq_summary.json",
                                               "memo_final.md", "breach_notice.json", "published.json"]),
    "revision_loop": ("eod-2020-02-24", ["memo_draft.r0.md", "verification.r0.json", "feedback.r1.json", "memo_draft.r1.md",
                                         "verification.r1.json", "memo_final.md"]),
    "human_change_request": ("eod-2020-03-19", ["memo_draft.r0.md", "feedback.r1.json", "memo_draft.r1.md", "memo_final.md"]),
    "prompt_injection": ("eod-2020-05-12", ["inputs/manifest.json", "dq_summary.json", "memo_draft.r0.md",
                                            "verification.r0.json", "memo_draft.r1.md", "memo_final.md"]),
    "provider_outage_degraded": ("eod-2020-04-21", ["memo_final.md", "gate.json"]),
    "revision_exhausted_degraded": ("eod-2020-03-24", ["memo_draft.r2.md", "verification.r2.json", "memo_final.md", "gate.json"]),
    "monthly_review": ("monthly-2020-03", ["backtest_review.json", "model_review_agent.json", "model_review.md"]),
}


def write_csv(path: Path, rows: list[sqlite3.Row]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(rows[0].keys())
        w.writerows(tuple(r) for r in rows)


def main() -> None:
    con = sqlite3.connect(HOME / "state.db")
    con.row_factory = sqlite3.Row
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    write_csv(EVIDENCE / "runs.csv", con.execute(
        "SELECT run_id, workflow, as_of, cutoff, version, status, trigger, round, degraded, degraded_reason, halted_reason, llm "
        "FROM runs ORDER BY as_of, run_id").fetchall())
    write_csv(EVIDENCE / "breach_register.csv", con.execute("SELECT * FROM breaches ORDER BY opened_on, limit_id").fetchall())
    write_csv(EVIDENCE / "var_ledger.csv", con.execute("SELECT * FROM var_ledger ORDER BY as_of").fetchall())
    write_csv(EVIDENCE / "approvals.csv", con.execute("SELECT * FROM approvals ORDER BY requested_at").fetchall())
    write_csv(EVIDENCE / "escalations.csv", con.execute("SELECT * FROM escalations ORDER BY id").fetchall())
    write_csv(EVIDENCE / "outbox.csv", con.execute("SELECT * FROM outbox ORDER BY key").fetchall())

    events = con.execute("SELECT sim_ts, run_id, stage, type, detail FROM events WHERE type NOT IN "
                         "('stage_started', 'stage_done', 'stage_skipped', 'llm_call', 'tool_call', 'run_created', "
                         "'run_completed', 'delivered', 'stage_waiting') ORDER BY id").fetchall()
    write_csv(EVIDENCE / "notable_events.csv", events)

    counts = Counter(r["type"] for r in con.execute("SELECT type FROM events"))
    status = Counter((r["workflow"], r["status"]) for r in con.execute("SELECT workflow, status FROM runs"))
    lines = ["# Full replay summary", "", "Window 2019-07-01 to 2020-06-30. Backend: `scripted:rules-v1`, the offline stand-in.",
             "Approvals were answered by `replay-policy`, a stand-in for the CRO. Market data is real; the book and faults are not.",
             "", "| Workflow | Status | Runs |", "|---|---|---|"]
    lines += [f"| {w} | {s} | {n} |" for (w, s), n in sorted(status.items())]
    lines += ["", "| Event | Count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in counts.most_common()]
    (EVIDENCE / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    for name, (run_id, files) in SAMPLES.items():
        target = EXAMPLES / name
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        for rel in files:
            source = HOME / "artifacts" / run_id / rel
            if source.exists():
                shutil.copy(source, target / Path(rel).name)
            else:
                print(f"missing: {run_id}/{rel}")
        with open(target / "events.jsonl", "w", encoding="utf-8", newline="\n") as f:
            for row in con.execute("SELECT sim_ts, stage, type, detail FROM events WHERE run_id = ? AND type NOT IN "
                                   "('stage_started', 'tool_call') ORDER BY id", (run_id,)):
                f.write(json.dumps({**dict(row), "detail": json.loads(row["detail"])}, sort_keys=True) + "\n")

    restate = con.execute("SELECT run_id FROM runs WHERE workflow = 'restate' ORDER BY as_of LIMIT 1").fetchone()
    target = EXAMPLES / "restatement"
    target.mkdir(exist_ok=True)
    for rel in ("restatement.json", "restatement.md"):
        shutil.copy(HOME / "artifacts" / restate["run_id"] / rel, target / rel)
    print(f"exported {len(SAMPLES) + 1} examples and {len(list(EVIDENCE.iterdir()))} evidence files")


if __name__ == "__main__":
    main()
