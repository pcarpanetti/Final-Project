"""Draw docs/workflow_diagram.(png|svg) and, when replay evidence exists, docs/var_backtest.png."""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

INK, MUTED, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e4e3df"
CODE, AGENT, HUMAN = "#2a78d6", "#eb6834", "#1baf7a"
TINT = {CODE: "#e3eefb", AGENT: "#fde8df", HUMAN: "#dcf4ea"}


def box(ax, x, y, w, h, title, sub, kind):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.08", fc=TINT[kind], ec=kind, lw=1.6))
    ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center", fontsize=9.6, fontweight="bold", color=INK)
    ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=7.6, color=MUTED)


def arrow(ax, a, b, color=MUTED, style="-|>", rad=0.0, ls="-", lw=1.4):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=12, color=color, lw=lw, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=0, shrinkB=0))


def band(ax, x, y, w, h, label):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.1", fc="#f4f3f0", ec=GRID, lw=1))
    ax.text(x + 0.25, y + h - 0.13, label, ha="left", va="top", fontsize=8.8, fontweight="bold", color=MUTED)


def elbow(ax, start, gap_y, end):
    """Leave a box from its bottom, run along the gap between bands and the left gutter, enter from the left."""
    gutter = 0.32
    ax.plot([start[0], start[0], gutter, gutter], [start[1], gap_y, gap_y, end[1]], color=MUTED, lw=1.4)
    arrow(ax, (gutter, end[1]), end)


def note(ax, x, y, n):
    ax.text(x, y, str(n), ha="center", va="center", fontsize=8, fontweight="bold", color="white",
            bbox=dict(boxstyle="circle,pad=0.22", fc=INK, ec=INK))


def workflow_diagram() -> None:
    fig, ax = plt.subplots(figsize=(16, 13.1))
    ax.set_xlim(0, 16)
    ax.set_ylim(-0.5, 12.6)
    ax.axis("off")
    fig.patch.set_facecolor(SURFACE)
    ax.text(0.2, 12.35, "RiskWatch: daily risk monitoring workflow", fontsize=16, fontweight="bold", color=INK, va="center")
    ax.text(0.2, 12.02, "Agents judge inside a stage. The controller owns everything between stages. Every number comes from code.",
            fontsize=10, color=MUTED, va="center")

    bw, bh = 2.25, 0.82
    xs = [0.45, 3.05, 5.65, 8.25]

    # Triggers
    band(ax, 0.2, 10.55, 10.6, 1.1, "Triggers  (riskwatch tick, safe to call any time)")
    trig = [("Schedule", "20:00 trading days, catch-up"), ("New input", "late file, vendor correction"),
            ("Month end", "VaR model review"), ("Timer", "approval SLA 14h")]
    for x, (t, s) in zip(xs, trig):
        box(ax, x, 10.63, bw, 0.66, t, s, CODE)

    # Data
    band(ax, 0.2, 8.95, 10.6, 1.4, "1  Data: only what was known at the cutoff")
    y = 9.05
    box(ax, xs[0], y, bw, bh, "ingest", "point-in-time snapshot", CODE)
    box(ax, xs[1], y, bw, bh, "dq_checks", "gaps, outliers, repeats, notes", CODE)
    box(ax, xs[2], y, bw, bh, "dq_triage", "Data Steward: real or error?", AGENT)
    box(ax, xs[3], y, bw, bh, "dq_apply", "clean returns, overrides", CODE)

    # Risk
    band(ax, 0.2, 7.35, 10.6, 1.4, "2  Risk: deterministic, recomputed independently later")
    y = 7.45
    box(ax, xs[0], y, bw, bh, "risk_engine", "VaR, ES, beta, stress, liquidity", CODE)
    box(ax, xs[1], y, bw, bh, "limit_check", "9 limits: ok, warning, breach", CODE)
    box(ax, xs[2], y, bw, bh, "register", "breach register, VaR ledger", CODE)

    # Narrative loop
    band(ax, 0.2, 5.3, 10.6, 1.85, "3  Narrative: bounded revision loop, at most 3 rounds")
    y = 5.42
    box(ax, xs[0], y, bw, bh, "analyst", "Risk Analyst: findings + claims", AGENT)
    box(ax, xs[1], y, bw, bh, "writer", "Memo Writer: tokens, no digits", AGENT)
    box(ax, xs[2], y, bw, bh, "verify", "13 independent code checks", CODE)
    box(ax, xs[3], y, bw, bh, "reviewer", "Reviewer: memo + facts only", AGENT)

    # Release
    band(ax, 0.2, 3.7, 10.6, 1.4, "4  Release: nothing leaves without a record")
    y = 3.8
    box(ax, xs[0], y, bw, bh, "finalise_memo", "fills tokens, or template", CODE)
    box(ax, xs[1], y, bw, bh, "gate_policy", "needs a human? hash memo", CODE)
    box(ax, xs[2], y, bw, bh, "approval", "CRO: approve, reject, revise", HUMAN)
    box(ax, xs[3], y, bw, bh, "publish", "outbox, delivered exactly once", CODE)

    # Forward flow
    for row_y in (9.05, 7.45, 5.42, 3.8):
        n = 2 if row_y == 7.45 else 3
        for i in range(n):
            arrow(ax, (xs[i] + bw, row_y + bh / 2), (xs[i + 1], row_y + bh / 2))
    elbow(ax, (xs[0] + bw / 2, 10.63), 10.45, (xs[0], 9.05 + bh / 2))
    elbow(ax, (xs[3] + bw / 2, 9.05), 8.85, (xs[0], 7.45 + bh / 2))
    elbow(ax, (xs[2] + bw / 2, 7.45), 7.25, (xs[0], 5.42 + bh / 2))
    elbow(ax, (xs[3] + bw / 2, 5.42), 5.2, (xs[0], 3.8 + bh / 2))

    # Revision loop-back
    top = 6.42
    ax.plot([xs[3] + bw / 2, xs[3] + bw / 2], [5.42 + bh, top], color=AGENT, lw=1.6, ls="--")
    ax.plot([xs[2] + bw / 2, xs[2] + bw / 2], [5.42 + bh, top], color=AGENT, lw=1.6, ls="--")
    ax.plot([xs[3] + bw / 2, xs[0] + bw / 2], [top, top], color=AGENT, lw=1.6, ls="--")
    arrow(ax, (xs[0] + bw / 2, top), (xs[0] + bw / 2, 5.42 + bh), color=AGENT, ls="--", lw=1.6)
    ax.text(xs[3] + bw, top + 0.32, "failed checks and reviewer issues go back as feedback", fontsize=8, color=INK, ha="right")
    # Human change request
    arrow(ax, (xs[2] + 0.5, 3.8 + bh), (xs[1] + bw / 2, 5.42), color=HUMAN, ls="--", rad=0.15, lw=1.6)
    ax.text(6.3, 4.86, "human asks for changes", fontsize=7.8, color=INK, ha="left")

    # Controller panel
    band(ax, 11.0, 3.7, 4.8, 7.95, "Controller (harness): no agent can reach this")
    items = [
        ("Persistent state", "SQLite: runs, stages, approvals, breaches,\nledger, outbox, LLM journal, event log"),
        ("Checkpoints", "Each stage: outputs hashed, then one\ntransaction commits result + side effects"),
        ("Resume", "Re-run the same command. Finished stages\nskip, LLM calls replay, deliveries are not repeated"),
        ("Retries", "Transient: 4 tries with backoff\nBad reply: 2 repairs. Permanent: none"),
        ("Limits", "Per run: 30 calls, 200k tokens, $1, 15 min\nPer day: $5. Per agent: 6 tool steps"),
        ("Permissions", "Per-role tool allowlist, all read-only\nDenied call is logged and escalated"),
        ("Stop rules", "Lost agent = template memo + human\nCode error or no data = halt + escalate\n3 halts in a row = circuit breaker"),
    ]
    yy = 11.12
    for title, text in items:
        ax.text(11.2, yy, title, fontsize=9, fontweight="bold", color=INK, va="top")
        lines = text.count("\n") + 1
        ax.text(11.2, yy - 0.24, text, fontsize=8, color=MUTED, va="top", linespacing=1.3)
        yy -= 0.5 + 0.235 * lines

    # Improvement loop
    band(ax, 0.2, 1.5, 15.6, 2.0, "5  Improvement: a change goes live only through this path")
    y = 1.6
    w2 = 2.55
    px = [0.45, 3.4, 6.35, 9.3, 12.65]
    box(ax, px[0], y, w2, bh + 0.1, "Proposal", "Model Reviewer or a person", AGENT)
    box(ax, px[1], y, w2, bh + 0.1, "Frozen version", "config + prompts + skills, hashed", CODE)
    box(ax, px[2], y, w2, bh + 0.1, "Replay fixed window", "253 days, labelled faults, sandbox", CODE)
    box(ax, px[3], y, w2 + 0.4, bh + 0.1, "Pre-registered rules", "hard gates, guardrails, primary test", CODE)
    box(ax, px[4], y, w2 + 0.3, bh + 0.1, "Human promotes", "or rollback: one pointer change", HUMAN)
    for i in range(4):
        end = px[i] + (w2 + 0.4 if i == 3 else w2)
        arrow(ax, (end, y + 0.46), (px[i + 1], y + 0.46))
    ax.text(0.45, 2.92, "Fixed baseline scorecard: VaR coverage, fault handling, false overrides, leakage perturbation test, breach days, tokens. "
            "Every step is appended to versions/registry.jsonl; runs keep the version they started on.",
            fontsize=8.2, color=MUTED, va="center")

    # Notes
    note(ax, xs[2] + bw - 0.08, 9.05 + bh - 0.06, 1)
    note(ax, xs[2] + bw - 0.08, 7.45 + bh - 0.06, 2)
    note(ax, xs[1] + bw - 0.08, 5.42 + bh - 0.06, 3)
    note(ax, xs[3] + bw - 0.08, 5.42 + bh - 0.06, 4)
    note(ax, xs[2] + bw - 0.08, 3.8 + bh - 0.06, 5)
    note(ax, xs[3] + bw - 0.08, 3.8 + bh - 0.06, 6)

    # Key and annotations
    kx = 0.3
    for color, label in ((CODE, "Deterministic code"), (AGENT, "LLM agent"), (HUMAN, "Human")):
        ax.add_patch(FancyBboxPatch((kx, 1.12), 0.26, 0.18, boxstyle="round,pad=0,rounding_size=0.03", fc=TINT[color], ec=color, lw=1.4))
        ax.text(kx + 0.34, 1.21, label, fontsize=8.6, color=INK, va="center")
        kx += 1.9
    notes = [
        "1  Quarantined vendor text never reaches a model. A sharp move while peers also move escalates to a human; it is never zeroed.",
        "2  Facts are recorded before approval, so a pending sign-off never blocks the next day's numbers.",
        "3  The writer emits tokens such as {{m:var99_1d}}. A typed digit fails verification, so a figure cannot be mistyped or invented.",
        "4  The reviewer never sees drafts or analyst reasoning, and can run on a different vendor's model.",
        "5  Required for any breach, data override, new warning or degraded memo. Clean days archive automatically.",
        "6  The memo hash is checked again at publish, so what was approved is what goes out. The system never trades.",
    ]
    for i, text in enumerate(notes):
        ax.text(0.3, 0.9 - i * 0.26, text, fontsize=8.8, color=INK, va="center")

    fig.savefig(DOCS / "workflow_diagram.png", dpi=170, bbox_inches="tight", facecolor=SURFACE)
    fig.savefig(DOCS / "workflow_diagram.svg", bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def var_backtest() -> None:
    path = ROOT / "evidence" / "replay" / "var_ledger.csv"
    if not path.exists():
        return
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    rows = [r for r in rows if r["hit"] != ""]
    x = list(range(len(rows)))
    var = [float(r["var99"]) * 100 for r in rows]
    loss = [-float(r["next_return"]) * 100 for r in rows]
    hits = [i for i, r in enumerate(rows) if r["hit"] == "1"]

    fig, ax = plt.subplots(figsize=(11, 4.6))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.bar(x, loss, width=0.8, color=CODE, label="Next-day loss (gain below zero)")
    ax.plot(x, var, color=AGENT, lw=2, label="99% VaR forecast made the day before")
    ax.scatter(hits, [loss[i] for i in hits], s=70, facecolor=INK, edgecolor=SURFACE, linewidth=2, zorder=5,
               label=f"Exception ({len(hits)} in {len(rows)} days; {len(rows) * 0.01:.1f} expected)")
    ticks = [i for i, r in enumerate(rows) if i == 0 or r["as_of"][:7] != rows[i - 1]["as_of"][:7]]
    ax.set_xticks(ticks[::2], [rows[i]["as_of"][:7] for i in ticks[::2]], fontsize=9, color=MUTED)
    ax.tick_params(axis="y", labelsize=9, labelcolor=MUTED, length=0)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("% of NAV", fontsize=9, color=MUTED)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_title("Baseline VaR missed the 2020 sell-off: exceptions cluster within a few weeks", loc="left",
                 fontsize=12, fontweight="bold", color=INK, pad=26)
    ax.legend(frameon=False, fontsize=9, loc="lower left", bbox_to_anchor=(-0.01, 1.0), ncol=3, labelcolor=MUTED, handlelength=1.4)
    fig.savefig(DOCS / "var_backtest.png", dpi=170, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    DOCS.mkdir(exist_ok=True)
    workflow_diagram()
    var_backtest()
