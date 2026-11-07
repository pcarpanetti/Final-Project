# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Two hard limits are breached, two limits are in warning, and today was a VaR exception.

## Limits
- [L:vol] Annualised EWMA volatility is {{m:vol_ann_ewma}} against a hard limit of {{h:vol}}. Status: breach.
- [L:drawdown] Drawdown from NAV peak is {{m:drawdown}} against a hard limit of {{h:drawdown}}. Status: breach.
- [L:es975] Expected shortfall at the tail level is {{m:es975_1d}} against a hard limit of {{h:es975}} and a warning level of {{w:es975}}. Status: warning.
- [L:var99] One-day VaR at the top confidence level is {{m:var99_1d}} against a hard limit of {{h:var99}} and a warning level of {{w:var99}}. Status: warning, new today.

## Drivers
- [F:F3] The volatility breach continues and has widened after a large negative portfolio return on the day ({{m:daily_return}}). Volatility is well beyond its hard limit.
- [F:F4] The drawdown breach continues and deepened. The day's large loss pushed NAV further below its peak. It is far beyond the hard limit.
- [F:F2] The expected shortfall warning continues and worsened. This fits the same loss-heavy data window. It sits close to its hard limit.
- [F:F1] The VaR warning is new. The rise came almost entirely from the market data window ({{m:var99_change_window}}), not from the book. Position moves slightly reduced it ({{m:var99_change_positions}}). The model may understate risk, so staying under the hard limit is not reassurance.
- [F:F5] Today was a VaR exception. The backtest zone is {{m:backtest_zone}}, which is outside the green zone. Exceptions exceed expectation ({{m:var_exceptions_250}} in the window), and both the coverage and independence tests reject. The technology sleeve holds the largest variance share ({{m:top_risk_contrib}}) and is also the largest weight.

## Data quality
None.

## For decision
- Decide whether to ask the portfolio manager for options to reduce volatility and drawdown, given both hard limits are breached.
- Decide whether to commission a review of the VaR model, given the yellow backtest zone and the clustering of exceptions.
