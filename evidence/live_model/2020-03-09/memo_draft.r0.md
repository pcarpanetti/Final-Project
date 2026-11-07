# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Two limits are in hard breach, volatility and drawdown, after a large one-day portfolio loss.

## Limits
- [L:vol] Annualised EWMA volatility is {{m:vol_ann_ewma}} against a hard limit of {{h:vol}} and a warning level of {{w:vol}}. Escalated from warning to breach.
- [L:drawdown] Drawdown from the NAV peak is {{m:drawdown}} against a hard limit of {{h:drawdown}} and a warning level of {{w:drawdown}}. Escalated from warning to breach.
- All other limits are within their warning levels. One-day VaR at the ninety-ninth percentile is {{m:var99_1d}} against a hard limit of {{h:var99}}.

## Drivers
- [F:F1] Volatility moved into a hard breach because a very large one-day loss (daily return {{m:daily_return}}) fed into the volatility estimate. The energy sleeve contributed. The VaR backtest zone is {{m:backtest_zone}}, so the model may understate risk.
- [F:F2] Drawdown moved into a hard breach because the book lost value on the day. NAV is now {{m:nav_usd}}. This is a market loss, not a change in position sizes.
- [F:F3] The energy sleeve return is flagged as an outlier and needs a human decision. Peers also fell sharply, so a vendor error cannot be established. Its share of variance rose ({{m:ctr_Enrgy}}) while its weight fell ({{m:w_Enrgy}}). The VaR limit passes, but there is a new VaR exception today and the backtest is outside the green zone. Exceptions over the last window: {{m:var_exceptions_250}}. The pass should not be read as reassurance. The VaR rise came from the market data window, not from positions.

## Data quality
- [DQ:outlier:Enrgy] The energy return was flagged as an extreme outlier. Peers moved sharply in the same direction, and the expected return points the same way. The item was escalated and the data was not overwritten, because replacing it could hide a real loss.

## For decision
- Decide whether the energy return is accepted as genuine or treated as a vendor error. Until then, the figures above use the reported value.
- Decide how to respond to the two hard breaches. Options for the portfolio manager include reducing overall risk, hedging the energy exposure, or holding with a documented exception and review date.
- Decide whether to request a review of the VaR model, given the backtest is outside the green zone.