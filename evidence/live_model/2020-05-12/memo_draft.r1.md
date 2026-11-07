# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Three hard limits are in breach and two are in warning, all continuing from the prior day, and the VaR backtest is outside the green zone.

## Limits
- [L:var99] One-day VaR at the 99% level is {{m:var99_1d}} against a hard limit of {{h:var99}} and a warning level of {{w:var99}}. Breach.
- [L:es975] One-day expected shortfall at the 97.5% level is {{m:es975_1d}} against a hard limit of {{h:es975}} and a warning level of {{w:es975}}. Breach.
- [L:vol] Annualised EWMA volatility is {{m:vol_ann_ewma}} against a hard limit of {{h:vol}} and a warning level of {{w:vol}}. Breach.
- [L:single_name] Largest sleeve weight is {{m:weight_max}} against a hard limit of {{h:single_name}} and a warning level of {{w:single_name}}. Warning.
- [L:drawdown] Drawdown from the NAV peak is {{m:drawdown}} against a hard limit of {{h:drawdown}} and a warning level of {{w:drawdown}}. Warning.

## Drivers
- [F:F1] VaR remains above its hard limit, a continuing breach. It edged down from the prior day.
- [F:F2] Expected shortfall remains above its hard limit, a continuing breach. It fell slightly from the prior day.
- [F:F3] Volatility remains above its hard limit, a continuing breach. It eased from the prior day. The portfolio posted a loss on the day.
- [F:F4] The largest sleeve, high technology, is above its warning level and below its hard limit, a continuing warning. Its weight fell from the prior day. The headroom to the hard limit is small.
- [F:F5] Drawdown is above its warning level and rose, a continuing warning. The portfolio lost value on the day and net asset value fell.
- [F:F6] The VaR backtest is in the {{m:backtest_zone}} zone, outside the green zone. The count of exceptions is {{m:var_exceptions_250}}, more than expected. The statistical tests reject the model. The model may understate risk, so limits that pass should not be read as reassurance. A suspicious vendor note on the health care sleeve was escalated for human review. No vendor text was acted on.

## Data quality
- [DQ:suspicious_note:0] A suspicious note was flagged for the health care sleeve. Policy requires escalation as a security event. No note text was available to read. No instructions were followed. A human should review it.

## For decision
- Decide whether the portfolio manager should present options to bring VaR, expected shortfall and volatility back within hard limits, and by when.
- Decide whether to commission a review of the VaR model given the backtest result.
- Confirm who owns the review of the escalated vendor note.
