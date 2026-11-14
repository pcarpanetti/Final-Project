"""Stage implementations. Each takes a StageContext; the controller decides when each one runs."""
from __future__ import annotations

import hashlib
import json
import os
import re

import numpy as np
import pandas as pd

from .. import crash
from ..agents.tools import Tools
from ..controller import InputNotReady, WaitForDependency
from ..memo import resolve, template_memo
from ..risk import backtest
from ..risk.engine import age_weights, compute_metrics
from ..risk.limits import evaluate_limits
from ..state import TERMINAL
from ..verify.checks import run_checks


def _csv(frame: pd.DataFrame | pd.Series) -> str:
    return frame.to_csv(lineterminator="\n", float_format="%.10g")


def _load(ctx, name: str) -> pd.DataFrame:
    return pd.read_csv(ctx.path(name), index_col=0)


def _policy(ctx) -> dict:
    return ctx.bundle["policy"]


def overall_status(rows: list[dict]) -> str:
    states = {r["status"] for r in rows}
    return "BREACH" if "breach" in states else "WARNING" if "warning" in states else "NORMAL"


def eod_run_id(day: str) -> str:
    return f"eod-{day}"


# ---- Predicates: named conditions the workflow YAML can refer to ----

def has_dq_exceptions(ctx) -> bool:
    return bool(ctx.read_json("dq_report.json")["exceptions"])


def not_degraded(ctx) -> bool:
    return not ctx.state.run(ctx.run["run_id"])["degraded"]


def verify_passed(ctx) -> bool:
    return not_degraded(ctx) and ctx.read_json(f"verification.r{ctx.round}.json")["passed"]


def approval_required(ctx) -> bool:
    return ctx.read_json("gate.json")["approval_required"]


PREDICATES = {"has_dq_exceptions": has_dq_exceptions, "not_degraded": not_degraded,
              "verify_passed": verify_passed, "approval_required": approval_required}


def loop_passed(ctx) -> bool:
    if not ctx.read_json(f"verification.r{ctx.round}.json")["passed"]:
        return False
    return ctx.read_json(f"review.r{ctx.round}.json")["verdict"] == "pass"


# ---- Data ----

LAUNCH_NAV = 100_000_000.0  # the default fund's size at launch; a workspace's own book sets `launch_nav`
DQ_HISTORY_DAYS = 61        # dq_checks compares today with the 60 days before it


def history_days(risk_cfg: dict) -> int:
    """Trading days of returns a run needs, today included. Older rows cannot change any figure."""
    return max(risk_cfg["var"]["lookback_days"] + 1, risk_cfg["ewma_window"], risk_cfg["beta_window"], DQ_HISTORY_DAYS)


def book_launch(ctx) -> str:
    """The fund launches at the close of the trading day before the workspace's first day."""
    first = ctx.state.get_kv("book_start")
    if not first:
        row = ctx.state.one("SELECT MIN(as_of) d FROM runs WHERE workflow = 'eod'")
        first = row["d"] if row and row["d"] else ctx.run["as_of"]
    launch = ctx.store.previous_day(first)
    if launch is None:
        raise ValueError(f"no trading day before {first} to launch the book")
    return launch


def ingest(ctx) -> None:
    run, policy = ctx.run, _policy(ctx)
    as_of, cutoff = run["as_of"], run["cutoff"]
    keep = history_days(ctx.bundle["risk_model"])
    snap = ctx.store.snapshot(as_of, cutoff, history=keep)
    if as_of not in snap.returns.index or as_of not in snap.factors.index:
        raise InputNotReady(f"market feed for {as_of} not published by {cutoff}")
    if as_of not in snap.weights.index:
        raise InputNotReady(f"positions for {as_of} not published by {cutoff}")
    weight_sum = float(snap.weights.loc[as_of].sum())
    if abs(weight_sum - 1.0) > policy["dq"]["positions_sum_tolerance"]:
        raise InputNotReady(f"positions for {as_of} fail reconciliation: weights sum to {weight_sum:.4f}")

    # An override stands only while the record it judged is still the latest one from the vendor.
    returns = snap.returns.tail(keep).copy()
    applied = []
    for o in ctx.state.q("SELECT * FROM dq_overrides WHERE as_of < ? ORDER BY as_of, asset", as_of):
        if o["as_of"] not in returns.index:
            continue  # older than any figure uses
        current = snap.published.at[o["as_of"], o["asset"]] if o["as_of"] in snap.published.index else None
        if not isinstance(current, str) or current == o["judged_published_at"]:
            returns.at[o["as_of"], o["asset"]] = 0.0
            applied.append({"as_of": o["as_of"], "asset": o["asset"], "action": o["action"]})

    # Today's weights and the day before, which is all the risk figures use.
    launch = book_launch(ctx)
    weights = snap.weights.loc[launch:as_of].tail(2)
    # NAV rescaled so the fund starts at its launch NAV. Drawdown needs only the peak since launch, so the
    # launch, peak and today rows are kept, which keeps each run's inputs small over decades.
    nav = snap.nav.loc[launch:as_of]
    nav = nav * (float(ctx.state.get_kv("launch_nav") or LAUNCH_NAV) / nav.loc[launch])
    nav = nav.loc[sorted({launch, nav.idxmax(), as_of})]

    ctx.write_text("inputs/returns.csv", _csv(returns))
    ctx.write_text("inputs/factors.csv", _csv(snap.factors.tail(keep)))
    ctx.write_text("inputs/weights.csv", _csv(weights))
    ctx.write_text("inputs/nav.csv", _csv(nav))
    ctx.write_json("inputs/manifest.json", {
        "as_of": as_of, "cutoff": cutoff, "max_published_at": snap.max_published_at,
        "published_today": {a: (v if isinstance(v, str) else None) for a, v in snap.published.loc[as_of].items()},
        "notes": snap.notes, "overrides_applied": applied, "version": run["version"]})


def _peer_evidence(hist: pd.DataFrame, today: pd.Series, asset: str, lam: float) -> dict:
    peers = [c for c in hist.columns if c != asset]
    h = hist.tail(60)
    x, y = h[peers].median(axis=1).to_numpy(), h[asset].to_numpy()
    beta = float(np.dot(x, y) / np.dot(x, x))
    resid_vol = float(np.std(y - beta * x))
    peer_today = float(today[peers].median())
    expected = beta * peer_today
    vol = float(np.sqrt(age_weights(60, lam) @ (y ** 2)))
    return {"z": round(float(today[asset]) / vol, 2), "peer_median": round(peer_today, 6),
            "expected_ret": round(expected, 6), "residual_z": round((float(today[asset]) - expected) / resid_vol, 2)}


def dq_checks(ctx) -> None:
    cfg = _policy(ctx)["dq"]
    returns = _load(ctx, "inputs/returns.csv")
    as_of = ctx.run["as_of"]
    today, hist = returns.loc[as_of], returns.loc[:as_of].iloc[:-1]
    filled = today.fillna(today.median())
    exceptions = []
    for asset in returns.columns:
        ret = today[asset]
        if pd.isna(ret):
            exceptions.append({"id": f"missing_row:{asset}", "type": "missing_row", "asset": asset})
            continue
        evidence = _peer_evidence(hist, filled, asset, cfg["outlier_vol_lambda"])
        base = {"asset": asset, "ret": float(ret), **evidence}
        if abs(evidence["z"]) > cfg["outlier_z"]:
            exceptions.append({"id": f"outlier:{asset}", "type": "outlier", **base})
        if float(ret) == float(hist[asset].iloc[-1]) and abs(ret) >= cfg["stale_min_abs_return"]:
            exceptions.append({"id": f"stale_repeat:{asset}", "type": "stale_repeat", **base})
    for i, note in enumerate(ctx.read_json("inputs/manifest.json")["notes"]):
        if any(re.search(p, note["note"]) for p in cfg["suspicious_note_patterns"]):
            exceptions.append({"id": f"suspicious_note:{i}", "type": "suspicious_note", "asset": note["asset"]})
    ctx.write_json("dq_report.json", {"exceptions": exceptions})


def dq_triage(ctx) -> None:
    exceptions = ctx.read_json("dq_report.json")["exceptions"]
    notes = ctx.read_json("inputs/manifest.json")["notes"]
    patterns = _policy(ctx)["dq"]["suspicious_note_patterns"]
    # Quarantined text never reaches a model; the agent only learns that a note was held back.
    safe_notes = [{"asset": n["asset"], "text": n["note"]} for n in notes
                  if not any(re.search(p, n["note"]) for p in patterns)]
    out = ctx.agent("data_steward", {"as_of": _day_label(ctx), "exceptions": exceptions, "vendor_notes_untrusted": safe_notes})
    decisions = {d["exception_id"]: d for d in out["decisions"]}
    resolved = []
    for e in exceptions:
        d = decisions.get(e["id"], {"exception_id": e["id"], "action": "escalate", "rationale": "No decision returned."})
        if e["type"] == "suspicious_note":
            d = {**d, "action": "escalate"}
        resolved.append(d)
    ctx.write_json("dq_decisions.json", {"decisions": resolved})


def _default_action(ctx, exception: dict) -> tuple[str, str]:
    """Used when no steward ran: restatements, or a degraded run with no agent available."""
    if exception["type"] == "missing_row":
        return "zero_return", "Fallback rule: no record to use."
    if ctx.run["workflow"] == "restate":
        return "accept", "Restatement run: vendor correction taken as reported."
    return "escalate", "Fallback rule: no steward decision available."


def dq_apply(ctx) -> None:
    exceptions = ctx.read_json("dq_report.json")["exceptions"]
    returns = _load(ctx, "inputs/returns.csv")
    manifest = ctx.read_json("inputs/manifest.json")
    as_of = ctx.run["as_of"]
    decided = {}
    if ctx.exists("dq_decisions.json"):
        decided = {d["exception_id"]: d for d in ctx.read_json("dq_decisions.json")["decisions"]}
    summary = []
    for e in exceptions:
        fallback = _default_action(ctx, e)
        d = decided.get(e["id"], {"action": fallback[0], "rationale": fallback[1]})
        action = "zero_return" if e["type"] == "missing_row" else d["action"]
        if action == "zero_return":
            returns.at[as_of, e["asset"]] = 0.0
            if ctx.run["workflow"] == "eod":
                ctx.on_commit("INSERT OR REPLACE INTO dq_overrides VALUES(?,?,?,?,?)", as_of, e["asset"], action,
                              manifest["published_today"].get(e["asset"]) or "", ctx.run["run_id"])
        summary.append({"id": e["id"], "type": e["type"], "asset": e.get("asset"), "action": action,
                        "rationale": d["rationale"]})
    if returns.loc[as_of].isna().any():
        raise InputNotReady(f"unresolved missing data for {as_of}")
    ctx.write_text("clean_returns.csv", _csv(returns))
    ctx.write_json("dq_summary.json", {"items": summary})


# ---- Risk ----

def risk_engine(ctx) -> None:
    risk_cfg = ctx.bundle["risk_model"]
    returns = _load(ctx, "clean_returns.csv")
    factors = _load(ctx, "inputs/factors.csv")
    weights = _load(ctx, "inputs/weights.csv")
    nav = _load(ctx, "inputs/nav.csv").iloc[:, 0]
    as_of = ctx.run["as_of"]
    assets = list(returns.columns)
    w = weights.loc[as_of, assets].to_numpy()
    earlier = weights.loc[:as_of].iloc[:-1]
    prev_w = earlier.iloc[-1][assets].to_numpy() if len(earlier) else None
    factor_series = {f: factors[f].reindex(returns.index).to_numpy() for f in risk_cfg["factors"]}
    metrics = compute_metrics(assets, returns.to_numpy(), w, prev_w, factor_series, nav.to_numpy(), risk_cfg)
    ctx.write_json("metrics.json", metrics)


def limit_check(ctx) -> None:
    rows = evaluate_limits(ctx.read_json("metrics.json"), ctx.bundle["limits"]["limits"])
    ctx.write_json("limit_status.json", {"status": overall_status(rows), "rows": rows})


def register(ctx) -> None:
    """Update the breach register and VaR ledger. Facts, so this does not wait for approval."""
    run, st = ctx.run, ctx.state
    as_of = run["as_of"]
    prev_day = ctx.store.previous_day(as_of)
    prev = st.one("SELECT status FROM runs WHERE run_id = ?", eod_run_id(prev_day)) if prev_day else None
    if prev and prev["status"] not in TERMINAL:
        row = st.stage(eod_run_id(prev_day), "register", 0)
        if not row or row["status"] != "done":
            raise WaitForDependency(f"{eod_run_id(prev_day)} has not reached register")

    limits = ctx.read_json("limit_status.json")["rows"]
    metrics = ctx.read_json("metrics.json")
    open_rows = {r["limit_id"]: r for r in st.q("SELECT * FROM breaches WHERE closed_on IS NULL")}
    delta: dict[str, list] = {"new": [], "escalated": [], "continuing": [], "resolved": []}
    for lim in limits:
        lid, status, value = lim["limit_id"], lim["status"], lim["value"]
        existing = open_rows.get(lid)
        if status == "ok":
            if existing:
                delta["resolved"].append(lid)
                ctx.on_commit("UPDATE breaches SET closed_on = ? WHERE breach_id = ?", as_of, existing["breach_id"])
            continue
        if existing is None:
            delta["new"].append(lid)
            ctx.on_commit("INSERT INTO breaches VALUES(?,?,?,?,?,?,?,NULL)", f"{lid}:{as_of}", lid, status, as_of,
                          as_of, 1, value)
            continue
        if status == "breach" and existing["severity"] == "warning":
            delta["escalated"].append(lid)
        else:
            delta["continuing"].append(lid)
        severity = "breach" if "breach" in (status, existing["severity"]) else "warning"
        ctx.on_commit("UPDATE breaches SET severity = ?, last_seen = ?, days_open = ?, peak = ? WHERE breach_id = ?",
                      severity, as_of, existing["days_open"] + 1, max(existing["peak"], value), existing["breach_id"])

    # A forecast made at T is scored with the T+1 return, and only in the T+1 run.
    daily = metrics["daily_return"]["value"]
    last = st.one("SELECT * FROM var_ledger WHERE as_of < ? ORDER BY as_of DESC LIMIT 1", as_of)
    hit_today = None
    if last is not None and last["hit"] is None:
        hit_today = int(-daily > last["var99"])
        ctx.on_commit("UPDATE var_ledger SET next_return = ?, hit = ? WHERE as_of = ?", daily, hit_today, last["as_of"])
    ctx.on_commit("INSERT OR REPLACE INTO var_ledger VALUES(?,?,?,NULL,NULL)", as_of, run["version"], metrics["var99_1d"]["value"])

    hits = [r["hit"] for r in st.q("SELECT hit FROM var_ledger WHERE hit IS NOT NULL AND as_of < ? ORDER BY as_of", as_of)]
    if hit_today is not None:
        hits.append(hit_today)
    summary = backtest.summarise(hits)
    ctx.write_json("breach_delta.json", delta)
    ctx.write_json("backtest.json", {**summary, "exception_today": bool(hit_today)})


def _day_label(ctx) -> str:
    return "T" if _policy(ctx)["memo"]["mask_calendar_dates"] else ctx.run["as_of"]


def previous_metrics(ctx) -> dict | None:
    prev_day = ctx.store.previous_day(ctx.run["as_of"])
    path = ctx.env.paths.artifacts / eod_run_id(prev_day or "") / "metrics.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# Agent requests carry metrics as id: [today, prior day]. Labels and units go once into the system prompt as a
# legend, which is the same every day, instead of into every request.
UNIT_NAMES = {"pct": "fraction", "usd": "USD", "ratio": "number", "count": "count", "days": "days", "text": "text"}


def _sig(value):
    """Six significant digits: far finer than any memo prints, in a fraction of the characters."""
    return float(f"{value:.6g}") if isinstance(value, float) else value


def compact_metrics(metrics: dict, prior: dict | None) -> dict:
    prior = prior or {}
    return {mid: [_sig(m["value"]), _sig(prior[mid]["value"]) if mid in prior else None] for mid, m in metrics.items()}


def compact_rows(rows: list[dict]) -> list[dict]:
    return [{k: _sig(v) for k, v in row.items()} for row in rows]


def metric_legend(metrics: dict) -> str:
    """One line per metric, except that a family such as w_<sleeve> ("Weight of <sleeve>") gets one line in all."""
    unit = lambda m: UNIT_NAMES.get(m["unit"], m["unit"])
    families: dict[tuple, list[str]] = {}
    for mid, m in metrics.items():
        prefix, _, rest = mid.partition("_")
        if rest and m["label"].endswith(" " + rest):
            families.setdefault((prefix, m["label"][:-len(rest) - 1], unit(m)), []).append(rest)
    families = {k: sorted(v) for k, v in families.items() if len(v) >= 3}
    grouped = {f"{prefix}_{x}" for (prefix, _, _), xs in families.items() for x in xs}
    lines = ["Metrics in the payload are given as id: [today, prior day]. Prior is null when there is no earlier day.",
             "A fraction of 0.0123 means 1.23%. Metric ids, with what each measures and its unit:"]
    lines += [f"- {prefix}_<x>: {head} <x> ({u}), for x in {', '.join(xs)}" for (prefix, head, u), xs in sorted(families.items())]
    lines += [f"- {mid}: {m['label']} ({unit(m)})" for mid, m in sorted(metrics.items()) if mid not in grouped]
    return "\n".join(lines)


def metrics_with_backtest(ctx) -> dict:
    metrics = ctx.read_json("metrics.json")
    bt = ctx.read_json("backtest.json")
    metrics["var_exceptions_250"] = {"value": bt["exceptions"], "unit": "count", "label": "VaR exceptions in the backtest window"}
    metrics["backtest_zone"] = {"value": bt["zone"], "unit": "text", "label": "Basel traffic-light zone"}
    return metrics


# ---- Agents ----

ANALYST_CHECKS = {"evidence_claims", "every_active_limit_explained"}


def _feedback(ctx, only_checks: set[str] | None = None) -> list[dict]:
    """Feedback for this round, optionally limited to the checks one role can actually fix."""
    name = f"feedback.r{ctx.round}.json"
    items = ctx.read_json(name) if ctx.exists(name) else []
    return [i for i in items if only_checks is None or i.get("check") in only_checks]


def analyst(ctx) -> None:
    feedback = _feedback(ctx, ANALYST_CHECKS)
    if ctx.round > 0 and not feedback:
        # Nothing here was criticised, so carry the findings forward rather than pay for a repeat.
        ctx.write_json(f"analysis.r{ctx.round}.json", ctx.read_json(f"analysis.r{ctx.round - 1}.json"))
        return
    metrics = metrics_with_backtest(ctx)
    limits = ctx.read_json("limit_status.json")["rows"]
    # The history of every active limit is sent up front: asking for it by tool would resend the whole request.
    tools = Tools(ctx)
    history = {r["limit_id"]: tools.get_breach_history(r["limit_id"]) for r in limits if r["status"] != "ok"}
    payload = {"as_of": _day_label(ctx), "metrics": compact_metrics(metrics, previous_metrics(ctx)),
               "limits": compact_rows(limits), "breach_history": history, "delta": ctx.read_json("breach_delta.json"),
               "backtest": ctx.read_json("backtest.json"), "dq": ctx.read_json("dq_summary.json")["items"],
               "feedback": feedback}
    ctx.write_json(f"analysis.r{ctx.round}.json", ctx.agent("risk_analyst", payload, metric_legend(metrics)))


def writer(ctx) -> None:
    payload = {"as_of": _day_label(ctx), "status": ctx.read_json("limit_status.json")["status"],
               "limits": compact_rows(ctx.read_json("limit_status.json")["rows"]), "delta": ctx.read_json("breach_delta.json"),
               "findings": ctx.read_json(f"analysis.r{ctx.round}.json")["findings"], "dq": ctx.read_json("dq_summary.json")["items"],
               "backtest": ctx.read_json("backtest.json"), "metric_ids": sorted(metrics_with_backtest(ctx)),
               "feedback": _feedback(ctx)}
    ctx.write_text(f"memo_draft.r{ctx.round}.md", ctx.agent("memo_writer", payload)["memo_markdown"])


def verify(ctx) -> None:
    result = run_checks(ctx)
    ctx.write_json(f"verification.r{ctx.round}.json", result)
    if not result["passed"]:
        ctx.event("verification_failed", {"failed": [c["id"] for c in result["checks"] if not c["passed"]]})
        ctx.write_json(f"feedback.r{ctx.round + 1}.json",
                       [{"source": "verifier", "check": c["id"], "detail": c["detail"]}
                        for c in result["checks"] if not c["passed"]])


def _resolved_memo(ctx, rnd: int, day: str | None = None) -> str:
    limit_status = ctx.read_json("limit_status.json")
    limits = {r["limit_id"]: r for r in limit_status["rows"]}
    return resolve(ctx.read_text(f"memo_draft.r{rnd}.md"), metrics_with_backtest(ctx), limits,
                   day or ctx.run["as_of"], limit_status["status"])


def reviewer(ctx) -> None:
    """Sees the finished memo and source facts only: no drafts, findings or analyst reasoning."""
    limit_status = ctx.read_json("limit_status.json")
    prior = previous_metrics(ctx)
    limits = [{**r, "prior_value": prior[r["metric"]]["value"] if prior else None} for r in limit_status["rows"]]
    metrics = metrics_with_backtest(ctx)
    payload = {"memo": _resolved_memo(ctx, ctx.round, _day_label(ctx)), "status": limit_status["status"],
               "metrics": compact_metrics(metrics, prior), "limits": compact_rows(limits),
               "delta": ctx.read_json("breach_delta.json"), "dq": ctx.read_json("dq_summary.json")["items"],
               "backtest": ctx.read_json("backtest.json"), "first_day_of_history": prior is None}
    out = ctx.agent("reviewer", payload, metric_legend(metrics))
    ctx.write_json(f"review.r{ctx.round}.json", out)
    if out["verdict"] != "pass":
        ctx.write_json(f"feedback.r{ctx.round + 1}.json", [{"source": "reviewer", **i} for i in out["issues"]])


def _verified_draft_with_concerns(ctx, rnd: int) -> str | None:
    """A draft that passed every check is too good to discard because the reviewer stayed unconvinced.

    It goes to the approver with the open concerns attached. A draft that failed a check never does.
    """
    name = f"verification.r{rnd}.json"
    if not ctx.exists(name) or not ctx.read_json(name)["passed"]:
        return None
    lines = ["", "## Open reviewer concerns"]
    review = f"review.r{rnd}.json"
    if ctx.exists(review):
        lines.append("All automated checks passed, but the independent reviewer was still not satisfied after the last round.")
        lines += [f"- {issue['problem']}" for issue in ctx.read_json(review)["issues"]]
    else:
        lines.append("All automated checks passed, but the independent review did not complete.")
    return _resolved_memo(ctx, rnd).rstrip() + "\n" + "\n".join(lines) + "\n"


def finalise_memo(ctx) -> None:
    run = ctx.state.run(ctx.run["run_id"])
    limit_status = ctx.read_json("limit_status.json")
    if run["degraded"]:
        memo = _verified_draft_with_concerns(ctx, run["round"]) or template_memo(
            run["as_of"], limit_status["status"], ctx.read_json("metrics.json"), limit_status["rows"],
            ctx.read_json("dq_summary.json")["items"], run["degraded_reason"])
    else:
        memo = _resolved_memo(ctx, run["round"])
    ctx.write_text("memo_final.md", memo)


# ---- Gate and publish ----

def gate_policy(ctx) -> None:
    policy = _policy(ctx)["gates"]
    wanted = set(policy["require_approval_for"])
    reasons = []
    workflow = ctx.run["workflow"]
    deliverable = {"eod": "memo_final.md", "restate": "restatement.md", "monthly": "model_review.md"}[workflow]
    if workflow == "eod":
        run = ctx.state.run(ctx.run["run_id"])
        rows = ctx.read_json("limit_status.json")["rows"]
        delta = ctx.read_json("breach_delta.json")
        items = ctx.read_json("dq_summary.json")["items"]
        if any(r["status"] == "breach" for r in rows):
            reasons.append("hard_breach")
        if delta["new"]:
            reasons.append("new_warning")
        if any(i["action"] == "zero_return" for i in items):
            reasons.append("dq_override")
        if any(i["action"] == "escalate" for i in items):
            reasons.append("dq_escalation")
        if run["degraded"]:
            reasons.append("degraded_memo")
    elif workflow == "restate":
        if ctx.read_json("restatement.json")["material"]:
            reasons.append("material_restatement")
    else:
        reasons.append("model_review")
    reasons = [r for r in reasons if r in wanted]
    required = bool(reasons) or not policy["auto_publish_clean_days"]
    digest = hashlib.sha256(ctx.path(deliverable).read_bytes()).hexdigest()
    ctx.write_json("gate.json", {"approval_required": required, "reasons": reasons,
                                 "deliverable": deliverable, "sha256": digest})


def _deliver(ctx, key: str, kind: str, source: str, destination: str) -> None:
    """At-least-once delivery to a receiver that ignores repeats, which together behave as exactly once."""
    st = ctx.state
    digest = hashlib.sha256(ctx.path(source).read_bytes()).hexdigest()
    st.x("INSERT OR IGNORE INTO outbox VALUES(?,?,?,?,?,?,'pending')", key, ctx.run["run_id"], kind, source, destination, digest)
    crash.point("publish:outbox_written")
    if st.one("SELECT status FROM outbox WHERE key = ?", key)["status"] == "delivered":
        ctx.event("delivery_skipped", {"key": key})
        return
    target = ctx.env.paths.published / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        ctx.event("delivery_suppressed", {"key": key, "reason": "receiver already has it"})
    else:
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(ctx.path(source).read_bytes())
        os.replace(tmp, target)
        ctx.event("delivered", {"key": key, "destination": destination})
    crash.point("publish:delivered")
    st.x("UPDATE outbox SET status = 'delivered' WHERE key = ?", key)


def publish(ctx) -> None:
    gate = ctx.read_json("gate.json")
    actual = hashlib.sha256(ctx.path(gate["deliverable"]).read_bytes()).hexdigest()
    if actual != gate["sha256"]:
        raise RuntimeError("deliverable changed after the approval gate")
    run_id, as_of, workflow = ctx.run["run_id"], ctx.run["as_of"], ctx.run["workflow"]
    if workflow == "eod":
        _deliver(ctx, f"memo:{run_id}", "memo", "memo_final.md", f"memos/{as_of}.md")
        rows = {r["limit_id"]: r for r in ctx.read_json("limit_status.json")["rows"]}
        delta = ctx.read_json("breach_delta.json")
        hard = [lid for lid in delta["new"] + delta["escalated"] if rows[lid]["status"] == "breach"]
        if hard:
            ctx.write_json("breach_notice.json", {"as_of": as_of, "limits": [rows[lid] for lid in hard]})
            _deliver(ctx, f"notice:{run_id}", "notice", "breach_notice.json", f"notices/{as_of}.json")
    elif workflow == "restate":
        if ctx.read_json("restatement.json")["material"]:
            _deliver(ctx, f"restatement:{run_id}", "restatement", "restatement.md", f"restatements/{run_id}.md")
    else:
        _deliver(ctx, f"review:{run_id}", "review", "model_review.md", f"reviews/{as_of[:7]}.md")
    ctx.write_json("published.json", {"outbox": [dict(r) for r in ctx.state.q(
        "SELECT key, kind, destination, sha256, status FROM outbox WHERE run_id = ? ORDER BY key", run_id)]})


# ---- Restatement and monthly review ----

def restate_diff(ctx) -> None:
    as_of = ctx.run["as_of"]
    original = ctx.env.paths.artifacts / eod_run_id(as_of)
    old_metrics = json.loads((original / "metrics.json").read_text(encoding="utf-8"))
    old_rows = json.loads((original / "limit_status.json").read_text(encoding="utf-8"))["rows"]
    metrics = ctx.read_json("metrics.json")
    rows = ctx.read_json("limit_status.json")["rows"]
    var_change = metrics["var99_1d"]["value"] - old_metrics["var99_1d"]["value"]
    return_change = metrics["daily_return"]["value"] - old_metrics["daily_return"]["value"]
    flips = [{"limit_id": a["limit_id"], "was": a["status"], "now": b["status"]}
             for a, b in zip(old_rows, rows) if a["status"] != b["status"]]
    material = abs(var_change) >= _policy(ctx)["restatement"]["material_var_change"] or bool(flips)
    ctx.write_json("restatement.json", {"as_of": as_of, "var_change": var_change, "return_change": return_change,
                                        "status_changes": flips, "material": material})
    lines = [f"# Restatement notice: {as_of}", "",
             "A vendor correction changed data behind an already issued report. The original report stands as issued.", "",
             f"- Change in 1-day 99% VaR: {var_change * 1e4:+.1f} bp of NAV",
             f"- Change in portfolio return on the day: {return_change * 1e4:+.1f} bp"]
    lines += [f"- Limit {f['limit_id']} moves from {f['was']} to {f['now']}" for f in flips] or ["- No limit status changed"]
    ctx.write_text("restatement.md", "\n".join(lines) + "\n")


def backtest_review(ctx) -> None:
    rows = ctx.state.q("SELECT as_of, var99, next_return, hit FROM var_ledger WHERE hit IS NOT NULL AND as_of <= ? "
                       "ORDER BY as_of", ctx.run["as_of"])
    hits = [r["hit"] for r in rows]
    ctx.write_json("backtest_review.json", {**backtest.summarise(hits), "exception_dates": [r["as_of"] for r in rows if r["hit"]]})


def model_reviewer(ctx) -> None:
    summary = ctx.read_json("backtest_review.json")
    masked = {k: v for k, v in summary.items() if k != "exception_dates"}
    out = ctx.agent("model_reviewer", {"backtest": masked, "model": ctx.bundle["risk_model"]["var"]})
    ctx.write_json("model_review_agent.json", out)
    lines = [f"# Monthly VaR model review: {ctx.run['as_of'][:7]}", "",
             f"- Observations: {summary['observations']}", f"- Exceptions: {summary['exceptions']} (expected {summary['expected']:.1f})",
             f"- Basel zone: {summary['zone']}", f"- Kupiec p-value: {summary['kupiec']['p_value']:.4f}",
             f"- Independence p-value: {summary['independence']['p_value']:.4f}", "",
             f"Assessment: {out['assessment']}. Recommendation: {out['recommendation']}.", "", out["rationale"]]
    if out.get("proposed_change"):
        lines += ["", f"Proposed for evaluation (not applied): {out['proposed_change']}"]
    ctx.write_text("model_review.md", "\n".join(lines) + "\n")


STAGES = {f.__name__: f for f in (ingest, dq_checks, dq_triage, dq_apply, risk_engine, limit_check, register, analyst,
                                  writer, verify, reviewer, finalise_memo, gate_policy, publish, restate_diff,
                                  backtest_review, model_reviewer)}
