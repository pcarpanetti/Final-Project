"""One-step start for RiskWatch: checks Python, installs what is missing, opens the browser app.

Run by start.bat (Windows) or start.sh (Mac, Linux). Uses only the standard library, because nothing else
may be installed yet. Dependencies go in a private folder in the user's home directory, which keeps them
out of this project and away from Windows path length limits.
"""
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_DIR = Path.home() / ".riskwatch" / "env"
NEEDED = ["numpy>=1.26", "pandas>=2.1", "PyYAML>=6.0"]


def has_dependencies(python: str) -> bool:
    check = subprocess.run([python, "-c", "import numpy, pandas, yaml"], capture_output=True)
    return check.returncode == 0


def env_python() -> Path:
    return ENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def install() -> str:
    print("First run: installing numpy, pandas and PyYAML. This takes a minute or two.", flush=True)
    if not env_python().exists():
        venv.create(ENV_DIR, with_pip=True)
    subprocess.run([str(env_python()), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *NEEDED], check=True)
    return str(env_python())


def main() -> int:
    if sys.version_info < (3, 10):
        print(f"RiskWatch needs Python 3.10 or newer, and this is {sys.version.split()[0]}.")
        print("Install a newer version from https://www.python.org/downloads/ and try again.")
        return 1
    if has_dependencies(sys.executable):
        python = sys.executable
    elif env_python().exists() and has_dependencies(str(env_python())):
        python = str(env_python())
    else:
        try:
            python = install()
        except (subprocess.CalledProcessError, OSError) as e:
            print(f"Could not install the dependencies: {e}")
            print("Check your internet connection, then try again. GETTING_STARTED.md has a manual route.")
            return 1
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    try:
        return subprocess.run([python, "-m", "riskwatch", "web", *sys.argv[1:]], env=env, cwd=ROOT).returncode
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
