# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Volatility and drawdown are both past their hard limits after a large one-day portfolio loss.

## Limits
- [L:drawdown] Drawdown from NAV peak is {{m:drawdown}} against a hard limit of {{h:drawdown}} (warning {{w:drawdown}}). It escalated today.
- [L:vol] Annualised EWMA volatility is {{m:vol_ann_ewma}} against a hard limit of {{h:vol}} (warning {{w:vol}}). It escalated today.
- All other limits are within their warning levels.

## Drivers
- [F:F2] Drawdown deepened past the hard limit on the large one-day loss. The daily return was {{m:daily_return}}. NAV fell. The book did not change materially, since the position-driven change in VaR was {{m:var99_change_positions}}.
- [F:F1] Volatility was already in breach and rose further on the same loss. The largest contributors to risk are HiTec ({{m:ctr_HiTec}}), Other ({{m:ctr_Other}}) and Hlth ({{m:ctr_Hlth}}). The energy sleeve contribution ({{m:ctr_Enrgy}}) rose even though its weight fell to {{m:w_Enrgy}}.
- [F:F3] The VaR backtest is in the yellow zone, with {{m:var_exceptions_250}} exceptions in the window and another exception today. The independence test gives only weak support against clustering. The historical VaR limit passing ({{m:var99_1d}}) should not be read as reassurance. Parametric VaR is higher at {{m:var99_param}}, so the model may understate risk.
- [F:F4] The energy sleeve return was flagged as a very large outlier. Peers also fell sharply, so it may be a genuine sector loss, but the magnitude is in doubt. Treat energy figures with caution until reviewed.

## Data quality
- [DQ:outlier:Enrgy] The energy return was flagged as an extreme outlier, with a very large residual against its beta-implied move. Peers are also down sharply, so this is not a quiet-peer bad tick. Zeroing the return could hide a real loss. It was escalated for a human decision. No vendor notes were supplied.

## For decision
- Rule on the energy return: accept it as a genuine move, or correct it. The ruling changes the size of the volatility and drawdown figures, not whether the breaches exist. Drawdown stays in breach on any reading, because the broad loss was mostly not energy. The effect on volatility has not been quantified.
- Both breaches need a response from the portfolio manager. Options for the portfolio manager to consider include reducing risk in the largest variance contributors, or accepting the breaches with a time-bound plan. The priority is the portfolio manager's call.
- Note the yellow backtest zone when weighing any reliance on the historical VaR figure.