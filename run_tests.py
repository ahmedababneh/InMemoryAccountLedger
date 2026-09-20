#!/usr/bin/env python3
"""Run the suite and check it fails in exactly the one way it is meant to.

    python3 run_tests.py

The suite contains one deliberately failing test
(`tests/test_known_design_gap.py`), so a plain `unittest discover` exits
non-zero by design and a CI job would call that a broken build. This wrapper
states the expectation instead:

    exit 0  -- everything passed except the one known gap, which failed
    exit 1  -- anything else, including the known gap unexpectedly passing

That last case matters. If someone "fixes" the gap without removing the test,
this runner fails rather than quietly going green, which is the only way the
expectation stays honest.
"""

from __future__ import annotations

import sys
import unittest

KNOWN_GAP = (
    "tests.test_known_design_gap.ReversalDoesNotUnwindConsequentialFees."
    "test_fees_caused_solely_by_an_entry_that_was_reversed_are_not_refunded"
)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir="tests", top_level_dir=".")
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stderr).run(suite)

    failed = {str(test.id()) for test, _ in result.failures}
    errored = {str(test.id()) for test, _ in result.errors}

    print()
    print("=" * 78)
    print(f"ran {result.testsRun} tests")
    print("=" * 78)

    problems = []
    if errored:
        problems.append(f"unexpected errors: {sorted(errored)}")
    unexpected = failed - {KNOWN_GAP}
    if unexpected:
        problems.append(f"unexpected failures: {sorted(unexpected)}")
    if KNOWN_GAP not in failed:
        problems.append(
            f"the known design gap did NOT fail: {KNOWN_GAP}\n"
            "  Either it was fixed (delete the test and say so in REJECTED.md)\n"
            "  or something is masking it."
        )

    if problems:
        print("UNEXPECTED RESULT")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    passed = result.testsRun - len(failed)
    print(f"  {passed} passed")
    print(f"  1 failed, as designed: {KNOWN_GAP.rsplit('.', 1)[-1]}")
    print("    see tests/test_known_design_gap.py for the annotated reasoning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
