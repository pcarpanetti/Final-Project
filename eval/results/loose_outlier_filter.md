# Evaluation: Raising the outlier threshold from 6 to 50 removes data-steward workload on volatile days.

Baseline `9ade7848e5dc`, candidate `579db12807ac`, backend `scripted:rules-v1`.

**Decision: REJECT**

- hard gate: ground-truth faults not handled: ['F1_bad_tick']
- primary: Kupiec p 0.0003 -> 0.0003, exceptions 10 -> 10: no improvement

| Metric | Baseline | Candidate |
|---|---|---|
| var_exceptions | 10 | 10 |
| kupiec_p | 0.0003 | 0.0003 |
| independence_p | 0.0512 | 0.0512 |
| basel_zone | red | red |
| avg_var99 | 0.0372 | 0.0372 |
| hard_breach_days | 84 | 84 |
| faults_handled_rate | 1.0000 | 0.8333 |
| false_dq_overrides | 0 | 0 |
| halted_runs | 0 | 0 |
| degraded_runs | 3 | 3 |
| cutoff_violations | 0 | 0 |
| approvals_requested | 109 | 108 |
| memos_published | 252 | 252 |
| llm_calls | 802 | 798 |
| llm_tokens | 1520249 | 1515712 |

Leakage perturbation test: passed on 3 days.
