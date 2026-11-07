"""Journaled, budgeted LLM calls. The controller owns this; agents only ever see text in and text out."""
from __future__ import annotations

import hashlib
import json
import random
import time

from .. import crash
from ..state import State
from .providers import Completion, PermanentError, TransientError, build_provider, prices
from .scripted import ScriptedProvider


class BudgetExceeded(RuntimeError):
    pass


class ProviderFailed(RuntimeError):
    """Retries are exhausted or the error is permanent; the stage's on_failure rule decides what happens."""


def request_hash(provider: str, model: str, messages: list[dict]) -> str:
    text = json.dumps([provider, model, messages], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LLMClient:
    def __init__(self, state: State, policy: dict, scripted_faults: dict | None = None, sleep=time.sleep):
        self.state, self.policy, self.sleep = state, policy, sleep
        self.scripted = ScriptedProvider(scripted_faults or {})
        self.providers: dict[str | None, object] = {}

    def provider_for(self, role: str | None):
        if role not in self.providers:
            self.providers[role] = build_provider(role) or self.scripted
        return self.providers[role]

    def describe(self) -> str:
        p = self.provider_for(None)
        return f"{p.name}:{p.model}"

    def check_budget(self, run_id: str, day: str, started_at: float) -> None:
        limits = self.policy["budgets"]["per_run"]
        used = self.state.llm_usage(run_id)
        if used["calls"] >= limits["max_llm_calls"]:
            raise BudgetExceeded(f"max_llm_calls {limits['max_llm_calls']} reached")
        if used["tokens"] >= limits["max_tokens"]:
            raise BudgetExceeded(f"max_tokens {limits['max_tokens']} reached")
        if used["cost"] >= limits["max_cost_usd"]:
            raise BudgetExceeded(f"max_cost_usd {limits['max_cost_usd']} reached")
        if time.time() - started_at >= limits["max_wall_seconds"]:
            raise BudgetExceeded(f"max_wall_seconds {limits['max_wall_seconds']} reached")
        day_cap = self.policy["budgets"]["per_day"]["max_cost_usd"]
        if self.state.llm_day_cost(day) >= day_cap:
            raise BudgetExceeded(f"per-day max_cost_usd {day_cap} reached")

    def complete(self, *, run_id: str, stage: str, role: str, messages: list[dict], max_tokens: int,
                 meta: dict, day: str, started_at: float) -> str:
        provider = self.provider_for(role)
        key = request_hash(provider.name, provider.model, messages)
        cached = self.state.llm_lookup(run_id, key)
        if cached is not None:
            self.state.event(run_id, stage, "llm_replayed", {"role": role})
            return cached

        self.check_budget(run_id, day, started_at)
        result = self._with_retries(provider, messages, max_tokens, meta, run_id, stage)
        price_in, price_out = prices()
        cost = (result.tokens_in * price_in + result.tokens_out * price_out) / 1e6
        crash.point(f"{stage}:llm_returned")
        self.state.llm_record(run_id, key, stage, role, provider.name, provider.model, result.text,
                              result.tokens_in, result.tokens_out, cost, day)
        self.state.event(run_id, stage, "llm_call", {"role": role, "provider": provider.name, "model": provider.model,
                                                     "tokens_in": result.tokens_in, "tokens_out": result.tokens_out})
        crash.point(f"{stage}:llm_journaled")
        return result.text

    def _with_retries(self, provider, messages, max_tokens, meta, run_id, stage) -> Completion:
        cfg = self.policy["retries"]["llm_transient"]
        for attempt in range(1, cfg["max_attempts"] + 1):
            try:
                return provider.complete(messages, max_tokens, meta)
            except PermanentError as e:
                self.state.event(run_id, stage, "llm_permanent_error", {"error": str(e)})
                raise ProviderFailed(str(e)) from e
            except TransientError as e:
                self.state.event(run_id, stage, "llm_transient_error", {"attempt": attempt, "error": str(e)})
                if attempt == cfg["max_attempts"]:
                    raise ProviderFailed(f"gave up after {attempt} attempts: {e}") from e
                delay = e.retry_after or min(cfg["max_seconds"], cfg["base_seconds"] * 2 ** (attempt - 1))
                self.sleep(delay * (0.5 + random.random() / 2))
        raise AssertionError("unreachable")
