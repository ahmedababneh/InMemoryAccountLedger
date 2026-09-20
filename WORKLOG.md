# WORKLOG

Timestamps are UTC, taken from `date -u` at the moment each entry was written.
This is a build log, not a changelog: it records what was tried, what broke,
and what was thrown away, in the order it actually happened.

---

### 2026-09-20T12:23Z — repo inspected

Empty repository, no commits, branch `claude/account-ledger-core-s3m82x` already
checked out. Remote `ahmedababneh/InMemoryAccountLedger`.

### 2026-09-20T12:24Z — worked the arithmetic by hand before writing code

Did the whole six-day replay on paper first, because the acceptance criteria can
only be judged against a computed answer and I did not want the implementation
to become the thing that "proves" the criteria. Key early finding: E7 (a Day-5
booking value-dated back to Day 2) makes Day 2, Day 4 and Day 5 close negative,
while Day 3 stays positive at AED 5.00. That is three overdraft fees, not one.
Flagged acceptance criterion 2 as suspect at this point, subject to the code
agreeing.

### 2026-09-20T12:27Z — checked whether float would actually hurt

Did not want to assert "floats are wrong" as folklore. Swept every AED balance
from 0.00 to 2000.00 and compared `round(float(b)*0.0004, 2)` against
`Decimal` with ROUND_HALF_UP: 14 divergences, the first at AED 187.50, and one
at AED 462.50 — five dirhams from this scenario's actual Day 4 balance of
465.00. Decimal it is, with the evidence recorded in REJECTED.md.

### 2026-09-20T12:31Z — `ledger/money.py`

Money rejects over-precise construction instead of silently rounding, and
multiplication returns a raw `Decimal` so that a rate calculation physically
cannot produce a storable amount without an explicit `Currency.round` call.
That makes every rounding site greppable.
