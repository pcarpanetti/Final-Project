"""Version registry. A version is a frozen snapshot of config, prompts and skills.

Runs load the snapshot, never the working tree, so a rollback restores the exact prior behaviour.
The registry is append-only; history is corrected by adding an event, never by editing one.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

from ..config import Paths, bundle_hash, validate_workflows


class VersionError(RuntimeError):
    pass


def _log(paths: Paths, event: dict) -> None:
    paths.versions.mkdir(parents=True, exist_ok=True)
    event = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **event}
    with open(paths.versions / "registry.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def history(paths: Paths) -> list[dict]:
    path = paths.versions / "registry.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def active(paths: Paths) -> str:
    path = paths.versions / "ACTIVE"
    if not path.exists():
        raise VersionError("no active version; run `riskwatch versions register --activate` first")
    return path.read_text(encoding="utf-8").strip()


def _set_active(paths: Paths, version: str) -> None:
    (paths.versions / "ACTIVE").write_text(version + "\n", encoding="utf-8", newline="\n")


def load_snapshot(paths: Paths, version: str) -> dict:
    path = paths.versions / version / "bundle.json"
    if not path.exists():
        raise VersionError(f"unknown version {version}")
    bundle = json.loads(path.read_text(encoding="utf-8"))
    if bundle_hash(bundle) != version:
        raise VersionError(f"snapshot for {version} has been altered")
    return bundle


def _git_commit(paths: Paths) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=paths.root, capture_output=True, text=True)
        return out.stdout.strip()
    except OSError:
        return ""


def register(paths: Paths, bundle: dict, note: str, source: str = "working tree") -> str:
    validate_workflows(bundle)
    version = bundle_hash(bundle)
    folder = paths.versions / version
    if not (folder / "bundle.json").exists():
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "bundle.json").write_text(json.dumps(bundle, sort_keys=True, ensure_ascii=False, indent=1),
                                            encoding="utf-8", newline="\n")
        _log(paths, {"event": "registered", "version": version, "note": note, "source": source,
                     "git_commit": _git_commit(paths)})
    return version


def record_evaluation(paths: Paths, version: str, baseline: str, decision: str, reasons: list[str], report: str) -> None:
    _log(paths, {"event": "evaluated", "version": version, "baseline": baseline, "decision": decision,
                 "reasons": reasons, "report": report})


def activate_first(paths: Paths, version: str, actor: str) -> None:
    if (paths.versions / "ACTIVE").exists():
        raise VersionError("an active version exists; use promote")
    _set_active(paths, version)
    _log(paths, {"event": "activated", "version": version, "by": actor})


def promote(paths: Paths, version: str, actor: str) -> None:
    """Refuse anything without a passing evaluation against the version it would replace."""
    current = active(paths)
    passed = [e for e in history(paths) if e["event"] == "evaluated" and e["version"] == version
              and e["baseline"] == current and e["decision"] == "accept"]
    if not passed:
        raise VersionError(f"{version} has no accepted evaluation against active version {current}")
    load_snapshot(paths, version)
    _set_active(paths, version)
    _log(paths, {"event": "promoted", "version": version, "from": current, "by": actor})


def rollback(paths: Paths, actor: str, reason: str) -> str:
    """Return to the version that was active before the current one."""
    current = active(paths)
    moves = [e for e in history(paths) if e["event"] in ("promoted", "rolled_back") and e["version"] == current]
    if not moves or "from" not in moves[-1]:
        raise VersionError(f"{current} has no earlier version to return to")
    target = moves[-1]["from"]
    load_snapshot(paths, target)
    _set_active(paths, target)
    _log(paths, {"event": "rolled_back", "version": target, "from": current, "by": actor, "reason": reason})
    return target
