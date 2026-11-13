"""Local web app. Standard library only, so it adds nothing to install.

It is another front door to the same harness: runs are `riskwatch` subprocesses, decisions go through
Controller.decide, and the page reads the same state and artifacts as the CLI. Agents never reach it.

It holds API keys, so it listens on 127.0.0.1 only, refuses unknown Host headers (DNS rebinding), and needs
a per-session token on every POST (another site cannot read the token, so it cannot forge a request).
"""
from __future__ import annotations

import io
import json
import os
import queue
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
import zipfile
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

from .. import book
from ..config import ROOT, default_paths
from ..controller import Controller, Env
from ..improve import versions
from ..llm.providers import (PRESETS, PermanentError, TransientError, build_provider, claude_login_status, list_models,
                             load_dotenv)
from ..pit import PointInTimeStore
from ..replay import load_scenario
from ..stages.pipeline import history_days
from .fingerprint import code_fingerprint
from .summary import period_summary

STATIC = Path(__file__).parent / "static"
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
CSP = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; form-action 'none'"
PUBLIC_SETTINGS = ("name", "provider", "model", "base_url", "protocol", "price_in", "price_out", "reviewer_provider",
                   "reviewer_model", "reviewer_base_url")
ENV_NAMES = {"provider": "LLM_PROVIDER", "model": "LLM_MODEL", "base_url": "LLM_BASE_URL", "protocol": "LLM_PROTOCOL",
             "price_in": "LLM_PRICE_IN_PER_MTOK", "price_out": "LLM_PRICE_OUT_PER_MTOK",
             "reviewer_provider": "LLM_PROVIDER_REVIEWER", "reviewer_model": "LLM_MODEL_REVIEWER",
             "reviewer_base_url": "LLM_BASE_URL_REVIEWER"}


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class App:
    """Everything the web server remembers. One instance per server, and one user per server."""

    def __init__(self, workspace: Path, port: int = 0):
        self.workspace = workspace
        self.port = port
        self.token = secrets.token_urlsafe(32)
        self.fingerprint = code_fingerprint()
        self.server: ThreadingHTTPServer | None = None
        self.lock = threading.Lock()
        self.job: dict | None = None
        self.proc: subprocess.Popen | None = None
        self.decisions: queue.Queue = queue.Queue()
        self.decision_error = ""
        self.queued = 0
        self.keys = {"api_key": "", "reviewer_api_key": ""}
        self.store = PointInTimeStore(ROOT / "data" / "feed")
        self.prepare_workspace()
        self.settings = self.load_settings()
        self.apply_env()
        threading.Thread(target=self.decision_worker, daemon=True).start()

    # ---- Workspace ----
    @property
    def home(self) -> Path:
        return self.workspace / "home"

    @property
    def paths(self):
        return replace(default_paths(), home=self.home, versions=self.workspace / "versions")

    def prepare_workspace(self) -> None:
        """The browser works on its own copy of the registry, so clicks never dirty the Git-tracked one."""
        self.home.mkdir(parents=True, exist_ok=True)
        if not (self.workspace / "versions").exists():
            shutil.copytree(ROOT / "versions", self.workspace / "versions")

    def db(self) -> sqlite3.Connection | None:
        if not self.paths.db.exists():
            return None
        con = sqlite3.connect(f"file:{self.paths.db.as_posix()}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        return con

    def rows(self, sql: str, *args) -> list[dict]:
        con = self.db()
        if con is None:
            return []
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        except sqlite3.OperationalError:
            return []
        finally:
            con.close()

    def read_json(self, run_id: str, name: str):
        path = self.paths.artifacts / run_id / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    # ---- Settings: keys stay in memory unless the user asks to remember them ----
    def load_settings(self) -> dict:
        load_dotenv(ROOT / ".env")
        self.keys["api_key"] = os.environ.get("LLM_API_KEY", "")
        self.keys["reviewer_api_key"] = os.environ.get("LLM_API_KEY_REVIEWER", "")
        path = self.workspace / "settings.json"
        saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return {k: saved.get(k, "") for k in PUBLIC_SETTINGS}

    def save_settings(self, data: dict) -> None:
        self.settings = {k: str(data.get(k, "") or "").strip() for k in PUBLIC_SETTINGS}
        for field in ("api_key", "reviewer_api_key"):
            if data.get(field):
                self.keys[field] = str(data[field]).strip()
        (self.workspace / "settings.json").write_text(json.dumps(self.settings, indent=1), encoding="utf-8")
        if data.get("remember_key"):
            self.write_dotenv()
        self.apply_env()

    def write_dotenv(self) -> None:
        path = ROOT / ".env"
        keep = [line for line in (path.read_text(encoding="utf-8").splitlines() if path.exists() else [])
                if not line.startswith(("LLM_API_KEY=", "LLM_API_KEY_REVIEWER="))]
        keep += [f"LLM_API_KEY={self.keys['api_key']}"] if self.keys["api_key"] else []
        keep += [f"LLM_API_KEY_REVIEWER={self.keys['reviewer_api_key']}"] if self.keys["reviewer_api_key"] else []
        path.write_text("\n".join(keep) + "\n", encoding="utf-8")

    def provider_env(self) -> dict:
        env = {name: self.settings.get(field, "") for field, name in ENV_NAMES.items()}
        env["LLM_API_KEY"] = self.keys["api_key"]
        env["LLM_API_KEY_REVIEWER"] = self.keys["reviewer_api_key"]
        return env

    def apply_env(self) -> None:
        """Make the environment match the form exactly, so a cleared field really is cleared."""
        for name, value in self.provider_env().items():
            if value:
                os.environ[name] = value
            else:
                os.environ.pop(name, None)

    def public_settings(self) -> dict:
        key = self.keys["api_key"]
        return {**self.settings, "has_key": bool(key), "key_hint": f"...{key[-4:]}" if len(key) > 8 else "",
                "has_reviewer_key": bool(self.keys["reviewer_api_key"]), "configured": bool(self.settings["provider"])}

    def backend_label(self) -> str:
        provider = self.settings["provider"] or "scripted"
        if provider == "scripted":
            return "Offline demo (rule-based, no model)"
        return f"{provider}: {self.settings['model'] or 'default model'}"

    # ---- Jobs: one at a time, each a normal `riskwatch` process ----
    def job_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start_job(self, kind: str, args: list[str], meta: dict, extra_env: dict | None = None) -> dict:
        with self.lock:
            if self.job_running():
                raise ApiError("Something is already running. Wait for it, or stop it first.", 409)
            job_id = f"{int(time.time())}"
            log = self.workspace / "job.log"
            env = {**os.environ, "RISKWATCH_HOME": str(self.home), "RISKWATCH_VERSIONS": str(self.workspace / "versions"),
                   "RISKWATCH_EVAL_OUT": str(self.workspace / "eval"), "PYTHONPATH": str(ROOT / "src"),
                   "PYTHONUNBUFFERED": "1", **(extra_env or {})}
            handle = open(log, "w", encoding="utf-8")
            self.proc = subprocess.Popen([sys.executable, "-m", "riskwatch", *args], env=env, cwd=ROOT, stdout=handle,
                                         stderr=subprocess.STDOUT)
            self.job = {"id": job_id, "kind": kind, "args": args, "state": "running", "started": time.time(), **meta}
            threading.Thread(target=self.watch_job, args=(self.proc, handle, self.job), daemon=True).start()
            return self.job

    def watch_job(self, proc: subprocess.Popen, handle, job: dict) -> None:
        code = proc.wait()
        handle.close()
        with self.lock:
            if job["state"] == "running":
                job["state"] = "finished" if code == 0 else "failed"
            job["exit_code"] = code
            job["ended"] = time.time()

    def stop_job(self) -> None:
        """A hard kill, on purpose: stopping is the same event as a crash, and the workflow recovers from it."""
        with self.lock:
            if self.job_running() and self.job:
                self.job["state"] = "stopped"
                self.proc.kill()
                self.proc.wait(timeout=10)

    def job_view(self) -> dict | None:
        if not self.job:
            return None
        view = {k: v for k, v in self.job.items() if k != "args"}
        log = self.workspace / "job.log"
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-200:] if log.exists() else []
        if self.job["state"] == "failed":
            view["error"] = "\n".join(lines[-8:])
        if self.job["kind"] == "run":
            days = self.store.trading_days(self.job["start"], self.job["end"])
            done = self.rows("SELECT COUNT(*) n FROM runs WHERE workflow = 'eod' AND as_of BETWEEN ? AND ? "
                             "AND status NOT IN ('pending', 'running', 'blocked_input', 'blocked_dependency')",
                             self.job["start"], self.job["end"])
            view["days_total"], view["days_done"] = len(days), done[0]["n"] if done else 0
        elif lines:
            view["last_line"] = lines[-1][:200]
        return view

    # ---- Decisions: queued, because a decision must take the same lease as a running job ----
    def decision_worker(self) -> None:
        while True:
            item = self.decisions.get()
            try:
                self.apply_decision(**item)
                self.decision_error = ""
            except Exception as e:  # shown to the user; one bad decision must not stop the worker
                self.decision_error = f"{item['run_id']}: {e}"
            finally:
                self.queued -= 1

    def make_env(self) -> Env:
        paths = self.paths
        version = versions.active(paths)
        faults = load_scenario(ROOT)["scripted_faults"] if self.job and self.job.get("drills") else None
        own = book.load(paths) is not None  # then Env reads that workspace's positions itself
        return Env(paths, versions.load_snapshot(paths, version), version, store=None if own else self.store,
                   mode="replay", scripted_faults=faults)

    def apply_decision(self, run_id: str, decision: str, note: str) -> None:
        env = self.make_env()
        try:
            env.state.sim_now = env.state.get_kv("last_tick")
            env.state.wait_for_lease(env.bundle["policy"]["lease"]["ttl_seconds"], timeout=600.0)
            try:
                Controller(env).decide(run_id, decision, self.settings["name"] or "web user", note)
            finally:
                env.state.release_lease()
        finally:
            env.close()

    def queue_decision(self, run_id: str, decision: str, note: str = "") -> None:
        self.queued += 1
        self.decisions.put({"run_id": run_id, "decision": decision, "note": note})

    # ---- Reset ----
    def start_over(self) -> None:
        with self.lock:
            if self.job_running():
                raise ApiError("Stop the current run first.", 409)
            if self.home.exists():
                archive = self.workspace / "archive"
                archive.mkdir(exist_ok=True)
                self.home.rename(archive / f"home-{int(time.time())}")
            self.home.mkdir(parents=True, exist_ok=True)
            self.job = None


# ---- API handlers: each takes (app, params or body) and returns JSON-ready data ----

def api_summary(app: App, q: dict) -> dict:
    counts = {r["status"]: r["n"] for r in app.rows("SELECT status, COUNT(*) n FROM runs GROUP BY status")}
    pending = app.rows("SELECT COUNT(*) n FROM approvals WHERE decision IS NULL")
    open_esc = app.rows("SELECT COUNT(*) n FROM escalations WHERE status = 'open'")
    last = app.rows("SELECT as_of FROM runs WHERE workflow = 'eod' ORDER BY as_of DESC LIMIT 1")
    version = versions.active(app.paths)
    book_start = kv(app, "book_start")
    return {"continue_from": continue_from(app, last[0]["as_of"] if last else None, book_start), "settings": app.public_settings(), "backend": app.backend_label(), "job": app.job_view(), "counts": counts,
            "pending": pending[0]["n"] if pending else 0, "escalations": open_esc[0]["n"] if open_esc else 0,
            "last_day": last[0]["as_of"] if last else None, "queued_decisions": app.queued,
            "decision_error": app.decision_error, "version": version, "book_start": book_start,
            "book": book.load(app.paths) if book_start else None}


def continue_from(app: App, last_day: str | None, book_start: str) -> str | None:
    """The latest start a new run may have in this workspace. Anything later would leave a gap of days
    that the scheduler would quietly fill in, because a missed day is a day to catch up."""
    if not book_start:
        return None
    return (app.store.next_day(last_day) or last_day) if last_day else book_start


def kv(app: App, key: str) -> str:
    rows = app.rows("SELECT value FROM kv WHERE key = ?", key)
    return rows[0]["value"] if rows else ""


def api_catalog(app: App, q: dict) -> dict:
    calendar = app.store.calendar
    bundle = versions.load_snapshot(app.paths, versions.active(app.paths))
    # The first day with enough history for the active risk model, and never before the feed's own floor.
    first = max(app.store.meta.get("first_run_day", calendar[0]), calendar[history_days(bundle["risk_model"]) - 1])
    return {"providers": {k: {"base_url": v["base_url"], "protocol": v["protocol"], "needs_key": bool(v["key_env"])}
                          for k, v in PRESETS.items()},
            "first_day": first, "last_day": calendar[-1], "calendar_size": len(calendar),
            "drill_window": load_scenario(ROOT)["window"], "budgets": bundle["policy"]["budgets"],
            "book": {"sleeves": [[a, book.LABELS[a]] for a in book.ASSETS], "default": book.DEFAULT,
                     "rebalance": list(book.REBALANCE)}}


def api_claude(app: App, q: dict) -> dict:
    return claude_login_status()


def api_claude_login(app: App, body: dict) -> dict:
    exe = shutil.which("claude")
    if not exe:
        raise ApiError("Claude Code is not installed on this computer.")
    subprocess.Popen([exe, "auth", "login"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"started": True}


def api_save_settings(app: App, body: dict) -> dict:
    if body.get("provider") and body["provider"] != "scripted" and body["provider"] not in PRESETS:
        raise ApiError("Unknown provider.")
    app.save_settings(body)
    return app.public_settings()


def api_test_connection(app: App, body: dict) -> dict:
    """One small real call, using exactly the settings a run would use."""
    app.save_settings(body)
    started = time.time()
    try:
        provider = build_provider(body.get("role"))
        if provider is None:
            return {"ok": True, "offline": True, "message": "Offline demo needs no connection."}
        reply = provider.complete(
            [{"role": "system", "content": "Reply with exactly one JSON object and nothing else."},
             {"role": "user", "content": 'Reply with {"action":"final","output":{"ok":true}}'}],
            200, {"role": "check", "as_of": "", "round": 0})
    except (PermanentError, TransientError) as e:
        return {"ok": False, "message": str(e)}
    return {"ok": True, "message": f"{provider.name} answered in {time.time() - started:.1f}s", "reply": reply.text[:200],
            "follows_format": '"ok"' in reply.text}


def api_models(app: App, body: dict) -> dict:
    key = body.get("api_key") or app.keys["api_key"]
    try:
        return {"models": list_models(body.get("provider", ""), body.get("base_url", ""), key, body.get("protocol", ""))}
    except (PermanentError, TransientError) as e:
        return {"models": [], "message": str(e)}


def api_start_run(app: App, body: dict) -> dict:
    start, end = body.get("start", ""), body.get("end", "")
    days = app.store.trading_days(start, end)
    if not days:
        raise ApiError("There are no trading days in that period.")
    catalog = api_catalog(app, {})
    if start < catalog["first_day"] or end > catalog["last_day"]:
        raise ApiError(f"Choose dates between {catalog['first_day']} and {catalog['last_day']}.")
    book_start = kv(app, "book_start")
    if book_start and start < book_start:
        raise ApiError(f"This workspace starts on {book_start}. Use Start over to run an earlier period.")
    last = app.rows("SELECT MAX(as_of) d FROM runs WHERE workflow = 'eod'")
    latest = continue_from(app, last[0]["d"] if last else None, book_start)
    if latest and start > latest:
        raise ApiError(f"This workspace continues from {latest}. Start there, or use Start over for a separate period.")
    if not app.settings["provider"]:
        raise ApiError("Connect a model first.")
    manual = body.get("approvals") == "manual"
    drills = bool(body.get("drills")) and app.settings["provider"] == "scripted"
    args = ["replay", "--start", start, "--end", end]
    if body.get("book") is not None:
        args += ["--book", str(stage_book(app, body["book"], book_start or start))]
    args += ["--manual-approvals"] if manual else []
    args += [] if drills else ["--no-drills"]
    args += ["--takeover"] if body.get("resume") or (app.job and app.job["state"] in ("stopped", "failed")) else []
    meta = {"start": start, "end": end, "manual": manual, "drills": drills, "backend": app.backend_label()}
    return app.start_job("run", args, meta)


def stage_book(app: App, spec, start: str) -> Path:
    """Check the portfolio here, so a mistake shows on the form, and hand it to the run as a file."""
    try:
        normal = book.validate(spec, app.store.calendar, start)
    except book.BookError as e:
        raise ApiError(str(e)) from e
    if kv(app, "book_start") and normal != book.load(app.paths):
        raise ApiError("This workspace already runs a different portfolio. Use Start over to change it.")
    path = app.workspace / "book-request.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def api_stop(app: App, body: dict) -> dict:
    app.stop_job()
    return {"stopped": True}


def api_runs(app: App, q: dict) -> dict:
    return {"runs": app.rows("SELECT run_id, workflow, as_of, cutoff, version, status, trigger, round, degraded, "
                             "degraded_reason, halted_reason, llm FROM runs ORDER BY as_of DESC, run_id DESC")}


def safe_run_id(run_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id or ""):
        raise ApiError("Bad run id.", 404)
    return run_id


def api_run(app: App, q: dict) -> dict:
    run_id = safe_run_id(q.get("id", [""])[0])
    runs = app.rows("SELECT * FROM runs WHERE run_id = ?", run_id)
    if not runs:
        raise ApiError("No such run.", 404)
    folder = app.paths.artifacts / run_id
    files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()) if folder.exists() else []
    verify = [f for f in files if f.startswith("verification.r")]
    return {
        "run": runs[0],
        "stages": app.rows("SELECT stage, round, status, attempts, error FROM stages WHERE run_id = ? ORDER BY rowid", run_id),
        "events": app.rows("SELECT sim_ts, stage, type, detail FROM events WHERE run_id = ? AND type NOT IN ('stage_started') "
                           "ORDER BY id DESC LIMIT 200", run_id),
        "files": files,
        "memo": read_text(folder / "memo_final.md"),
        "verification": {f: app.read_json(run_id, f) for f in verify},
        "reviews": {f: app.read_json(run_id, f) for f in files if f.startswith("review.r")},
        "dq": app.read_json(run_id, "dq_summary.json"),
        "dq_report": app.read_json(run_id, "dq_report.json"),
        "limits": app.read_json(run_id, "limit_status.json"),
        "gate": app.read_json(run_id, "gate.json"),
        "llm_calls": app.rows("SELECT stage, role, provider, model, response, tokens_in, tokens_out FROM llm_calls "
                              "WHERE run_id = ? ORDER BY rowid", run_id),
        "approvals": app.rows("SELECT * FROM approvals WHERE run_id = ? ORDER BY epoch", run_id),
    }


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def api_file(app: App, q: dict) -> dict:
    run_id = safe_run_id(q.get("run", [""])[0])
    base = (app.paths.artifacts / run_id).resolve()
    target = (base / q.get("name", [""])[0]).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise ApiError("No such file.", 404)
    return {"name": target.name, "text": target.read_text(encoding="utf-8", errors="replace")[:400000]}


def api_pending(app: App, q: dict) -> dict:
    items = []
    for row in app.rows("SELECT a.run_id, a.requested_at, a.reasons, r.as_of, r.workflow, r.degraded FROM approvals a "
                        "JOIN runs r ON r.run_id = a.run_id WHERE a.decision IS NULL ORDER BY r.as_of, a.run_id"):
        gate = app.read_json(row["run_id"], "gate.json") or {}
        name = gate.get("deliverable", "memo_final.md")
        items.append({**row, "reasons": json.loads(row["reasons"] or "[]"),
                      "text": read_text(app.paths.artifacts / row["run_id"] / name),
                      "limits": (app.read_json(row["run_id"], "limit_status.json") or {}).get("rows", [])})
    return {"items": items}


def api_decide(app: App, body: dict) -> dict:
    decision = body.get("decision")
    if decision not in ("approve", "reject", "request_changes"):
        raise ApiError("Unknown decision.")
    if decision != "approve" and not str(body.get("note", "")).strip():
        raise ApiError("Add a note so the record explains this decision.")
    run_id = safe_run_id(body.get("run_id", ""))
    if not app.rows("SELECT 1 FROM approvals WHERE run_id = ? AND decision IS NULL", run_id):
        raise ApiError("That item has already been decided.", 409)
    app.queue_decision(run_id, decision, str(body.get("note", "")))
    return {"queued": True}


def api_approve_all(app: App, body: dict) -> dict:
    rows = app.rows("SELECT run_id FROM approvals WHERE decision IS NULL ORDER BY requested_at")
    for row in rows:
        app.queue_decision(row["run_id"], "approve", "Approved in bulk from the web app.")
    return {"queued": len(rows)}


def api_dashboard(app: App, q: dict) -> dict:
    latest = app.rows("SELECT run_id, as_of, status, llm FROM runs WHERE workflow = 'eod' AND status != 'blocked_input' "
                      "ORDER BY as_of DESC LIMIT 1")
    day = None
    if latest:
        run = latest[0]
        metrics = app.read_json(run["run_id"], "metrics.json") or {}
        limits = app.read_json(run["run_id"], "limit_status.json") or {}
        backtest = app.read_json(run["run_id"], "backtest.json") or {}
        day = {**run, "metrics": {k: metrics[k] for k in ("nav_usd", "daily_return", "var99_1d", "es975_1d", "drawdown",
                                                          "vol_ann_ewma", "top_risk_asset", "weight_max_asset") if k in metrics},
               "limits": limits.get("rows", []), "overall": limits.get("status"), "backtest": backtest}
    return {
        "day": day,
        "var": app.rows("SELECT as_of, var99, next_return, hit FROM var_ledger ORDER BY as_of"),
        "breaches": app.rows("SELECT * FROM breaches ORDER BY closed_on IS NULL DESC, opened_on DESC LIMIT 100"),
        "escalations": app.rows("SELECT id, sim_ts, run_id, severity, reason FROM escalations ORDER BY id DESC LIMIT 50"),
        "usage": (app.rows("SELECT COUNT(*) calls, COALESCE(SUM(tokens_in + tokens_out), 0) tokens, "
                           "COALESCE(SUM(cost_usd), 0) cost FROM llm_calls") or [{"calls": 0, "tokens": 0, "cost": 0}])[0],
    }


def published_files(app: App) -> list[Path]:
    base = app.paths.published
    return sorted((p for p in base.rglob("*") if p.is_file() and not p.name.endswith(".tmp")), reverse=True) if base.exists() else []


def api_reports(app: App, q: dict) -> dict:
    base = app.paths.published
    items = [{"path": p.relative_to(base).as_posix(), "kind": p.relative_to(base).parts[0], "name": p.stem}
             for p in published_files(app)]
    return {"items": items}


def api_report(app: App, q: dict) -> dict:
    base = app.paths.published.resolve()
    target = (base / q.get("path", [""])[0]).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise ApiError("No such report.", 404)
    return {"text": target.read_text(encoding="utf-8")}


def build_output_zip(app: App) -> bytes:
    """The full output of the workspace: everything published, the period summary and the audit tables."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("SUMMARY.md", period_summary(app.rows, app.backend_label(), versions.active(app.paths), book.load(app.paths)))
        for path in published_files(app):
            z.write(path, Path("published") / path.relative_to(app.paths.published))
        tables = {"runs": "SELECT run_id, workflow, as_of, cutoff, version, status, trigger, round, degraded, llm FROM runs ORDER BY as_of",
                  "breach_register": "SELECT * FROM breaches ORDER BY opened_on", "var_ledger": "SELECT * FROM var_ledger ORDER BY as_of",
                  "approvals": "SELECT * FROM approvals ORDER BY requested_at", "escalations": "SELECT * FROM escalations ORDER BY id"}
        for name, sql in tables.items():
            rows = app.rows(sql)
            if rows:
                lines = [",".join(rows[0])] + [",".join(csv_cell(v) for v in r.values()) for r in rows]
                z.writestr(f"audit/{name}.csv", "\n".join(lines) + "\n")
    return buffer.getvalue()


def csv_cell(value) -> str:
    text = "" if value is None else str(value)
    return '"' + text.replace('"', '""') + '"' if any(c in text for c in ',"\n') else text


def api_improve(app: App, q: dict) -> dict:
    paths = app.paths
    current = versions.active(paths)
    results = {}
    for folder in (ROOT / "eval" / "results", app.workspace / "eval" / "results"):
        for path in sorted(folder.glob("*.json")) if folder.exists() else []:
            data = json.loads(path.read_text(encoding="utf-8"))
            results[path.stem] = {"version": data["version"], "verdict": data["verdict"], "scorecard": {
                k: data["scorecard"][k] for k in ("var_exceptions", "kupiec_p", "independence_p", "basel_zone", "avg_var99")}}
    candidates = []
    for path in sorted((ROOT / "eval" / "candidates").glob("*.yaml")):
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        candidates.append({"name": path.stem, "hypothesis": spec["hypothesis"], "result": results.get(path.stem)})
    log = versions.history(paths)
    can_promote = sorted({e["version"] for e in log if e["event"] == "evaluated" and e["baseline"] == current
                          and e["decision"] == "accept"})
    moved = [e for e in log if e["event"] in ("promoted", "rolled_back") and e["version"] == current]
    return {"active": current, "candidates": candidates, "history": log[-30:], "can_promote": can_promote,
            "can_rollback": bool(moved and "from" in moved[-1])}


def api_evaluate(app: App, body: dict) -> dict:
    name = str(body.get("candidate", ""))
    path = ROOT / "eval" / "candidates" / f"{name}.yaml"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or not path.exists():
        raise ApiError("Unknown candidate.")
    # Scorecards compare like with like, so evaluation always uses the offline backend.
    return app.start_job("evaluate", ["eval", "--candidate", str(path)], {"candidate": name}, {"LLM_PROVIDER": "scripted"})


def api_baseline(app: App, body: dict) -> dict:
    return app.start_job("evaluate", ["eval", "--baseline"], {"candidate": "baseline"}, {"LLM_PROVIDER": "scripted"})


def api_promote(app: App, body: dict) -> dict:
    try:
        versions.promote(app.paths, str(body.get("version", "")), app.settings["name"] or "web user")
    except versions.VersionError as e:
        raise ApiError(str(e)) from e
    return {"active": versions.active(app.paths)}


def api_rollback(app: App, body: dict) -> dict:
    try:
        return {"active": versions.rollback(app.paths, app.settings["name"] or "web user", str(body.get("note") or "rollback from web app"))}
    except versions.VersionError as e:
        raise ApiError(str(e)) from e


def api_start_over(app: App, body: dict) -> dict:
    app.start_over()
    return {"ok": True}


def api_health(app: App, q: dict) -> dict:
    """Lets launch.py tell whether this server is RiskWatch, which code it runs, and whether it is busy."""
    return {"app": "riskwatch", "fingerprint": app.fingerprint, "busy": bool(app.job and app.job["state"] == "running")}


def api_shutdown(app: App, body: dict) -> dict:
    """Used by launch.py to replace an older copy. Never while a job runs: that would interrupt it."""
    if app.job and app.job["state"] == "running":
        raise ApiError("A run is in progress. Stop it first.", 409)
    threading.Thread(target=app.server.shutdown, daemon=True).start()
    return {"ok": True}


GET_ROUTES = {"/api/health": api_health, "/api/summary": api_summary, "/api/catalog": api_catalog, "/api/claude": api_claude, "/api/runs": api_runs,
              "/api/run": api_run, "/api/file": api_file, "/api/pending": api_pending, "/api/dashboard": api_dashboard,
              "/api/reports": api_reports, "/api/report": api_report, "/api/improve": api_improve}
POST_ROUTES = {"/api/settings": api_save_settings, "/api/test": api_test_connection, "/api/models": api_models,
               "/api/claude/login": api_claude_login, "/api/start": api_start_run, "/api/stop": api_stop,
               "/api/decide": api_decide, "/api/approve-all": api_approve_all, "/api/evaluate": api_evaluate,
               "/api/baseline": api_baseline, "/api/promote": api_promote, "/api/rollback": api_rollback,
               "/api/start-over": api_start_over, "/api/shutdown": api_shutdown}


class Handler(BaseHTTPRequestHandler):
    app: App
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:
        pass

    def host_allowed(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def send_bytes(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, status: int = 200) -> None:
        self.send_bytes(status, json.dumps(data, default=str).encode("utf-8"), "application/json; charset=utf-8")

    def run_route(self, fn, arg) -> None:
        try:
            self.send_json(fn(self.app, arg))
        except ApiError as e:
            self.send_json({"error": str(e)}, e.status)
        except Exception as e:
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_GET(self) -> None:
        if not self.host_allowed():
            return self.send_bytes(403, b"Forbidden", "text/plain")
        url = urlparse(self.path)
        if url.path in GET_ROUTES:
            return self.run_route(GET_ROUTES[url.path], parse_qs(url.query))
        if url.path == "/api/download":
            data = build_output_zip(self.app)
            return self.send_bytes(200, data, "application/zip",
                                   {"Content-Disposition": 'attachment; filename="riskwatch-output.zip"'})
        name = "index.html" if url.path == "/" else url.path.lstrip("/")
        path = (STATIC / name).resolve()
        if not path.is_relative_to(STATIC.resolve()) or not path.is_file() or path.suffix not in MIME:
            return self.send_bytes(404, b"Not found", "text/plain")
        body = path.read_bytes()
        if name == "index.html":
            body = body.replace(b"__TOKEN__", self.app.token.encode())
        self.send_bytes(200, body, MIME[path.suffix])

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        if not self.host_allowed() or not secrets.compare_digest(self.headers.get("X-RiskWatch-Token", ""), self.app.token):
            return self.send_bytes(403, b"Forbidden", "text/plain")
        route = POST_ROUTES.get(urlparse(self.path).path)
        if route is None:
            return self.send_bytes(404, b"Not found", "text/plain")
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self.send_json({"error": "Bad JSON."}, 400)
        self.run_route(route, body)


class LocalServer(ThreadingHTTPServer):
    """Refuses a port that another program already holds.

    The standard server sets SO_REUSEADDR, which on Windows lets a second server bind a port in use. It then
    reports success while the first one keeps every request, so a restarted app silently serves old code.
    """

    allow_reuse_address = os.name != "nt"

    def server_bind(self) -> None:
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class PortInUse(Exception):
    pass


def make_server(workspace: Path, port: int) -> tuple[ThreadingHTTPServer, App]:
    app = App(workspace, port)
    handler = type("BoundHandler", (Handler,), {"app": app})
    try:
        server = LocalServer(("127.0.0.1", port), handler)
    except OSError as e:  # only the bind: any other startup error must surface as itself
        raise PortInUse(port) from e
    app.port, app.server = server.server_address[1], server
    return server, app


def serve(port: int, open_browser: bool) -> None:
    workspace = Path(os.environ.get("RISKWATCH_WEB_HOME", ROOT / "runtime" / "web"))
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        server, app = make_server(workspace, port)
    except PortInUse:
        sys.exit(f"Port {port} is already in use, probably by another RiskWatch window. Close that window, or start "
                 f"this one on another port with: python launch.py --port {port + 1}")
    url = f"http://127.0.0.1:{app.port}/"
    # Read by launch.py to replace this copy when a newer version starts. Same trust as settings.json.
    marker = workspace / "server.json"
    marker.write_text(json.dumps({"port": app.port, "token": app.token, "fingerprint": app.fingerprint}), encoding="utf-8")
    print(f"RiskWatch is running at {url}\nKeep this window open. Press Ctrl+C to stop.", flush=True)
    if open_browser:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
        print("Stopped, because a newer copy of RiskWatch is taking over.")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        app.stop_job()
        server.server_close()
        marker.unlink(missing_ok=True)
