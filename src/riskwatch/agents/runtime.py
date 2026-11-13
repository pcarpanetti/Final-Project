"""Provider-neutral agent loop. The model proposes; this harness validates and executes.

Tool use is plain JSON in the text channel rather than a vendor's function-calling API, so the same
loop works with any chat model.
"""
from __future__ import annotations

import json
import re


COMPACT = (",", ":")  # no padding spaces in the JSON sent to models: the same data in fewer tokens


class AgentFailed(RuntimeError):
    """The agent could not produce a valid result within its limits."""


def validate(value, schema: dict, path: str = "$") -> list[str]:
    """Small subset of JSON Schema: type, required, properties, items, enum."""
    errors: list[str] = []
    kind = schema.get("type")
    checks = {"object": dict, "array": list, "string": str}
    if kind in checks and not isinstance(value, checks[kind]):
        return [f"{path}: expected {kind}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in {schema['enum']}")
    if kind == "object":
        errors += [f"{path}.{k}: required" for k in schema.get("required", []) if k not in value]
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errors += validate(value[key], sub, f"{path}.{key}")
    if kind == "array" and "items" in schema:
        for i, item in enumerate(value):
            errors += validate(item, schema["items"], f"{path}[{i}]")
    return errors


def parse_reply(text: str) -> dict:
    """Accept the JSON object even when a model wraps it in fences or a sentence."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in reply")
    reply = json.loads(text[start:end + 1])
    if not isinstance(reply, dict):
        raise ValueError("reply is not a JSON object")
    return reply


def system_prompt(bundle: dict, role: str, legend: str = "") -> str:
    """Everything here is the same from day to day, so providers that cache a repeated prefix can reuse it."""
    spec = bundle["agents"]["roles"][role]
    parts = [bundle["prompts"][spec["prompt"]]]
    parts += [bundle["skills"][f"{s}/SKILL.md"] for s in spec.get("skills", [])]
    parts.append(f"Tools you may call: {', '.join(spec['tools']) or 'none'}.")
    parts.append(f"Your final output must satisfy this schema:\n{json.dumps(spec['output_schema'], indent=1)}")
    parts.append(bundle["agents"]["protocol"])
    parts += [legend] if legend else []
    return "\n\n".join(parts)


def run_agent(ctx, role: str, payload: dict, tools, legend: str = "") -> dict:
    """Run one role to completion. `ctx.complete` is journaled, so resuming replays finished calls."""
    spec = ctx.bundle["agents"]["roles"][role]
    retries = ctx.bundle["policy"]["retries"]
    messages = [
        {"role": "system", "content": system_prompt(ctx.bundle, role, legend)},
        {"role": "user", "content": json.dumps({"payload": payload}, sort_keys=True, ensure_ascii=False, separators=COMPACT)},
    ]
    repairs = tool_steps = 0
    while True:
        text = ctx.complete(role, messages, spec["max_tokens"])
        messages.append({"role": "assistant", "content": text})
        try:
            reply = parse_reply(text)
            action = reply.get("action")
            if action == "tool":
                tool_steps += 1
                if tool_steps > retries["max_tool_steps"]:
                    raise AgentFailed(f"{role} exceeded {retries['max_tool_steps']} tool steps")
                result = _call_tool(ctx, role, spec, reply, tools)
                messages.append({"role": "user", "content": json.dumps({"tool_result": result}, sort_keys=True, separators=COMPACT)})
                continue
            if action != "final":
                raise ValueError(f"unknown action {action!r}")
            errors = validate(reply.get("output"), spec["output_schema"])
            if errors:
                raise ValueError("; ".join(errors[:5]))
            return reply["output"]
        except (ValueError, json.JSONDecodeError) as e:
            repairs += 1
            ctx.event("agent_invalid_reply", {"role": role, "error": str(e), "repair": repairs})
            if repairs > retries["schema_repair"]:
                raise AgentFailed(f"{role} gave no valid reply after {repairs} attempts: {e}") from e
            messages.append({"role": "user", "content": f"Your reply was rejected: {e}. Reply again, following the protocol."})


def _call_tool(ctx, role: str, spec: dict, reply: dict, tools) -> dict:
    name = reply.get("tool")
    if name not in spec["tools"]:
        ctx.event("tool_denied", {"role": role, "tool": name})
        ctx.escalate("high", f"agent {role} requested forbidden tool {name}")
        return {"error": f"tool {name!r} is not permitted for this role"}
    ctx.event("tool_call", {"role": role, "tool": name})
    try:
        return {"result": tools.call(name, reply.get("args") or {})}
    except (KeyError, ValueError, TypeError) as e:
        return {"error": str(e)}
