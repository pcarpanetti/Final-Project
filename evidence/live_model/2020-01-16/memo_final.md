# Daily Risk Memo: 2020-01-16

## Status
Overall status: WARNING. Two limits are in warning and none is breached. Both warnings continue from the prior day.

## Limits
- [L:single_name] Largest sleeve weight is 24.71% against a warning level of 24.50% and a hard limit of 25.00%. The sleeve is HiTec.
- [L:liquidity] Days to liquidate the slowest sleeve is 3.04 days against a warning level of 3.00 days and a hard limit of 5.00 days.
- All other limits are ok.

## Drivers
- [F:F1] The largest sleeve, HiTec, is above the warning level and below the hard limit. Its weight rose from the prior day. The largest risk contributor is HiTec at 36.72% of portfolio variance. That share is well above its weight, so it does more risk work than its size suggests.
- [F:F2] Days to liquidate the slowest sleeve are above the warning level and below the hard limit. They lengthened slightly from the prior day. This is a continuing warning.
- [F:F3] The data quality process found a very large one-day move in the Telcm sleeve with no matching peer move. It judged this a likely bad vendor tick. Telcm was treated as unchanged for today, so the reported risk figures depend on that choice. The VaR backtest is in the green zone with no exceptions.

## Data quality
- [DQ:outlier:Telcm] Telcm showed an outlier return far above what its peers and expected return explain. It was treated as a zero return for today, provisionally. A human should review the vendor price. The vendor supplied no notes.

## For decision
- Confirm or overturn the provisional zero return on Telcm. If the move is real, the risk figures need a rerun.
- Options for the portfolio manager, for discussion only: review the size of the HiTec sleeve relative to its warning level, and review the liquidity of the slowest sleeve. This memo gives no trade instruction.
