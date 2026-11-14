# Daily Risk Memo: 2020-01-16

## Status
Overall status: WARNING. No limit is breached, and two warnings continue from the prior day.

## Limits
- [L:single_name] Largest sleeve weight is 24.71% against a warning level of 24.50% and a hard limit of 25.00%. Status is warning.
- [L:liquidity] Days to liquidate the slowest sleeve are 3.04 days against a warning level of 3.00 days and a hard limit of 5.00 days. Status is warning.
- All other limits are within their warning levels.

## Drivers
- [F:F1] The high tech sleeve is the largest and stays above the warning level but below the hard limit. Its weight edged higher to 24.71%. Its share of portfolio variance is 36.72%, well above its weight. It does more risk work than its size suggests.
- [F:F2] Days to liquidate the slowest sleeve crept up. It stays just above the warning level and well short of the hard limit. There is no new breach.
- [F:F3] The data quality check flagged an extreme telecom return as a likely bad tick. The sleeve was held unchanged pending human review. Read the portfolio return of 0.76% and the risk figures with that provisional adjustment in mind. The telecom weight and variance share did not rise.
- The VaR backtest is in the green zone.

## Data quality
- [DQ:outlier:Telcm] The telecom return was far above what its peers and the market explain. Peers were quiet and no shared market move accounts for it. It was treated as a likely bad tick. The sleeve was held unchanged provisionally for human review. No vendor notes were supplied.

## For decision
- Confirm or reject the provisional treatment of the telecom return after human review.
- Options for the portfolio manager on the two warnings: accept them as continuing, or consider reducing the high tech weight and the slowest sleeve's liquidation time. This memo gives no trade instruction.
