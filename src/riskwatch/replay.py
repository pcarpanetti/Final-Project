"""Drive the workflow through history on a simulated clock, one tick at a time."""
from __future__ import annotations

from pathlib import Path

import yaml

from .controller import Controller, Env
from .scheduler import tick

REPLAY_ACTOR = "replay-policy"


def load_scenario(root: Path, name: str = "replay") -> dict:
    return yaml.safe_load((root / "scenarios" / f"{name}.yaml").read_text(encoding="utf-8"))


def answer_pending(env: Env, ctl: Controller, scenario: dict, now: str) -> None:
    rules = scenario["approvals"]
    for row in env.state.q("SELECT run_id FROM runs WHERE status = 'awaiting_approval' ORDER BY as_of"):
        rule = rules.get("overrides", {}).get(row["run_id"], {})
        if now < rule.get("hold_until", ""):
            continue
        ctl.decide(row["run_id"], rule.get("decision", rules["default"]), REPLAY_ACTOR, rule.get("note", ""))
        # request_changes re-enters the gate, so answer the fresh request with the default rule.
        if env.state.run(row["run_id"])["status"] == "awaiting_approval":
            ctl.decide(row["run_id"], rules["default"], REPLAY_ACTOR, "")


def replay(env: Env, scenario: dict, start: str | None = None, end: str | None = None,
           on_day=None, takeover: bool = False, manual: bool = False) -> None:
    """With `manual`, nothing answers approvals: they wait for a person, and the days carry on.

    Simulated time runs far faster than a person, so the approval SLA is not applied in that mode.
    """
    start = start or scenario["window"]["start"]
    end = end or scenario["window"]["end"]
    if not env.state.get_kv("book_start"):
        env.state.set_kv("book_start", start)
    ctl = Controller(env)
    for day in env.store.trading_days(start, end):
        for time_of_day in scenario["tick_times"]:
            now = f"{day}T{time_of_day}"
            tick(env, now, takeover, sla=not manual, lease_wait=600.0)
            takeover = False
            if not manual:
                answer_pending(env, ctl, scenario, now)
        if on_day:
            on_day(day)
