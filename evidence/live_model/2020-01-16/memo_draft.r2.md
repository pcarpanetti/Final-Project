# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. No hard limit is breached. Two warnings continue: single-sleeve weight and days to liquidate.

## Limits
- [L:single_name] Largest sleeve weight {{m:weight_max}} against a warning of {{w:single_name}} and a hard limit of {{h:single_name}}.
- [L:liquidity] Days to liquidate {{m:liq_days_max}} against a warning of {{w:liquidity}} and a hard limit of {{h:liquidity}}.
- One-day VaR at the top confidence level is {{m:var99_1d}} against a hard limit of {{h:var99}}. This is within limit.
- Expected shortfall is {{m:es975_1d}} against a hard limit of {{h:es975}}. This is within limit.
- Worst stress loss is {{m:stress_worst}} against a hard limit of {{h:stress}}. This is within limit.

## Drivers
- [F:F1] The high tech sleeve is the largest and stays in warning. Its weight rose slightly, to {{m:w_HiTec}}. It carries a risk share of {{m:top_risk_contrib}}, well above its weight, so it does more risk work than its size suggests.
- [F:F2] Days to liquidate the slowest sleeve are above the warning level and rose from the prior day. They are still well short of the hard limit.
- [F:F3] The VaR backtest is in the green zone, with {{m:var_exceptions_250}} exceptions in the recent window. The small VaR change came from position moves, not the market data window.

## Data quality
- [DQ:outlier:Telcm] An extreme one-day move in the telecom sleeve was flagged. Peers did not share it and beta does not explain it. It was treated as a likely bad tick. The return was set to zero provisionally, pending human review.

## For decision
- Confirm or reverse the provisional zeroing of the telecom return after review.
- Options for the portfolio manager on the two warnings: hold the high tech weight and liquidity positions as they are and keep monitoring, or lower the high tech weight or the slowest-to-liquidate sleeve. The memo does not recommend a trade.
