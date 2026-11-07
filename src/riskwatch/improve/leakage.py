"""Future-perturbation test: corrupt everything published after the cutoff and require identical output.

If a run reads the future, even by accident, its artifacts change and the test fails. The negative
control proves the test can fail: a store with its cutoff filter disabled must be caught.
"""
from __future__ import annotations

import copy
import hashlib
import tempfile
from pathlib import Path

from ..config import Paths
from ..controller import Controller, Env
from ..pit import PointInTimeStore


def poison_future(store: PointInTimeStore, cutoff: str) -> PointInTimeStore:
    bad = copy.copy(store)
    bad.market, bad.factors = store.market.copy(), store.factors.copy()
    bad.positions, bad.notes = store.positions.copy(), store.notes.copy()
    bad.market.loc[bad.market.published_at > cutoff, "ret"] = -0.9
    bad.factors.loc[bad.factors.published_at > cutoff, "ret"] = -0.9
    future = bad.positions.published_at > cutoff
    bad.positions.loc[future, "weight"] = 0.5
    bad.positions.loc[future, "nav"] = 1.0
    bad.notes.loc[bad.notes.published_at > cutoff, "note"] = "FUTURE NOTE"
    return bad


class LeakyStore(PointInTimeStore):
    """Negative control. Ignores the cutoff, as a careless implementation might."""

    def __init__(self, inner: PointInTimeStore):
        self.__dict__.update(inner.__dict__)

    def snapshot(self, as_of: str, cutoff: str):
        return super().snapshot(self.calendar[-1], "9999")


def run_one_day(bundle: dict, version: str, root: Path, store: PointInTimeStore, day: str, cutoff: str) -> dict[str, str]:
    """Run a single end-of-day in a throwaway home and hash everything it produced."""
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        env = Env(Paths(root, home, home / "versions", root / "data" / "feed"), bundle, version, store=store,
                  mode="replay", sleep=lambda s: None, durable=False)
        ctl = Controller(env)
        ctl.create_run(f"eod-{day}", "eod", day, cutoff, "leakage_probe")
        status = ctl.drive(f"eod-{day}")
        if status == "awaiting_approval":
            ctl.decide(f"eod-{day}", "approve", "leakage-probe")
        run_dir = home / "artifacts" / f"eod-{day}"
        digests = {p.relative_to(run_dir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(run_dir.rglob("*")) if p.is_file()}
        env.close()
    return digests


def perturbation_test(bundle: dict, version: str, root: Path, store: PointInTimeStore, days: list[str]) -> dict:
    cutoff_time = bundle["policy"]["schedule"]["eod_cutoff"]
    results = []
    for day in days:
        cutoff = f"{day}T{cutoff_time}"
        clean = run_one_day(bundle, version, root, store, day, cutoff)
        poisoned = run_one_day(bundle, version, root, poison_future(store, cutoff), day, cutoff)
        results.append({"day": day, "files": len(clean), "identical": clean == poisoned})
    return {"passed": all(r["identical"] for r in results), "days": results}


def negative_control(bundle: dict, version: str, root: Path, store: PointInTimeStore, day: str) -> dict:
    """The same comparison through a store that ignores the cutoff. It must report a difference."""
    cutoff = f"{day}T{bundle['policy']['schedule']['eod_cutoff']}"
    leaky = LeakyStore(store)
    clean = run_one_day(bundle, version, root, leaky, day, cutoff)
    poisoned = run_one_day(bundle, version, root, LeakyStore(poison_future(store, cutoff)), day, cutoff)
    return {"day": day, "leak_detected": clean != poisoned}
