---
name: breach-analysis
description: How to explain a limit breach or warning from risk metrics without inventing causes.
---

# Breach analysis

1. **Say what kind of event it is.** Use `breach_delta`: `new` needs the most explanation, `continuing` needs
   only what changed, and `resolved` needs one line.
2. **Separate book from market.** If `var99_change_positions` dominates, the book changed. If
   `var99_change_window` dominates, the market data changed, for example a large loss entering the window.
3. **Find the concentration.** `top_risk_asset` and the `ctr_*` metrics show which sleeve drives variance.
   Compare with the sleeve's weight: a variance share well above its weight means the sleeve is doing more
   than its size suggests.
4. **Stay inside the evidence.** "Risk rose because the largest loss in the window entered the sample" is
   supported. A statement about why markets fell is not, because nothing supplied says why.
5. **Respect the backtest.** If VaR exceptions are clustering, say the model may be understating risk. Do not
   present a limit that passes on a failing model as reassurance.
