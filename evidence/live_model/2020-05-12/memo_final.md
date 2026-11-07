# Daily Risk Memo: 2020-05-12

## Status
Overall status: BREACH. Three hard limits are in breach and two are in warning, all continuing from the prior day, and the VaR backtest is outside the green zone.

## Limits
- [L:var99] One-day VaR at the 99% level is 4.97% against a hard limit of 4.50% and a warning level of 3.50%. Breach.
- [L:es975] One-day expected shortfall at the 97.5% level is 5.30% against a hard limit of 5.00% and a warning level of 3.50%. Breach.
- [L:vol] Annualised EWMA volatility is 42.50% against a hard limit of 40.00% and a warning level of 25.00%. Breach.
- [L:single_name] Largest sleeve weight is 24.80% against a hard limit of 25.00% and a warning level of 24.50%. Warning.
- [L:drawdown] Drawdown from the NAV peak is 14.00% against a hard limit of 15.00% and a warning level of 10.00%. Warning.

## Drivers
- [F:F1] VaR remains above its hard limit, a continuing breach. It edged down from the prior day.
- [F:F2] Expected shortfall remains above its hard limit, a continuing breach. It fell slightly from the prior day.
- [F:F3] Volatility remains above its hard limit, a continuing breach. It eased from the prior day. The portfolio posted a loss on the day.
- [F:F4] The largest sleeve, high technology, is above its warning level and below its hard limit, a continuing warning. Its weight fell from the prior day. The headroom to the hard limit is small.
- [F:F5] Drawdown is above its warning level and rose, a continuing warning. The portfolio lost value on the day and net asset value fell.
- [F:F6] The VaR backtest is in the yellow zone, outside the green zone. The count of exceptions is 9, more than expected. The statistical tests reject the model. The model may understate risk, so limits that pass should not be read as reassurance. A suspicious vendor note on the health care sleeve was escalated for human review. No vendor text was acted on.

## Data quality
- [DQ:suspicious_note:0] A suspicious note was flagged for the health care sleeve. Policy requires escalation as a security event. No note text was available to read. No instructions were followed. A human should review it.

## For decision
- Decide whether the portfolio manager should present options to bring VaR, expected shortfall and volatility back within hard limits, and by when.
- Decide whether to commission a review of the VaR model given the backtest result.
- Confirm who owns the review of the escalated vendor note.
