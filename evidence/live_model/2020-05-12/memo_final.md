# Daily Risk Memo: 2020-05-12

## Status
Overall status: BREACH. Three hard limits are breached, two more are at warning, and the VaR backtest is outside the green zone.

## Limits
- [L:var99] One-day 99% VaR is 4.97% against a hard limit of 4.50%. Breach.
- [L:es975] One-day 97.5% expected shortfall is 5.30% against a hard limit of 5.00%. Breach.
- [L:vol] Annualised EWMA volatility is 42.50% against a hard limit of 40.00%. Breach.
- [L:single_name] Largest sleeve weight is 24.80% against a warning level of 24.50% and a hard limit of 25.00%. Warning.
- [L:drawdown] Drawdown from NAV peak is 14.00% against a warning level of 10.00% and a hard limit of 15.00%. Warning.

## Drivers
- [F:F1] The VaR breach continues. VaR edged lower. The small change came entirely from position moves, not from the market data window.
- [F:F2] The expected shortfall breach continues. It is essentially unchanged and slightly lower.
- [F:F3] The volatility breach continues. Volatility eased a little from the prior day.
- [F:F4] The largest sleeve, HiTec, is above the warning level and below the hard limit. Its weight slipped marginally. It also carries the largest share of portfolio variance, at 25.69%.
- [F:F5] The drawdown warning continues. The drawdown deepened because the portfolio had a negative return on the day, which took net asset value lower.
- [F:F6] The VaR backtest is in the yellow zone, outside the green zone. The model shows 9 exceptions, more than expected, and the coverage test rejects the model. The model may understate risk. Do not read the VaR figures as reassurance.

## Data quality
- [DQ:suspicious_note:0] A suspicious note was flagged on Hlth. Policy treats this as a security event. No note text was available, and nothing was followed. It is escalated for human review.

## For decision
- Decide whether to accept the three continuing hard-limit breaches and set a deadline for the portfolio manager to present options. Options could include reducing HiTec exposure or lowering overall risk.
- Decide whether to commission a review of the VaR model, given the backtest result.
- Assign an owner for the Hlth security review.