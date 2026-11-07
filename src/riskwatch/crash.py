"""Named crash points for recovery testing. Inert unless RISKWATCH_CRASH_AT is set.

The process dies with os._exit, so no `finally` block, commit or flush gets a chance to run. That is
what a power cut or `kill -9` does. Tests can set RISKWATCH_CRASH_MODE=raise to stay in one process.
"""
from __future__ import annotations

import os


class SimulatedCrash(BaseException):
    """Derives from BaseException so `except Exception` in the harness cannot swallow it."""


def point(name: str) -> None:
    if os.environ.get("RISKWATCH_CRASH_AT") != name:
        return
    if os.environ.get("RISKWATCH_CRASH_MODE") == "raise":
        raise SimulatedCrash(name)
    os._exit(137)
