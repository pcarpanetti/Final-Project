# Daily Risk Memo: 2020-03-16

## Status
Overall status: BREACH. Two hard limits are breached, two limits are in warning, and today was a VaR exception.

## Limits
- [L:vol] Annualised EWMA volatility is 78.86% against a hard limit of 40.00%. Status: breach.
- [L:drawdown] Drawdown from NAV peak is 30.28% against a hard limit of 15.00%. Status: breach.
- [L:es975] Expected shortfall at the tail level is 4.82% against a hard limit of 5.00% and a warning level of 3.50%. Status: warning.
- [L:var99] One-day VaR at the top confidence level is 4.25% against a hard limit of 4.50% and a warning level of 3.50%. Status: warning, new today.

## Drivers
- [F:F3] The volatility breach continues and has widened after a large negative portfolio return on the day (-11.57%). Volatility is well beyond its hard limit.
- [F:F4] The drawdown breach continues and deepened. The day's large loss pushed NAV further below its peak. It is far beyond the hard limit.
- [F:F2] The expected shortfall warning continues and worsened. This fits the same loss-heavy data window. It sits close to its hard limit.
- [F:F1] The VaR warning is new. The rise came almost entirely from the market data window (0.96%), not from the book. Position moves slightly reduced it (-0.01%). The model may understate risk, so staying under the hard limit is not reassurance.
- [F:F5] Today was a VaR exception. The backtest zone is yellow, which is outside the green zone. Exceptions exceed expectation (8 in the window), and both the coverage and independence tests reject. The technology sleeve holds the largest variance share (26.89%) and is also the largest weight.

## Data quality
None.

## For decision
- Decide whether to ask the portfolio manager for options to reduce volatility and drawdown, given both hard limits are breached.
- Decide whether to commission a review of the VaR model, given the yellow backtest zone and the clustering of exceptions.
