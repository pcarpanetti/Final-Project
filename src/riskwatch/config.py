"""Load the versioned bundle: configuration, prompts and skills, hashed together as one unit."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILES = ("risk_model", "limits", "policy", "workflows", "agents")


@dataclass(frozen=True)
class Paths:
    root: Path
    home: Path
    versions: Path
    data: Path

    @property
    def db(self) -> Path:
        return self.home / "state.db"

    @property
    def artifacts(self) -> Path:
        return self.home / "artifacts"

    @property
    def published(self) -> Path:
        return self.home / "published"


def default_paths() -> Paths:
    return Paths(
        root=ROOT,
        home=Path(os.environ.get("RISKWATCH_HOME", ROOT / "runtime")),
        versions=Path(os.environ.get("RISKWATCH_VERSIONS", ROOT / "versions")),
        data=ROOT / "data" / "feed",
    )


def deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _read_tree(folder: Path, pattern: str) -> dict[str, str]:
    return {p.relative_to(folder).as_posix(): p.read_text(encoding="utf-8").replace("\r\n", "\n")
            for p in sorted(folder.glob(pattern))}


def load_source_bundle(root: Path = ROOT, overlay: dict | None = None) -> dict:
    """Assemble a bundle from the working tree. Only `versions register` and evaluation use this."""
    bundle: dict = {name: yaml.safe_load((root / "config" / f"{name}.yaml").read_text(encoding="utf-8"))
                    for name in CONFIG_FILES}
    bundle["prompts"] = _read_tree(root / "prompts", "*.md")
    bundle["skills"] = _read_tree(root / "skills", "*/SKILL.md")
    return deep_merge(bundle, overlay) if overlay else bundle


def bundle_hash(bundle: dict) -> str:
    text = json.dumps(bundle, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def validate_workflows(bundle: dict) -> None:
    for name, wf in bundle["workflows"].items():
        seen: set[str] = set()
        for stage in wf["stages"]:
            missing = set(stage.get("depends_on", [])) - seen
            if missing:
                raise ValueError(f"workflow {name}: {stage['name']} depends on later stages {sorted(missing)}")
            if stage["kind"] == "agent" and stage["agent"] not in bundle["agents"]["roles"]:
                raise ValueError(f"workflow {name}: unknown agent {stage['agent']}")
            seen.add(stage["name"])
