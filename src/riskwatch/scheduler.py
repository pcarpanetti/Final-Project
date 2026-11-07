"""Triggers. `tick` is the only entry point a scheduler needs, and it is safe to call at any time.

In production a cron job calls `riskwatch tick` every 30 minutes. In replay, a simulated clock calls it.
"""
from __future__ import annotations

import json

from .controller import Controller, Env
from .state import OPEN


def _add_hours(stamp: str, hours: float) -> str:
    from datetime import datetime, timedelta
    return (datetime.fromisoformat(stamp) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")


def eod_cutoff(env: Env, day: str) -> str:
    return f"{day}T{env.bundle['policy']['schedule']['eod_cutoff']}"


def scan_new_inputs(env: Env, ctl: Controller, now: str) -> None:
    """New-input trigger: a correction for an already reported date starts a restatement run."""
    st = env.state
    after = st.get_kv("corrections_scanned_to", "0000")
    days: dict[str, str] = {}
    for row in env.store.corrections_between(after, now):
        original = st.one("SELECT cutoff, status FROM runs WHERE run_id = ?", f"eod-{row['as_of']}")
        if original and original["cutoff"] < row["published_at"] and original["status"] not in ("pending", "blocked_input"):
            days[row["as_of"]] = max(days.get(row["as_of"], ""), row["published_at"])
    for day, published in sorted(days.items()):
        run_id = f"restate-{day}-{published.replace('-', '').replace(':', '').replace('T', '')}"
        ctl.create_run(run_id, "restate", day, now, "new_input:vendor_correction", parent=f"eod-{day}")
    st.set_kv("corrections_scanned_to", now)


def retry_blocked(env: Env, now: str) -> None:
    """Re-open runs waiting for data. Waiting past the cutoff is a logged decision, not a silent one."""
    st = env.state
    deadline_time = env.bundle["policy"]["schedule"]["hard_deadline"]
    for run in st.q("SELECT * FROM runs WHERE status = 'blocked_input' ORDER BY as_of"):
        if now <= run["cutoff"]:
            continue
        if now > f"{run['as_of']}T{deadline_time}":
            st.set_run(run["run_id"], status="halted_no_input")
            st.escalate(run["run_id"], "critical", f"no usable input by {deadline_time}: {run['halted_reason']}")
            continue
        st.x("DELETE FROM stages WHERE run_id = ? AND status = 'waiting'", run["run_id"])
        st.event(run["run_id"], None, "cutoff_extended", {"from": run["cutoff"], "to": now, "why": run["halted_reason"]})
        st.set_run(run["run_id"], cutoff=now, status="pending")


def schedule_due(env: Env, ctl: Controller, now: str) -> None:
    """Scheduled trigger. Creating runs for every due date also catches up after any downtime."""
    st = env.state
    start = st.get_kv("book_start")
    if not start:
        return
    for day in env.store.trading_days(start, now[:10]):
        cutoff = eod_cutoff(env, day)
        if cutoff <= now:
            ctl.create_run(f"eod-{day}", "eod", day, cutoff, "schedule:eod")
        nxt = env.store.next_day(day)
        if nxt and nxt[:7] != day[:7] and f"{nxt}T09:00" <= now:
            ctl.create_run(f"monthly-{day[:7]}", "monthly", day, f"{nxt}T09:00", "schedule:month_end")


def check_sla(env: Env, now: str) -> None:
    st = env.state
    hours = env.bundle["policy"]["escalation"]["approval_sla_hours"]
    for row in st.q("SELECT * FROM approvals WHERE decision IS NULL AND sla_escalated = 0"):
        if row["requested_at"] and _add_hours(row["requested_at"], hours) <= now:
            st.x("UPDATE approvals SET sla_escalated = 1 WHERE run_id = ? AND epoch = ?", row["run_id"], row["epoch"])
            st.escalate(row["run_id"], "medium", f"approval unanswered for {hours}h, routed to backup approver")


def circuit_open(env: Env) -> bool:
    """Stop starting work after repeated halts: something systematic is wrong and a human must look."""
    st = env.state
    if st.get_kv("circuit") == "open":
        return True
    limit = env.bundle["policy"]["escalation"]["circuit_breaker_halts"]
    recent = [r["status"] for r in st.q("SELECT status FROM runs WHERE workflow = 'eod' ORDER BY as_of DESC LIMIT ?", limit)]
    if len(recent) == limit and all(s.startswith("halted") for s in recent):
        st.set_kv("circuit", "open")
        st.escalate(None, "critical", f"circuit breaker opened after {limit} halted runs", dedupe=f"circuit:{st.sim_now}")
        return True
    return False


def open_runs(env: Env) -> list[str]:
    marks = ",".join("?" * len(OPEN))
    rows = env.state.q(f"SELECT run_id FROM runs WHERE status IN ({marks}) ORDER BY as_of, run_id", *sorted(OPEN))
    return [r["run_id"] for r in rows]


def tick(env: Env, now: str, takeover: bool = False) -> dict:
    st = env.state
    st.sim_now = now
    ctl = Controller(env)
    st.acquire_lease(env.bundle["policy"]["lease"]["ttl_seconds"], takeover)
    try:
        if circuit_open(env):
            return {"now": now, "circuit": "open", "runs": {}}
        scan_new_inputs(env, ctl, now)
        retry_blocked(env, now)
        schedule_due(env, ctl, now)
        results = {}
        for run_id in open_runs(env):
            if st.run(run_id)["status"] != "awaiting_approval":
                results[run_id] = ctl.drive(run_id)
        check_sla(env, now)
        return {"now": now, "circuit": "closed", "runs": results}
    finally:
        st.release_lease()


def status_summary(env: Env) -> str:
    rows = env.state.q("SELECT status, COUNT(*) n FROM runs GROUP BY status ORDER BY status")
    return json.dumps({r["status"]: r["n"] for r in rows}, sort_keys=True)
