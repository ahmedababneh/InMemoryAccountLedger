# In-memory account ledger core

A value-dated, append-only ledger core in pure Python. No web
layer, no persistence, no UI, no database, and no third-party dependencies —
the whole system is a function from an event stream to a set of projections.

Python 3.9+. Nothing to install.

```bash
python3 run.py          # replay the six-day stream and print the report
python3 run_tests.py    # run the suite (expects exactly one known failure)
```

---

## The short version

Six days, two accounts, ten events. The interesting one is **E7**: a debit
booked on Day 5 but value-dated back to Day 2. It retroactively overdraws three
days that had already closed in credit, costs AED 75.00 in fees, causes an
authorization to be declined — and is then reversed on Day 6, by which point
most of that cannot be undone.

Results:

| | ACC-001 (AED) | ACC-002 (BHD) |
|---|---:|---:|
| Day 6 closing balance | **390.93** | **10.008** |
| Overdraft fees | 75.00 (3 days) | none |
| Interest capitalised | 0.93 | 0.008 |

**Four of the eight acceptance criteria are wrong.** Criteria 2, 6, 7 and 8 are
refused, with computed evidence, in [REJECTED.md](REJECTED.md). Criterion 5 is
accepted as stated but its condition never fires.

---

## Reading the output

`python3 run.py` prints five sections.

### 1. One block per day

For each day, for each account: **closing ledger balance**, **fee
assessments**, **authorization states**, and **errors** — plus active holds,
available balance, and interest.

Everything in a day block is **point-in-time**: what the ledger actually held
at that day's close, not what it later decided. This matters. Day 2 prints
AED 250.00 here, even though it eventually restates to 225.00, because 250.00
is what Day 2 genuinely closed at before anyone had heard of E7.

Day 5 is where the exercise happens:

```
Day 5
  ACC-001
    Closing ledger balance .... AED -230.00
    Available balance ......... AED -230.00
    Fee assessments ...........
      overdraft AED 25.00 value_date=Day 2 (that day closed AED -370.00)  <- back-valued to a day already closed
      overdraft AED 25.00 value_date=Day 4 (that day closed AED -180.00)  <- back-valued to a day already closed
      overdraft AED 25.00 value_date=Day 5 (that day closed AED -205.00)
    Authorization states ......
      Auth-A   SETTLED  hold AED 200.00  placed Day 2  closed Day 4
      Auth-B   DECLINED hold AED 90.00  requested Day 5  no hold placed
    Errors ....................
      E8  DECLINED: available AED -155.00 less hold AED 90.00 = AED -245.00, below zero
    Interest revised for earlier days
      Day 2    -> AED 0.00  (delta AED -0.10, basis now AED -395.00)
```

Three fees assessed in one close, two of them value-dated into days that had
already been reported. An authorization declined on a balance that will be
reversed tomorrow. Three past days' interest struck out. All caused by one
back-valued debit.

### 2. Restated closing balances

Both answers side by side, with a `*` on every day a later arrival changed:

```
    day         as-of that day          restated           delta
    2               AED 250.00        AED 225.00      AED -25.00  *
    5              AED -230.00        AED 390.00      AED 620.00  *
```

Neither column is the "real" one. A day genuinely has two closing balances, and
a ledger that can only show one of them cannot do value dating.

### 3. Interest reconciliation

Each day's basis, rate and rounded accrual, then the sum against the
capitalised credit. The brief requires the rounded dailies to sum **exactly**
to the capitalised total; this section is where you check that, and it prints
`MATCH`.

### 4. Final position

Closing balance, total fees, interest, entry count.

### 5. Entry log

Every entry ever written, in order, including the ones that were reversed. E7's
−620.00 and E9's +620.00 both appear. Nothing is ever removed.

---

## Running the tests

```bash
python3 run_tests.py
```

**71 tests: 70 pass, 1 fails on purpose.**

That one failure is a deliverable, not a defect. `run_tests.py` encodes the
expectation and exits 0 when exactly the known test fails — and exits 1 if it
ever *stops* failing, so nobody can fix the design and leave a test asserting
nothing.

```
  70 passed
  1 failed, as designed: test_fees_caused_solely_by_an_entry_that_was_reversed_are_not_refunded
```

For the raw picture, `python3 -m unittest discover -s tests -t . -v` works too;
it exits non-zero, which is correct and is why the wrapper exists.

| File | Covers |
|------|--------|
| `tests/test_money.py` | Per-currency precision, explicit rounding, float divergence |
| `tests/test_rules.py` | The six non-negotiable rules, boundary cases, determinism |
| `tests/test_acceptance_criteria.py` | One class per criterion, including the four refused |
| `tests/test_known_design_gap.py` | The deliberate failure |

### The failing test

The engine sweeps history to **add** overdraft fees that a backdated entry
newly justifies — that is why there are three. It never asks whether a fee it
already booked has **lost** its justification. After E9 reverses E7, no day in
the window closes negative, yet AED 75.00 of fees remain for an overdraft the
ledger's own final numbers say never happened.

It is not fixed because fixing it means silently answering a question the brief
does not answer: whether a charge assessed correctly on the information
available at the time survives a later restatement. That is a commercial policy
decision. The hook exists (`Policy.reversal_refunds_consequential_fees`), and
the failing test forces someone to decide rather than inherit my guess.

`tests/test_known_design_gap.py` is annotated inline with what the failure
reveals, why it is a policy gap rather than an arithmetic bug, and what closing
it would cost.

---

## How it works

### Balances are projections, not totals

No account stores a balance. Every balance is computed from the entry log over
two coordinates:

- **`value_date`** — the day an entry takes economic effect
- **`booked_day`** — the day the ledger learned it exists

```python
book.closing_balance("ACC-001", day=2, known_through=2)   # AED  250.00
book.closing_balance("ACC-001", day=2, known_through=5)   # AED -370.00
book.closing_balance("ACC-001", day=2)                    # AED  225.00
```

Same day, three honest answers: what Day 2 closed at, what it closed at once E7
arrived, and what it closed at once the Day-2 fee was booked too. A running
total holds exactly one of these. That is why there isn't one.

### Append-only is structural

Records are frozen dataclasses behind an `AppendOnlyLog` that exposes `append`
and iteration and nothing else. The rule is enforced by the type system rather
than by comment, and it shapes everything downstream:

- a **reversal** is a compensating entry; the original stays forever;
- a **hold** is never decremented — PLACED and RELEASED are separate records,
  and "what is held now" is folded from the log;
- a **rejection** is a recorded fact with no entry, so the ledger remembers
  that someone tried to settle Auth-Z;
- a **revised accrual** appends a delta. Day 2's interest was written three
  times (0.10 → 0.00 → 0.09) and all three records survive.

### A day closes in a fixed order

```
apply this day's events, in stream order
  ├─ assess overdraft fees   (sweep all days, loop to a fixpoint)
  ├─ accrue interest          (sweep all days, append revisions)
  └─ capitalise               (last day only)
```

Fees **before** interest, because a fee is a real posting that lowers the
balance interest is computed on.

Both sweeps re-examine **every** day in the window, not just today — that is
what makes backdating work. The fee sweep loops to a fixpoint because a fee is
value-dated to the day it is assessed for, so booking one can push a later day
negative in turn. It does not happen at AED 25.00; it would above AED 30.00.

### Money knows its own precision

`Money` **rejects** over-precise construction instead of rounding it away, and
multiplication returns an unrounded `Decimal` so a rate calculation physically
cannot produce a storable amount without an explicit `Currency.round` call.
Every rounding site is greppable.

```python
AED.exact("3.334")                    # PrecisionError
AED.exact("465.00").scaled_by(RATE)   # Decimal('0.186000') — not Money yet
AED.round(_)                          # AED 0.19
```

---

## Layout

```
run.py                  replay and print the report
run_tests.py            run the suite with the one-known-failure expectation
ledger/
  money.py              Money, Currency, precision, explicit rounding
  records.py            frozen record types, AppendOnlyLog
  book.py               storage and the projections read off it
  policy.py             every configurable number
  engine.py             replay: apply a day, then close it
  report.py             text rendering
  scenario.py           the brief's event stream, as data
tests/
  test_money.py                 9 tests
  test_rules.py                30 tests
  test_acceptance_criteria.py  31 tests
  test_known_design_gap.py      1 test, fails on purpose
```

## The other documents

| | |
|---|---|
| [REJECTED.md](REJECTED.md) | The four refused criteria with computed evidence, and seven approaches abandoned mid-build |
| [NUMBERS.md](NUMBERS.md) | Every constant, and a measured sensitivity analysis for each |
| [AMBIGUITIES.md](AMBIGUITIES.md) | 22 ambiguities, numbered and cited from source comments |
| [WORKLOG.md](WORKLOG.md) | Timestamped build log, including the things that went wrong |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Scale limits, the value-dating surface in production, authorization lifecycle, and every scope cut ranked by risk. Also as [ARCHITECTURE.pdf](ARCHITECTURE.pdf), regenerated with `python3 tools/md2pdf.py ARCHITECTURE.md ARCHITECTURE.pdf` |
