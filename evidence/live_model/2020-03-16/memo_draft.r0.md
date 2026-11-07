# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Two hard limits are breached after a large loss day, and the backtest is outside the green zone.

## Limits
- [L:vol] Annualised EWMA volatility {{m:vol_ann_ewma}} against a hard limit of {{h:vol}}. Status: breach.
- [L:drawdown] Drawdown from NAV peak {{m:drawdown}} against a hard limit of {{h:drawdown}}. Status: breach.
- [L:var99] One-day 99% VaR {{m:var99_1d}} against a warning limit of {{w:var99}} and a hard limit of {{h:var99}}. Status: warning. New today.
- [L:es975] One-day 97.5% expected shortfall {{m:es975_1d}} against a warning limit of {{w:es975}} and a hard limit of {{h:es975}}. Status: warning.

## Drivers
- [F:F3] The volatility breach continues and worsened. The EWMA estimate is well beyond the hard limit after the large loss day.
- [F:F4] The drawdown breach continues and deepened. NAV fell on a large negative return, and drawdown is far beyond the hard limit.
- [F:F1] The VaR warning is new. The rise came almost entirely from the market data window, where a large loss entered the sample. Position changes slightly reduced VaR. The book did not drive the move.
- [F:F2] The expected shortfall warning continues. Tail risk rose further, in line with the large negative portfolio return.
- [F:F5] The VaR backtest zone is {{m:backtest_zone}}, so it is outside the green zone. Exceptions over the window: {{m:var_exceptions_250}}. An exception occurred today. Both the frequency and independence tests reject the model. Exceptions cluster, so the model may understate risk. Passing limits should not be read as reassurance.

## Data quality
None.

## For decision
- Decide whether to ask the portfolio manager for options to bring volatility and drawdown back within the hard limits. Options could include reducing gross exposure or hedging market beta. The choice sits with the portfolio manager.
- Decide whether to commission a review of the VaR model, given the yellow backtest zone and clustered exceptions.