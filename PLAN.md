# Pre-submission plan (handoff)

Work agreed with the user (Pablo Carpanetti) on 2026-11-12, not yet started. Do the steps in order and commit after each
one. Ask the user before step 4, which is optional.

## Context you need first

- **Course brief:** `final_project.pdf`. It is Git-ignored and stays out of the ZIP. The ZIP must be named
  `studentID-final-project.zip`, must contain the full `.git/`, and the final changes must be committed.
- **The user wants the browser app to be the main way in.** Every feature must work through the web app (`start.bat`,
  `src/riskwatch/web/`) and be described in `GETTING_STARTED.md`. The CLI is secondary.
- **The LLM layer must stay provider-agnostic**, and the offline `scripted` backend stays the default.
- **The portfolio is fixed today.** `scripts/build_feed.py:18` defines `TARGET` weights for 10 sleeves and
  rebalances monthly (lines 72-83). It writes a single committed `data/feed/positions.csv`, and the
  `bad_weight_scale` faults are injected into that file. `PointInTimeStore(feed_dir)` (`src/riskwatch/pit.py:29`) reads it. It is
  built from `paths.data` in `controller.py:42`, separately in `web/server.py:77`, and in `improve/evaluate.py:109`.
  `stages/pipeline.py:119-124` rebases NAV to `LAUNCH_NAV` at `book_launch()`, the day before the
  workspace's `book_start`.
- **The limits in `config/limits.yaml` are calibrated to the default book.** For example, the single-sleeve warning is
  24.5% and HiTec targets 24%.
- **Faults and drills exist only in the window** `scenarios/replay.yaml` → `window`, July 2019 to June 2020. The web
  app exposes this as `catalog.drill_window`.
- **Tests:** `python -m pytest -q` takes about 2 minutes. The browser check is `scripts/browser_check.py`.
- **`scripts/package_submission.py` refuses to run on a dirty tree.** Commit this file or delete it before packaging.

## 1. Fix the ZIP name (done)

The user chose `25210660154-PabloCarpanetti-FinalProject.zip`, overriding the brief's `studentID-final-project.zip`.
`scripts/package_submission.py` builds that name. Don't delete the old ZIP in the parent folder without asking.

## 2a. Simplify the Run setup page

All of this is in `pageRun()` in `src/riskwatch/web/static/app.js`, around lines 340-425.
- **Dates:** show From and To date inputs all the time. The default is 2020-02-18 to 2020-03-13. If the workspace has
  results, pre-fill From with `summary.continue_from`.
- **Shortcuts:** replace the 8 `PERIODS` cards with three text shortcuts that fill in the dates:
  - Crash month: 2020-02-18 to 2020-03-13
  - Full test year: 2019-07-01 to 2020-06-30
  - Black Monday 1987: 1987-10-01 to 1987-10-30

  Remove Quick look, the first half of 2020, 2008 and 2022. List them in `GETTING_STARTED.md` as dates worth trying.
- **Fault line:** add one line under the dates: "Includes the labelled vendor faults and drills" or "Clean market data
  only", using `hasDrills()`.
- **Drills checkbox:** remove it. Send `drills: offline && hasDrills(start, end)`. Nothing changes on the server side.
- **Approvals:** keep both options ("I review breach days" and "Approve automatically") as a compact two-option switch.
- **Workspace notices:** cut each one to a single sentence. Keep the "Start over and run" behaviour.

## 2b. Let the user set the portfolio

Add a "Portfolio" card on the same page.
- **Fields:** target weight per sleeve, non-negative and summing to 100% (show the running total), a starting NAV
  (default $100m), and rebalancing: monthly, quarterly or none. There is also an optional list of "from date X, new
  targets" entries, so a user can change holdings mid-period. Default to the current `TARGET` book.
- **Per-workspace positions:**
  - Factor the drift and rebalance logic out of `build_feed.py` into a shared function.
  - When a run starts with a custom book, write that workspace's `positions.csv` (same columns, clean,
    `vendor_seq=1`) into the workspace's runtime folder, and point the controller's store at it. The other feed files
    can stay shared.
  - Save the book definition with the workspace, like `book_start`.
  - Leave the committed `data/feed/positions.csv` byte-identical.
- **Changing the book:** do this only through "Start over", the same as an earlier start date.
- **Evaluation:** `riskwatch eval` and the baseline always use the default book. Say so in the UI and the docs. Also say
  that the limits, stress shocks and ADV are calibrated to the default book.
- **Pass the book through:** add a `--book <json>` option (or similar) to `riskwatch replay`/`init` in `cli.py`, and pass
  it through `api_start_run` (`web/server.py:359`).
- **Tests:**
  - custom weights reconcile to 100%
  - cutoffs still hold
  - a custom book changes the metrics
  - the default book and evaluation baseline are unchanged
  - the server rejects weights that are negative or don't sum to 100%

## 3. Refresh stale evidence

`evidence/README.md` ("What was not tested") says the four candidates in `eval/candidates/` were scored before the
last harness fixes.
- Re-run `riskwatch eval --candidate <file>` for each. Each takes about 5 minutes.
- Run `scripts/recheck_baseline.py`.
- Update `eval/results/`, the evidence README and the design note's section 4 if the numbers moved.
- Remove that caveat once it no longer applies.

## 4. Optional: P&L materiality for restatements (ask the user first)

Restatement materiality only looks at VaR moving 5bp or more, or a limit status changing. The 2020-04-08 correction
moved the reported return by 26bp and produced no notice.
- Add a P&L threshold as a new candidate.
- Evaluate it, then promote and version it if it passes.
- Document the cycle in the evidence and the design note.

## 5. Final pass

- Run the full `pytest` and `scripts/browser_check.py`.
- Retake the affected screenshots in `docs/screens/`, at least `2-run-setup.png`.
- Update `GETTING_STARTED.md` (the Run step and the portfolio) and `README.md` (the walkthrough and honest limits, now
  that the book is configurable).
- Delete or commit this file.
- Commit, then run `scripts/package_submission.py`.
