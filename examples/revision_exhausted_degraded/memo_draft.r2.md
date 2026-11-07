# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Worst item: 1-day 99% VaR. Portfolio return on the day {{m:daily_return}}, NAV {{m:nav_usd}}.

## Limits
- [L:var99] 1-day 99% VaR {{m:var99_1d}} against a hard limit of {{h:var99}} (breach).
- [L:es975] 1-day 97.5% expected shortfall {{m:es975_1d}} against a hard limit of {{h:es975}} (breach).
- [L:vol] Annualised EWMA volatility {{m:vol_ann_ewma}} against a hard limit of {{h:vol}} (breach).
- [L:single_name] Largest sleeve weight {{m:weight_max}} against a hard limit of {{h:single_name}} (breach).
- [L:drawdown] Drawdown from NAV peak {{m:drawdown}} against a hard limit of {{h:drawdown}} (breach).
- [L:top3] Top three sleeve weights {{m:top3_weight}} against a hard limit of {{h:top3}} (warning).

## Drivers
- Losses reached about 5.2 percent of NAV.
- [F:F1] 1-day 99% VaR is a continuing breach.
- [F:F2] 1-day 97.5% expected shortfall is a continuing breach.
- [F:F3] Annualised EWMA volatility is a continuing breach.
- [F:F4] Largest sleeve weight is a continuing breach.
- [F:F5] Top three sleeve weights is a continuing warning.
- [F:F6] Drawdown from NAV peak is a continuing breach.
- The VaR backtest is in the yellow zone with {{m:var_exceptions_250}} exceptions, so VaR may be understating risk.

## Data quality
None.

## For decision
- Decide whether to accept or address the 1-day 99% VaR breach.
- Decide whether to accept or address the 1-day 97.5% expected shortfall breach.
- Decide whether to accept or address the Annualised EWMA volatility breach.
- Decide whether to accept or address the Largest sleeve weight breach.
- Decide whether to accept or address the Drawdown from NAV peak breach.
