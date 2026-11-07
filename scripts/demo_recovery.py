"""Recovery evidence: hard-kill a running workflow at random moments, then compare with a clean run.

Each kill is an external TerminateProcess/SIGKILL at an arbitrary instant, not a planned crash point.
The killed run resumes by simply re-running the same command. Afterwards every artifact, published
file and durable table must match an uninterrupted control run of the same window. A kill counts only
if the process was still running when it landed.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, END = "2020-03-02", "2020-03-31"
OUT = ROOT / "evidence" / "recovery"
KILLS = 4
SEED = 20260107


def command(takeover: bool) -> list[str]:
    cmd = [sys.executable, "-m", "riskwatch", "replay", "--start", START, "--end", END]
    return cmd + ["--takeover"] if takeover else cmd


def environment(home: Path) -> dict:
    env = {**os.environ, "RISKWATCH_HOME": str(home), "PYTHONPATH": str(ROOT / "src"), "LLM_PROVIDER": "scripted"}
    env.pop("RISKWATCH_CRASH_AT", None)
    return env


def tree(folder: Path) -> dict[str, str]:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file() and not p.name.endswith(".tmp")}


def tables(db: Path) -> dict:
    con = sqlite3.connect(db)
    queries = {
        "breaches": "SELECT * FROM breaches ORDER BY breach_id",
        "var_ledger": "SELECT * FROM var_ledger ORDER BY as_of",
        "outbox": "SELECT key, sha256, status FROM outbox ORDER BY key",
        "dq_overrides": "SELECT * FROM dq_overrides ORDER BY as_of, asset",
        "llm_journal": "SELECT run_id, request_hash, response FROM llm_calls ORDER BY run_id, request_hash",
        "runs": "SELECT run_id, status, round, degraded, cutoff FROM runs ORDER BY run_id",
    }
    data = {name: [list(r) for r in con.execute(sql).fetchall()] for name, sql in queries.items()}
    data["_counts"] = {
        "delivered_events": con.execute("SELECT COUNT(*) FROM events WHERE type = 'delivered'").fetchone()[0],
        "llm_call_events": con.execute("SELECT COUNT(*) FROM events WHERE type = 'llm_call'").fetchone()[0],
        "interrupted_stages": con.execute("SELECT COUNT(*) FROM events WHERE type = 'stage_interrupted'").fetchone()[0],
        "resumed_runs": con.execute("SELECT COUNT(*) FROM events WHERE type = 'run_resumed'").fetchone()[0],
        "lease_takeovers": con.execute("SELECT COUNT(*) FROM events WHERE type = 'lease_takeover'").fetchone()[0],
    }
    con.close()
    return data


def main() -> None:
    rng = random.Random(SEED)
    log: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        control_home, crash_home = Path(tmp) / "control", Path(tmp) / "crash"

        print("control run ...", flush=True)
        t0 = time.time()
        subprocess.run(command(False), env=environment(control_home), check=True, capture_output=True, cwd=ROOT)
        duration = time.time() - t0
        print(f"control took {duration:.1f}s", flush=True)

        attempt = 0
        while sum(k["process_was_running"] for k in log) < KILLS:
            attempt += 1
            if attempt > KILLS * 3:
                sys.exit("could not land enough kills; lengthen the window")
            # Kept short of the remaining work: a resumed run skips what is done, so it finishes sooner.
            delay = rng.uniform(4.0, 9.0)
            proc = subprocess.Popen(command(attempt > 1), env=environment(crash_home), cwd=ROOT,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(delay)
            alive = proc.poll() is None
            proc.kill()
            proc.wait()
            log.append({"attempt": attempt, "after_seconds": round(delay, 2), "process_was_running": alive})
            print(log[-1], flush=True)

        print("final resume ...", flush=True)
        subprocess.run(command(True), env=environment(crash_home), check=True, capture_output=True, cwd=ROOT)

        art_a, art_b = tree(control_home / "artifacts"), tree(crash_home / "artifacts")
        pub_a, pub_b = tree(control_home / "published"), tree(crash_home / "published")
        tab_a, tab_b = tables(control_home / "state.db"), tables(crash_home / "state.db")
        counts_a, counts_b = tab_a.pop("_counts"), tab_b.pop("_counts")

    checks = {
        "artifacts_identical": art_a == art_b,
        "published_files_identical": pub_a == pub_b,
        **{f"table_{k}_identical": tab_a[k] == tab_b[k] for k in tab_a},
        "each_delivery_happened_once": counts_b["delivered_events"] == len(pub_b),
        f"at_least_{KILLS}_real_kills": sum(k["process_was_running"] for k in log) >= KILLS,
    }
    report = {"window": [START, END], "kills": log, "artifact_files": len(art_a), "published_files": len(pub_a),
              "control_counts": counts_a, "killed_run_counts": counts_b, "checks": checks, "passed": all(checks.values())}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hard_kill_report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")

    lines = [f"# Hard-kill recovery test ({'PASSED' if report['passed'] else 'FAILED'})", "",
             f"Window {START} to {END}, offline scripted backend. Generated by `scripts/demo_recovery.py`.", "",
             f"The process was killed {sum(k['process_was_running'] for k in log)} times from outside at random moments,",
             "then resumed by re-running the same command. The result is compared with an uninterrupted control run.", "",
             "| Attempt | Killed after (s) | Process was running |", "|---|---|---|"]
    lines += [f"| {k['attempt']} | {k['after_seconds']} | {k['process_was_running']} |" for k in log]
    lines += ["", "| Check | Result |", "|---|---|"] + [f"| {k} | {'pass' if v else 'FAIL'} |" for k, v in checks.items()]
    lines += ["", "| Count | Control | Killed run |", "|---|---|---|"]
    lines += [f"| {k} | {counts_a[k]} | {counts_b[k]} |" for k in counts_a]
    lines += ["", f"{len(art_a)} artifact files and {len(pub_a)} published files compared by SHA-256."]
    (OUT / "hard_kill_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("PASSED" if report["passed"] else f"FAILED: {checks}")
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
