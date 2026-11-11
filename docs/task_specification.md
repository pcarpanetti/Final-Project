# Task specification: daily portfolio risk monitoring

## The task

Every trading day, a risk team must work out how much risk a portfolio carries, whether any limit has been
crossed, why risk moved, and whether the data behind those answers can be trusted. It then has to tell the
right person before the next open. The job never finishes: today's report depends on yesterday's open breaches,
on a VaR model whose accuracy is only known in hindsight, and on vendor data that may be corrected days later.

**Intended user.** A risk analyst who prepares the report and a Chief Risk Officer (CRO) who signs it off, at a
small multi-asset manager. The portfolio manager and CIO read it.

**Scope note.** This is a study project. The manager, book, NAV and limits are fictional. The "current process"
below is a stylised account of how such a desk typically works, not a record of a specific employer.

## Current process

1. Around 18:00 an analyst downloads the vendor file and the administrator's positions.
2. They eyeball the data for gaps and odd prices, fixing problems by hand in a spreadsheet.
3. A spreadsheet or risk system produces VaR, exposures and stress results.
4. They compare results with limits, then search old emails to see which breaches were already open.
5. They write the commentary, and the CRO reads and signs it.
6. When the vendor corrects a price days later, someone may or may not notice. Each month someone counts VaR
   exceptions by hand.

The weak points are the ones this workflow targets: judgement calls leave no record, state lives in people's
heads and inboxes, corrections get missed, and nothing proves that a report used only what was known at the time.

## Stages and dependencies

| # | Stage | Depends on | Type |
|---|---|---|---|
| 1 | Ingest a point-in-time snapshot | Feed and positions published | Code |
| 2 | Data quality checks | 1 | Code |
| 3 | Triage flagged data (only if any) | 2 | Agent |
| 4 | Apply decisions, build clean returns | 3 | Code |
| 5 | Compute risk metrics | 4 | Code |
| 6 | Check limits | 5 | Code |
| 7 | Update breach register and VaR ledger | 6, and day T-1 at stage 7 | Code |
| 8 | Explain what changed | 7 | Agent |
| 9 | Draft the memo | 8 | Agent |
| 10 | Verify the draft | 9 | Code |
| 11 | Independent review | 10 passed | Agent |
| 12 | Finalise the memo (or template fallback) | 11 | Code |
| 13 | Decide whether approval is needed | 12 | Code |
| 14 | Human approval (when required) | 13 | Human |
| 15 | Publish through the outbox | 14 | Code |

Stages 8 to 11 form a revision loop of at most three rounds. Two more workflows reuse these stages: **restatement**
(1, 2, 4, 5, 6, a diff, then gate and publish) and **monthly model review** (backtest, Model Reviewer agent, gate,
publish). `config/workflows.yaml` is the definition the controller executes.

## Triggers

| Trigger | Type | Starts |
|---|---|---|
| 20:00 each trading day | Schedule | End-of-day run for that date |
| Any `tick` after downtime | Schedule, catching up | One run per missed date, each with its original cutoff |
| Vendor correction for a reported date | New input | Restatement run |
| Late or corrected file after a block | New input | The blocked run resumes, with the cutoff change logged |
| First business day of a month | Schedule | Monthly model review |
| Approval unanswered for 14 hours | Timer | Escalation to the backup approver |

## Inputs, permitted sources and information cutoffs

| Input | Source in this project | Available at |
|---|---|---|
| Daily sleeve returns | Ken French 10 Industry Portfolios, value-weighted, 1984 to September 2026 | 18:00 on T |
| Factor returns | Ken French 3 Factors, same range | 18:00 on T |
| Positions and NAV | Simulated administrator file; the fund launches with $100m the day before a workspace's first day | 18:30 on T |
| Vendor notes | Simulated, **untrusted** free text | As published |
| Limits, risk model, policy | `config/`, frozen in a version | Fixed per version |

**Permitted sources are these files and nothing else.** No agent has web access or any tool that reaches outside
its own run folder.

**Cutoff.** A run for date T sees only rows with `as_of <= T` and `published_at <=` the cutoff, which is 20:00 on T.
If data is late, the cutoff can be extended, but only by the controller, only up to the 23:30 deadline, and
always with a logged event. A correction published after the cutoff never changes the report already issued. It
starts a restatement instead. A VaR forecast made at T is scored only in the T+1 run.

## Work products and acceptance criteria

| Work product | Accepted when |
|---|---|
| Point-in-time snapshot and manifest | No input published after the cutoff; weights reconcile to 100% within 0.1% |
| Risk metrics and limit status | An independent pure-Python recomputation agrees within 1e-9; limits re-evaluate identically |
| Data quality decisions | Every exception decided; quarantined notes always escalated; reasons recorded |
| Breach register and VaR ledger | Updated exactly once per day, in the same transaction as the stage checkpoint |
| Daily risk memo | All 13 automated checks pass and the independent reviewer passes it. Otherwise a person sees it first: with the reviewer's open concerns attached, or as a marked template memo if a check still fails |
| Approval record | Every breach, data override or degraded memo has a named decision before release |
| Breach notice | Issued once, for each new hard breach, only after approval |
| Restatement notice | Issued when VaR moves by 5bp or more of NAV, or any limit status changes |
| Monthly model review | Kupiec, independence and Basel results computed by code; any proposal goes to the evaluation process |

## Why this needs a persistent workflow

A one-shot script could compute today's VaR. It could not do this job, because the job has these properties:

- **State outlives any single run.** Whether a breach is new or on day 40, and whether yesterday's forecast was
  exceeded, depend on earlier runs.
- **It waits for people and for data.** Approval can take hours, and a late file arrives when it arrives. A script
  would have to hold a process open or lose its place.
- **Inputs change after the fact.** A correction three days later has to find the run it affects and leave the
  original report intact.
- **Failure has consequences.** After a crash, repeating a publish sends the CRO a duplicate, repeating a register
  update double-counts a breach day, and repeating LLM calls costs money. Each action needs a record that it happened.
- **Its quality is only visible over time.** A VaR model is judged over hundreds of days, so a change has to be
  tested on a fixed history, recorded and reversible.
