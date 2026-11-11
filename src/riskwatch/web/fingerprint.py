"""Identify which code a running server was started from. Standard library only, so launch.py can use it
before any dependency is installed."""
from __future__ import annotations

import hashlib
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SUFFIXES = {".py", ".js", ".css", ".html"}


def code_fingerprint(package: Path = PACKAGE) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in package.rglob("*") if p.suffix in SUFFIXES and "__pycache__" not in p.parts):
        digest.update(path.relative_to(package).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]
