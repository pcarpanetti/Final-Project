# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Two limits are in warning and none is breached. The Telcm data point is zeroed provisionally and awaits human review.

## Limits
- [L:single_name] Largest sleeve weight ({{m:weight_max_asset}}) is {{m:weight_max}} against a warning of {{w:single_name}} and a hard limit of {{h:single_name}}.
- [L:liquidity] Days to liquidate the slowest sleeve are {{m:liq_days_max}} against a warning of {{w:liquidity}} and a hard limit of {{h:liquidity}}.
- [L:var99] One-day 99th percentile VaR is {{m:var99_1d}} against a warning of {{w:var99}} and a hard limit of {{h:var99}}. Status is ok.

## Drivers
- [F:F1] The largest sleeve stays above its warning level, and its weight rose slightly from the prior day. The book is a little closer to the hard limit.
- [F:F2] Days to liquidate are still above the warning level and rose slightly from the prior day. They remain well short of the hard limit.
- [F:F3] A large one-day move in the telecom sleeve is not shared by peers and is not explained by beta. It was treated as a likely bad tick and zeroed provisionally. One-day VaR is essentially unchanged, with a day-on-day change of {{m:var99_change}}. The VaR backtest is in the green zone ({{m:backtest_zone}}), with no exception today.

## Data quality
- [DQ:outlier:Telcm] The Telcm return was flagged as an outlier far above the residual threshold. Peers were quiet. The return was set to zero provisionally for human review. The reported figures assume the move is a bad tick. The effect on them has not been quantified. If the move is genuine, VaR, expected shortfall and the other figures are understated until the review is complete.

## For decision
- Decide whether to keep the provisional zeroing of the Telcm return until the review is done, or to rerun the metrics with the raw return to size the effect.
- The portfolio manager may want to consider options for the largest sleeve weight and the liquidation days. The options include leaving them under watch or reducing exposure. This memo gives no trade instruction.