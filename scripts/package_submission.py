"""Build 25210660154-PabloCarpanetti-FinalProject.zip from the committed local folder, including the full .git/.

Refuses to run with uncommitted changes, because the brief says to commit before compressing. The ZIP
is written beside the project folder and checked by unpacking it and running `git fsck` on the copy.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDENT_ID = "25210660154"
NAME = "PabloCarpanetti"
SKIP_DIRS = {"runtime", "__pycache__", ".pytest_cache", ".venv", "riskwatch.egg-info", "build", "dist"}
SKIP_FILES = {".env", "final_project.pdf"}


def git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def main() -> None:
    dirty = git("status", "--porcelain")
    if dirty:
        sys.exit(f"commit first, the working tree has changes:\n{dirty}")
    if git("rev-parse", "--is-shallow-repository") != "false":
        sys.exit("repository is shallow")

    target = ROOT.parent / f"{STUDENT_ID}-{NAME}-FinalProject.zip"
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                if name in SKIP_FILES or name.endswith((".zip", ".pyc")):
                    continue
                path = Path(folder) / name
                z.write(path, Path(ROOT.name) / path.relative_to(ROOT))
                count += 1

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(target) as z:
            z.extractall(tmp)
        copy = Path(tmp) / ROOT.name
        git("-c", f"safe.directory={copy.as_posix()}", "fsck", "--full", cwd=copy)
        commits = git("-c", f"safe.directory={copy.as_posix()}", "rev-list", "--count", "HEAD", cwd=copy)
        status = git("-c", f"safe.directory={copy.as_posix()}", "status", "--porcelain", cwd=copy)
    print(f"{target}\n{count} files, {target.stat().st_size / 1e6:.1f} MB, {commits} commits in the unpacked copy, "
          f"git fsck clean, working tree {'clean' if not status else 'NOT clean: ' + status}")


if __name__ == "__main__":
    main()
