# Daily Risk Memo: 2020-05-12

## Status
Overall status: BREACH. Worst item: 1-day 99% VaR. Portfolio return on the day -1.98%, NAV $99.1m.

## Limits
- [L:var99] 1-day 99% VaR 4.97% against a hard limit of 4.50% (breach).
- [L:es975] 1-day 97.5% expected shortfall 5.30% against a hard limit of 5.00% (breach).
- [L:vol] Annualised EWMA volatility 42.50% against a hard limit of 40.00% (breach).
- [L:single_name] Largest sleeve weight 24.80% against a hard limit of 25.00% (warning).
- [L:drawdown] Drawdown from NAV peak 14.00% against a hard limit of 15.00% (warning).

## Drivers
- [F:F1] 1-day 99% VaR is a continuing breach.
- [F:F2] 1-day 97.5% expected shortfall is a continuing breach.
- [F:F3] Annualised EWMA volatility is a continuing breach.
- [F:F4] Largest sleeve weight is a continuing warning.
- [F:F5] Drawdown from NAV peak is a continuing warning.
- The VaR backtest is in the yellow zone with 9 exceptions, so VaR may be understating risk.

## Data quality
- [DQ:suspicious_note:0] suspicious note on Hlth: escalate. Vendor note contains instruction-like text.

## For decision
- Decide whether to accept or address the 1-day 99% VaR breach.
- Decide whether to accept or address the 1-day 97.5% expected shortfall breach.
- Decide whether to accept or address the Annualised EWMA volatility breach.
- Confirm the treatment of [DQ:suspicious_note:0].
