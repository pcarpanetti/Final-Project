# Daily Risk Memo: 2020-03-09

## Status
Overall status: BREACH. Two limits are in hard breach after a large one-day market loss, and the VaR backtest is in the yellow zone.

## Limits
- [L:vol] Annualised EWMA volatility is 44.31% against a hard limit of 40.00% (warning 25.00%). Status: breach.
- [L:drawdown] Drawdown from the NAV peak is 19.04% against a hard limit of 15.00% (warning 10.00%). Status: breach.
- All other limits are within their warning levels.

## Drivers
- [F:F1] Volatility moved from escalated to a hard breach after a very large one-day loss. The Energy sleeve added to its share of variance (contribution 8.40%). Daily return was -7.80%.
- [F:F2] Drawdown moved to a hard breach as the loss lowered NAV to $93.3m. The cause is the market move, not a change in positions. Sleeve weights barely moved.
- [F:F3] Historical VaR (3.20%, hard limit 4.50%) and expected shortfall (3.43%, hard limit 5.00%) pass their limits. This is not reassurance. The VaR change came from the market data window, not from the book. A VaR exception occurred today. Exceptions are above the expected count. The backtest zone is yellow, so the model may understate risk. Parametric VaR is 6.49%, well above the historical figure.

## Data quality
- [DQ:outlier:Enrgy] The Energy return was flagged as an extreme outlier. Peers are also moving sharply, so it may be a real loss and not a bad tick. It was not zeroed or corrected. It is escalated to a human for review.

## For decision
- Decide whether the portfolio manager should present options to bring volatility and drawdown back inside limits. This memo does not recommend specific trades.
- Assign a human to confirm whether the Energy return is genuine.
- Decide whether to review the VaR model, given the yellow backtest zone.