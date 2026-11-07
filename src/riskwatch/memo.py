"""Turn memo drafts into final text. Figures come only from artifacts, through tokens."""
from __future__ import annotations

import re

TOKEN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def format_value(value, unit: str) -> str:
    if unit == "pct":
        return f"{value * 100:.2f}%"
    if unit == "usd":
        return f"${value / 1e6:,.1f}m"
    if unit == "days":
        return f"{value:.1f} days"
    if unit == "count":
        return str(int(value))
    if unit == "ratio":
        return f"{value:.2f}"
    return str(value)


def limit_unit(limit: dict, metrics: dict) -> str:
    return metrics[limit["metric"]]["unit"]


def resolve_token(token: str, metrics: dict, limits: dict, as_of: str, status: str) -> str:
    """Return the text for one token, or raise KeyError if it does not exist."""
    if token == "as_of":
        return as_of
    if token == "status":
        return status
    kind, _, ref = token.partition(":")
    if kind == "m":
        m = metrics[ref]
        return format_value(m["value"], m["unit"])
    if kind in ("h", "w"):
        lim = limits[ref]
        return format_value(lim["hard" if kind == "h" else "warn"], limit_unit(lim, metrics))
    raise KeyError(token)


def resolve(draft: str, metrics: dict, limits: dict, as_of: str, status: str) -> str:
    return TOKEN.sub(lambda m: resolve_token(m.group(1), metrics, limits, as_of, status), draft)


def template_memo(as_of: str, status: str, metrics: dict, limit_rows: list[dict], dq: list[dict],
                  reason: str) -> str:
    """Numbers-only fallback used when the agents are unavailable or could not pass review."""
    lines = [f"# Daily Risk Memo: {as_of}", "",
             "> Degraded memo: generated from a fixed template without analyst commentary.",
             f"> Reason: {reason}", "", "## Status",
             f"Overall status: {status}. Portfolio return on the day "
             f"{format_value(metrics['daily_return']['value'], 'pct')}, "
             f"NAV {format_value(metrics['nav_usd']['value'], 'usd')}.", "", "## Limits"]
    active = sorted((r for r in limit_rows if r["status"] != "ok"), key=lambda r: r["status"] != "breach")
    for r in active:
        unit = metrics[r["metric"]]["unit"]
        lines.append(f"- [L:{r['limit_id']}] {r['label']} {format_value(r['value'], unit)} against a hard limit of "
                     f"{format_value(r['hard'], unit)} ({r['status']}).")
    lines += ([] if active else ["None."]) + ["", "## Drivers", "Not available in degraded mode.", "", "## Data quality"]
    lines += [f"- [DQ:{d['id']}] {d['type'].replace('_', ' ')} on {d.get('asset') or 'feed'}: "
              f"{d['action'].replace('_', ' ')}." for d in dq] or ["None."]
    lines += ["", "## For decision", "- Review this degraded memo and the escalation that caused it.", ""]
    return "\n".join(lines)
