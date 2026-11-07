"""The period summary that goes at the top of the downloadable output."""
from __future__ import annotations


def period_summary(rows, backend: str, version: str) -> str:
    """`rows` runs a read-only query, so this works from any state database."""
    runs = rows("SELECT workflow, status, COUNT(*) n, MIN(as_of) first, MAX(as_of) last FROM runs GROUP BY workflow, status")
    eod = rows("SELECT MIN(as_of) first, MAX(as_of) last, COUNT(*) n FROM runs WHERE workflow = 'eod'")
    ledger = rows("SELECT COUNT(*) n, COALESCE(SUM(hit), 0) hits FROM var_ledger WHERE hit IS NOT NULL")
    breaches = rows("SELECT limit_id, severity, opened_on, closed_on, days_open, peak FROM breaches "
                    "WHERE severity = 'breach' ORDER BY opened_on")
    approvals = rows("SELECT decision, COUNT(*) n FROM approvals GROUP BY decision")
    escalations = rows("SELECT sim_ts, severity, run_id, reason FROM escalations ORDER BY id")
    usage = rows("SELECT provider, model, COUNT(*) calls, SUM(tokens_in + tokens_out) tokens FROM llm_calls GROUP BY provider, model")

    period = eod[0] if eod else {"first": "", "last": "", "n": 0}
    lines = ["# RiskWatch output summary", "", f"Period: {period['first']} to {period['last']} ({period['n']} daily runs)",
             f"Model backend: {backend}", f"Workflow version: `{version}`", "",
             "Market returns are real (Ken French data library). The book, limits and vendor faults are fictional.",
             "", "## Runs", "", "| Workflow | Status | Count |", "|---|---|---|"]
    lines += [f"| {r['workflow']} | {r['status']} | {r['n']} |" for r in runs]

    if ledger and ledger[0]["n"]:
        n, hits = ledger[0]["n"], ledger[0]["hits"]
        lines += ["", "## VaR backtest", "", f"{hits} exceptions in {n} scored days, against {n * 0.01:.1f} expected at 99%."]

    lines += ["", "## Hard breaches", ""]
    if breaches:
        lines += ["| Limit | Opened | Closed | Days open | Peak |", "|---|---|---|---|---|"]
        lines += [f"| {b['limit_id']} | {b['opened_on']} | {b['closed_on'] or 'open'} | {b['days_open']} | {b['peak']:.4f} |"
                  for b in breaches]
    else:
        lines.append("None.")

    lines += ["", "## Approvals", "", "| Decision | Count |", "|---|---|"]
    lines += [f"| {a['decision'] or 'still pending'} | {a['n']} |" for a in approvals] or ["| None | 0 |"]

    lines += ["", "## Escalations", ""]
    lines += [f"- {e['sim_ts']} [{e['severity']}] {e['run_id'] or 'system'}: {e['reason']}" for e in escalations] or ["None."]

    lines += ["", "## Model usage", ""]
    lines += [f"- {u['provider']} {u['model']}: {u['calls']} calls, {u['tokens']:,} tokens" for u in usage] or ["No calls."]
    return "\n".join(lines) + "\n"
