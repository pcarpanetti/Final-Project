"""Independent, deterministic checks on a memo draft. Failing any one sends the draft back."""
from __future__ import annotations

import re

from ..memo import TOKEN, resolve_token
from ..risk.limits import evaluate_limits
from .recompute import max_abs_error, recompute

TOLERANCE = 1e-9


def _result(check_id: str, ok: bool, detail: str = "") -> dict:
    return {"id": check_id, "passed": bool(ok), "detail": detail}


def check_recompute(ctx, metrics: dict) -> dict:
    independent = recompute(ctx.dir, ctx.run["as_of"], ctx.bundle["risk_model"]["var"])
    bad = {k: (metrics[k]["value"], v) for k, v in independent.items()
           if max_abs_error(metrics[k]["value"], v) > TOLERANCE * max(1.0, abs(v))}
    return _result("recompute_metrics", not bad, f"mismatches: {bad}" if bad else f"{len(independent)} metrics agree")


def check_limits(ctx, metrics: dict, limit_status: dict) -> dict:
    fresh = evaluate_limits(metrics, ctx.bundle["limits"]["limits"])
    return _result("limit_reevaluation", fresh == limit_status["rows"], "" if fresh == limit_status["rows"] else "statuses differ")


def check_cutoff(ctx) -> dict:
    manifest = ctx.read_json("inputs/manifest.json")
    ok = manifest["max_published_at"] <= manifest["cutoff"]
    last_row = ctx.read_text("clean_returns.csv").rstrip().rsplit("\n", 1)[-1].split(",")[0]
    ok_date = last_row <= ctx.run["as_of"]
    return _result("information_cutoff", ok and ok_date,
                   f"latest input {manifest['max_published_at']}, cutoff {manifest['cutoff']}, last row {last_row}")


def check_tokens(draft: str, metrics: dict, limits: dict) -> dict:
    bad = []
    for token in TOKEN.findall(draft):
        try:
            resolve_token(token.strip(), metrics, limits, "", "")
        except KeyError:
            bad.append(token)
    return _result("tokens_resolve", not bad, f"unknown tokens: {bad}" if bad else "")


def check_no_typed_numbers(draft: str, memo_cfg: dict) -> dict:
    """Every digit in the memo must arrive through a token, or be an allowed literal or tag."""
    text = TOKEN.sub(" ", draft)
    text = re.sub(r"\[(?:L|F|DQ):[^\]]*\]", " ", text)
    for literal in sorted(memo_cfg["allowed_literals"], key=len, reverse=True):
        text = text.replace(literal, " ")
    typed = re.findall(r"\S*\d\S*", text)
    return _result("no_typed_numbers", not typed, f"typed figures: {typed[:5]}" if typed else "")


def check_sections(draft: str, memo_cfg: dict) -> dict:
    missing = [s for s in memo_cfg["required_sections"] if f"## {s}" not in draft]
    return _result("required_sections", not missing, f"missing: {missing}" if missing else "")


def check_status_line(draft: str) -> dict:
    return _result("status_from_token", "{{status}}" in draft, "" if "{{status}}" in draft else "status must use the {{status}} token")


def check_coverage(draft: str, rows: list[dict], findings: list[dict], dq_items: list[dict]) -> dict:
    missing = [f"[L:{r['limit_id']}]" for r in rows if r["status"] != "ok" and f"[L:{r['limit_id']}]" not in draft]
    missing += [f"[F:{f['id']}]" for f in findings if f"[F:{f['id']}]" not in draft]
    missing += [f"[DQ:{d['id']}]" for d in dq_items if f"[DQ:{d['id']}]" not in draft]
    return _result("coverage", not missing, f"missing tags: {missing}" if missing else "")


def check_findings_cover_limits(rows: list[dict], findings: list[dict]) -> dict:
    explained = {f["limit_id"] for f in findings}
    missing = [r["limit_id"] for r in rows if r["status"] != "ok" and r["limit_id"] not in explained]
    return _result("every_active_limit_explained", not missing, f"no finding for: {missing}" if missing else "")


def check_evidence(findings: list[dict], metrics: dict, prior: dict | None, limits: dict) -> dict:
    """Test each analyst claim against the numbers."""
    by_metric = {lim["metric"]: lim for lim in limits.values()}
    wrong = []
    for finding in findings:
        for ev in finding["evidence"]:
            mid, claim = ev["metric"], ev["claim"]
            if mid not in metrics:
                wrong.append(f"{finding['id']}: unknown metric {mid}")
                continue
            value = metrics[mid]["value"]
            if claim in ("positive", "negative"):
                ok = value > 0 if claim == "positive" else value < 0
            elif claim in ("above_warn", "above_hard"):
                lim = by_metric.get(mid)
                ok = lim is not None and value >= lim["warn" if claim == "above_warn" else "hard"]
            elif prior is None or mid not in prior:
                continue
            else:
                ok = value > prior[mid]["value"] if claim == "rose" else value < prior[mid]["value"]
            if not ok:
                wrong.append(f"{finding['id']}: {mid} {claim} is false")
    return _result("evidence_claims", not wrong, "; ".join(wrong[:5]))


def check_prohibited(draft: str, memo_cfg: dict) -> dict:
    hits = [p for p in memo_cfg["prohibited_phrases"] if re.search(p, draft)]
    return _result("no_trade_instructions", not hits, f"matched: {hits}" if hits else "")


def check_no_future_terms(draft: str, memo_cfg: dict, mode: str) -> dict:
    if mode != "replay":
        return _result("no_future_knowledge", True, "only enforced in historical replay")
    lowered = draft.lower()
    hits = [t for t in memo_cfg["replay_forbidden_terms"] if t in lowered]
    return _result("no_future_knowledge", not hits, f"terms not present in any input: {hits}" if hits else "")


def check_injection(draft: str, dq_cfg: dict) -> dict:
    hits = [p for p in dq_cfg["suspicious_note_patterns"] if re.search(p, draft)]
    return _result("no_injected_text", not hits, f"matched: {hits}" if hits else "")


def run_checks(ctx) -> dict:
    from ..stages.pipeline import metrics_with_backtest, previous_metrics

    draft = ctx.read_text(f"memo_draft.r{ctx.round}.md")
    metrics = metrics_with_backtest(ctx)
    limit_status = ctx.read_json("limit_status.json")
    rows = limit_status["rows"]
    limits = {r["limit_id"]: r for r in rows}
    findings = ctx.read_json(f"analysis.r{ctx.round}.json")["findings"]
    dq_items = ctx.read_json("dq_summary.json")["items"]
    policy = ctx.bundle["policy"]
    memo_cfg = policy["memo"]
    checks = [
        check_recompute(ctx, ctx.read_json("metrics.json")),
        check_limits(ctx, ctx.read_json("metrics.json"), limit_status),
        check_cutoff(ctx),
        check_tokens(draft, metrics, limits),
        check_no_typed_numbers(draft, memo_cfg),
        check_sections(draft, memo_cfg),
        check_status_line(draft),
        check_coverage(draft, rows, findings, dq_items),
        check_findings_cover_limits(rows, findings),
        check_evidence(findings, metrics, previous_metrics(ctx), limits),
        check_prohibited(draft, memo_cfg),
        check_no_future_terms(draft, memo_cfg, ctx.env.mode),
        check_injection(draft, policy["dq"]),
    ]
    return {"passed": all(c["passed"] for c in checks), "checks": checks}
