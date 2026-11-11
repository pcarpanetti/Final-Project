"""What start.bat does when RiskWatch is already running on its port."""
import json
import socket
import sys
import threading

import pytest

from riskwatch.config import ROOT
from riskwatch.web.server import make_server

sys.path.insert(0, str(ROOT))
import launch  # noqa: E402


@pytest.fixture
def running(tmp_path, monkeypatch):
    """A real server, plus the marker file serve() writes, in a private workspace."""
    workspace = tmp_path / "ws"
    server, app = make_server(workspace, 0)
    (workspace / "server.json").write_text(json.dumps({"port": app.port, "token": app.token}), encoding="utf-8")
    def serve():  # as serve() does: the socket closes as soon as the server stops
        server.serve_forever()
        server.server_close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    monkeypatch.setenv("RISKWATCH_WEB_HOME", str(workspace))
    opened = []
    monkeypatch.setattr(launch.webbrowser, "open", opened.append)
    monkeypatch.setattr(launch.sys, "argv", ["launch.py"])
    yield app, thread, opened
    app.stop_job()
    server.shutdown()
    server.server_close()


def test_free_port_means_start_normally(running):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    assert launch.handle_running_copy(free) is None


def test_same_version_already_running_is_just_opened(running):
    app, thread, opened = running
    assert launch.handle_running_copy(app.port) == 0
    assert opened == [f"http://127.0.0.1:{app.port}/"] and thread.is_alive()


def test_older_idle_copy_is_replaced(running):
    """Regression: a restarted app kept serving old code because an older copy still held the port."""
    app, thread, opened = running
    app.fingerprint = "older-code"
    assert launch.handle_running_copy(app.port) is None
    thread.join(10)
    assert not thread.is_alive() and not launch.port_in_use(app.port)


def test_older_copy_in_the_middle_of_a_run_is_left_alone(running):
    app, thread, opened = running
    app.fingerprint = "older-code"
    app.job = {"state": "running", "kind": "run"}
    assert launch.handle_running_copy(app.port) == 1
    assert thread.is_alive() and opened


def test_another_program_on_the_port_is_explained_not_touched(monkeypatch, capsys):
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        port = other.getsockname()[1]
        monkeypatch.setattr(launch.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("not http")))
        assert launch.handle_running_copy(port) == 1
    assert "another program" in capsys.readouterr().out
