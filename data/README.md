# Data

`raw/` holds a small window (2017-01-03 to 2020-06-30) of two public datasets from the
[Kenneth R. French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html),
CRSP vintage 202609, copyright Eugene F. Fama and Kenneth R. French. Returns are in percent.

| File | Source dataset |
|---|---|
| `raw/ff_industry10_vw_daily_pct.csv` | 10 Industry Portfolios, daily, value-weighted |
| `raw/ff_factors_daily_pct.csv` | Fama/French 3 Factors, daily |

`feed/` is generated from `raw/` by `scripts/build_feed.py` and is what the workflow reads.
It turns the static history into a **bitemporal vendor feed**: every row has both the date it
describes (`as_of`) and the time it became known (`published_at`).

What is real and what is not:

- **Real:** all market returns, except the handful of rows listed in `faults.yaml`.
- **Fictional:** the portfolio, its NAV, target weights and limits. The ten industry portfolios
  stand in for ten investable sleeves. No client or employer data is used.
- **Injected:** the vendor faults in `faults.yaml`. They exist so the evaluation has labelled
  ground truth. Only `build_feed.py` and the evaluation harness read that file; a test checks
  that no production stage does.
