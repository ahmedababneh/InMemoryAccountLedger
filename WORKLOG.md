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

### 2026-09-20T12:36Z — `ledger/records.py`

All record types frozen. The append-only rule is enforced structurally, not by
comment: `AppendOnlyLog` exposes `append` and iteration and nothing else. First
real design consequence recorded — a hold cannot be "decremented", so placing
and releasing became two records and "what is held now" became a projection.

### 2026-09-20T12:40Z — `ledger/book.py`, and the decision that made the rest easy

Balances are projections over two coordinates, `value_date` and `booked_day`,
not a running total. `closing_balance(day, known_through)` answers both "what
did we believe Day 2 closed at on Day 2" (AED 250.00) and "what did Day 2
actually close at once E7 arrived" (AED -370.00). Smoke-tested both; the
-370.00 of acceptance criterion 1 falls straight out.

I had started with a single running balance per account and a list of entries.
Threw it away within a few minutes: it cannot represent the two answers above
at the same time, which is the entire substance of this exercise. Recorded in
REJECTED.md.

### 2026-09-20T12:46Z — `ledger/policy.py`

Pulled every number out of the engine. The overdraft fee is keyed by currency
and BHD is deliberately *absent*: the brief gives a fee for AED only, so an
overdrawn BHD account raises `PolicyNotConfigured` instead of posting an
AED-shaped 25 into a 3dp account. Verified the accrual figures against the
paper run: 250.00 -> 0.10, 465.00 -> 0.19, 415.00 -> 0.17, 5.00 -> 0.00.

The 5.00 -> 0.00 case is worth noting: at 0.04%/day any AED balance under
12.50 accrues literally nothing once rounded. Wrote that up in NUMBERS.md.

### 2026-09-20T12:52Z — `ledger/engine.py`

Fee sweep needed a fixpoint loop, not a single pass. A fee is value-dated to
the day it is assessed *for*, so booking a Day-2 fee lowers Day 3, 4 and 5 as
well and can itself create a new overdraft. First cut was one linear pass over
the days; it happened to give the right answer for this stream and is still
wrong, so it went. Recorded in REJECTED.md under abandoned approaches.

Also botched `split_into_instalments` on the first attempt -- built the parts
through a nested conditional expression with an inline `__import__` in it,
which worked and was unreadable. Rewrote it in whole minor units with an
explicit conservation check.

### 2026-09-20T12:58Z — first full replay, and it matches the paper run

ACC-001 closes: D1 250.00, D2 -370.00 -> restated 225.00, D5 -230.00 as of
Day 5, 390.93 at end of Day 6. Three overdraft fees, all assessed on Day 5,
value-dated to days 2, 4 and 5. Auth-A approved and settled; Auth-Z rejected;
Auth-B DECLINED (available was already -155.00 when it arrived). ACC-002
closes 10.008 with instalments 3.333 / 3.333 / 3.334.

That settles four acceptance criteria as wrong: 2, 6, 7 and 8. Criterion 5 is
the interesting one -- it is a conditional whose antecedent never fires,
because Auth-B is declined. Writing that up carefully rather than just calling
it wrong.

### 2026-09-20T13:06Z — `ledger/report.py` and `run.py`, plus two bugs in my own reporting

Caught two things the report was quietly misrepresenting:

1. The per-day "interest accrued today" line read the *final* net accrual, so
   Day 2 printed 0.09 — the restated figure — when the ledger had actually
   booked 0.10 at Day 2's close. Added `evaluated_through` to
   `net_accrual_for_day` so the daily section is genuinely point-in-time, and
   added an explicit "interest revised for earlier days" block so the
   restatement is visible where it happens rather than inferred.

2. The reconciliation table showed a Day 6 basis of AED 390.93, which includes
   the capitalisation credit that was not in the basis used. The number was
   right by accident — the accrual sweep runs before capitalisation — but the
   displayed basis was a lie, and the correctness depended on step ordering.
   Added `Book.interest_basis`, which excludes capitalisation entries by kind.
   Now Day 6 cannot earn interest on its own interest regardless of what order
   the closing steps run in.

Neither changed a single output figure. Both were worth fixing: the first
because a point-in-time report that silently shows restated numbers defeats the
purpose, the second because "correct only because of statement order" is a bug
waiting for a refactor.

### 2026-09-20T13:19Z — made the criterion-2 refusal falsifiable instead of rhetorical

I had written "criterion 2 is wrong under either reading of fee value-dating"
as an assertion. That is exactly the kind of claim that turns out to be wrong
when someone checks, so I implemented the other reading behind a policy flag
(`fee_value_dated_to_assessment_day`) and ran it. Three fees either way — days
2, 4 and 5 — only the value_dates move. Now a test proves it.

### 2026-09-20T13:24Z — sensitivity sweep for NUMBERS.md

Ran the replay across a range of fee amounts and interest rates rather than
reasoning about "why not half it" from an armchair:

* Fee AED 25.00 -> 3 fees. The fourth appears at AED 30.01, not 30.00: at
  exactly 30.00 Day 3 closes at 0.00, and zero is not negative. This scenario
  sits five dirhams from a fee cascade.
* Halving the rate to 0.02% gives AED 0.47 capitalised, not half of 0.93
  (0.465). Rounding six dailies is not linear in the rate. That is the real
  answer to "why not half it" and I would not have found it by thinking.

### 2026-09-20T13:31Z — counterfactual run for criterion 6

Replayed the stream with E7 and E9 both removed to get the genuine "pre-E7
values": Day 6 closes 466.03 with zero fees, against the actual 390.93 with
three. And Auth-B is APPROVED in that world and DECLINED in the real one — a
reversal on Day 6 cannot travel back and approve a card authorization refused
on Day 5. That third reason is the one I find decisive, because unlike the fees
it could not be fixed by any refund policy.

### 2026-09-20T13:36Z — 64 tests green

`tests/test_money.py` (9), `tests/test_rules.py` (24),
`tests/test_acceptance_criteria.py` (31). Every criterion has a test, including
the four refused ones — an absent test would make a refusal look like an
oversight.

### 2026-09-20T13:47Z — the deliberately failing test

Picked the fee/reversal gap over the other candidates. Considered and rejected:

* *Sum-of-rounded vs rounded-sum* (0.93 vs 0.92). Real, but the brief mandates
  sum-of-rounded explicitly, so a test against it would be arguing with the
  spec rather than exposing a weakness in my design.
* *No back-value window.* An entry value-dated to Day 1 arriving on Day 6
  silently rewrites the whole window; real cores cap this. Genuine, but it is a
  missing feature rather than a wrong behaviour, and the brief supplies no
  window length.
* *Fee/reversal asymmetry.* Chosen. The engine re-sweeps history to ADD fees a
  backdated entry newly justifies, but never asks whether a fee it already
  booked has lost its justification. The customer ends the window AED 75.00
  down for an overdraft the ledger's own final numbers say never happened.

It is the right one because the asymmetry is in code I wrote, not in the brief,
and because "the record is immutable" and "the money stays taken" are two
different claims that my design quietly conflates.

### 2026-09-20T13:52Z — `run_tests.py`

`unittest discover` exits non-zero by design here, which a CI job would call a
broken build. The wrapper encodes the actual expectation: 64 pass, exactly one
named test fails. It also exits 1 if the known gap *stops* failing, so nobody
can quietly fix the design and leave the test asserting nothing.

### 2026-09-20T14:05Z — REJECTED.md

Four refusals: 2, 6, 7, 8. Criterion 5 accepted as stated, with a warning — it
is a conditional whose antecedent is false, and calling a true statement
"wrong" because its premise does not hold would itself be wrong. The honest
answer is to accept the rule and assert the decline loudly.

### 2026-09-20T14:14Z — AMBIGUITIES.md, 22 entries

Numbered, and the numbers are cited from source comments so they cannot drift.
Checked every cross-reference resolves. Marked each entry outcome-changing or
not, because an ambiguity that cannot move a published figure is a different
kind of thing from one that can, and lumping them together would pad the list.

Caught one wrong claim while writing it: I had written that a residual hold
after partial settlement would leave Auth-B "declined by 245.00 either way".
It would be -260.00 in that world, not -245.00. The conclusion held — declined
either way — but the number was wrong, so I fixed it.

### 2026-09-20T14:22Z — NUMBERS.md, and two surprises

Measured every sensitivity rather than reasoning about it, and two results were
not what I expected:

* The fee cascade threshold is exactly AED 30.00, *exclusive*. At 30.00 Day 3
  closes at precisely 0.00 and zero is not negative, so three fees. At 30.01,
  four. This scenario sits five dirhams from a different answer.
* Halving the interest rate does not halve the interest. 0.04%/day gives
  AED 0.93; 0.02%/day gives 0.47, not 0.465. Rounding six dailies independently
  is not linear in the rate. That is the real answer to "why that value and not
  half it" and I would not have got it by thinking about it.

Also noticed `ledger/__init__.py` was missing entirely — the package had been
importing as a namespace package this whole time. Added it with the module map.

### 2026-09-20T14:38Z — README, then an adversarial re-read that found a real bug

Wrote the README, then went back through the engine looking for things that
were wrong rather than things that were missing. Found one, and it is the
embarrassing kind: `assess_overdraft_fees` skipped any account whose currency
had no configured fee. Silently. The comment sitting two lines below it said we
"refuse loudly rather than posting a number the brief never gave us", and both
NUMBERS.md and AMBIGUITIES.md #12 stated flatly that an overdrawn BHD account
raises `PolicyNotConfigured`.

It did not. It charged nothing and moved on.

The documentation described the behaviour I intended and the code had the
behaviour that was easy to write, and because ACC-002 never goes negative,
nothing in the output or the test suite would ever have caught it. That is the
worst shape a bug can have: invisible, and with three documents vouching for
the opposite.

Fixed the code rather than the docs, since the docs had it right. An overdrawn
account in an unpriced currency now raises with the offending days named. Two
tests added — one that the raise happens, one that a BHD account staying
positive is unaffected, which is ACC-002's actual situation.

Lesson recorded rather than quietly absorbed: I wrote three documents asserting
a guard existed without once running the path that would exercise it.

### 2026-09-20T14:44Z — pyflakes clean, counts corrected

Dead imports removed across the package. Moved the test `sys.path` bootstrap
into `tests/__init__.py` so no test module needs a dummy import to trigger it.
67 tests now: 66 pass, 1 fails by design. Corrected the counts in the README,
which I had already written against the old numbers.

### 2026-09-20T14:56Z — the same bug again, three more times

Having just fixed one flag that lied about its behaviour, I went looking for
others instead of assuming it was isolated. Grepped every policy setting for
whether anything actually reads it. Three do not:

    settlement_releases_full_hold        declared, never read
    hold_expiry_days                     declared, never read
    reversal_refunds_consequential_fees  declared, never read

All three look like configuration. Flipping any of them changed nothing
whatsoever — a reader could set `hold_expiry_days = 3`, see identical output,
and reasonably conclude hold expiry does not affect this scenario. It does not
affect it because the feature does not exist.

Considered implementing all three. Decided against: none is needed to support
any claim I make, and the brief asks for a ledger core rather than a policy
engine. `fee_value_dated_to_assessment_day` earned its implementation because
REJECTED.md's refusal of criterion 2 depends on being able to run both
branches; these three earn nothing.

So they raise instead. `Policy.__post_init__` refuses any non-default value for
an unimplemented setting, with a message naming what implementing it would
involve and where the decision is documented. The flag still serves its real
purpose — a name to cite from source comments — without pretending to be a
switch.

Then went back and corrected three documents that had described the reversal
flag as a working "hook". It is a labelled decision, not a hook, and saying
otherwise was the same lie one level up.

### 2026-09-20T15:02Z — final state

71 tests: 70 pass, 1 fails by design. pyflakes clean. `run.py` output verified
against the figures I worked out on paper before writing any code, and against
the block quoted in the README.

### 2026-09-20T15:20Z — README called it "double-entry". It is not.

Checking my own claims before writing the architecture document, and the very
first line of the README described this as a "double-entry ledger core". It is
single-entry: `Entry` carries one `account_id` and one signed amount, with no
contra leg and no transaction grouping that would force the legs to sum to
zero. Nothing in the system would notice a posting that went to one account and
nowhere else, because that is what every posting does.

Corrected the README rather than the code. Adding a real contra side is a
structural change well outside what the brief asked for, and claiming it is the
part that was actually wrong.

### 2026-09-20T15:26Z — measured the scaling instead of guessing at it

Benchmarked the replay along three axes before writing anything about
performance. The result was not what I expected:

    100x events   (30 -> 3,000, 6 days)     0.01s ->   0.52s      ~52x
    30x days      (6 -> 180, 10 ev/day)     0.01s -> 125.62s  ~12,562x
    100x accounts (2 -> 200, 30 days)        0.72s ->  13.33s     ~18x

Transaction volume is close to linear and entirely survivable. **Window length
is cubic** — the measured exponent is 2.8, which is what you get from two
day-sweeps that each re-scan every entry across every prior day. A year-long
window for two accounts would take a quarter of an hour.

And at 200 accounts over 30 days there are 2,363 accrual records against 1,343
ledger entries: the derived journal is larger than the log it is derived from,
on a fixed 300 events. Accruals grow with accounts x days, not with volume.

### 2026-09-20T15:48Z — ARCHITECTURE.md, and two measurement errors of my own

Wrote up the scale, value-dating, authorization-lifecycle and scope-cut
analysis. Two things I got wrong first and had to correct:

1. **My benchmark was instrumented.** The first scaling run wrapped every
   replay in `tracemalloc`, which hooks every allocation. It reported 125.62s
   for a 180-day window; the honest figure is 38.51s. Roughly a 3x inflation,
   uniformly applied, so the *shape* held — but I had drafted absolute numbers
   from it. Re-ran without instrumentation and rewrote the table.

2. **I claimed the back-value window fixes compute and storage "at once".** It
   does not. The paired run showed accrual counts identical between windowed
   and unbounded (146/146, 251/251, 728/728), which I nearly published as
   evidence for a claim it actually refutes. The reason was my generator only
   backdated within five days, so a five-day window had nothing to suppress.
   Re-ran with deeper backdating: the window cuts revisions 35-64% once
   backdating exceeds it, but cannot touch the baseline accounts x days growth.
   Storage needs accrual compaction, which is a separate change.

The second one is the more instructive failure. The measurement was right and
my reading of it was wrong, in the direction that flattered the argument I had
already written.

Also confirmed by direct test: an account that transacts once and then sits
idle appends one accrual record per day forever — 40 records over 40 idle days
— unless its balance is below the AED 12.50 dust threshold, in which case zero.
The journal grows only for accounts worth having.

### 2026-09-20T16:12Z — PDF down from 9 pages to 4

The first PDF gave every numbered section its own page, which read well and ran
to nine. Compressed the layout rather than cutting content: dropped the
per-section page breaks, body 10pt to 8.5pt, leading 1.5 to 1.33, tables 8.2pt
to 6.9pt, margins 20/17mm to 12mm, and folded the cover block into an inline
masthead. Four pages, all content intact (verified by extracting the text back
out and checking the figures).

Tried going further for three. It did not work: body 8.2pt with 6.6pt tables
still produced four pages, just with smaller type and more whitespace on the
last one. Reverted — no page saved, only legibility lost. The content sits at
about three and a half pages, so four is where it lands without either cutting
material or dropping below a readable size.
