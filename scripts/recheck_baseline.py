"""Does the frozen baseline still reproduce on the current code?

Harness code is not part of a version's hash, so a code change could move results silently. This replays
the active version and compares every scorecard field with the frozen one. Token counts may drift when
agent requests change, so they are reported separately from the behaviour fields.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["LLM_PROVIDER"] = "scripted"

from riskwatch.config import default_paths  # noqa: E402
from riskwatch.improve import evaluate, versions  # noqa: E402


def main() -> None:
    paths = default_paths()
    version = versions.active(paths)
    frozen = json.loads((ROOT / "eval" / "baselines" / f"{version}.json").read_text(encoding="utf-8"))
    fresh = evaluate.run_scorecard(versions.load_snapshot(paths, version), ROOT)
    a, b = frozen["scorecard"], fresh["scorecard"]
    drift_fields = {"llm_tokens"}
    changed = {k: (a[k], b[k]) for k in a if a[k] != b[k] and k not in drift_fields}
    ok = not changed and fresh["leakage"]["passed"]
    lines = [f"# Baseline reproduction check ({'PASSED' if ok else 'FAILED'})", "",
             f"Version `{version}`, replayed on the final code by `scripts/recheck_baseline.py`.", "",
             f"{len(a) - len(drift_fields)} behaviour fields compared with the frozen scorecard: "
             f"{'all identical' if not changed else changed}.",
             f"LLM tokens: {a['llm_tokens']:,} frozen, {b['llm_tokens']:,} now. The stand-in's token count moves when agent "
             "requests carry more facts. It is not a behaviour field.",
             f"Leakage perturbation test: {'passed' if fresh['leakage']['passed'] else 'FAILED'}."]
    out = ROOT / "evidence" / "versioning" / "baseline_recheck.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("PASSED" if ok else f"FAILED: {changed}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
