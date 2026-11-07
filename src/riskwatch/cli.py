"""Command line interface. Humans and cron use this; agents have no way to reach it."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

from .config import ROOT, default_paths, deep_merge, load_source_bundle
from .controller import Controller, Env
from .improve import versions
from .llm.providers import PermanentError, build_provider, load_dotenv
from .replay import load_scenario, replay
from .scheduler import status_summary, tick
from .state import LeaseHeld


def make_env(mode: str = "live", scenario: dict | None = None) -> Env:
    paths = default_paths()
    version = versions.active(paths)
    return Env(paths, versions.load_snapshot(paths, version), version, mode=mode,
               scripted_faults=(scenario or {}).get("scripted_faults"))


def cmd_init(args) -> None:
    env = make_env()  # a replay sets this itself; init is for `tick`-driven operation
    env.state.set_kv("book_start", args.start)
    print(f"Book start {args.start}, version {env.version}, state in {env.paths.db}")


def cmd_tick(args) -> None:
    env = make_env("replay" if args.now else "live", load_scenario(ROOT) if args.scenario else None)
    now = args.now or datetime.now().strftime("%Y-%m-%dT%H:%M")
    print(json.dumps(tick(env, now, args.takeover), indent=1))


def cmd_replay(args) -> None:
    scenario = load_scenario(ROOT)
    if args.no_drills:
        scenario["scripted_faults"] = {}
        scenario["approvals"]["overrides"] = {}
    env = make_env("replay", scenario)
    replay(env, scenario, args.start, args.end, lambda d: print(d, status_summary(env), flush=True), args.takeover,
           args.manual_approvals)
    print(status_summary(env))


def cmd_status(args) -> None:
    env = make_env()
    if args.run_id:
        print(json.dumps(env.state.run(args.run_id), indent=1))
        for row in env.state.q("SELECT stage, round, status, attempts, error FROM stages WHERE run_id = ? ORDER BY rowid", args.run_id):
            print(f"  {row['stage']:<16} r{row['round']} {row['status']:<12} attempts={row['attempts']} {row['error'] or ''}")
        return
    print(status_summary(env))
    for row in env.state.q("SELECT run_id, status, halted_reason FROM runs WHERE status NOT IN ('completed') ORDER BY as_of"):
        print(f"  {row['run_id']:<40} {row['status']:<20} {row['halted_reason'] or ''}")
    for row in env.state.q("SELECT severity, run_id, reason FROM escalations WHERE status = 'open' ORDER BY id DESC LIMIT 10"):
        print(f"  ! {row['severity']:<8} {row['run_id']}: {row['reason']}")


def cmd_pending(args) -> None:
    env = make_env()
    for row in env.state.q("SELECT a.run_id, a.requested_at, a.reasons FROM approvals a WHERE a.decision IS NULL"):
        print(f"{row['run_id']:<40} requested {row['requested_at']} reasons {row['reasons']}")


def cmd_decide(args) -> None:
    env = make_env()
    env.state.sim_now = args.now or env.state.get_kv("last_tick")
    env.state.wait_for_lease(env.bundle["policy"]["lease"]["ttl_seconds"], timeout=60.0)
    try:
        print(Controller(env).decide(args.run_id, args.decision, args.by, args.note))
    finally:
        env.state.release_lease()


def cmd_resume(args) -> None:
    env = make_env("replay" if args.replay else "live", load_scenario(ROOT) if args.replay else None)
    st = env.state
    st.acquire_lease(env.bundle["policy"]["lease"]["ttl_seconds"], args.takeover)
    try:
        run = st.run(args.run_id)
        if run["status"].startswith("halted"):
            st.event(args.run_id, None, "manual_resume", {"from": run["status"]})
            st.x("DELETE FROM stages WHERE run_id = ? AND status = 'failed'", args.run_id)
            st.set_run(args.run_id, status="pending", halted_reason=None)
        print(Controller(env).drive(args.run_id))
    finally:
        st.release_lease()


def cmd_circuit_reset(args) -> None:
    env = make_env()
    env.state.set_kv("circuit", "closed")
    env.state.event(None, None, "circuit_reset", {"by": args.by})
    print("circuit closed")


def cmd_provider_check(args) -> None:
    provider = build_provider(args.role)
    if provider is None:
        print("LLM_PROVIDER is unset or 'scripted': offline rule-based backend, no network, no key needed.")
        return
    print(f"Calling {provider.name} model {provider.model} at {provider.base_url} ...")
    reply = provider.complete([{"role": "system", "content": "Reply with exactly one JSON object."},
                               {"role": "user", "content": 'Reply with {"action":"final","output":{"ok":true}}'}],
                              200, {"role": "check", "as_of": "", "round": 0})
    print(f"Reply ({reply.tokens_in} tokens in, {reply.tokens_out} out): {reply.text[:200]}")


def cmd_versions(args) -> None:
    paths = default_paths()
    if args.action == "register":
        overlay = yaml.safe_load(Path(args.candidate).read_text(encoding="utf-8"))["overlay"] if args.candidate else None
        version = versions.register(paths, load_source_bundle(ROOT, overlay), args.note or "registered", args.candidate or "working tree")
        print(version)
        if args.activate:
            versions.activate_first(paths, version, args.by)
    elif args.action == "promote":
        versions.promote(paths, args.version, args.by)
        print(f"active version is now {args.version}")
    elif args.action == "rollback":
        print(f"active version is now {versions.rollback(paths, args.by, args.note or 'rollback')}")
    else:
        print(f"active: {versions.active(paths)}")
        for e in versions.history(paths):
            print(json.dumps(e, sort_keys=True))


def cmd_eval(args) -> None:
    from .improve import evaluate
    paths = default_paths()
    rules = yaml.safe_load((ROOT / "eval" / "policy.yaml").read_text(encoding="utf-8"))
    current = versions.active(paths)
    out_dir = Path(os.environ.get("RISKWATCH_EVAL_OUT", ROOT / "eval"))
    baseline_file = out_dir / "baselines" / f"{current}.json"
    if not baseline_file.exists() and (ROOT / "eval" / "baselines" / f"{current}.json").exists():
        baseline_file = ROOT / "eval" / "baselines" / f"{current}.json"
    if args.baseline:
        baseline_file = out_dir / "baselines" / f"{current}.json"
        result = evaluate.run_scorecard(versions.load_snapshot(paths, current), ROOT)
        baseline_file.parent.mkdir(parents=True, exist_ok=True)
        baseline_file.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(f"baseline scorecard frozen: {baseline_file}")
        return
    if not baseline_file.exists():
        sys.exit(f"no frozen baseline for {current}; run `riskwatch eval --baseline` first")
    baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
    spec = yaml.safe_load(Path(args.candidate).read_text(encoding="utf-8"))
    bundle = deep_merge(versions.load_snapshot(paths, current), spec["overlay"])
    version = versions.register(paths, bundle, spec["hypothesis"], args.candidate)
    result = evaluate.run_scorecard(bundle, ROOT)
    verdict = evaluate.decide(result, baseline, rules)
    name = Path(args.candidate).stem
    results_dir = out_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / f"{name}.json").write_text(json.dumps({**result, "verdict": verdict}, indent=1, sort_keys=True) + "\n",
                                              encoding="utf-8", newline="\n")
    report = results_dir / f"{name}.md"
    evaluate.write_comparison(report, result, baseline, verdict, spec["hypothesis"])
    recorded = report.relative_to(ROOT).as_posix() if report.is_relative_to(ROOT) else report.name
    versions.record_evaluation(paths, version, current, verdict["decision"], verdict["reasons"], recorded)
    print(f"{name}: {verdict['decision'].upper()} ({version})")
    for reason in verdict["reasons"]:
        print(f"  {reason}")


def cmd_web(args) -> None:
    from .web.server import serve
    serve(args.port, not args.no_browser)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="riskwatch", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="set the first date the book is monitored")
    s.add_argument("--start", required=True)
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("tick", help="scheduler entry point: start whatever is due")
    s.add_argument("--now", help="simulated time, e.g. 2020-03-16T20:00")
    s.add_argument("--scenario", action="store_true", help="apply the replay fault scenario")
    s.add_argument("--takeover", action="store_true", help="take the lease from a crashed controller")
    s.set_defaults(fn=cmd_tick)

    s = sub.add_parser("replay", help="run history on a simulated clock")
    s.add_argument("--start")
    s.add_argument("--end")
    s.add_argument("--takeover", action="store_true", help="take the lease from a crashed controller")
    s.add_argument("--manual-approvals", action="store_true", help="leave approvals for a person to answer")
    s.add_argument("--no-drills", action="store_true", help="leave out the simulated agent and approver drills")
    s.set_defaults(fn=cmd_replay)

    s = sub.add_parser("status", help="show runs, or the stages of one run")
    s.add_argument("run_id", nargs="?")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("pending", help="list approvals waiting for a human")
    s.set_defaults(fn=cmd_pending)

    for name, decision in (("approve", "approve"), ("reject", "reject"), ("request-changes", "request_changes")):
        s = sub.add_parser(name, help=f"record a human decision: {decision}")
        s.add_argument("run_id")
        s.add_argument("--by", required=True)
        s.add_argument("--note", default="")
        s.add_argument("--now")
        s.set_defaults(fn=cmd_decide, decision=decision)

    s = sub.add_parser("resume", help="continue an interrupted or halted run")
    s.add_argument("run_id")
    s.add_argument("--takeover", action="store_true")
    s.add_argument("--replay", action="store_true", help="resume under the replay scenario")
    s.set_defaults(fn=cmd_resume)

    s = sub.add_parser("circuit-reset", help="close the circuit breaker after investigating")
    s.add_argument("--by", required=True)
    s.set_defaults(fn=cmd_circuit_reset)

    s = sub.add_parser("provider-check", help="test the configured LLM provider with one small call")
    s.add_argument("--role", help="check the override for one role, e.g. reviewer")
    s.set_defaults(fn=cmd_provider_check)

    s = sub.add_parser("versions", help="register, promote, roll back or list versions")
    s.add_argument("action", choices=["list", "register", "promote", "rollback"])
    s.add_argument("version", nargs="?")
    s.add_argument("--candidate")
    s.add_argument("--note")
    s.add_argument("--by", default="unknown")
    s.add_argument("--activate", action="store_true")
    s.set_defaults(fn=cmd_versions)

    s = sub.add_parser("web", help="start the browser app")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    s.set_defaults(fn=cmd_web)

    s = sub.add_parser("eval", help="freeze the baseline or test a candidate against it")
    s.add_argument("--baseline", action="store_true")
    s.add_argument("--candidate")
    s.set_defaults(fn=cmd_eval)
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    args = build_parser().parse_args(argv)
    try:
        args.fn(args)
    except (versions.VersionError, PermanentError) as e:
        sys.exit(f"error: {e}")
    except LeaseHeld as e:
        sys.exit(f"error: {e}. If that controller crashed, repeat the command with --takeover.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
