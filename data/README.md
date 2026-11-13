# Data

`raw/` holds 1984-01-03 to 2026-09-30 of two public datasets from the
[Kenneth R. French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html),
CRSP vintage 202609, copyright Eugene F. Fama and Kenneth R. French. Returns are in percent.
`scripts/extract_raw_data.py` cuts these files out of the library's two downloads, which are not committed.

Runs may start on any trading day from 1986-01-02. The two years before that are history the risk model
needs: 1-day VaR uses the last 500 days.

| File | Source dataset |
|---|---|
| `raw/ff_industry10_vw_daily_pct.csv` | 10 Industry Portfolios, daily, value-weighted |
| `raw/ff_factors_daily_pct.csv` | Fama/French 3 Factors, daily |

`feed/` is generated from `raw/` by `scripts/build_feed.py` and is what the workflow reads.
It turns the static history into a **bitemporal vendor feed**: every row has both the date it
describes (`as_of`) and the time it became known (`published_at`). `feed/meta.json` gives the range.

The book in `feed/positions.csv` is one continuous portfolio, rebalanced to target at each month end. It is
anchored at $100m on 2019-06-28, the eve of the fixed evaluation window, so extending the history left every
earlier row of the feed byte-for-byte unchanged. A workspace then launches the fund with $100m on the trading
day before its own first day, so NAV and drawdown are measured from the period you choose.

A workspace can instead run its own book: target weights for the ten sleeves, a starting NAV, monthly, quarterly or
no rebalancing, and dated changes of targets. `src/riskwatch/book.py` writes that book's positions file into the
workspace before its first run, using the same simulation as `build_feed.py`, and runs read it through the
point-in-time store like any other input. Its positions are clean: the injected positions fault belongs to the default
book. Evaluation always uses the default book.

What is real and what is not:

- **Real:** all market returns, except the handful of rows listed in `faults.yaml`.
- **Fictional:** the portfolio, its NAV, target weights and limits, whether default or your own. The ten industry portfolios
  stand in for ten investable sleeves. No client or employer data is used.
- **Injected:** the vendor faults in `faults.yaml`. They exist so the evaluation has labelled
  ground truth. Only `build_feed.py` and the evaluation harness read that file; a test checks
  that no production stage does. All six sit between July 2019 and June 2020, so every other
  period runs on clean market data with nothing labelled to catch.
- **Calibrated to 2019-20:** the limits, stress shocks and liquidity assumptions. The ADV figures are
  held at their 2019 levels across the whole history, so liquidity readings drift as a long run's NAV grows.
