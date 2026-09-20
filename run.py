#!/usr/bin/env python3
"""Replay the six-day event stream and print the per-day report.

    python3 run.py

No arguments, no dependencies, no I/O beyond stdout. Everything is in memory.
"""

from __future__ import annotations

import sys

from ledger.engine import Engine
from ledger.report import render
from ledger.scenario import ACCOUNTS, build_events


def main() -> int:
    engine = Engine(ACCOUNTS, build_events()).run()
    print(render(engine))
    return 0


if __name__ == "__main__":
    sys.exit(main())
