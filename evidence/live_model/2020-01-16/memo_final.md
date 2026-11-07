# Daily Risk Memo: 2020-01-16

## Status
Overall status: WARNING. No hard limit is breached. Two warnings continue: single-sleeve weight and days to liquidate.

## Limits
- [L:single_name] Largest sleeve weight 24.71% against a warning of 24.50% and a hard limit of 25.00%.
- [L:liquidity] Days to liquidate 3.0 days against a warning of 3.0 days and a hard limit of 5.0 days.
- One-day VaR at the top confidence level is 3.19% against a hard limit of 4.50%. This is within limit.
- Expected shortfall is 2.92% against a hard limit of 5.00%. This is within limit.
- Worst stress loss is 20.52% against a hard limit of 25.00%. This is within limit.

## Drivers
- [F:F1] The high tech sleeve is the largest and stays in warning. Its weight rose slightly, to 24.71%. It carries a risk share of 36.72%, well above its weight, so it does more risk work than its size suggests.
- [F:F2] Days to liquidate the slowest sleeve are above the warning level and rose from the prior day. They are still well short of the hard limit.
- [F:F3] The VaR backtest is in the green zone, with 0 exceptions in the recent window. The small VaR change came from position moves, not the market data window.

## Data quality
- [DQ:outlier:Telcm] An extreme one-day move in the telecom sleeve was flagged. Peers did not share it and beta does not explain it. It was treated as a likely bad tick. The return was set to zero provisionally, pending human review.

## For decision
- Confirm or reverse the provisional zeroing of the telecom return after review.
- Options for the portfolio manager on the two warnings: hold the high tech weight and liquidity positions as they are and keep monitoring, or lower the high tech weight or the slowest-to-liquidate sleeve. The memo does not recommend a trade.

## Open reviewer concerns
All automated checks passed, but the independent reviewer was still not satisfied after the last round.
- Causation (rubric item 3): Driver F3 says the small VaR change "came from position moves, not the market data window". The facts show only that VaR moved from 3.187% to 3.189%. They contain no attribution of the change to positions versus data. This is a cause asserted without evidence. The flagged Telcm outlier was also zeroed in the return data, so the data window did change.
- Reassurance and clarity: the liquidity line reads "3.0 days against a warning of 3.0 days". Rounding hides that the value is 3.04, above the warning level. The reader sees equal numbers under a warning flag and cannot tell why it is a warning. The days-to-liquidate rise is also not quantified.
- Data quality impact is not stated. The Telcm return was zeroed provisionally, but the memo does not say whether the reported limit figures (VaR, ES, vol, weights) use the zeroed value. A CRO cannot tell how far to trust the "within limit" statements until the review is done.
