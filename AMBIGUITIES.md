# AMBIGUITIES

Twenty-two places where the brief admits more than one reading, what I chose,
and what it would have cost to choose otherwise.

The numbering is stable: source comments cite these by number
(`AMBIGUITIES.md #10`), so entries are never renumbered. Items marked
**outcome-changing** would produce different published figures under the other
reading — those are the ones worth arguing about. The rest are decisions that
happen not to bite in this particular stream, which is exactly why they need
writing down: nothing in the output would tell you they were ever in question.

---

## Time and ordering

### #1 — What a "day" is — **not outcome-changing**

The brief gives Day 1 to Day 6 and no clock, timezone, or cut-off time. Days
are modelled as bare ordinals (`Day = int`), with opening balances at Day 0.

Chosen because inventing timestamps would smuggle in a cut-off policy nobody
specified — and a cut-off is a real commercial decision. If a ledger runs its
day-end at 23:00 Gulf Standard Time, a transaction at 23:30 belongs to
tomorrow, and "which day did this land in" becomes a question with a
configurable answer. The brief sidesteps that entirely, so the model does too.

The cost: this ledger cannot express two entries on the same day in a defined
order except by stream position. It does not need to here.

### #2 — Stream order contradicts booked-day order — **not outcome-changing (verified)**

The brief says "replayed in this order", and then lists E10 (booked Day 5)
*after* E9 (booked Day 6). Read literally that asks the ledger to close Day 6
and then post into Day 5, which no ledger can do.

**Chosen:** group by `booked_day`, preserve stream order *within* a day. The
within-day order is the part that matters — E7 must precede E8 on Day 5, and
that ordering is exactly what declines Auth-B.

I did not take on faith that the readings agree. `test_stream_order_and_
booked_day_order_agree_for_this_stream` replays with E10 moved ahead of E9 and
asserts identical closing balances for every day and both accounts. They agree
because E9 touches ACC-001 and E10 touches ACC-002, and the two never interact.
If that ever stops being true the test fails, which is why it is a test and not
a sentence.

### #14 — Forward value-dating — **does not arise**

Every event in the stream has `value_date ≤ booked_day`. Nothing says what a
forward-valued entry would mean.

**Chosen:** reject at construction. A future-valued entry raises rather than
posting. It would need an answer to whether it counts toward available balance
before its value date — a real question with real fraud implications — and
guessing an answer that is never exercised is worse than refusing.

---

## Overdraft fees

### #3 — Which day "the day assessed" means — **not outcome-changing (verified)**

"Booked with value_date equal to the day assessed." When a Day-5 sweep notices
that Day 2 closed negative, is the fee value-dated to Day 2 (the day assessed
*for*) or Day 5 (the day the assessment *ran*)?

**Chosen:** Day 2 — the day whose balance was negative. It is the reading that
makes criterion 1's careful phrase "before any fee is assessed" meaningful, and
it keeps the fee attached to the fact that justified it.

Both are implemented (`Policy.fee_value_dated_to_assessment_day`) because
REJECTED.md claims criterion 2 is wrong either way, and I wanted that to be a
test rather than a promise. Three fees under both readings; only the
`value_date` stamps move. The Day-6 closing balance is identical, since all
fees land inside the window either way.

### #4 — Whether a fee can trigger another fee — **outcome-changing**

The fee is a ledger entry value-dated to a day inside the window, so it lowers
that day's closing balance *and every later day's*. It can therefore push a day
negative that was positive before the fee existed.

**Chosen:** yes, fees cascade, and assessment loops to a fixpoint. A fee is a
real debit; pretending it does not affect later balances would mean the printed
closing balance and the balance used for fee decisions were different numbers.

It does not bite here — Day 3 closes at 30.00 before the Day-2 fee and 5.00
after, positive either way — but it is five dirhams from biting. At any fee
above AED 30.00 the cascade produces a fourth fee on Day 3. A single linear
pass would silently miss it (see REJECTED.md, abandoned approaches).

### #5 — Whether a fee survives a restatement that removes its cause — **outcome-changing**

After E9, no day in the window closes negative. Three fees remain on the book
for an overdraft the ledger's final state says did not happen.

**Chosen:** fees stand. `Policy.reversal_refunds_consequential_fees = False`.

This is the most consequential judgement call in the build and I am least
comfortable with it. The argument for standing pat: the fees were correctly
assessed on Day 5 against everything then known, the ledger is append-only, and
whether a correct-at-the-time charge survives later information is a commercial
policy question the brief does not answer.

The argument against: the customer is AED 75.00 poorer for a transaction that
was withdrawn, and append-only does not actually require that — a compensating
FEE_REVERSAL entry is the same mechanism E9 itself uses.

Rather than pick quietly, I left it as the deliberately failing test
(`tests/test_known_design_gap.py`), which forces a reviewer to decide instead
of inheriting my choice.

### #6 — Which balance the fee test looks at — **not outcome-changing**

A fee makes its own day's balance more negative. If the trigger test ran on the
post-fee balance, every fee would justify itself forever.

**Chosen:** the trigger test reads the day's balance *before* that day's own fee
— enforced by checking "has this day already been charged" first. Fees
value-dated to *earlier* days are included, because those are real debits that
genuinely lowered this day. That asymmetry is deliberate, and it is what makes
the fixpoint converge instead of spinning.

### #12 — No overdraft fee for BHD — **does not arise, but guarded**

AED 25.00 is given. Nothing is given for BHD.

**Chosen:** the fee table is keyed by currency and BHD is deliberately absent.
An overdrawn BHD account raises `PolicyNotConfigured` rather than posting 25 of
something into a 3 dp account.

ACC-002 is never negative, so this never fires. It is guarded anyway because a
default here would be invisible and wrong: 25.00 as a BHD amount is 25 dinars,
roughly 24 times the AED fee. A silent default would be a plausible-looking
number that is off by an order of magnitude.

### #13 — Whether the fee scales with the overdraft — **not outcome-changing**

"Overdraft fee: AED 25.00" is flat, with no tiering, no per-day-outstanding
accrual, no cap.

**Chosen:** flat, exactly once per day, no cap across the window. ACC-001 pays
three, totalling AED 75.00 against a peak overdraft of AED 370.00 — a little
over 20%. Many jurisdictions cap total overdraft charges per period. None is
specified, so none is applied, but the absence is a choice and not an oversight.

---

## Interest

### #15 — Whether backdating revises past accruals — **outcome-changing**

E7 changes what Days 2, 3 and 4 closed at. Their accruals were computed on the
old figures.

**Chosen:** recompute every past day on every close. Value-dating exists
*because* interest depends on when money was actually available; leaving the old
accruals would make the capitalised total the sum of six numbers that no longer
describe the account.

Append-only is honoured by appending a **delta**, never editing. Day 2's accrual
was written three times — 0.10 on Day 2, struck to 0.00 on Day 5 when E7
landed, restored to 0.09 on Day 6 after E9 — and all three records survive. Net
is the sum, and it equals `round(225.00 × 0.0004)` exactly.

Cost: AED 0.93 capitalised rather than the 1.03 a never-revise design would
produce.

### #16 — Whether Day 6 accrues before capitalising — **outcome-changing**

Accruals "capitalize as a single credit at end of Day 6". Does Day 6 itself
accrue, and on which balance?

**Chosen:** Day 6 accrues, on its closing balance *before* capitalisation.
Otherwise interest earns interest inside a window the brief describes as simple
daily accrual, and the "single credit" would be partly circular.

Made explicit rather than implicit: `Book.interest_basis` excludes
capitalisation entries by kind. Originally this was correct only because the
accrual sweep happened to run before capitalisation in `close_day` — true, but
a refactor away from being wrong. Six accruals, not five; ACC-001 would
capitalise 0.77 instead of 0.93 if Day 6 were excluded.

### #17 — Round each day, or round the total — **outcome-changing, settled by the brief**

**Settled:** "The rounded daily accruals must sum exactly to the capitalised
total" forces round-then-sum. The capitalised figure *is* the sum of the rounded
dailies, which is the only construction where that rule holds by design.

Worth recording because the two differ here: the exact accruals total 0.918000,
which rounds to **0.92**, while the rounded dailies sum to **0.93**. One fils,
in the customer's favour, and it is a property of the mandated method rather
than an error. See REJECTED.md criterion 8.

### #18 — Rounding mode — **not outcome-changing in this stream**

Not specified.

**Chosen:** ROUND_HALF_UP. It is the retail-banking convention and it matches
what a customer checking the arithmetic by hand expects. Python's built-in
`round` is half-to-even, which would quietly disagree.

No accrual in this scenario lands on an exact tie, so the choice changes nothing
here — but it is one balance away from mattering. A balance of AED 412.50
accrues exactly 0.165: half-up gives 0.17, half-even gives 0.16.

### #19 — Zero balances — **not outcome-changing**

"Positive balances only." Zero is not positive, so a flat account accrues
nothing. ACC-002 accrues 0.000 on Days 1–4. The same answer falls out of the
arithmetic anyway, since 0 × 0.0004 = 0, but the rule is implemented as stated
rather than relied on numerically.

### #20 — Debit interest — **not outcome-changing**

"Positive balances only" says what happens on credit balances and is silent on
debit ones. **Chosen:** overdrawn days accrue nothing at all — no debit
interest. The brief's answer to a negative balance is the AED 25.00 fee;
charging interest as well would be inventing a second penalty. ACC-001 accrues
0.00 on Days 2, 4 and 5 under the Day-5 view.

### #21 — The dust threshold — **not outcome-changing, but visible in the output**

Not an ambiguity so much as a consequence nobody would predict. Rounding each
daily accrual to 2 dp means any AED balance below **12.50** accrues literally
nothing: 12.49 × 0.0004 = 0.004996, which rounds to 0.00.

This is visible in the run. Under the Day-5 view, Day 3 closes at AED 5.00 and
accrues 0.00. It is correct under the mandated method and it is the kind of
thing that generates a customer complaint, so it is documented rather than
buried. The BHD equivalent threshold is 1.25.

---

## Authorizations, settlements and holds

### #7 — Splitting an amount that will not divide — **outcome-changing**

"BHD 10.000, posted as three equal instalments." No three equal 3 dp amounts sum
to 10.000.

**Chosen:** conservation over equality — 3.333, 3.333, **3.334**, with the
residual minor unit on the **last** instalment. Tail rather than head is
arbitrary but deterministic, and it leaves the earlier instalments as the clean
repeated figure a customer expects. Full argument in REJECTED.md criterion 7.

### #8 — Settling for less than the hold — **outcome-changing**

E5 settles Auth-A for AED 185.00 against a 200.00 hold. Does the remaining
15.00 stay held?

**Chosen:** the settlement closes the authorization and releases the hold in
full. That is standard card behaviour and it matches what "settles" means: the
transaction is finished. Leaving a 15.00 residue would require an expiry policy
to ever clear it (#11), and the brief supplies none.

Outcome-changing in a narrow way: a residual hold would leave ACC-001's
available balance 15.00 lower from Day 4 onward. No *ledger* balance moves, and
Auth-B is declined either way — it would face −170.00 rather than −155.00 — so
no published closing balance changes. The available-balance column for Days 4
through 6 does.

### #9 — Settling for more than the hold — **does not arise**

**Chosen:** permitted (`allow_settlement_over_hold = True`). Card schemes allow
settlement overage, and the alternative — rejecting a settlement for a
transaction the customer genuinely made — is worse than letting the balance go
negative, which this ledger handles with a fee. Configurable, and never
exercised: E5 settles under its hold.

### #10 — Whether a debit can be refused — **outcome-changing**

E7 drives ACC-001 to −155.00. Should it have been rejected?

**Chosen:** no. Debits post unconditionally. The brief gates *authorizations* on
available balance and answers an overdrawn ledger with a *fee* — which only
makes sense if balances are allowed to go negative. A ledger that refused E7
would never assess an overdraft fee at all, making that rule dead code.

The asymmetry is the point and it is how real systems work: an authorization is
a request you can decline, a settled debit is a fact you must record.

### #11 — Hold expiry — **does not arise**

"Auth-B is never settled inside the window." Card holds normally expire after
some days.

**Chosen:** no expiry (`hold_expiry_days = None`). No period is specified, and
inventing one — 3 days? 7? — would change results arbitrarily. Setting it
raises rather than silently doing nothing, since no expiry logic exists behind
the name. Auth-B is
declined so it places no hold anyway; had it been approved, its 90.00 would
have stayed held through Day 6.

### #22 — Whether a declined authorization is recorded — **not outcome-changing**

**Chosen:** yes. Auth-B leaves an event, a `DECLINED` decision with its reason,
and a line in the Day 5 report. No hold, no entry, no movement of money.

Append-only means the ledger remembers refusals, not just successes. A system
that dropped E6 and E8 on the floor could not answer "did anyone try to settle
Auth-Z" or "why was this customer declined" — the two questions most likely to
be asked about this window.

---

## Accounts

### Opening balances as entries — **not outcome-changing**

Both accounts open at zero. **Chosen:** post an explicit opening entry anyway,
value-dated Day 0. It costs one row per account and it means an account's
balance is always simply the sum of its entries, with no special case for where
the opening figure went. At zero it is invisible; at a non-zero opening it is
the difference between a ledger and a ledger with an asterisk.
