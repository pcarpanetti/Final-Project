# Daily Risk Memo: 2020-03-16

## Status
Overall status: BREACH. Two limits are in breach and two are in warning, and the VaR backtest is outside the green zone.

## Limits
- [L:vol] Annualised EWMA volatility is 78.86% against a hard limit of 40.00%. This is a breach and continues from before.
- [L:drawdown] Drawdown from the NAV peak is 30.28% against a hard limit of 15.00%. This is a breach and continues from before.
- [L:var99] One-day VaR at the ninety-ninth percentile is 4.25% against a warning limit of 3.50% and a hard limit of 4.50%. This warning is new today.
- [L:es975] One-day expected shortfall at the ninety-seventh-and-a-half percentile is 4.82% against a warning limit of 3.50% and a hard limit of 5.00%. This warning continues and is closer to the hard limit.

## Drivers
- [F:F3] The volatility breach continues. Volatility rose after a large negative portfolio return on the day. The portfolio return was -11.57%.
- [F:F4] The drawdown breach continues and deepened. The portfolio lost value on the day after a gain the day before. Net asset value fell to $80.3m.
- [F:F1] The VaR warning is new. The rise came almost entirely from the market data window, most likely a large loss entering the sample. The window effect was 0.96%. Position changes slightly reduced VaR, by -0.01%.
- [F:F2] The expected shortfall warning continues and worsened. It is nearer the hard limit but not through it. This fits the heavier loss tail in the data window.
- [F:F5] The VaR backtest zone is yellow, outside the green zone. There were 8 exceptions over the window, more than expected, including one today. The tests reject both correct coverage and independence. The model may understate risk. The VaR warning should not be read as a ceiling on losses.

## Data quality
- None.

## For decision
- Decide whether the portfolio manager should present options to reduce volatility and drawdown risk, given the two breaches.
- Decide whether to ask for a review of the VaR model, given the backtest result.
