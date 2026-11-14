"""The web app, tested over real HTTP against a real server. Runs use the offline backend."""
import io
import json
import shutil
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import zipfile

import pytest

from riskwatch.llm import providers
from riskwatch.llm.providers import ClaudeCodeCLI, PermanentError, TransientError
from riskwatch.web.server import make_server


class Client:
    def __init__(self, port, token):
        self.base, self.token = f"http://127.0.0.1:{port}", token

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=30) as r:
            return json.loads(r.read())

    def raw(self, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read(), dict(r.headers)

    def post(self, path, body=None, token="use-real", headers=None):
        hdrs = {"Content-Type": "application/json", "X-RiskWatch-Token": self.token if token == "use-real" else token, **(headers or {})}
        req = urllib.request.Request(self.base + path, data=json.dumps(body or {}).encode(), headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except json.JSONDecodeError:
                return e.code, {"error": raw.decode()}


@pytest.fixture
def web(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    server, app = make_server(tmp_path / "ws", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = Client(server.server_address[1], app.token)
    client.app = app
    yield client
    app.stop_job()
    server.shutdown()
    server.server_close()


def connect_offline(web):
    assert web.post("/api/settings", {"name": "Test Approver", "provider": "scripted"})[0] == 200


def run_to_end(web, start="2020-03-16", end="2020-03-17", approvals="manual", drills=False, book=None):
    code, job = web.post("/api/start", {"start": start, "end": end, "approvals": approvals, "drills": drills, "book": book})
    assert code == 200, job
    deadline = time.time() + 120
    while time.time() < deadline:
        state = web.get("/api/summary")["job"]
        if state["state"] != "running":
            return state
        time.sleep(0.3)
    raise AssertionError("run did not finish")


def wait_for(fn, seconds=30):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if fn():
            return
        time.sleep(0.2)
    raise AssertionError("condition not met")


def test_page_and_assets_are_served_with_a_session_token(web):
    status, body, headers = web.raw("/")
    assert status == 200 and web.token.encode() in body
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert web.raw("/app.js")[0] == 200 and web.raw("/styles.css")[0] == 200


def test_no_external_resources_are_loaded(web):
    for name in ("/", "/app.js", "/styles.css"):
        text = web.raw(name)[1].decode()
        assert "https://cdn" not in text and "<script src=\"http" not in text


def test_post_without_the_token_is_refused(web):
    assert web.post("/api/settings", {"provider": "scripted"}, token="wrong")[0] == 403
    assert web.post("/api/stop", token="")[0] == 403
    assert web.get("/api/summary")["settings"]["configured"] is False


def test_unknown_host_header_is_refused_to_stop_dns_rebinding(web):
    with pytest.raises(urllib.error.HTTPError) as e:
        web.raw("/api/summary", {"Host": "evil.example.com"})
    assert e.value.code == 403
    assert web.post("/api/stop", headers={"Host": "evil.example.com"})[0] == 403


def test_a_second_server_cannot_take_a_port_that_is_in_use(web, tmp_path):
    """Regression: on Windows a second server bound the same port, said it was running, and got no requests."""
    from riskwatch.web.server import PortInUse, make_server
    with pytest.raises(PortInUse):
        make_server(tmp_path / "second", web.app.port)


def test_a_startup_error_is_not_misreported_as_a_busy_port(tmp_path, monkeypatch):
    """Regression: every OSError, such as a missing data file, used to be reported as "port in use"."""
    from riskwatch.web import server as web_server
    monkeypatch.setattr(web_server, "PointInTimeStore", lambda *a: (_ for _ in ()).throw(FileNotFoundError("feed")))
    with pytest.raises(FileNotFoundError):
        web_server.make_server(tmp_path / "ws", 0)


def test_server_listens_only_on_loopback(web):
    assert web.app.port and web.base.startswith("http://127.0.0.1")


def test_api_key_is_never_returned_and_never_written_to_settings(web):
    secret = "sk-test-abcdefghijklmnop-1234"
    web.post("/api/settings", {"name": "T", "provider": "openai", "model": "m", "api_key": secret})
    summary = web.raw("/api/summary")[1].decode()
    assert secret not in summary and '"has_key": true' in summary and "...1234" in summary
    saved = (web.app.workspace / "settings.json").read_text(encoding="utf-8")
    assert secret not in saved


def test_saved_key_is_kept_when_the_form_sends_it_blank(web):
    web.post("/api/settings", {"name": "T", "provider": "openai", "model": "m", "api_key": "sk-keepme-123456"})
    web.post("/api/settings", {"name": "T", "provider": "openai", "model": "m2", "api_key": ""})
    assert web.app.keys["api_key"] == "sk-keepme-123456"


def test_run_needs_a_connected_model_and_a_valid_period(web):
    assert web.post("/api/start", {"start": "2020-03-16", "end": "2020-03-17"})[0] == 400
    connect_offline(web)
    assert web.post("/api/start", {"start": "2030-01-01", "end": "2030-01-02"})[0] == 400
    assert web.post("/api/start", {"start": "1985-12-02", "end": "1985-12-06"})[0] == 400
    assert web.post("/api/start", {"start": "2026-09-28", "end": "2026-10-30"})[0] == 400


def test_catalog_offers_1986_to_2026_and_says_where_the_drills_are(web):
    catalog = web.get("/api/catalog")
    assert (catalog["first_day"], catalog["last_day"]) == ("1986-01-02", "2026-09-30")
    assert catalog["drill_window"] == {"start": "2019-07-01", "end": "2020-06-30"}


def test_a_historical_period_runs_in_the_app(web):
    connect_offline(web)
    assert run_to_end(web, "1987-10-16", "1987-10-20", approvals="auto")["state"] == "finished"
    assert set(web.get("/api/summary")["counts"]) == {"completed"}


def test_a_period_that_would_leave_a_gap_needs_a_fresh_workspace(web):
    """Otherwise the scheduler would quietly catch up every day in between."""
    connect_offline(web)
    run_to_end(web, approvals="auto")
    summary = web.get("/api/summary")
    assert summary["continue_from"] == "2020-03-18"
    code, body = web.post("/api/start", {"start": "2022-01-03", "end": "2022-01-05", "approvals": "auto"})
    assert code == 400 and "2020-03-18" in body["error"]
    assert web.post("/api/start-over")[0] == 200
    assert run_to_end(web, "2022-01-03", "2022-01-05", approvals="auto")["state"] == "finished"
    assert sorted(r["as_of"] for r in web.get("/api/runs")["runs"] if r["workflow"] == "eod") == ["2022-01-03", "2022-01-04", "2022-01-05"]


HALF_AND_HALF = {"NoDur": 0.5, "Durbl": 0, "Manuf": 0, "Enrgy": 0, "HiTec": 0, "Telcm": 0, "Shops": 0, "Hlth": 0.5, "Utils": 0, "Other": 0}


def test_the_app_runs_your_own_portfolio_and_keeps_it(web):
    connect_offline(web)
    catalog = web.get("/api/catalog")["book"]
    assert [a for a, _ in catalog["sleeves"]][:2] == ["NoDur", "Durbl"] and catalog["default"]["nav"] == 100_000_000
    own = {"targets": HALF_AND_HALF, "nav": 25_000_000, "rebalance": "quarterly", "changes": []}
    assert run_to_end(web, approvals="auto", book=own)["state"] == "finished"
    assert web.get("/api/summary")["book"] == {**own, "nav": 25_000_000.0, "targets": {k: float(v) for k, v in HALF_AND_HALF.items()}}
    nav = web.app.paths.artifacts / "eod-2020-03-16" / "inputs" / "nav.csv"
    assert nav.read_text(encoding="utf-8").splitlines()[1] == "2020-03-13,25000000"
    # Continuing needs no book, but a different one needs a fresh workspace.
    code, body = web.post("/api/start", {"start": "2020-03-18", "end": "2020-03-18", "approvals": "auto", "book": {**own, "nav": 30_000_000}})
    assert code == 400 and "Start over" in body["error"]
    with zipfile.ZipFile(io.BytesIO(web.raw("/api/download")[1])) as z:
        assert "Own portfolio: $25.0m at launch, rebalanced to target each quarter end." in z.read("SUMMARY.md").decode()
    assert web.post("/api/start-over")[0] == 200
    assert web.get("/api/summary")["book"] is None


def test_the_app_refuses_a_portfolio_that_cannot_run(web):
    connect_offline(web)
    for targets, message in (({**HALF_AND_HALF, "Durbl": -0.1, "Manuf": 0.1}, "negative"), ({**HALF_AND_HALF, "Hlth": 0.4}, "90.00%")):
        code, body = web.post("/api/start", {"start": "2020-03-16", "end": "2020-03-17", "book": {"targets": targets}})
        assert code == 400 and message in body["error"]
    assert web.get("/api/summary")["job"] is None


def test_full_path_from_connect_to_download(web):
    connect_offline(web)
    assert web.post("/api/test", {"name": "Test Approver", "provider": "scripted"})[1]["offline"] is True
    assert run_to_end(web)["state"] == "finished"
    assert set(web.get("/api/summary")["counts"]) == {"awaiting_approval"}

    pending = web.get("/api/pending")["items"]
    assert [i["run_id"] for i in pending] == ["eod-2020-03-16", "eod-2020-03-17"]
    assert "hard_breach" in pending[0]["reasons"] and "# Daily Risk Memo" in pending[0]["text"]

    assert web.post("/api/decide", {"run_id": "eod-2020-03-16", "decision": "reject"})[0] == 400  # needs a note
    assert web.post("/api/decide", {"run_id": "eod-2020-03-16", "decision": "approve"})[0] == 200
    assert web.post("/api/decide", {"run_id": "eod-2020-03-17", "decision": "request_changes", "note": "Say more"})[0] == 200
    wait_for(lambda: web.get("/api/run?id=eod-2020-03-16")["run"]["status"] == "completed")
    wait_for(lambda: web.get("/api/run?id=eod-2020-03-17")["run"]["round"] == 1)
    wait_for(lambda: len(web.get("/api/pending")["items"]) == 1)
    assert web.post("/api/approve-all")[1]["queued"] == 1
    wait_for(lambda: not web.get("/api/pending")["items"])

    approval = web.get("/api/run?id=eod-2020-03-16")["approvals"][0]
    assert approval["actor"] == "Test Approver" and approval["decision"] == "approve"

    board = web.get("/api/dashboard")
    assert board["day"]["as_of"] == "2020-03-17" and board["day"]["overall"] == "BREACH" and board["breaches"]

    reports = web.get("/api/reports")["items"]
    assert {"memos/2020-03-16.md", "memos/2020-03-17.md"} <= {r["path"] for r in reports}
    assert "# Daily Risk Memo" in web.get("/api/report?path=memos/2020-03-16.md")["text"]

    status, data, headers = web.raw("/api/download")
    assert "riskwatch-output.zip" in headers["Content-Disposition"]
    z = zipfile.ZipFile(io.BytesIO(data))
    assert "SUMMARY.md" in z.namelist() and "published/memos/2020-03-16.md" in z.namelist() and "audit/approvals.csv" in z.namelist()
    assert "Test Approver" in z.read("audit/approvals.csv").decode()


def test_auto_approval_needs_no_person(web):
    connect_offline(web)
    run_to_end(web, approvals="auto")
    assert web.get("/api/pending")["items"] == []
    assert web.get("/api/run?id=eod-2020-03-16")["approvals"][0]["actor"] == "replay-policy"


def test_only_one_job_at_a_time_and_stop_then_resume_finishes_cleanly(web):
    connect_offline(web)
    assert web.post("/api/start", {"start": "2020-02-18", "end": "2020-03-13", "approvals": "auto"})[0] == 200
    assert web.post("/api/start", {"start": "2020-02-18", "end": "2020-03-13"})[0] == 409
    wait_for(lambda: web.get("/api/summary")["job"]["days_done"] >= 3, 60)
    web.post("/api/stop")
    wait_for(lambda: web.get("/api/summary")["job"]["state"] == "stopped")
    done = web.get("/api/summary")["job"]["days_done"]
    assert 0 < done < 19
    assert web.post("/api/start", {"start": "2020-02-18", "end": "2020-03-13", "approvals": "auto", "resume": True})[0] == 200
    wait_for(lambda: web.get("/api/summary")["job"]["state"] == "finished", 120)
    assert web.get("/api/summary")["job"]["days_done"] == 19


def test_paths_cannot_escape_their_folders(web):
    connect_offline(web)
    run_to_end(web)
    for path in ("/api/file?run=eod-2020-03-16&name=../../state.db", "/api/file?run=..&name=settings.json",
                 "/api/report?path=../state.db", "/api/report?path=../../settings.json", "/api/run?id=../x"):
        with pytest.raises(urllib.error.HTTPError) as e:
            web.raw(path)
        assert e.value.code == 404
    with pytest.raises(urllib.error.HTTPError):
        web.raw("/../server.py")


def test_memo_text_from_an_agent_is_never_treated_as_html():
    from riskwatch.web import server
    source = (server.STATIC / "app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in source.replace("never innerHTML", "") and "insertAdjacentHTML" not in source
    assert "eval(" not in source


def test_start_over_archives_instead_of_deleting(web):
    connect_offline(web)
    run_to_end(web, approvals="auto")
    assert web.post("/api/start-over")[0] == 200
    assert web.get("/api/runs")["runs"] == []
    assert list((web.app.workspace / "archive").glob("home-*/state.db"))


def test_a_running_evaluation_reports_how_far_it_has_got(web):
    web.app.job = {"id": "e1", "kind": "evaluate", "args": [], "state": "running", "candidate": "short_window_var"}
    log = web.app.workspace / "job.log"
    log.write_text("Replaying the test year: day 36 of 253 (2019-08-20)\n"
                   "Replaying the test year: day 37 of 253 (2019-08-21)\n", encoding="utf-8")
    job = web.get("/api/summary")["job"]
    assert (job["days_done"], job["days_total"]) == (37, 253)
    # The leakage check comes after the last day, and the bar stays full while it runs.
    with log.open("a", encoding="utf-8") as f:
        f.write("Replaying the test year: day 253 of 253 (2020-06-30)\n"
                "Checking that no later data leaks into a day (3 probe days)\n")
    job = web.get("/api/summary")["job"]
    assert (job["days_done"], job["days_total"]) == (253, 253)
    assert job["last_line"].startswith("Checking that no later data leaks")


def test_improve_works_on_a_private_copy_of_the_registry(web):
    from riskwatch.config import ROOT
    before = (ROOT / "versions" / "registry.jsonl").read_bytes()
    data = web.get("/api/improve")
    assert len(data["candidates"]) >= 4 and data["active"]
    assert data["can_promote"]
    # Every version on offer has a plain name and scores to compare, so nobody chooses by hash.
    offered = data["can_promote"][0]
    assert data["models"][data["active"]]["title"] == "500-day historical VaR"
    assert data["models"][offered]["title"] == "Age-weighted VaR, gentle"
    assert data["models"][data["active"]]["scorecard"] and data["models"][offered]["scorecard"]
    assert data["rollback_to"] is None
    code, _ = web.post("/api/promote", {"version": offered})
    assert code == 200
    promoted = web.get("/api/improve")
    assert promoted["active"] == offered
    assert promoted["rollback_to"] == data["active"]
    assert promoted["models"][data["active"]]["title"] == "500-day historical VaR"
    assert web.post("/api/rollback", {})[0] == 200
    assert web.get("/api/improve")["active"] == data["active"]
    assert web.post("/api/promote", {"version": "nonsense"})[0] == 400
    assert (ROOT / "versions" / "registry.jsonl").read_bytes() == before


def test_database_is_opened_read_only_for_viewing(web):
    connect_offline(web)
    run_to_end(web, approvals="auto")
    con = web.app.db()
    with pytest.raises(sqlite3.OperationalError):
        con.execute("DELETE FROM runs")
    con.close()


# ---- Claude Code adapter, with the CLI faked ----

def fake_claude(monkeypatch, stdout, seen=None, returncode=0):
    class Result:
        def __init__(self):
            self.stdout, self.stderr, self.returncode = stdout, "", returncode

    def run(cmd, **kwargs):
        if seen is not None:
            seen.update(cmd=cmd, **kwargs)
        return Result()

    monkeypatch.setattr(providers.shutil, "which", lambda name: "claude-exe")
    monkeypatch.setattr(providers.subprocess, "run", run)


MESSAGES = [{"role": "system", "content": "be careful"}, {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "{}"}, {"role": "user", "content": "again"}]
META = {"role": "t", "as_of": "", "round": 0}


def test_claude_agent_runs_with_every_capability_removed(monkeypatch):
    seen = {}
    fake_claude(monkeypatch, json.dumps({"subtype": "success", "result": "ok", "usage": {"input_tokens": 5, "cache_read_input_tokens": 3, "output_tokens": 2}}), seen)
    out = ClaudeCodeCLI("sonnet").complete(MESSAGES, 100, META)
    cmd = seen["cmd"]
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert {"--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"} <= set(cmd)
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert "be careful" in seen["input"] and "again" in seen["input"]
    assert "be careful" not in " ".join(cmd), "long prompts must go through stdin, not arguments"
    assert (out.text, out.tokens_in, out.tokens_out) == ("ok", 8, 2)


@pytest.mark.parametrize("payload,error", [
    ({"is_error": True, "subtype": "success", "result": "Please run /login"}, PermanentError),
    ({"is_error": True, "subtype": "success", "result": "Overloaded"}, TransientError),
    ({"subtype": "error_during_execution"}, TransientError),
])
def test_claude_errors_are_classified(monkeypatch, payload, error):
    fake_claude(monkeypatch, json.dumps(payload))
    with pytest.raises(error):
        ClaudeCodeCLI().complete(MESSAGES, 100, META)


def test_missing_claude_cli_is_a_clear_permanent_error(monkeypatch):
    monkeypatch.setattr(providers.shutil, "which", lambda name: None)
    with pytest.raises(PermanentError, match="not installed"):
        ClaudeCodeCLI().complete(MESSAGES, 100, META)
    assert providers.claude_login_status() == {"installed": False, "logged_in": False}


def test_claude_login_provider_needs_no_key_or_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude-code")
    p = providers.build_provider()
    assert isinstance(p, ClaudeCodeCLI) and p.model == "default"
