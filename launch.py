"""One-step start for RiskWatch: checks Python, installs what is missing, opens the browser app.

Run by start.bat (Windows) or start.sh (Mac, Linux). Uses only the standard library, because nothing else
may be installed yet. Dependencies go in a private folder in the user's home directory, which keeps them
out of this project and away from Windows path length limits.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_DIR = Path.home() / ".riskwatch" / "env"
NEEDED = ["numpy>=1.26", "pandas>=2.1", "PyYAML>=6.0"]
DEFAULT_PORT = 8765


def has_dependencies(python: str) -> bool:
    check = subprocess.run([python, "-c", "import numpy, pandas, yaml"], capture_output=True)
    return check.returncode == 0


def env_python() -> Path:
    return ENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def install() -> str:
    print("First run: installing numpy, pandas and PyYAML. This takes a minute or two.", flush=True)
    if not env_python().exists():
        venv.create(ENV_DIR, with_pip=True)
    # Pure-Python PyYAML is plenty here, and it avoids needing a C compiler on very new Python versions.
    env = {**os.environ, "PYYAML_FORCE_LIBYAML": "0"}
    subprocess.run([str(env_python()), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *NEEDED], check=True, env=env)
    return str(env_python())


def option(name: str, default: str) -> str:
    args = sys.argv[1:]
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default


def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def call(url: str, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"} | ({"X-RiskWatch-Token": token} if token else {})
    req = urllib.request.Request(url, data=b"{}" if token else None, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def handle_running_copy(port: int) -> int | None:
    """Decide what to do when the port is taken. None means it is free now and this copy should start.

    Double-clicking start.bat again should not fail: an up-to-date copy is simply opened, and an older idle
    copy is replaced, since it would otherwise keep serving old code.
    """
    if not port_in_use(port):
        return None
    url = f"http://127.0.0.1:{port}/"
    try:
        running = call(url + "api/health")
    except (OSError, ValueError):
        running = {}
    if running.get("app") != "riskwatch":
        print(f"Port {port} is in use by another program, or by an older RiskWatch that cannot be replaced.")
        print(f"Close it, or start RiskWatch on another port with: python launch.py --port {port + 1}")
        return 1
    sys.path.insert(0, str(ROOT / "src"))
    from riskwatch.web.fingerprint import code_fingerprint
    if running["fingerprint"] == code_fingerprint():
        print(f"RiskWatch is already running at {url}")
        if "--no-browser" not in sys.argv:
            webbrowser.open(url)
            print("It is open in your browser now. You can close this window.")
        return 0
    if running["busy"]:
        print(f"An older copy of RiskWatch is running a job at {url}")
        print("Let it finish, or stop it in the app, then double-click start.bat again to update it.")
        webbrowser.open(url)
        return 1
    workspace = Path(os.environ.get("RISKWATCH_WEB_HOME", ROOT / "runtime" / "web"))
    try:
        call(url + "api/shutdown", json.loads((workspace / "server.json").read_text(encoding="utf-8"))["token"])
    except (OSError, ValueError, KeyError):
        print(f"An older copy of RiskWatch is running at {url} and could not be stopped from here.")
        print("Close its window, then double-click start.bat again.")
        return 1
    deadline = time.time() + 15
    while port_in_use(port) and time.time() < deadline:
        time.sleep(0.3)
    print("Replaced an older copy of RiskWatch that was still running.")
    return None


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # messages appear before the server takes over the window
    if sys.version_info < (3, 10):
        print(f"RiskWatch needs Python 3.10 or newer, and this is {sys.version.split()[0]}.")
        print("Install a newer version from https://www.python.org/downloads/ and try again.")
        return 1
    outcome = handle_running_copy(int(option("--port", str(DEFAULT_PORT))))
    if outcome is not None:
        return outcome
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
