# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Volatility and drawdown are both past their hard limits, and both escalated today after a large one-day loss.

## Limits
- [L:drawdown] Drawdown from NAV peak is {{m:drawdown}} against a hard limit of {{h:drawdown}} and a warning of {{w:drawdown}}. Breach.
- [L:vol] Annualised EWMA volatility is {{m:vol_ann_ewma}} against a hard limit of {{h:vol}} and a warning of {{w:vol}}. Breach.
- All other limits are within warning levels.

## Drivers
- [F:F1] Volatility was already in breach and rose further on a large one-day portfolio loss of {{m:daily_return}}. The energy sleeve now explains more of the variance ({{m:ctr_Enrgy}}) even though its weight fell to {{m:w_Enrgy}}.
- [F:F2] Drawdown deepened past the hard limit because of the one-day loss. NAV is now {{m:nav_usd}}. The book did not change much: the position-driven change in VaR was {{m:var99_change_positions}}.
- [F:F3] The VaR backtest is in the {{m:backtest_zone}} zone, outside the green zone. There were {{m:var_exceptions_250}} exceptions in the window, including one today. The independence test gives only weak support against clustering. The VaR limit passing, at {{m:var99_1d}}, is not reassurance, because the model may understate risk. Parametric VaR is {{m:var99_param}}, well above the historical figure.
- [F:F4] The data quality check flagged the energy sleeve return as a very large outlier. Peers also fell sharply, so this may be a real sector loss, but the size is in doubt. Treat the energy figures with caution until reviewed.

## Data quality
- [DQ:outlier:Enrgy] The energy return was flagged as an outlier with a very large residual against peers. Peers are also sharply down, so it could be a genuine loss. It was not zeroed or corrected. It is escalated for a human decision.

## For decision
- Rule on the energy return: confirm it as a genuine move or as a bad print. The answer changes the volatility and drawdown figures.
- Decide whether to ask the portfolio manager for options to bring volatility and drawdown back within limits, with the energy sleeve as the first area to review.
- Decide whether to review the VaR model given the backtest result.