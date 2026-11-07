# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Two limits are in warning and none is breached.

## Limits
- [L:single_name] Largest sleeve weight is {{m:weight_max}} against a warning of {{w:single_name}} and a hard limit of {{h:single_name}}.
- [L:liquidity] Days to liquidate is {{m:liq_days_max}} against a warning of {{w:liquidity}} and a hard limit of {{h:liquidity}}.

## Drivers
- [F:F1] The high tech sleeve is the largest and remains in warning. Its weight rose slightly from the prior day, which moves the book closer to the hard limit. Its share of risk is well above its weight.
- [F:F2] Days to liquidate the slowest sleeve are above the warning level and rose from the prior day. This is a continuing warning and is well short of the hard limit.
- [F:F3] The telecom move was flagged as a likely bad tick and zeroed provisionally. The VaR backtest is in the green zone. The small VaR change came from position moves, not from the market data window.

## Data quality
- [DQ:outlier:Telcm] The telecom sleeve showed an extreme one-day move that peers do not share and beta does not explain. It was treated as a likely bad tick. The return was set to zero provisionally, pending human review.

## For decision
- Confirm whether the provisional zero return for telecom stands, or whether the move should be reviewed with the data vendor.
- Decide whether the portfolio manager should present options to bring the high tech weight back below the warning level, and options to reduce the liquidation time.