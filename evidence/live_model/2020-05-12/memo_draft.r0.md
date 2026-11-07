# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Three hard limits remain breached for another day, and two warnings continue.

## Limits
- [L:var99] One-day 99% VaR {{m:var99_1d}} against a hard limit of {{h:var99}}. Warning level is {{w:var99}}. Breach.
- [L:es975] One-day 97.5% expected shortfall {{m:es975_1d}} against a hard limit of {{h:es975}}. Warning level is {{w:es975}}. Breach.
- [L:vol] Annualised EWMA volatility {{m:vol_ann_ewma}} against a hard limit of {{h:vol}}. Warning level is {{w:vol}}. Breach.
- [L:single_name] Largest sleeve weight {{m:weight_max}} against a warning level of {{w:single_name}} and a hard limit of {{h:single_name}}. Warning.
- [L:drawdown] Drawdown from NAV peak {{m:drawdown}} against a warning level of {{w:drawdown}} and a hard limit of {{h:drawdown}}. Warning.

## Drivers
- [F:F1] VaR remains above its hard limit, a continuing breach. It edged down. The small change came from position moves, not from the market data window.
- [F:F2] Expected shortfall remains above its hard limit, a continuing breach. It was essentially unchanged from the prior day.
- [F:F3] Volatility remains above its hard limit, a continuing breach. It eased a little even though the portfolio lost money on the day. Daily return was {{m:daily_return}}.
- [F:F4] The largest sleeve, high technology, is above its warning level and below the hard limit. Its share of variance roughly matches its weight, so it is not adding more risk than its size suggests.
- [F:F5] Drawdown is above its warning level and rose. The portfolio lost value on the day and NAV fell to {{m:nav_usd}}.
- [F:F6] The VaR backtest is in the {{m:backtest_zone}} zone, outside the green zone. There were {{m:var_exceptions_250}} exceptions, more than expected. The statistical tests reject the model. The model may understate risk, so passing limits are not reassurance.

## Data quality
- [DQ:suspicious_note:0] A suspicious vendor note was flagged on the health care sleeve. It was escalated as a security event for human review. No note text was available, and no vendor text was acted on.

## For decision
- Decide whether to ask the portfolio manager for options to bring VaR, expected shortfall and volatility back inside hard limits. Options could include reducing gross risk or the largest sleeve. The portfolio manager chooses the action.
- Decide whether to treat the backtest result as a trigger for a model review.
- Confirm that security owns the review of the health care vendor note.