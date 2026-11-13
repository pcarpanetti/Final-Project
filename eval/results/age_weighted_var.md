# Evaluation: Age-weighted historical VaR reacts faster in a volatility spike and cuts exception clustering.

Baseline `9ade7848e5dc`, candidate `72d87728f9e4`, backend `scripted:rules-v1`.

**Decision: REJECT**

- guardrail: average VaR up 31%

| Metric | Baseline | Candidate |
|---|---|---|
| var_exceptions | 10 | 7 |
| kupiec_p | 0.0003 | 0.0190 |
| independence_p | 0.0512 | 0.1743 |
| basel_zone | red | yellow |
| avg_var99 | 0.0372 | 0.0487 |
| hard_breach_days | 84 | 84 |
| faults_handled_rate | 1.0000 | 1.0000 |
| false_dq_overrides | 0 | 0 |
| halted_runs | 0 | 0 |
| degraded_runs | 3 | 3 |
| cutoff_violations | 0 | 0 |
| approvals_requested | 109 | 109 |
| memos_published | 252 | 252 |
| llm_calls | 928 | 928 |
| llm_tokens | 2152336 | 2162948 |

Leakage perturbation test: passed on 3 days.
