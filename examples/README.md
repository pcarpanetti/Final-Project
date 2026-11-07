# Example outputs

These are real artifacts from the full replay in `evidence/replay/`, copied here by `scripts/export_evidence.py`. Agent
text comes from the offline scripted backend, so it is template-like. The figures come from the risk engine.
Each folder includes `events.jsonl`, the run's event log.

| Folder | Date | What it shows | Start with |
|---|---|---|---|
| `clean_day/` | 2019-11-05 | No exceptions, so the memo archives without a human | `memo_final.md` |
| `hard_breach_day/` | 2020-03-16 | A -11.57% day: metrics, limits, findings, verification, review, gate | `memo_final.md` |
| `bad_tick_caught/` | 2020-01-16 | A vendor error zeroed, with the evidence for that decision | `dq_report.json` |
| `real_move_escalated/` | 2020-03-09 | A real -19.7% sector move escalated rather than overwritten, plus a breach notice | `dq_decisions.json` |
| `revision_loop/` | 2020-02-24 | A draft missing a limit, the failed check, the feedback, and the corrected draft | `verification.r0.json` |
| `human_change_request/` | 2020-03-19 | An approver's note driving a new draft | `feedback.r1.json` |
| `prompt_injection/` | 2020-05-12 | A vendor note attacking the workflow, and a compromised draft being rejected | `memo_draft.r0.md` |
| `provider_outage_degraded/` | 2020-04-21 | The provider is down, and the numbers still reach a human | `memo_final.md` |
| `revision_exhausted_degraded/` | 2020-03-24 | The revision loop stops at three rounds | `memo_final.md` |
| `restatement/` | 2020-01-16 | The notice comparing a report with its vendor correction | `restatement.md` |
| `monthly_review/` | 2020-03 | VaR backtest statistics and a proposal, which goes to evaluation and is not applied | `model_review.md` |

Inputs are the files in `data/feed/`. To regenerate these outputs, run `riskwatch replay` and then
`python scripts/export_evidence.py`.
