# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Worst item: 1-day 99% VaR. Portfolio return on the day {{m:daily_return}}, NAV {{m:nav_usd}}.

## Limits
- [L:var99] 1-day 99% VaR {{m:var99_1d}} against a hard limit of {{h:var99}} (breach).
- [L:es975] 1-day 97.5% expected shortfall {{m:es975_1d}} against a hard limit of {{h:es975}} (breach).
- [L:vol] Annualised EWMA volatility {{m:vol_ann_ewma}} against a hard limit of {{h:vol}} (breach).
- [L:single_name] Largest sleeve weight {{m:weight_max}} against a hard limit of {{h:single_name}} (warning).
- [L:drawdown] Drawdown from NAV peak {{m:drawdown}} against a hard limit of {{h:drawdown}} (warning).

## Drivers
- [F:F1] 1-day 99% VaR is a continuing breach.
- [F:F2] 1-day 97.5% expected shortfall is a continuing breach.
- [F:F3] Annualised EWMA volatility is a continuing breach.
- [F:F4] Largest sleeve weight is a continuing warning.
- [F:F5] Drawdown from NAV peak is a continuing warning.
- The VaR backtest is in the yellow zone with {{m:var_exceptions_250}} exceptions, so VaR may be understating risk.

## Data quality
- [DQ:suspicious_note:0] suspicious note on Hlth: escalate. Vendor note contains instruction-like text.

## For decision
- Decide whether to accept or address the 1-day 99% VaR breach.
- Decide whether to accept or address the 1-day 97.5% expected shortfall breach.
- Decide whether to accept or address the Annualised EWMA volatility breach.
- Confirm the treatment of [DQ:suspicious_note:0].
