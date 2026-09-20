"""Shared fixtures. One replay, reused, because the engine is deterministic."""

from __future__ import annotations

import functools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger.engine import Engine  # noqa: E402
from ledger.scenario import ACCOUNTS, build_events  # noqa: E402


@functools.lru_cache(maxsize=1)
def replayed() -> Engine:
    """The canonical six-day replay, run once per process."""
    return Engine(ACCOUNTS, build_events()).run()


def fresh() -> Engine:
    """An unrun engine over the same stream, for tests that vary the inputs."""
    return Engine(ACCOUNTS, build_events())
