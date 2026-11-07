# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Two limits are in hard breach after a large one-day market loss, and the VaR backtest is in the yellow zone.

## Limits
- [L:vol] Annualised EWMA volatility is {{m:vol_ann_ewma}} against a hard limit of {{h:vol}} (warning {{w:vol}}). Status: breach.
- [L:drawdown] Drawdown from the NAV peak is {{m:drawdown}} against a hard limit of {{h:drawdown}} (warning {{w:drawdown}}). Status: breach.
- All other limits are within their warning levels.

## Drivers
- [F:F1] Volatility moved from escalated to a hard breach after a very large one-day loss. The Energy sleeve added to its share of variance (contribution {{m:ctr_Enrgy}}). Daily return was {{m:daily_return}}.
- [F:F2] Drawdown moved to a hard breach as the loss lowered NAV to {{m:nav_usd}}. The cause is the market move, not a change in positions. Sleeve weights barely moved.
- [F:F3] Historical VaR ({{m:var99_1d}}, hard limit {{h:var99}}) and expected shortfall ({{m:es975_1d}}, hard limit {{h:es975}}) pass their limits. This is not reassurance. The VaR change came from the market data window, not from the book. A VaR exception occurred today. Exceptions are above the expected count. The backtest zone is {{m:backtest_zone}}, so the model may understate risk. Parametric VaR is {{m:var99_param}}, well above the historical figure.

## Data quality
- [DQ:outlier:Enrgy] The Energy return was flagged as an extreme outlier. Peers are also moving sharply, so it may be a real loss and not a bad tick. It was not zeroed or corrected. It is escalated to a human for review.

## For decision
- Decide whether the portfolio manager should present options to bring volatility and drawdown back inside limits. This memo does not recommend specific trades.
- Assign a human to confirm whether the Energy return is genuine.
- Decide whether to review the VaR model, given the yellow backtest zone.