# REJECTED

Two halves: acceptance criteria I refuse, and approaches I abandoned mid-build.

Every number quoted here is produced by `python3 run.py` and asserted by a test
in `tests/test_acceptance_criteria.py`. Nothing in this file is reasoned from
an armchair; where I make a claim about what *would* happen under a different
policy, I implemented that policy and ran it.

---

## Part 1 — Acceptance criteria

Verdicts at a glance:

| # | Criterion | Verdict |
|---|-----------|---------|
| 1 | Day 2 closes at AED −370.00 at end of Day 5, pre-fee | **Accepted** |
| 2 | E7 causes exactly one overdraft fee, on Day 2 | **Refused** |
| 3 | The Day 4 settlement of Auth-A must be accepted | **Accepted** |
| 4 | Settlement of an unknown authorization is rejected, no funds move | **Accepted** |
| 5 | If Auth-B is approved, its hold cuts available but not ledger balance | **Accepted as stated** — but its condition never fires |
| 6 | After E9, all balances and fees return to pre-E7 values | **Refused** |
| 7 | The three BHD instalments must each be BHD 3.334 | **Refused** |
| 8 | Any remainder between rounded dailies and the capitalised total is discarded | **Refused** |

---

### Criterion 1 — ACCEPTED

> The Day 2 closing ledger balance, evaluated at end of Day 5 and before any
> fee is assessed, is AED −370.00.

Correct, and it is the criterion that tells you the author understands
value-dating.

```
E1  +1,200.00  value_date Day 1
E2    −950.00  value_date Day 1
E7    −620.00  value_date Day 2   (booked Day 5)
                ─────────
                 −370.00
```

Day 2 has two true closing balances and the criterion is careful to say which
one it means. At the end of Day 2 the ledger had never heard of E7 and Day 2
closed at **AED 250.00**. At the end of Day 5, with E7 known, the same day
closes at **AED −370.00**. Both are printed side by side in the restatement
table of `run.py`.

The "before any fee is assessed" qualifier is load-bearing too: once the Day-2
overdraft fee is booked — value-dated to Day 2 — that day restates again, to
−395.00. The criterion is asking for the balance the fee decision was *taken
on*, which is the figure this ledger stores on the assessment record itself.

Verified by `Criterion1_Day2ClosesAtMinus370`.

---

### Criterion 2 — REFUSED

> E7 causes exactly one overdraft fee to be assessed, on Day 2.

**E7 causes three overdraft fees: on Day 2, Day 4 and Day 5. AED 75.00, not
AED 25.00.**

The error is treating a back-valued debit as a point event. It is not. An entry
value-dated to Day 2 sits in the running balance of Day 2 *and every day after
it*. The 620.00 does not stop applying on Day 3.

Closing balances once E7 is known (end of Day 5, each figure after any fee
value-dated to an earlier day):

| Day | Closing balance | Negative? | Fee |
|-----|----------------:|-----------|-----|
| 1 | 250.00 | no | — |
| 2 | −370.00 | **yes** | AED 25.00 |
| 3 | 5.00 | no | — |
| 4 | −180.00 | **yes** | AED 25.00 |
| 5 | −205.00 | **yes** | AED 25.00 |

Day 3 is the interesting one. E4's 400.00 credit lifts the balance from
−395.00 back to **5.00** — positive by five dirhams, so no fee. Day 3 is the
only thing standing between this scenario and a fourth fee, and it survives by
about the price of a coffee. The rule is "once per day per account", not "once
per overdraft", so a balance that dips, recovers and dips again is charged
twice.

**The refusal does not depend on resolving an ambiguity.** "Booked with
value_date equal to the day assessed" can be read two ways: the day whose
balance was negative (Day 2), or the day the assessment actually ran (Day 5).
I implemented both — `Policy.fee_value_dated_to_assessment_day` — and ran them:

| Reading | Fees for days | Fee value_dates | Count |
|---------|---------------|-----------------|-------|
| day whose balance was negative (default) | 2, 4, 5 | 2, 4, 5 | **3** |
| day the assessment ran | 2, 4, 5 | 5, 5, 5 | **3** |

Three either way. The criterion is wrong under both readings.

It is also wrong in a way that does not depend on the fee amount. Only if the
fee exceeded **AED 30.00** would Day 3 be dragged negative too, making it four:

| Fee | Days charged | Count |
|-----|--------------|-------|
| AED 12.50 | 2, 4, 5 | 3 |
| AED 25.00 | 2, 4, 5 | 3 |
| AED 30.00 | 2, 4, 5 | 3 |
| AED 30.01 | 2, **3**, 4, 5 | 4 |
| AED 50.00 | 2, 3, 4, 5 | 4 |

There is no fee amount at which the answer is one.

Verified by `Criterion2_RefusedOneFeeOnDay2`.

---

### Criterion 3 — ACCEPTED

> The Day 4 settlement of Auth-A must be accepted.

Correct. Auth-A was approved on Day 2 (available 250.00 − 200.00 = 50.00,
comfortably above zero), the hold was active and unsettled on Day 4, and Day 4
opened at 650.00. E5 settles for AED 185.00 against a 200.00 hold: a debit of
185.00 posts with value_date Day 4, and the authorization closes.

The implementation detail worth stating, because the brief does not: settling
for **less** than the hold releases the hold **in full**. The 15.00 difference
is not left stranded as a residual hold. A settlement closes its
authorization; that is what a settlement is. See AMBIGUITIES.md #8.

Verified by `Criterion3_AuthASettlementAccepted`.

---

### Criterion 4 — ACCEPTED

> Any settlement referencing an authorization ID not present in the ledger must
> be rejected and the funds must not leave the account.

Correct, and this is the one criterion that is a genuine safety property rather
than an arithmetic claim. E6 settles "Auth-Z", for which no authorization event
exists anywhere in the stream. It is rejected: **no entry is posted**, so
Day 4 closes at 465.00 and not 285.00, and AED 180.00 never appears in the
ledger in any form.

Rejected is not the same as forgotten. The ledger is append-only, so E6 is
recorded as an event and a `REJECTED` decision with its reason. A system that
dropped the message on the floor would be unable to answer "did anyone ever try
to settle Auth-Z", which is precisely the question a fraud investigator asks.

Verified by `Criterion4_UnknownAuthSettlementRejected`.

---

### Criterion 5 — ACCEPTED AS STATED, with a warning

> If Auth-B is approved, its hold reduces available balance but not ledger
> balance.

I am not refusing this one, and I want to be precise about why, because it
would be easy to score it either way.

**As a statement of the rule, it is correct** and the engine implements it. A
hold is not a posting. It never appears in the entry log, it never moves the
ledger balance, and it reduces only the available balance that gates the next
authorization. Auth-A is the working demonstration: on Day 2 the ledger balance
is 250.00, the hold is 200.00, and the available balance is 50.00.

**But its condition never fires. Auth-B is DECLINED.**

E7 is booked on Day 5 and arrives *before* E8 in the stream. By the time E8 is
evaluated, the ledger balance as of Day 5 is already **AED −155.00**
(465.00 − 620.00). Applying a 90.00 hold gives −245.00, which is below zero,
so the rule in the brief — approved only if available "remains at or above zero
after the hold is applied" — refuses it. No hold is placed. Nothing is posted.

So the criterion is a conditional whose antecedent is false. It is not a false
statement, which is why it is not in the refused list. But anyone reading it as
an assertion that Auth-B *is* approved has been caught by the same trap as
criterion 2: forgetting that E7 is back-valued and lands first.

The order matters and nothing else does. Replay the stream with E7 and E9
removed and Auth-B is **APPROVED** — available would have been 465.00 − 90.00 =
375.00. The decline is manufactured entirely by a 620.00 debit that was
withdrawn the next day.

Verified by `Criterion5_HoldsDoNotMoveLedgerBalance`, which asserts both the
decline and the rule the criterion actually states.

---

### Criterion 6 — REFUSED

> After E9, all balances and fees return to their pre-E7 values.

**Refused on three independent grounds. Any one of them is fatal; the third
cannot be fixed by any policy.**

I replayed the stream with E7 and E9 both removed to get the genuine "pre-E7"
world, rather than guessing at it:

| | Actual (E7 then E9) | Pre-E7 world |
|---|---:|---:|
| Day 6 closing balance | **AED 390.93** | **AED 466.03** |
| Overdraft fees | 3, totalling AED 75.00 | 0 |
| Interest capitalised | AED 0.93 | AED 1.03 |
| Auth-B | **DECLINED** | **APPROVED** |

**Ground 1 — the fees remain.** The ledger is append-only. E9 is a compensating
entry, not an eraser. The three fees assessed on Day 5 are still entries in the
book on Day 6, and the closing balance is AED 75.00 lighter than the pre-E7
world for exactly that reason.

**Ground 2 — interest does not return either.** Days 2 through 5 accrued on
balances depressed by the fees: Day 2 accrues 0.09 rather than 0.10, Day 4 0.17
rather than 0.19. The capitalised total is 0.93 against 1.03. The gap between
the two worlds is AED 75.10 — the fees plus ten fils of interest never earned.

**Ground 3 — Auth-B's decline is permanent, and this is the decisive one.**
On Day 5 a customer was refused an authorization because of a balance E7 had
made negative. E9 arrives on Day 6. A reversal can give back money; it cannot
travel back in time and approve a transaction that was declined yesterday. The
merchant has already been told no. Unlike the fees, no refund policy closes
this: the event is not a number in a ledger, it is something that happened in
the world.

That third ground is why I state elsewhere that criterion 6 stays wrong even
after the known design gap in `tests/test_known_design_gap.py` is closed. Refund
every fee and restore every fils of interest, and Auth-B is still declined.

**Being fair to the criterion:** the *principal* does return exactly. Strip the
fee entries out and Day 2 restates to precisely AED 250.00, its pre-E7 figure.
The reversal is arithmetically perfect. What does not return is everything the
original entry *caused* while it stood. A criterion saying "the reversed
entry's own effect is fully undone" would be correct; this one claims far more.

Verified by `Criterion6_RefusedReversalRestoresEverything`.

---

### Criterion 7 — REFUSED

> The three BHD instalments in E10 must each be BHD 3.334.

**BHD 3.334 × 3 = BHD 10.002. The event credits BHD 10.000.**

The criterion invents two millifils that nobody sent. In a real ledger that is
not a rounding quibble, it is an unbalanced posting — the credit side exceeds
the instruction, and the difference has no counterparty. Repeated across a
batch it is a suspense account that grows every day and a reconciliation break
somebody has to chase.

The trap is the word "equal". BHD 10.000 divided by three is 3.333… and **there
is no set of three equal amounts at three decimal places that sums to 10.000**.
Something must give, and the only question is what:

- give up conservation → 3.334 × 3 = 10.002, money created;
- give up conservation the other way → 3.333 × 3 = 9.999, money destroyed;
- give up exact equality → **3.333, 3.333, 3.334 = 10.000**.

Conservation wins. It always wins. Equality between instalments is a
presentational nicety; a ledger that does not conserve value is not a ledger.
The residual minor unit goes on the **last** instalment — an arbitrary but
deterministic choice, documented in AMBIGUITIES.md #7 and NUMBERS.md.

Note this is a BHD-specific problem. The same split in AED (2 dp) would be
3.33, 3.33, 3.34 — and in a currency with no minor units it would be worse.
`split_into_instalments` works in whole minor units and raises if the parts
ever fail to sum to the total, so the invariant is enforced rather than hoped
for.

Verified by `Criterion7_RefusedInstalmentsOf3334`.

---

### Criterion 8 — REFUSED

> If the rounded daily interest accruals do not sum to the capitalised total,
> the remainder is discarded.

**Refused twice over: it contradicts the brief, and it describes a situation
this design cannot be in.**

*First*, it is flatly inconsistent with a non-negotiable rule stated a few
lines earlier in the same brief:

> The rounded daily accruals must sum exactly to the capitalised total.

"Must sum exactly" and "if they do not sum, discard the difference" cannot both
be requirements. The second is an escape hatch from the first, and a rule with
an escape hatch is not a rule.

*Second*, there is no remainder to discard, because the capitalised total **is**
the sum of the rounded dailies. That is the only construction under which the
non-negotiable rule holds by design rather than by luck, so it is the one I
built. There is no parallel unrounded running total from which the capitalised
figure could drift.

The distinction the criterion misses is *sum-then-round* versus
*round-then-sum*, and for ACC-001 they genuinely differ:

| Day | Basis | Exact accrual | Rounded |
|-----|------:|--------------:|--------:|
| 1 | 250.00 | 0.100000 | 0.10 |
| 2 | 225.00 | 0.090000 | 0.09 |
| 3 | 625.00 | 0.250000 | 0.25 |
| 4 | 415.00 | 0.166000 | **0.17** |
| 5 | 390.00 | 0.156000 | **0.16** |
| 6 | 390.00 | 0.156000 | **0.16** |
| | | **0.918000** | **0.93** |

Round the exact sum once and you get **AED 0.92**. Sum the rounded dailies and
you get **AED 0.93**. The brief mandates the second, so the customer is one
fils better off and the bank wears it.

That one fils is not a remainder — it is the cost of the accounting method the
brief chose, and it is *already inside* the capitalised figure. There is
nothing left over. Discarding anything would mean the daily statements and the
capitalisation entry disagreed, which is the exact failure the non-negotiable
rule exists to prevent.

Had a remainder somehow existed, discarding it would still be the wrong answer.
Money that leaves one side of a ledger has to arrive somewhere; "discarded" is
not a destination. The right treatments are to carry it forward to the next
period, or to book it to a rounding-difference account where it can be
reconciled. Both keep the books balanced. Discarding does not.

Verified by `Criterion8_RefusedDiscardTheRemainder`.

---

## Part 2 — Approaches abandoned mid-build

### A single running balance per account

The first ten minutes. An `Account` with a `balance` field, updated as entries
were applied.

Killed by E7. A running total can hold exactly one answer to "what did Day 2
close at", and this scenario requires two: AED 250.00 as believed on Day 2, and
AED −370.00 once E7 arrived on Day 5. Criterion 1 explicitly asks for the
second while the Day-2 report needs the first.

Replaced by projections over two coordinates — `value_date` and `booked_day` —
with no stored totals at all. `closing_balance(day, known_through)` answers both
questions from the same entry log. Everything downstream got simpler: fee
reassessment and interest revision are both just the same projection evaluated
with a later `known_through`.

The cost is that every balance is an O(entries) scan. At six days and eleven
entries that is irrelevant. At production scale it would need a materialised
snapshot per (account, value_date) invalidated on backdated arrival — but that
is a cache over this model, not a different model, which is the point.

### A single linear pass for overdraft fees

First implementation swept days 1..N once, assessing a fee wherever the closing
balance was negative.

Wrong, and — worse — it produced the right answer for this scenario, which is
how bugs survive. A fee is value-dated to the day it is assessed for, so
booking the Day-2 fee lowers Days 3, 4 and 5 too and can push a day negative
that was positive when the pass looked at it. Here it does not quite happen:
Day 3 sits at 30.00 before the Day-2 fee and 5.00 after, positive either way.
At a fee above AED 30.00 the single pass would miss the Day-3 fee entirely.

Replaced with a loop to a fixpoint: keep sweeping until a pass assesses nothing.
Terminates trivially, since each pass either assesses a fee for a day that had
none or stops, and there are finitely many days.

### Compute each day's interest once and never revisit it

Tempting, and wrong for the same reason a running balance is wrong. Value-dating
exists *because* interest depends on when money was actually available. A debit
back-valued to Day 2 means the customer did not have that money from Day 2
onward, and the Days 2–4 accruals computed on the old balances are simply
incorrect. Keeping them would make the capitalised total the sum of six figures
that no longer describe the account.

Replaced with a recomputation sweep on every close. Append-only is respected by
never editing an accrual record: a revision appends a **delta**, and a day's net
accrual is the sum of its records. Day 2's accrual was written three times —
0.10 on Day 2, struck to 0.00 on Day 5 when E7 landed, restored to 0.09 on Day 6
after E9 — and all three records survive. The audit trail shows the correction
instead of hiding it, and the net is still exactly `round(225.00 × 0.0004)`.

### Mutable holds

`account.holds[auth_id] -= settled_amount`, with the entry deleted at zero.

Abandoned as soon as I wrote the append-only rule down. A decremented hold
cannot answer "what was held on Day 3", and a deleted one cannot answer "was
Auth-A ever authorised". Replaced by an append-only hold log of PLACED and
RELEASED records, with "what is held right now" derived from it. `HoldState` is
reconstructed by folding the log, never stored.

This also made the declined Auth-B representable at all. A mutable dict has
nowhere to put "someone asked for a 90.00 hold and was refused" — there is no
hold to record. The log has the decision, so the report can show Auth-B as
DECLINED on Day 5 rather than simply omitting it.

### Floating-point amounts

Never seriously entertained, but I checked rather than repeating folklore.
Sweeping every AED balance from 0.00 to 2000.00 and comparing
`round(float(b) * 0.0004, 2)` against `Decimal` with ROUND_HALF_UP gives **14
divergences**. The first is at AED 187.50. One is at **AED 462.50** — five
dirhams from this scenario's actual Day 4 balance of 465.00 — where float says
0.18 and the correct answer is 0.19.

Two separate faults compound there: binary representation, and Python's `round`
being half-to-even where a retail ledger wants half-up. Pinned as a test in
`tests/test_money.py` so the justification is executable.

### Processing the stream in listed order

The brief says "replayed in this order", and the listed order puts E10 (booked
Day 5) after E9 (booked Day 6). Taken literally that asks the ledger to close
Day 6 and then post into Day 5.

Abandoned in favour of grouping by `booked_day`, preserving stream order
*within* each day — which is what actually matters, because E7 must precede E8
on Day 5 and that ordering is what declines Auth-B.

Rather than assert the two readings agree, I tested it: replaying with E10 moved
before E9 produces identical closing balances on every day for both accounts,
because E9 touches ACC-001 and E10 touches ACC-002 and the two never interact.
If a future stream made them touch the same account, that test starts failing —
which is the point of writing it as a test rather than a comment.

### Refunding consequential fees on reversal

Written, then pulled back out, and the hole it left is the deliberately failing
test.

The argument for it is strong and I make it at length in
`tests/test_known_design_gap.py`: after E9, no day in the window closes
negative, so the customer is AED 75.00 down for an overdraft the ledger's own
final numbers say never happened. Append-only does not forbid the fix either —
a compensating FEE_REVERSAL entry is the same mechanism E9 already uses.

I pulled it because implementing it means silently answering a question the
brief does not answer: whether a fee assessed correctly on the information
available at the time survives a later restatement. That is a commercial policy
decision, banks genuinely differ on it, and a plausible-looking implementation
would bury the choice where no reviewer would find it. It also has real teeth —
reversing the Day-2 fee lifts Days 3, 4 and 5, which may unjustify their fees in
turn, so it needs a second fixpoint loop running opposite to the first, and the
two can oscillate unless "once per day" is read as "once ever" rather than "once
currently in force".

So the decision has a name (`Policy.reversal_refunds_consequential_fees`,
default `False`), the gap is documented, and a failing test makes sure it is
decided rather than inherited. Setting the flag `True` raises rather than
quietly doing nothing — it marks where the choice lives, it is not a working
switch, and pretending otherwise would be its own small lie.
