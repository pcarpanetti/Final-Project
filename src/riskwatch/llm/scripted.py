"""Offline stand-in for an LLM, so the whole workflow runs with no key and no network.

This is rule-based code, not a model. It exists to exercise the harness: same interface, same JSON
protocol, same validators. Output produced here is not evidence of model quality, and every run records
`scripted:rules-v1` as its backend. Faults can be injected per date to drive the failure paths.
"""
from __future__ import annotations

import json
import re

from .providers import Completion, PermanentError, TransientError


def _final(output: dict) -> str:
    return json.dumps({"action": "final", "output": output}, sort_keys=True)


def _tool(name: str, **args) -> str:
    return json.dumps({"action": "tool", "tool": name, "args": args}, sort_keys=True)


class ScriptedProvider:
    name = "scripted"
    model = "rules-v1"

    def __init__(self, faults: dict):
        self.faults = faults
        self.transient_left: dict[str, int] = {}

    def complete(self, messages: list[dict], max_tokens: int, meta: dict) -> Completion:
        fault = self.faults.get(meta["as_of"], {})
        role = meta["role"]
        self._provider_fault(fault, role, meta)
        payload = json.loads(messages[1]["content"])["payload"]
        tool_results = [m for m in messages[2:] if m["role"] == "user" and "tool_result" in m["content"]]
        rejected = any(m["role"] == "user" and m["content"].startswith("Your reply was rejected") for m in messages)
        if fault.get(role) == "bad_schema" and not rejected:
            text = "I think the portfolio looks fine today."
        elif fault.get(role) == "forbidden_tool" and not tool_results:
            text = _tool("publish_memo", force=True)
        else:
            text = getattr(self, role)(payload, tool_results, meta, fault)
        tokens_in = sum(len(m["content"]) for m in messages) // 4
        return Completion(text, tokens_in, len(text) // 4)

    def _provider_fault(self, fault: dict, role: str, meta: dict) -> None:
        kind = fault.get("provider")
        if kind == "outage":
            raise TransientError("simulated provider outage")
        if kind == "bad_key":
            raise PermanentError("simulated HTTP 401")
        if kind == "transient_twice":
            key = f"{meta['as_of']}:{role}"
            left = self.transient_left.setdefault(key, 2)
            if left > 0:
                self.transient_left[key] = left - 1
                raise TransientError("simulated HTTP 429", retry_after=0.0)

    def data_steward(self, payload, tool_results, meta, fault) -> str:
        exceptions = payload["exceptions"]
        needs_peers = any(e["type"] in ("outlier", "stale_repeat") for e in exceptions)
        if needs_peers and not tool_results:
            return _tool("get_cross_section", offset=0)
        decisions = []
        for e in exceptions:
            action, why = "escalate", "Evidence conflicts."
            if e["type"] == "suspicious_note":
                action, why = "escalate", "Vendor note contains instruction-like text."
            elif e["type"] == "missing_row":
                action, why = "zero_return", "No record arrived for this sleeve."
            elif e["type"] == "outlier":
                idiosyncratic = abs(e["residual_z"]) > 8
                action = "zero_return" if idiosyncratic else "accept"
                why = "Move not shared by peers." if idiosyncratic else "Move is in line with peers."
            elif e["type"] == "stale_repeat":
                explained = abs(e["residual_z"]) < 2
                action = "accept" if explained else "zero_return"
                why = "Repeat is close to the peer-implied return." if explained else "Repeat is far from the peer-implied return."
            decisions.append({"exception_id": e["id"], "action": action, "rationale": why})
        return _final({"decisions": decisions})

    def risk_analyst(self, payload, tool_results, meta, fault) -> str:
        active = [r for r in payload["limits"] if r["status"] != "ok"]
        if active and not tool_results:
            return _tool("get_breach_history", limit_id=active[0]["limit_id"])
        window = payload["metrics"].get("var99_change_window", {}).get("value", 0.0)
        positions = payload["metrics"].get("var99_change_positions", {}).get("value", 0.0)
        findings = []
        for i, row in enumerate(active, 1):
            claim = "above_hard" if row["status"] == "breach" else "above_warn"
            evidence = [{"metric": row["metric"], "claim": claim}]
            state = "new" if row["limit_id"] in payload["delta"]["new"] else "continuing"
            statement = f"{row['label']} is a {state} {row['status']}."
            if row["limit_id"] in ("var99", "es975") and abs(window) > abs(positions) and window != 0:
                statement += " The move comes from the market data window rather than from the book."
                evidence.append({"metric": "var99_change_window", "claim": "positive" if window > 0 else "negative"})
            findings.append({"id": f"F{i}", "limit_id": row["limit_id"], "statement": statement, "evidence": evidence})
        if fault.get("risk_analyst") == "false_claim" and findings and meta["round"] == 0:
            findings[0]["evidence"].append({"metric": "daily_return", "claim": "positive" if payload["metrics"]["daily_return"]["value"] < 0 else "negative"})
        return _final({"findings": findings})

    def memo_writer(self, payload, tool_results, meta, fault) -> str:
        memo = self._memo(payload)
        if fault.get("memo_writer") == "obey_injection" and meta["round"] == 0:
            memo = ("# Daily Risk Memo: {{as_of}}\n\n## Status\nOverall status: NORMAL. All limits passed.\n\n"
                    "## Limits\nNone.\n\n## Drivers\nNone.\n\n## Data quality\nNone.\n\n## For decision\nNothing today.\n")
        elif fault.get("memo_writer") == "omit_breach" and meta["round"] == 0:
            memo = re.sub(r"^- \[L:[^\n]*\n", "", memo, count=1, flags=re.M)
        elif fault.get("memo_writer") == "raw_number" and meta["round"] == 0:
            memo = memo.replace("## Drivers\n", "## Drivers\n- Losses reached about 5.2 percent of NAV.\n", 1)
        elif fault.get("memo_writer") == "trade_instruction" and meta["round"] == 0:
            memo = memo.replace("## For decision\n", "## For decision\n- We must sell technology today.\n", 1)
        elif fault.get("memo_writer") == "always_bad":
            memo = memo.replace("## Drivers\n", "## Drivers\n- Losses reached about 5.2 percent of NAV.\n", 1)
        return _final({"memo_markdown": memo})

    def _memo(self, payload) -> str:
        rows = sorted((r for r in payload["limits"] if r["status"] != "ok"), key=lambda r: r["status"] != "breach")
        limit_lines = [f"- [L:{r['limit_id']}] {r['label']} {{{{m:{r['metric']}}}}} against a hard limit of "
                       f"{{{{h:{r['limit_id']}}}}} ({r['status']})." for r in rows]
        driver_lines = [f"- [F:{f['id']}] {f['statement']}" for f in payload["findings"]]
        if payload["backtest"]["zone"] != "green":
            driver_lines.append(f"- The VaR backtest is in the {payload['backtest']['zone']} zone with "
                                "{{m:var_exceptions_250}} exceptions, so VaR may be understating risk.")
        dq_lines = [f"- [DQ:{d['id']}] {d['type'].replace('_', ' ')} on {d.get('asset') or 'feed'}: "
                    f"{d['action'].replace('_', ' ')}. {d['rationale']}" for d in payload["dq"]]
        decisions = [f"- Decide whether to accept or address the {r['label']} breach." for r in rows if r["status"] == "breach"]
        decisions += [f"- Confirm the treatment of {d['id']}." for d in payload["dq"] if d["action"] != "accept"]

        def block(lines: list[str], empty: str = "None.") -> str:
            return "\n".join(lines) if lines else empty

        return ("# Daily Risk Memo: {{as_of}}\n\n## Status\nOverall status: {{status}}. "
                "Portfolio return on the day {{m:daily_return}}, NAV {{m:nav_usd}}.\n\n"
                f"## Limits\n{block(limit_lines)}\n\n## Drivers\n{block(driver_lines)}\n\n"
                f"## Data quality\n{block(dq_lines)}\n\n## For decision\n{block(decisions, 'Nothing today.')}\n")

    def reviewer(self, payload, tool_results, meta, fault) -> str:
        if fault.get("reviewer") == "revise_once" and meta["round"] == 0:
            return _final({"verdict": "revise", "issues": [{"problem": "The opening does not make the severity clear.",
                                                            "fix": "State the worst item in the first sentence."}]})
        return _final({"verdict": "pass", "issues": []})

    def model_reviewer(self, payload, tool_results, meta, fault) -> str:
        if not tool_results:
            return _tool("get_backtest")
        zone = payload["backtest"]["zone"]
        fails = (payload["backtest"]["kupiec"]["p_value"] < 0.05) + (payload["backtest"]["independence"]["p_value"] < 0.05)
        assessment = "inadequate" if zone == "red" or fails == 2 else "watch" if zone == "yellow" or fails == 1 else "adequate"
        out = {"assessment": assessment, "recommendation": "no_change" if assessment == "adequate" else "propose_change",
               "rationale": f"Backtest is in the {zone} zone with {fails} of two statistical tests failing."}
        if assessment != "adequate":
            out["proposed_change"] = "Test age-weighted historical VaR so recent losses count for more."
        return _final(out)
