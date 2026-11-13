"""The harness. It decides what runs, when, how often and whether to stop.

Agents make judgement calls inside a stage. Everything about execution lives here: ordering, retries,
checkpoints, budgets, approvals and escalation. No agent can reach this code.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import traceback
from pathlib import Path

from . import crash
from .agents.runtime import AgentFailed
from .agents.runtime import run_agent as _run_agent
from .agents.tools import Tools
from .config import Paths
from .llm.client import BudgetExceeded, LLMClient, ProviderFailed
from .pit import PointInTimeStore
from .state import TERMINAL, State


class InputNotReady(Exception):
    """Required data is not available or not usable at the cutoff."""


class WaitForDependency(Exception):
    """An upstream run has not reached the point this stage depends on."""


class Env:
    """Everything a run needs from the outside world. Evaluation builds its own isolated Env."""

    def __init__(self, paths: Paths, bundle: dict, version: str, *, store: PointInTimeStore | None = None,
                 mode: str = "live", scripted_faults: dict | None = None, sleep=time.sleep,
                 durable: bool = True):
        self.paths, self.bundle, self.version, self.mode = paths, bundle, version, mode
        self.durable = durable
        self.state = State(paths.db, durable)
        self.store = store or PointInTimeStore(paths.data, paths.book)
        self.llm = LLMClient(self.state, bundle["policy"], scripted_faults, sleep)

    def bundle_for(self, version: str) -> dict:
        """A run keeps the version it started on, even if the active version changes mid-flight."""
        if version == self.version:
            return self.bundle
        from .improve.versions import load_snapshot
        return load_snapshot(self.paths, version)

    def close(self) -> None:
        self.state.close()


class StageContext:
    def __init__(self, env: Env, run: dict, bundle: dict, stage: str, rnd: int, started_at: float):
        self.env, self.run, self.bundle, self.stage, self.round = env, run, bundle, stage, rnd
        self.state, self.store, self.started_at = env.state, env.store, started_at
        self.dir = env.paths.artifacts / run["run_id"]
        self.outputs: dict[str, str] = {}
        self.commit_ops: list = []

    def path(self, name: str) -> Path:
        return self.dir / name

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    def read_text(self, name: str) -> str:
        return self.path(name).read_text(encoding="utf-8")

    def read_json(self, name: str):
        return json.loads(self.read_text(name))

    def write_text(self, name: str, text: str) -> None:
        """Write to a temp file then rename, so a crash can never leave half an artifact."""
        target = self.path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            if self.env.durable:
                f.flush()
                os.fsync(f.fileno())
        os.replace(tmp, target)
        self.outputs[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()

    def write_json(self, name: str, obj) -> None:
        self.write_text(name, json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n")

    def on_commit(self, sql: str, *args) -> None:
        """Queue a state change that lands in the same transaction as this stage's completion."""
        self.commit_ops.append((sql, args))

    def event(self, etype: str, detail: dict | None = None) -> None:
        self.state.event(self.run["run_id"], self.stage, etype, detail)

    def escalate(self, severity: str, reason: str) -> None:
        self.state.escalate(self.run["run_id"], severity, reason)

    def complete(self, role: str, messages: list[dict], max_tokens: int) -> str:
        return self.env.llm.complete(
            run_id=self.run["run_id"], stage=self.stage, role=role, messages=messages, max_tokens=max_tokens,
            meta={"role": role, "as_of": self.run["as_of"], "round": self.round, "stage": self.stage},
            day=self.run["as_of"], started_at=self.started_at)

    def agent(self, role: str, payload: dict, legend: str = "") -> dict:
        return _run_agent(self, role, payload, Tools(self), legend)


class Controller:
    def __init__(self, env: Env):
        self.env = env

    def create_run(self, run_id: str, workflow: str, as_of: str, cutoff: str, trigger: str,
                   parent: str | None = None) -> bool:
        return self.env.state.create_run(run_id, workflow, as_of, cutoff, self.env.version, trigger, parent,
                                         self.env.llm.describe())

    def drive(self, run_id: str) -> str:
        """Advance a run as far as it can go. Safe to call repeatedly and after any crash."""
        st = self.env.state
        run = st.run(run_id)
        if run["status"] in TERMINAL:
            return run["status"]
        bundle = self.env.bundle_for(run["version"])
        wf = bundle["workflows"][run["workflow"]]

        interrupted = st.mark_interrupted(run_id)
        if interrupted:
            st.event(run_id, None, "run_resumed", {"interrupted": interrupted})
        if not self._artifacts_intact(run, wf):
            return st.run(run_id)["status"]

        st.set_run(run_id, status="running")
        started = time.time()
        wall_limit = bundle["policy"]["budgets"]["per_run"]["max_wall_seconds"]
        while True:
            run = st.run(run_id)
            stage = self._next_stage(run, wf)
            if stage is None:
                st.set_run(run_id, status="completed")
                st.event(run_id, None, "run_completed")
                return "completed"
            if time.time() - started > wall_limit:
                return self._halt(run_id, "halted_budget", f"wall time above {wall_limit}s")
            if not self._run_stage(run, bundle, wf, stage, started):
                return st.run(run_id)["status"]

    def _round_of(self, run: dict, wf: dict, name: str) -> int:
        return run["round"] if name in wf.get("revision_loop", {}).get("stages", []) else 0

    def _next_stage(self, run: dict, wf: dict) -> dict | None:
        finished = {"done", "skipped", "degraded"}
        statuses = {}
        for stage in wf["stages"]:
            row = self.env.state.stage(run["run_id"], stage["name"], self._round_of(run, wf, stage["name"]))
            statuses[stage["name"]] = row["status"] if row else None
            if statuses[stage["name"]] in finished:
                continue
            blocked = [d for d in stage.get("depends_on", []) if statuses[d] not in finished]
            if blocked:
                raise RuntimeError(f"{stage['name']} is ready but {blocked} are unfinished")
            return stage
        return None

    def _halt(self, run_id: str, status: str, reason: str) -> str:
        st = self.env.state
        st.set_run(run_id, status=status, halted_reason=reason)
        st.escalate(run_id, "high", f"{status}: {reason}")
        return status

    def _artifacts_intact(self, run: dict, wf: dict) -> bool:
        """Trust a checkpoint only if its outputs still hash correctly; otherwise redo the work."""
        run_dir = self.env.paths.artifacts / run["run_id"]
        names = [s["name"] for s in wf["stages"]]
        rows = self.env.state.q("SELECT stage, round, outputs FROM stages WHERE run_id = ? AND status = 'done'",
                                run["run_id"])
        bad = set()
        for row in rows:
            for rel, digest in json.loads(row["outputs"] or "{}").items():
                path = run_dir / rel
                if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    bad.add(row["stage"])
        if not bad:
            return True
        first = min(names.index(b) for b in bad)
        tail = wf["stages"][first:]
        done = {r["stage"] for r in rows}
        unsafe = [s["name"] for s in tail if s.get("side_effect") and s["name"] in done]
        self.env.state.event(run["run_id"], None, "artifact_corrupt", {"stages": sorted(bad), "unsafe": unsafe})
        if unsafe:
            self._halt(run["run_id"], "halted_error", f"corrupt artifacts upstream of completed {unsafe}")
            return False
        self.env.state.clear_stages(run["run_id"], [s["name"] for s in tail])
        return True

    def _run_stage(self, run: dict, bundle: dict, wf: dict, stage: dict, started: float) -> bool:
        """Execute one stage and checkpoint it. Returns False when the run must stop for now."""
        from .stages import pipeline
        st = self.env.state
        run_id, name = run["run_id"], stage["name"]
        rnd = self._round_of(run, wf, name)
        ctx = StageContext(self.env, run, bundle, name, rnd, started)
        st.renew_lease()

        predicate = stage.get("when")
        if predicate and not pipeline.PREDICATES[predicate](ctx):
            st.begin_stage(run_id, name, rnd)
            st.end_stage(run_id, name, rnd, "skipped")
            return self._after_stage(ctx, wf)

        if stage["kind"] == "gate":
            return self._approval(ctx)

        st.begin_stage(run_id, name, rnd)
        crash.point(f"{name}:started")
        try:
            pipeline.STAGES[name](ctx)
            crash.point(f"{name}:work_done")
            with st.transaction():
                for sql, args in ctx.commit_ops:
                    st.x(sql, *args)
                crash.point(f"{name}:mid_commit")
                st.end_stage(run_id, name, rnd, "done", ctx.outputs)
            crash.point(f"{name}:committed")
        except InputNotReady as e:
            st.end_stage(run_id, name, rnd, "waiting", error=str(e))
            st.set_run(run_id, status="blocked_input", halted_reason=str(e))
            return False
        except WaitForDependency as e:
            st.end_stage(run_id, name, rnd, "waiting", error=str(e))
            st.set_run(run_id, status="blocked_dependency", halted_reason=str(e))
            return False
        except (ProviderFailed, AgentFailed, BudgetExceeded) as e:
            st.end_stage(run_id, name, rnd, "failed", error=str(e))
            if stage.get("on_failure") != "degrade":
                self._halt(run_id, "halted_error", f"{name}: {e}")
                return False
            self._degrade(run_id, name, rnd, str(e))
            return True
        except Exception as e:
            st.end_stage(run_id, name, rnd, "failed", error=traceback.format_exc(limit=4))
            self._halt(run_id, "halted_error", f"{name}: {type(e).__name__}: {e}")
            return False
        return self._after_stage(ctx, wf)

    def _degrade(self, run_id: str, stage: str, rnd: int, reason: str) -> None:
        """Lose the narrative, keep the numbers: the run continues to a template memo and a human."""
        st = self.env.state
        st.x("UPDATE stages SET status = 'degraded' WHERE run_id = ? AND stage = ? AND round = ?", run_id, stage, rnd)
        st.set_run(run_id, degraded=1, degraded_reason=f"{stage}: {reason}")
        st.escalate(run_id, "high", f"degraded at {stage}: {reason}")

    def _after_stage(self, ctx: StageContext, wf: dict) -> bool:
        from .stages import pipeline
        loop = wf.get("revision_loop")
        if not loop or ctx.stage != loop["stages"][-1]:
            return True
        st, run_id = self.env.state, ctx.run["run_id"]
        run = st.run(run_id)
        if run["degraded"] or pipeline.loop_passed(ctx):
            return True
        max_rounds = ctx.bundle["policy"]["revision"]["max_rounds"]
        if run["round"] + 1 < max_rounds:
            st.set_run(run_id, round=run["round"] + 1)
            st.event(run_id, None, "revision_started", {"round": run["round"] + 1})
        else:
            self._degrade(run_id, ctx.stage, ctx.round, f"no acceptable memo after {max_rounds} rounds")
        return True

    def _approval(self, ctx: StageContext) -> bool:
        st, run_id = self.env.state, ctx.run["run_id"]
        row = st.one("SELECT * FROM approvals WHERE run_id = ? ORDER BY epoch DESC LIMIT 1", run_id)
        if row is None or row["decision"] == "request_changes":
            epoch = 0 if row is None else row["epoch"] + 1
            reasons = ctx.read_json("gate.json")["reasons"]
            st.x("INSERT INTO approvals(run_id, epoch, requested_at, reasons) VALUES(?,?,?,?)",
                 run_id, epoch, st.sim_now, json.dumps(reasons))
            st.event(run_id, "approval", "approval_requested", {"reasons": reasons})
            row = None
        if row is None or row["decision"] is None:
            if not st.stage(run_id, "approval", 0):
                st.begin_stage(run_id, "approval", 0)
                st.end_stage(run_id, "approval", 0, "waiting")
            st.set_run(run_id, status="awaiting_approval")
            return False
        if row["decision"] == "approve":
            st.end_stage(run_id, "approval", 0, "done")
            return True
        st.end_stage(run_id, "approval", 0, "done")
        st.set_run(run_id, status="rejected", halted_reason=row["note"] or "rejected by approver")
        st.event(run_id, "approval", "run_rejected", {"by": row["actor"]})
        return False

    def decide(self, run_id: str, decision: str, actor: str, note: str = "") -> str:
        """Record a human decision. Only a person (or a replay policy standing in for one) calls this."""
        st = self.env.state
        run = st.run(run_id)
        if run["status"] != "awaiting_approval":
            raise ValueError(f"{run_id} is {run['status']}, not awaiting approval")
        if decision not in ("approve", "reject", "request_changes"):
            raise ValueError(f"unknown decision {decision}")
        bundle = self.env.bundle_for(run["version"])
        wf = bundle["workflows"][run["workflow"]]
        can_revise = ("revision_loop" in wf and not run["degraded"]
                      and run["round"] + 1 < bundle["policy"]["revision"]["max_rounds"])
        if decision == "request_changes" and not can_revise:
            st.event(run_id, "approval", "request_changes_unavailable", {"note": note})
            decision = "reject"
        with st.transaction():
            st.x("UPDATE approvals SET decision = ?, actor = ?, note = ?, decided_at = ? "
                 "WHERE run_id = ? AND decided_at IS NULL", decision, actor, note, st.sim_now, run_id)
            st.event(run_id, "approval", "human_decision", {"decision": decision, "by": actor, "note": note})
            if decision == "request_changes":
                nxt = run["round"] + 1
                st.set_run(run_id, round=nxt)
                st.clear_stages(run_id, ["finalise_memo", "gate_policy", "approval"])
                ctx = StageContext(self.env, run, bundle, "approval", nxt, time.time())
                ctx.write_json(f"feedback.r{nxt}.json", [{"source": "human", "by": actor, "note": note}])
        return self.drive(run_id)
