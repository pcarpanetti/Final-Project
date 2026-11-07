# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Two hard limits are breached, volatility and drawdown, after a one-day portfolio return of {{m:daily_return}}.

## Limits
- [L:vol] Annualised EWMA volatility is {{m:vol_ann_ewma}} against a warning of {{w:vol}} and a hard limit of {{h:vol}}. Breach.
- [L:drawdown] Drawdown from the NAV peak is {{m:drawdown}} against a warning of {{w:drawdown}} and a hard limit of {{h:drawdown}}. Breach.
- All other limits are within their warning levels. One-day VaR at the top confidence level is {{m:var99_1d}} against a hard limit of {{h:var99}}.

## Drivers
- [F:F1] Volatility moved into a hard breach as the large one-day loss fed the volatility estimate. The energy return is an open data item (see Data quality). The VaR backtest is in the {{m:backtest_zone}} zone, so the model may understate risk.
- [F:F2] On the reported data, drawdown is in a hard breach because NAV fell on the day. Position sizes barely moved. The loss is in market value, not in positioning.
- [F:F3] The energy return is flagged as an outlier. Peers also fell sharply, so a vendor error cannot be established. Energy is {{m:w_Enrgy}} of weight and {{m:ctr_Enrgy}} of variance. The VaR limit passes, but the parametric VaR is {{m:var99_param}}, above the hard limit of {{h:var99}}. VaR exceptions are clustering, with a new one today and {{m:var_exceptions_250}} in the window. The pass is not comfort. The VaR rise came from the market data window, not from positions.
- Sensitivity: at the energy weight, the flagged return explains only a small part of the day's {{m:daily_return}}. The drawdown breach would very likely persist if the energy return were corrected. The volatility margin is narrower, so rerun it once the data decision is made.

## Data quality
- [DQ:outlier:Enrgy] The energy return was flagged as an extreme outlier. The peer median also fell sharply and the expected return points the same way. No vendor notes were supplied. Overwriting the value could hide a real loss, so it was escalated and left unchanged pending a human decision.

## For decision
- Decide how to treat the energy return: accept it as reported, or override it. Rerun the metrics after the decision.
- The two hard breaches need a management response. Options are to reduce risk, to hold with a documented exception and review date, or another course. The portfolio manager chooses the action.