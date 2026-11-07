"""Wire-level tests of the adapters against a local HTTP server. No real vendor is contacted."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from conftest import eod
from riskwatch.llm.providers import PRESETS, AnthropicMessages, OpenAICompatible, PermanentError, TransientError, build_provider


class FakeVendor(BaseHTTPRequestHandler):
    """Speaks just enough of both protocols, and records what it receives."""
    requests: list = []
    script: list = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeVendor.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
        status, payload, extra = FakeVendor.script.pop(0) if FakeVendor.script else self.default(body)
        data = json.dumps(payload).encode()
        self.send_response(status)
        for k, v in extra.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def default(self, body):
        reply = '{"action": "final", "output": {"ok": true}}'
        if self.path.endswith("/chat/completions"):
            return 200, {"choices": [{"message": {"content": reply}}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}, {}
        return 200, {"content": [{"type": "text", "text": reply}], "usage": {"input_tokens": 7, "output_tokens": 3}}, {}


@pytest.fixture
def server():
    FakeVendor.requests, FakeVendor.script = [], []
    httpd = HTTPServer(("127.0.0.1", 0), FakeVendor)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
META = {"role": "t", "as_of": "", "round": 0}


def test_openai_wire_format(server):
    p = OpenAICompatible("custom", f"{server}/v1", "key-123", "some-model")
    out = p.complete(MESSAGES, 100, META)
    req = FakeVendor.requests[0]
    assert req["path"] == "/v1/chat/completions"
    assert req["headers"]["Authorization"] == "Bearer key-123"
    assert req["body"]["model"] == "some-model" and req["body"]["messages"] == MESSAGES
    assert req["body"]["max_tokens"] == 100 and "temperature" not in req["body"]
    assert (out.tokens_in, out.tokens_out) == (7, 3)


def test_newer_openai_models_get_the_renamed_token_parameter(server):
    OpenAICompatible("openai", f"{server}/v1", "k", "m", token_param="max_completion_tokens").complete(MESSAGES, 100, META)
    body = FakeVendor.requests[0]["body"]
    assert body["max_completion_tokens"] == 100 and "max_tokens" not in body


def test_anthropic_wire_format(server):
    p = AnthropicMessages("anthropic", server, "key-123", "some-model")
    out = p.complete(MESSAGES, 100, META)
    req = FakeVendor.requests[0]
    assert req["path"] == "/v1/messages"
    assert req["headers"]["X-Api-Key"] == "key-123" and req["headers"]["Anthropic-Version"] == "2023-06-01"
    assert req["body"]["system"] == "sys" and req["body"]["messages"] == [MESSAGES[1]]
    assert out.text.startswith('{"action"')


@pytest.mark.parametrize("status,error", [(429, TransientError), (500, TransientError), (503, TransientError),
                                          (400, PermanentError), (401, PermanentError), (404, PermanentError)])
def test_status_codes_are_classified(server, status, error):
    FakeVendor.script.append((status, {"error": "x"}, {}))
    with pytest.raises(error):
        OpenAICompatible("custom", server, "k", "m").complete(MESSAGES, 10, META)


def test_retry_after_header_is_read(server):
    FakeVendor.script.append((429, {}, {"Retry-After": "7"}))
    with pytest.raises(TransientError) as e:
        OpenAICompatible("custom", server, "k", "m").complete(MESSAGES, 10, META)
    assert e.value.retry_after == 7.0


def test_unreachable_host_is_transient():
    with pytest.raises(TransientError):
        OpenAICompatible("custom", "http://127.0.0.1:9", "k", "m", timeout=2).complete(MESSAGES, 10, META)


@pytest.mark.parametrize("name", sorted(set(PRESETS) - {"custom"}))
def test_every_preset_builds_from_environment_variables(monkeypatch, name):
    monkeypatch.setenv("LLM_PROVIDER", name)
    monkeypatch.setenv("LLM_MODEL", "any-model")
    monkeypatch.setenv("LLM_API_KEY", "k")
    p = build_provider()
    assert p.name == name and p.model == "any-model" and p.base_url.startswith("http")
    assert isinstance(p, AnthropicMessages) == (name == "anthropic")


def test_any_openai_compatible_endpoint_works_through_custom(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "m")
    assert build_provider().base_url == "https://llm.example.com/v1"


def test_vendor_specific_key_variable_is_accepted(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "kimi")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("MOONSHOT_API_KEY", "secret")
    assert build_provider().api_key == "secret"


def test_one_role_can_run_on_a_different_vendor(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "main-model")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_PROVIDER_REVIEWER", "anthropic")
    monkeypatch.setenv("LLM_MODEL_REVIEWER", "review-model")
    assert build_provider("reviewer").name == "anthropic"
    assert build_provider("reviewer").model == "review-model"
    assert build_provider("memo_writer").name == "openai"


@pytest.mark.parametrize("missing,message", [("LLM_MODEL", "LLM_MODEL"), ("LLM_API_KEY", "OPENAI_API_KEY")])
def test_missing_settings_fail_with_a_clear_message(monkeypatch, missing, message):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv(missing)
    with pytest.raises(PermanentError, match=message):
        build_provider()


def test_unset_provider_means_offline_scripted():
    assert build_provider() is None


@pytest.mark.parametrize("protocol", ["openai", "anthropic"])
def test_full_run_through_a_real_http_provider(protocol, server, monkeypatch, make_env, paths):
    """A whole workflow over HTTP, with a fake vendor that always answers badly.

    The harness must survive a model it cannot trust: bad replies degrade to the template memo.
    """
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_PROTOCOL", protocol)
    monkeypatch.setenv("LLM_BASE_URL", server)
    monkeypatch.setenv("LLM_MODEL", "fake")
    monkeypatch.setenv("LLM_API_KEY", "k")
    env = make_env()
    _, run_id, status = eod(env, "2020-03-16")
    assert status == "awaiting_approval"
    assert env.state.run(run_id)["degraded"] == 1
    assert env.state.run(run_id)["llm"] == "custom:fake"
    assert FakeVendor.requests
    assert "[L:var99]" in (paths.artifacts / run_id / "memo_final.md").read_text(encoding="utf-8")
