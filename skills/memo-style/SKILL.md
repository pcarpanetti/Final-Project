---
name: memo-style
description: Required structure and tone of the daily risk memo.
---

# Memo style

Use exactly this skeleton:

```
# Daily Risk Memo: {{as_of}}

## Status
Overall status: {{status}}. One sentence on the day.

## Limits
- [L:var99] 1-day 99% VaR {{m:var99_1d}} against a hard limit of {{h:var99}}.

## Drivers
- [F:F1] The finding, in plain words.

## Data quality
- [DQ:outlier:Telcm] What was flagged and what was done.

## For decision
- What the Chief Risk Officer needs to decide today, or "Nothing today."
```

- Lead with the worst news. Breaches come before warnings.
- If a section has no items, write "None." Keep the heading.
- Describe options for the portfolio manager. Never give a trade instruction: this memo reports risk and
  does not manage the book.
- If the VaR backtest is outside the green zone, say so under Drivers.
- Short sentences. No adjectives without evidence.
