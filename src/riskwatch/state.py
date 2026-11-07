"""Durable workflow state in SQLite. Everything needed to resume a run lives here or in its artifacts."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

TERMINAL = {"completed", "rejected", "halted_error", "halted_budget", "halted_no_input"}
OPEN = {"pending", "running", "blocked_input", "blocked_dependency", "awaiting_approval"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY, workflow TEXT, as_of TEXT, cutoff TEXT, version TEXT,
  status TEXT, trigger TEXT, parent_run TEXT, round INTEGER DEFAULT 0,
  degraded INTEGER DEFAULT 0, degraded_reason TEXT, halted_reason TEXT, llm TEXT);
CREATE TABLE IF NOT EXISTS stages(
  run_id TEXT, stage TEXT, round INTEGER, status TEXT, attempts INTEGER DEFAULT 0,
  outputs TEXT, error TEXT, PRIMARY KEY(run_id, stage, round));
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, wall_ts REAL, sim_ts TEXT, run_id TEXT, stage TEXT,
  type TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS llm_calls(
  run_id TEXT, request_hash TEXT, stage TEXT, role TEXT, provider TEXT, model TEXT,
  response TEXT, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL, day TEXT,
  PRIMARY KEY(run_id, request_hash));
CREATE TABLE IF NOT EXISTS outbox(
  key TEXT PRIMARY KEY, run_id TEXT, kind TEXT, source TEXT, destination TEXT, sha256 TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS approvals(
  run_id TEXT, epoch INTEGER, requested_at TEXT, reasons TEXT, decision TEXT, actor TEXT, note TEXT,
  decided_at TEXT, sla_escalated INTEGER DEFAULT 0, PRIMARY KEY(run_id, epoch));
CREATE TABLE IF NOT EXISTS breaches(
  breach_id TEXT PRIMARY KEY, limit_id TEXT, severity TEXT, opened_on TEXT, last_seen TEXT,
  days_open INTEGER, peak REAL, closed_on TEXT);
CREATE TABLE IF NOT EXISTS var_ledger(
  as_of TEXT PRIMARY KEY, version TEXT, var99 REAL, next_return REAL, hit INTEGER);
CREATE TABLE IF NOT EXISTS dq_overrides(
  as_of TEXT, asset TEXT, action TEXT, judged_published_at TEXT, run_id TEXT, PRIMARY KEY(as_of, asset));
CREATE TABLE IF NOT EXISTS escalations(
  id INTEGER PRIMARY KEY AUTOINCREMENT, sim_ts TEXT, run_id TEXT, severity TEXT, reason TEXT,
  status TEXT DEFAULT 'open', dedupe TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS lease(id INTEGER PRIMARY KEY CHECK(id = 1), owner TEXT, expires REAL);
"""


class LeaseHeld(RuntimeError):
    pass


class State:
    """Thin wrapper over one SQLite file. Each public write commits, unless inside `transaction()`."""

    def __init__(self, path: Path, durable: bool = True):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute(f"PRAGMA synchronous={'FULL' if durable else 'OFF'}")
        self.db.executescript(SCHEMA)
        self.owner = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.sim_now = ""
        self._in_tx = False

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def transaction(self):
        if self._in_tx:
            yield
            return
        self.db.execute("BEGIN IMMEDIATE")
        self._in_tx = True
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")
        finally:
            self._in_tx = False

    def q(self, sql: str, *args) -> list[sqlite3.Row]:
        return self.db.execute(sql, args).fetchall()

    def one(self, sql: str, *args) -> sqlite3.Row | None:
        return self.db.execute(sql, args).fetchone()

    def x(self, sql: str, *args) -> None:
        self.db.execute(sql, args)

    # Lease: one controller at a time. A crashed owner stops renewing and the lease expires.
    def acquire_lease(self, ttl: float, takeover: bool = False) -> None:
        now = time.time()
        with self.transaction():
            row = self.one("SELECT owner, expires FROM lease WHERE id = 1")
            if row and row["owner"] != self.owner and row["expires"] > now and not takeover:
                raise LeaseHeld(f"lease held by {row['owner']} for {row['expires'] - now:.0f}s more")
            if row and row["owner"] != self.owner and takeover:
                self.event(None, None, "lease_takeover", {"from": row["owner"]})
            self.x("INSERT INTO lease(id, owner, expires) VALUES(1, ?, ?) "
                   "ON CONFLICT(id) DO UPDATE SET owner = excluded.owner, expires = excluded.expires",
                   self.owner, now + ttl)

    def release_lease(self) -> None:
        self.x("DELETE FROM lease WHERE owner = ?", self.owner)

    def event(self, run_id: str | None, stage: str | None, etype: str, detail: dict | None = None) -> None:
        self.x("INSERT INTO events(wall_ts, sim_ts, run_id, stage, type, detail) VALUES(?,?,?,?,?,?)",
               time.time(), self.sim_now, run_id, stage, etype, json.dumps(detail or {}, sort_keys=True))

    def escalate(self, run_id: str | None, severity: str, reason: str, dedupe: str | None = None) -> None:
        self.x("INSERT OR IGNORE INTO escalations(sim_ts, run_id, severity, reason, dedupe) VALUES(?,?,?,?,?)",
               self.sim_now, run_id, severity, reason, dedupe or f"{run_id}:{reason}")
        self.event(run_id, None, "escalated", {"severity": severity, "reason": reason})

    # Runs
    def create_run(self, run_id, workflow, as_of, cutoff, version, trigger, parent=None, llm="") -> bool:
        cur = self.db.execute(
            "INSERT OR IGNORE INTO runs(run_id, workflow, as_of, cutoff, version, status, trigger, parent_run, llm) "
            "VALUES(?,?,?,?,?,'pending',?,?,?)", (run_id, workflow, as_of, cutoff, version, trigger, parent, llm))
        created = cur.rowcount == 1
        if created:
            self.event(run_id, None, "run_created", {"trigger": trigger, "version": version, "cutoff": cutoff})
        return created

    def run(self, run_id: str) -> dict:
        row = self.one("SELECT * FROM runs WHERE run_id = ?", run_id)
        if row is None:
            raise KeyError(f"no such run: {run_id}")
        return dict(row)

    def set_run(self, run_id: str, **fields) -> None:
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.x(f"UPDATE runs SET {cols} WHERE run_id = ?", *fields.values(), run_id)

    # Stages
    def stage(self, run_id: str, stage: str, rnd: int) -> dict | None:
        row = self.one("SELECT * FROM stages WHERE run_id = ? AND stage = ? AND round = ?", run_id, stage, rnd)
        return dict(row) if row else None

    def begin_stage(self, run_id: str, stage: str, rnd: int) -> None:
        self.x("INSERT INTO stages(run_id, stage, round, status, attempts) VALUES(?,?,?,'running',1) "
               "ON CONFLICT(run_id, stage, round) DO UPDATE SET status = 'running', attempts = attempts + 1",
               run_id, stage, rnd)
        self.event(run_id, stage, "stage_started", {"round": rnd})

    def end_stage(self, run_id: str, stage: str, rnd: int, status: str, outputs: dict | None = None,
                  error: str | None = None) -> None:
        self.x("UPDATE stages SET status = ?, outputs = ?, error = ? WHERE run_id = ? AND stage = ? AND round = ?",
               status, json.dumps(outputs or {}, sort_keys=True), error, run_id, stage, rnd)
        self.event(run_id, stage, f"stage_{status}", {"round": rnd, "error": error} if error else {"round": rnd})

    def mark_interrupted(self, run_id: str) -> list[str]:
        rows = self.q("SELECT stage, round FROM stages WHERE run_id = ? AND status = 'running'", run_id)
        for r in rows:
            self.x("UPDATE stages SET status = 'interrupted' WHERE run_id = ? AND stage = ? AND round = ?",
                   run_id, r["stage"], r["round"])
            self.event(run_id, r["stage"], "stage_interrupted", {"round": r["round"]})
        return [r["stage"] for r in rows]

    def clear_stages(self, run_id: str, names: list[str]) -> None:
        for name in names:
            self.x("DELETE FROM stages WHERE run_id = ? AND stage = ?", run_id, name)

    # Durable key/value, used for scan watermarks and the circuit breaker
    def get_kv(self, key: str, default: str = "") -> str:
        row = self.one("SELECT value FROM kv WHERE key = ?", key)
        return row["value"] if row else default

    def set_kv(self, key: str, value: str) -> None:
        self.x("INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
               key, value)

    # LLM journal
    def llm_lookup(self, run_id: str, request_hash: str) -> str | None:
        row = self.one("SELECT response FROM llm_calls WHERE run_id = ? AND request_hash = ?", run_id, request_hash)
        return row["response"] if row else None

    def llm_record(self, run_id, request_hash, stage, role, provider, model, response,
                   tokens_in, tokens_out, cost, day) -> None:
        self.x("INSERT OR REPLACE INTO llm_calls VALUES(?,?,?,?,?,?,?,?,?,?,?)", run_id, request_hash, stage, role,
               provider, model, response, tokens_in, tokens_out, cost, day)

    def llm_usage(self, run_id: str) -> dict:
        row = self.one("SELECT COUNT(*) calls, COALESCE(SUM(tokens_in + tokens_out), 0) tokens, "
                       "COALESCE(SUM(cost_usd), 0) cost FROM llm_calls WHERE run_id = ?", run_id)
        return dict(row)

    def llm_day_cost(self, day: str) -> float:
        return self.one("SELECT COALESCE(SUM(cost_usd), 0) c FROM llm_calls WHERE day = ?", day)["c"]
