# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. Two limits are in breach and two are in warning, and the VaR backtest is outside the green zone.

## Limits
- [L:vol] Annualised EWMA volatility is {{m:vol_ann_ewma}} against a hard limit of {{h:vol}}. This is a breach and continues from before.
- [L:drawdown] Drawdown from the NAV peak is {{m:drawdown}} against a hard limit of {{h:drawdown}}. This is a breach and continues from before.
- [L:var99] One-day VaR at the ninety-ninth percentile is {{m:var99_1d}} against a warning limit of {{w:var99}} and a hard limit of {{h:var99}}. This warning is new today.
- [L:es975] One-day expected shortfall at the ninety-seventh-and-a-half percentile is {{m:es975_1d}} against a warning limit of {{w:es975}} and a hard limit of {{h:es975}}. This warning continues and is closer to the hard limit.

## Drivers
- [F:F3] The volatility breach continues. Volatility rose after a large negative portfolio return on the day. The portfolio return was {{m:daily_return}}.
- [F:F4] The drawdown breach continues and deepened. The portfolio lost value on the day after a gain the day before. Net asset value fell to {{m:nav_usd}}.
- [F:F1] The VaR warning is new. The rise came almost entirely from the market data window, most likely a large loss entering the sample. The window effect was {{m:var99_change_window}}. Position changes slightly reduced VaR, by {{m:var99_change_positions}}.
- [F:F2] The expected shortfall warning continues and worsened. It is nearer the hard limit but not through it. This fits the heavier loss tail in the data window.
- [F:F5] The VaR backtest zone is {{m:backtest_zone}}, outside the green zone. There were {{m:var_exceptions_250}} exceptions over the window, more than expected, including one today. The tests reject both correct coverage and independence. The model may understate risk. The VaR warning should not be read as a ceiling on losses.

## Data quality
- None.

## For decision
- Decide whether the portfolio manager should present options to reduce volatility and drawdown risk, given the two breaches.
- Decide whether to ask for a review of the VaR model, given the backtest result.
