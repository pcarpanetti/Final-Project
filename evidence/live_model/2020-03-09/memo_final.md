# Daily Risk Memo: 2020-03-09

## Status
Overall status: BREACH. Two hard limits were breached today, volatility and drawdown, after a large one-day portfolio loss.

## Limits
- [L:vol] Annualised EWMA volatility is 44.31% against a hard limit of 40.00% and a warning level of 25.00%. This is a new breach today.
- [L:drawdown] Drawdown from the NAV peak is 19.04% against a hard limit of 15.00% and a warning level of 10.00%. This is a new breach today.
- All other limits are within bounds.

## Drivers
- [F:F1] Volatility crossed the hard limit today. It was above the warning level of 25.00% but below the hard limit of 40.00% the day before. It is now 44.31% after a portfolio return of -7.80%. The energy sleeve explains a larger share of variance, even though its weight fell to 4.78%.
- [F:F2] Drawdown crossed the hard limit because of the large one-day loss, and NAV fell. The book did not change materially. The position-driven change in VaR was -0.01%.
- [F:F3] The VaR backtest is in the yellow zone, outside the green zone. There were 5 exceptions in the window, including one today. The independence test gives only weak support against clustering. The historical VaR limit passing is not reassurance, since the model may understate risk. Parametric VaR is 6.49% against historical VaR of 3.20%.
- [F:F4] The data quality check flagged the energy sleeve return as a very large outlier. Peers also fell sharply, so it may be a genuine sector loss, but the size is in doubt. Treat the energy figures with caution until reviewed.

## Data quality
- [DQ:outlier:Enrgy] The energy sleeve return was flagged as an extreme outlier. Peers also moved sharply down, so it is not a clear bad tick. It was escalated for a human decision. No correction was applied, so the loss is still in the figures.

## For decision
- Decide whether the energy return is genuine or a data error. Until then, the volatility and drawdown figures may be overstated or understated.
- Decide how to respond to the two hard breaches. Options for the portfolio manager include reducing overall risk, cutting the energy sleeve, or documenting a time-limited exception. This memo does not recommend a trade.
- Decide whether the yellow backtest zone calls for a model review.