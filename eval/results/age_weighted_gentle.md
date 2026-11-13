# Evaluation: A gentler age decay of 0.995 keeps part of the coverage gain while staying inside the VaR guardrail. Chosen after seeing age_weighted_var fail that guardrail on this same window.

Baseline `9ade7848e5dc`, candidate `8ff0abcc6c98`, backend `scripted:rules-v1`.

**Decision: ACCEPT**

- all gates, guardrails and primary test passed

| Metric | Baseline | Candidate |
|---|---|---|
| var_exceptions | 10 | 8 |
| kupiec_p | 0.0003 | 0.0054 |
| independence_p | 0.0512 | 0.0181 |
| basel_zone | red | yellow |
| avg_var99 | 0.0372 | 0.0451 |
| hard_breach_days | 84 | 84 |
| faults_handled_rate | 1.0000 | 1.0000 |
| false_dq_overrides | 0 | 0 |
| halted_runs | 0 | 0 |
| degraded_runs | 3 | 3 |
| cutoff_violations | 0 | 0 |
| approvals_requested | 109 | 109 |
| memos_published | 252 | 252 |
| llm_calls | 802 | 802 |
| llm_tokens | 1519237 | 1524699 |

Leakage perturbation test: passed on 3 days.
