"""Test package.

Puts the repository root on `sys.path` so the tests import `ledger` whether
they are run from the root, from inside `tests/`, or through `run_tests.py`.
Doing it here rather than in each module means no test file needs a dummy
import to trigger it.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
