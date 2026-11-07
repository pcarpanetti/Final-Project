import shutil
from pathlib import Path

import pytest

from riskwatch.config import ROOT, Paths, bundle_hash, load_source_bundle
from riskwatch.controller import Controller, Env
from riskwatch.pit import PointInTimeStore


@pytest.fixture(scope="session")
def store():
    return PointInTimeStore(ROOT / "data" / "feed")


@pytest.fixture(scope="session")
def bundle():
    return load_source_bundle()


@pytest.fixture
def paths(tmp_path):
    return Paths(ROOT, tmp_path / "home", tmp_path / "versions", ROOT / "data" / "feed")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Tests never depend on the caller's provider settings."""
    for key in ("LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "RISKWATCH_CRASH_AT", "RISKWATCH_CRASH_MODE"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def make_env(paths, bundle, store):
    envs = []

    def factory(faults=None, the_bundle=None, mode="replay", the_paths=None):
        b = the_bundle or bundle
        env = Env(the_paths or paths, b, bundle_hash(b), store=store, mode=mode, scripted_faults=faults,
                  sleep=lambda s: None, durable=False)
        envs.append(env)
        return env

    yield factory
    for env in envs:
        env.close()


def eod(env, day="2020-03-16"):
    """Create and drive one end-of-day run."""
    ctl = Controller(env)
    run_id = f"eod-{day}"
    env.state.sim_now = f"{day}T20:00"
    ctl.create_run(run_id, "eod", day, f"{day}T20:00", "test")
    return ctl, run_id, ctl.drive(run_id)


def tree_digest(folder: Path) -> dict:
    import hashlib
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}
