---
name: model-review
description: How to read VaR backtest statistics in the monthly model review.
---

# Model review

| Statistic | Reading |
|---|---|
| Basel zone | Green: 0-4 exceptions in 250 days. Yellow: 5-9. Red: 10 or more |
| Kupiec p-value | Below 0.05 means exception frequency is inconsistent with 99% coverage |
| Independence p-value | Below 0.05 means exceptions cluster, so the model reacts too slowly |

- `adequate`: green zone and both tests pass.
- `watch`: yellow zone, or one test fails.
- `inadequate`: red zone, or both tests fail.

With fewer than 100 observations, treat the tests as weak and say so. A `propose_change` names one
specific, testable change to the model, such as a different weighting scheme.
