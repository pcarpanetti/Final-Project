# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Three hard limits stay in breach and two warnings continue, with no new or escalated items.

## Limits
- [L:var99] One-day VaR at the 99% level is {{m:var99_1d}} against a hard limit of {{h:var99}}. Breach.
- [L:es975] One-day expected shortfall at the 97.5% level is {{m:es975_1d}} against a hard limit of {{h:es975}}. Breach.
- [L:vol] Annualised EWMA volatility is {{m:vol_ann_ewma}} against a hard limit of {{h:vol}}. Breach.
- [L:single_name] Largest sleeve weight is {{m:weight_max}} against a warning level of {{w:single_name}} and a hard limit of {{h:single_name}}. Warning.
- [L:drawdown] Drawdown from the NAV peak is {{m:drawdown}} against a warning level of {{w:drawdown}} and a hard limit of {{h:drawdown}}. Warning.

## Drivers
- [F:F1] The VaR breach continues and is almost unchanged. The small decline came from position changes, not from the market data window.
- [F:F2] The expected shortfall breach continues. It fell marginally and stays above its hard limit, in line with the VaR tail signal.
- [F:F3] Volatility eased a little but is still above its hard limit. One day of easing does not resolve the breach.
- [F:F4] The largest sleeve, HiTec, is above the warning level and below the hard limit. Its weight edged down. Its share of portfolio variance is roughly in line with its weight, so it is large but not disproportionately risky.
- [F:F5] The drawdown warning deepened after a loss on the day, with daily return at {{m:daily_return}} and NAV lower at {{m:nav_usd}}. It is closer to the hard limit but has not crossed it.
- [F:F6] The VaR backtest is in the yellow zone, outside the green zone. There are {{m:var_exceptions_250}} exceptions in the window, more than expected. The tests reject both the expected frequency and independence. The model may understate risk, so the VaR figure is not reassurance.
- [F:F7] A data quality item for the Hlth sleeve was escalated as a security event. No note text was supplied and nothing was acted on.

## Data quality
- [DQ:suspicious_note:0] A suspicious note was flagged for Hlth. Under triage policy it is a security event, so it was escalated to a human. The vendor note list was empty, so there was no text to read, and no note content was followed.

## For decision
- Decide whether the portfolio manager must present a plan to bring VaR, expected shortfall and volatility back inside hard limits, and by what date.
- Options for the portfolio manager to consider: reduce overall risk, reduce the HiTec sleeve, or ask for a formal exception with a stated rationale and end date.
- Decide whether to commission a review of the VaR model, given the yellow-zone backtest.
- Confirm that the Hlth security event has an owner in the security function.