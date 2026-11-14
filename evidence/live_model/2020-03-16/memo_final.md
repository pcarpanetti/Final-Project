# Daily Risk Memo: 2020-03-16

## Status
Overall status: BREACH. Two hard limits are breached, two warnings are open, and the VaR backtest is outside the green zone.

## Limits
- [L:vol] Annualised EWMA volatility is 78.86% against a hard limit of 40.00%. Breach.
- [L:drawdown] Drawdown from the NAV peak is 30.28% against a hard limit of 15.00%. Breach.
- [L:var99] One-day VaR at the top confidence level is 4.25%. The warning level is 3.50% and the hard limit is 4.50%. Warning, new today.
- [L:es975] One-day expected shortfall is 4.82%. The warning level is 3.50% and the hard limit is 5.00%. Warning, continuing.

## Drivers
- [F:F3] The volatility breach continues and has risen further. It stays far above the hard limit after a large negative portfolio return on the day.
- [F:F4] The drawdown breach continues and deepened sharply because of a large loss on the day. It is well beyond the hard limit.
- [F:F1] The VaR warning is new. The move comes from the market data window, not from the book. The position-driven change was -0.01% and the window change was 0.96%, which accounts for the whole rise.
- [F:F2] The expected shortfall warning continues and has worsened since the prior day, in line with the larger tail losses now in the data window.
- [F:F5] The backtest zone is yellow. There was a VaR exception today, and exceptions over the window number 8, more than expected. The tests reject both the exception count and the independence of exceptions. The model may be understating risk, so the VaR figures should not be read as reassurance.

## Data quality
None.

## For decision
- Decide whether to ask the portfolio manager for options to bring volatility and drawdown back inside the hard limits, with a timeline.
- Decide whether to open a review of the VaR model, given the yellow backtest zone and the failed independence test.
