"""Provider adapters. Two wire protocols cover almost every vendor, so no vendor SDK is needed.

`openai` speaks POST {base}/chat/completions, which OpenAI, Kimi, OpenRouter, DeepSeek, Qwen,
Mistral, Groq, Together, Ollama, vLLM and others all accept. `anthropic` speaks POST {base}/v1/messages.
Anything else with an OpenAI-compatible endpoint works through LLM_PROVIDER=custom and LLM_BASE_URL.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PRESETS: dict[str, dict] = {
    "openai":     {"protocol": "openai", "base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY", "token_param": "max_completion_tokens"},
    "anthropic":  {"protocol": "anthropic", "base_url": "https://api.anthropic.com", "key_env": "ANTHROPIC_API_KEY"},
    "kimi":       {"protocol": "openai", "base_url": "https://api.moonshot.ai/v1", "key_env": "MOONSHOT_API_KEY"},
    "openrouter": {"protocol": "openai", "base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY"},
    "deepseek":   {"protocol": "openai", "base_url": "https://api.deepseek.com/v1", "key_env": "DEEPSEEK_API_KEY"},
    "qwen":       {"protocol": "openai", "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "key_env": "DASHSCOPE_API_KEY"},
    "mistral":    {"protocol": "openai", "base_url": "https://api.mistral.ai/v1", "key_env": "MISTRAL_API_KEY"},
    "groq":       {"protocol": "openai", "base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY"},
    "ollama":     {"protocol": "openai", "base_url": "http://localhost:11434/v1", "key_env": ""},
    "custom":     {"protocol": "openai", "base_url": "", "key_env": ""},
}


class TransientError(RuntimeError):
    """Worth retrying: rate limits, server errors, dropped connections."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class PermanentError(RuntimeError):
    """Retrying cannot help: bad key, unknown model, malformed request."""


@dataclass
class Completion:
    text: str
    tokens_in: int
    tokens_out: int


def load_dotenv(path: Path) -> None:
    """Minimal .env reader so no extra dependency is needed. Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _post_json(url: str, headers: dict, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        if e.code == 429 or e.code >= 500:
            retry_after = e.headers.get("Retry-After")
            raise TransientError(f"HTTP {e.code}: {detail}",
                                 float(retry_after) if retry_after and retry_after.isdigit() else None) from e
        raise PermanentError(f"HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise TransientError(f"connection failed: {e}") from e
    except json.JSONDecodeError as e:
        raise TransientError(f"non-JSON response: {e}") from e


class OpenAICompatible:
    def __init__(self, name: str, base_url: str, api_key: str, model: str, token_param: str = "max_tokens",
                 temperature: float | None = None, timeout: float = 120.0):
        self.name, self.model = name, model
        self.base_url, self.api_key = base_url.rstrip("/"), api_key
        self.token_param, self.temperature, self.timeout = token_param, temperature, timeout

    def complete(self, messages: list[dict], max_tokens: int, meta: dict) -> Completion:
        body: dict = {"model": self.model, "messages": messages, self.token_param: max_tokens}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = _post_json(f"{self.base_url}/chat/completions", headers, body, self.timeout)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise TransientError(f"unexpected response shape: {str(data)[:200]}") from e
        usage = data.get("usage") or {}
        return Completion(text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


class AnthropicMessages:
    def __init__(self, name: str, base_url: str, api_key: str, model: str, temperature: float | None = None,
                 timeout: float = 120.0):
        self.name, self.model = name, model
        self.base_url, self.api_key = base_url.rstrip("/"), api_key
        self.temperature, self.timeout = temperature, timeout

    def complete(self, messages: list[dict], max_tokens: int, meta: dict) -> Completion:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        body: dict = {"model": self.model, "max_tokens": max_tokens, "system": system,
                      "messages": [m for m in messages if m["role"] != "system"]}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        data = _post_json(f"{self.base_url}/v1/messages", headers, body, self.timeout)
        try:
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        except (KeyError, TypeError) as e:
            raise TransientError(f"unexpected response shape: {str(data)[:200]}") from e
        usage = data.get("usage") or {}
        return Completion(text, usage.get("input_tokens", 0), usage.get("output_tokens", 0))


def _role_env(name: str, role: str | None) -> str | None:
    """LLM_MODEL_REVIEWER beats LLM_MODEL, so one role can run on a different model."""
    if role:
        value = os.environ.get(f"{name}_{role.upper()}")
        if value:
            return value
    return os.environ.get(name)


def build_provider(role: str | None = None):
    """Build the adapter chosen by LLM_PROVIDER, or None for the offline scripted backend."""
    name = (_role_env("LLM_PROVIDER", role) or "scripted").lower()
    if name == "scripted":
        return None
    if name not in PRESETS:
        raise PermanentError(f"unknown LLM_PROVIDER {name!r}; choose from scripted, {', '.join(PRESETS)}")
    preset = PRESETS[name]
    base_url = _role_env("LLM_BASE_URL", role) or preset["base_url"]
    model = _role_env("LLM_MODEL", role)
    api_key = _role_env("LLM_API_KEY", role) or os.environ.get(preset["key_env"] or "", "")
    if not model:
        raise PermanentError("LLM_MODEL is required when LLM_PROVIDER is not 'scripted'")
    if not base_url:
        raise PermanentError("LLM_BASE_URL is required for LLM_PROVIDER=custom")
    if not api_key and preset["key_env"]:
        raise PermanentError(f"set LLM_API_KEY or {preset['key_env']}")
    raw_temp = os.environ.get("LLM_TEMPERATURE")
    temperature = float(raw_temp) if raw_temp else None
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "120"))
    protocol = _role_env("LLM_PROTOCOL", role) or preset["protocol"]
    if protocol == "anthropic":
        return AnthropicMessages(name, base_url, api_key, model, temperature, timeout)
    token_param = os.environ.get("LLM_TOKEN_PARAM") or preset.get("token_param", "max_tokens")
    return OpenAICompatible(name, base_url, api_key, model, token_param, temperature, timeout)


def prices() -> tuple[float, float]:
    """USD per million input and output tokens, for the cost limit. Unset means cost reads as zero."""
    return (float(os.environ.get("LLM_PRICE_IN_PER_MTOK", "0")),
            float(os.environ.get("LLM_PRICE_OUT_PER_MTOK", "0")))
