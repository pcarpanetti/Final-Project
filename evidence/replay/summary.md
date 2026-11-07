# Full replay summary

Window 2019-07-01 to 2020-06-30. Backend: `scripted:rules-v1`, the offline stand-in.
Approvals were answered by `replay-policy`, a stand-in for the CRO. Market data is real; the book and faults are not.

| Workflow | Status | Runs |
|---|---|---|
| eod | completed | 252 |
| eod | rejected | 1 |
| monthly | completed | 11 |
| restate | completed | 3 |

| Event | Count |
|---|---|
| stage_started | 3917 |
| stage_done | 3494 |
| llm_call | 928 |
| stage_skipped | 418 |
| delivered | 268 |
| run_created | 267 |
| run_completed | 266 |
| tool_call | 143 |
| stage_waiting | 111 |
| approval_requested | 109 |
| human_decision | 109 |
| llm_transient_error | 10 |
| verification_failed | 8 |
| revision_started | 8 |
| escalated | 5 |
| cutoff_extended | 2 |
| stage_failed | 2 |
| run_rejected | 1 |
| agent_invalid_reply | 1 |
| tool_denied | 1 |
| llm_permanent_error | 1 |
