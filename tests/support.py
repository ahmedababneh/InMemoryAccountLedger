"""Shared fixture. One replay, reused, because the engine is deterministic."""

from __future__ import annotations

import functools

from ledger.engine import Engine
from ledger.scenario import ACCOUNTS, build_events


@functools.lru_cache(maxsize=1)
def replayed() -> Engine:
    """The canonical six-day replay, run once per process."""
    return Engine(ACCOUNTS, build_events()).run()
