# Daily Risk Memo: 2020-03-09

## Status
Overall status: BREACH. Two hard limits are breached, volatility and drawdown, after a one-day portfolio return of -7.80%.

## Limits
- [L:vol] Annualised EWMA volatility is 44.31% against a warning of 25.00% and a hard limit of 40.00%. Breach.
- [L:drawdown] Drawdown from the NAV peak is 19.04% against a warning of 10.00% and a hard limit of 15.00%. Breach.
- All other limits are within their warning levels. One-day VaR at the top confidence level is 3.20% against a hard limit of 4.50%.

## Drivers
- [F:F1] Volatility moved into a hard breach as the large one-day loss fed the volatility estimate. The energy return is an open data item (see Data quality). The VaR backtest is in the yellow zone, so the model may understate risk.
- [F:F2] On the reported data, drawdown is in a hard breach because NAV fell on the day. Position sizes barely moved. The loss is in market value, not in positioning.
- [F:F3] The energy return is flagged as an outlier. Peers also fell sharply, so a vendor error cannot be established. Energy is 4.78% of weight and 8.40% of variance. The VaR limit passes, but the parametric VaR is 6.49%, above the hard limit of 4.50%. VaR exceptions are clustering, with a new one today and 5 in the window. The pass is not comfort. The VaR rise came from the market data window, not from positions.
- Sensitivity: at the energy weight, the flagged return explains only a small part of the day's -7.80%. The drawdown breach would very likely persist if the energy return were corrected. The volatility margin is narrower, so rerun it once the data decision is made.

## Data quality
- [DQ:outlier:Enrgy] The energy return was flagged as an extreme outlier. The peer median also fell sharply and the expected return points the same way. No vendor notes were supplied. Overwriting the value could hide a real loss, so it was escalated and left unchanged pending a human decision.

## For decision
- Decide how to treat the energy return: accept it as reported, or override it. Rerun the metrics after the decision.
- The two hard breaches need a management response. Options are to reduce risk, to hold with a documented exception and review date, or another course. The portfolio manager chooses the action.