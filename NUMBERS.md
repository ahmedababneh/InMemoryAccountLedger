# NUMBERS

Every constant in this system, where it lives, why it is that value, and what
changes if you halve it.

All constants live in `ledger/policy.py` or `ledger/money.py`. Nothing in the
engine hardcodes a rate, a fee, a precision or a day count; a reviewer who
wants to challenge a number changes it in one place and re-runs `run.py`.

The "why not half it" column is not rhetorical. Every sensitivity below was
measured by re-running the replay with the value changed, not reasoned about.
Two of them surprised me.

---

## The constants

| Constant | Value | Where | Source |
|----------|-------|-------|--------|
| Overdraft fee, AED | 25.00 | `OverdraftPolicy.fees` | given |
| Overdraft fee, BHD | *deliberately absent* | `OverdraftPolicy.fees` | chosen |
| Daily interest rate | 0.0004 (0.04%/day) | `InterestPolicy.daily_rate` | given |
| Credit-only interest | `True` | `InterestPolicy.credit_only` | given |
| AED minor units | 2 | `money.AED` | given / ISO 4217 |
| BHD minor units | 3 | `money.BHD` | given / ISO 4217 |
| Rounding mode | `ROUND_HALF_UP` | `Currency.round` | chosen |
| Window | Day 1 – Day 6 | `Policy.first_day/last_day` | given |
| Opening balances | 0.00 / 0.000 | `scenario.py` | given |
| E10 instalments | 3 | `scenario.py` | given |
| Residual instalment | last | `split_into_instalments` | chosen |
| Fee value-dating | day assessed *for* | `Policy.fee_value_dated_to_assessment_day` | chosen |
| Settlement releases full hold | `True` | `Policy.settlement_releases_full_hold` | chosen |
| Settlement may exceed hold | `True` | `Policy.allow_settlement_over_hold` | chosen |
| Hold expiry | `None` | `Policy.hold_expiry_days` | chosen |
| Reversal refunds fees | `False` | `Policy.reversal_refunds_consequential_fees` | chosen |

---

## Overdraft fee — AED 25.00

**Given by the brief.** Kept as configuration rather than a literal because
the interesting property is not its value but its *cascade threshold*.

**Why not half it?** Halving it to 12.50 changes the money but not the
structure — still three fees, on Days 2, 4 and 5. What matters is the other
direction. A fee is value-dated to the day it is assessed for, so it lowers
every later day too, and above a threshold it pushes Day 3 negative and earns a
fourth fee:

| Fee | Days charged | Count | ACC-001 Day 6 close |
|-----|--------------|:-----:|--------------------:|
| 0.00 | 2, 4, 5 | 3 | 466.03 |
| 12.50 | 2, 4, 5 | 3 | 428.48 |
| **25.00** | **2, 4, 5** | **3** | **390.93** |
| 29.99 | 2, 4, 5 | 3 | 375.93 |
| 30.00 | 2, 4, 5 | 3 | 375.90 |
| 30.01 | 2, **3**, 4, 5 | 4 | 345.82 |
| 50.00 | 2, 3, 4, 5 | 4 | 265.75 |

**The threshold is exactly AED 30.00, and it is exclusive.** At 30.00 Day 3
closes at precisely 0.00, and zero is not negative, so no fee. At 30.01 it tips.

That is the answer to "why that value and not half it": at 25.00 this scenario
sits **five dirhams** from a qualitatively different result. The margin comes
from Day 3's balance of 30.00 before its fee — E1 1,200.00 − E2 950.00 − E7
620.00 + E4 400.00. Nothing in the output warns you how close that is, which is
why it is written down here.

## Overdraft fee, BHD — deliberately absent

**Chosen.** The brief prices an overdraft in AED and says nothing about BHD.
The fee table is keyed by currency and has no BHD entry, so an overdrawn BHD
account raises `PolicyNotConfigured` rather than posting a number nobody chose.

**Why not default it to 25?** Because BHD 25.000 is about 24 times the AED fee
— roughly USD 66 against USD 6.80. A default here would be invisible, plausible
and wrong by an order of magnitude. ACC-002 never goes negative so this never
fires; it is guarded because the failure mode is silent.

## Daily interest rate — 0.04% per day

**Given by the brief.** Stored as `Decimal("0.0004")`, never a float.

**Why not half it?** Because halving the rate does *not* halve the interest, and
this is the result I did not predict:

| Rate | ACC-001 daily accruals | Capitalised |
|------|------------------------|------------:|
| 0.02%/day | 0.05, 0.05, 0.13, 0.08, 0.08, 0.08 | **AED 0.47** |
| **0.04%/day** | **0.10, 0.09, 0.25, 0.17, 0.16, 0.16** | **AED 0.93** |
| 0.08%/day | 0.20, 0.18, 0.50, 0.33, 0.31, 0.31 | AED 1.83 |

Half of 0.93 is 0.465. The answer at half the rate is **0.47**, and at double
the rate it is 1.83 rather than 1.86. Rounding six daily figures independently
is not linear in the rate, so you cannot scale the output by scaling the input.
For a bank pricing a product across a portfolio, that non-linearity is the
whole reason the daily figures have to be computed rather than extrapolated.

At 0.04%/day the annualised simple rate is about **14.6%**, which is a credible
retail deposit rate in neither direction — high for a current account, low for
an overdraft — but it is what the brief specifies.

**The dust threshold.** Rounding each accrual to the currency's precision means
small balances accrue *nothing*:

- AED: any balance below **12.50** accrues 0.00 (12.49 × 0.0004 = 0.004996).
- BHD: any balance below **1.250** accrues 0.000.

This is visible in the output. Under the Day-5 view, Day 3 closes at AED 5.00
and accrues nothing at all. Correct under the mandated method, and exactly the
sort of thing that produces a customer query.

## Credit-only interest — `True`

**Given:** "positive balances only". Zero is not positive, so a flat account
accrues nothing either — ACC-002 accrues 0.000 on Days 1–4.

**Why not accrue on debit balances too?** Because the brief already answers a
negative balance with the AED 25.00 fee. Charging debit interest as well would
be a second penalty nobody specified. ACC-001 accrues 0.00 on Days 2, 4 and 5
under the Day-5 view, which is the single largest reason the capitalised total
is 0.93 rather than 1.03.

## Precision — AED 2, BHD 3

**Given, and correct per ISO 4217.** AED has 2 minor units (fils), BHD has 3
(also fils; a Bahraini dinar is 1,000 fils). Precision is a property of the
`Currency`, never a global constant, and `Money` *rejects* construction at the
wrong precision rather than rounding silently.

**Why not run everything at 3 dp and round at the edges?** Because the rounding
would then happen wherever a value happened to leave the system, which is
untraceable. Rejecting AED 3.334 at construction means a fils-level amount can
never enter an AED account by accident. `Currency.round` is the only way to
change precision, so every rounding site is greppable.

**Why not more precision internally?** There *is* more precision internally —
`Money.scaled_by` returns an unrounded `Decimal` on purpose, and the interest
computation carries full precision right up to the single explicit rounding
call. What is constrained is *storage*, which is what the brief asks for.

## Rounding mode — ROUND_HALF_UP

**Chosen; the brief does not say.** Half-up is the retail-banking convention
and matches what a customer checking the arithmetic by hand expects. Python's
built-in `round` is half-to-even and would quietly disagree.

**Why not banker's rounding?** ROUND_HALF_EVEN is the better choice
statistically — it removes the upward bias that half-up introduces across many
roundings, which matters at portfolio scale. I chose half-up anyway because
this is a customer-facing retail ledger where being explicable beats being
unbiased, and because a customer told their 0.165 became 0.16 has a fair
complaint.

**Does it matter here?** Not in this stream: no accrual lands on an exact tie.
It is one balance away from mattering — AED 412.50 accrues exactly 0.165, where
half-up gives 0.17 and half-even 0.16.

**Why Decimal rather than float at all?** Measured rather than assumed.
Sweeping every AED balance from 0.00 to 2,000.00 and comparing
`round(float(b) * 0.0004, 2)` against Decimal half-up produces **14
divergences**, the first at AED 187.50. One is at **AED 462.50** — five dirhams
from this scenario's real Day 4 balance of 465.00 — where float gives 0.18 and
the correct answer is 0.19. Pinned as a test in `tests/test_money.py`.

## Window — Day 1 to Day 6

**Given.** Capitalisation lands on `last_day`.

**Why not halve it to three days?** The scenario stops working: E5's settlement,
E7's backdated debit, E8's authorization and E9's reversal all live on Days 4–6,
so a three-day window tests none of the behaviour the exercise is about. Six
days is the minimum that admits a back-valued entry (Day 5 → Day 2) *and* a
reversal of it (Day 6) *and* a capitalisation after both.

**Why not more?** Nothing breaks, and nothing new is exercised. The engine
re-sweeps every day in the window on every close — O(days² × entries) — which
is free at six days and would need the materialised snapshot described in
REJECTED.md at a real horizon.

## Instalments — 3, residual on the last

**Count given; allocation chosen.** BHD 10.000 into three cannot be three equal
3 dp amounts, so the split is 3.333, 3.333, **3.334**.

**Why the last and not the first?** Purely a tie-break: both conserve the total,
which is the only property that matters. The tail keeps the earlier instalments
as the clean repeated figure a customer expects to see, and it is deterministic,
which beats "spread the residual randomly" for reconciliation.

**Why not 3.334 each?** That sums to 10.002 and credits money nobody sent. See
REJECTED.md criterion 7.

## Policy flags with no scenario coverage

Four flags exist for behaviour the stream never exercises. Each is a deliberate
choice recorded in AMBIGUITIES.md rather than an accident:

| Flag | Value | Why |
|------|-------|-----|
| `settlement_releases_full_hold` | `True` | A settlement closes its authorization; E5's 15.00 shortfall is not left stranded. |
| `allow_settlement_over_hold` | `True` | Card schemes permit overage; refusing a transaction the customer genuinely made is worse than a negative balance, which this ledger already handles. |
| `hold_expiry_days` | `None` | No period is specified and inventing one (3 days? 7?) would change results arbitrarily. |
| `reversal_refunds_consequential_fees` | `False` | The one I am least comfortable with. Left as the deliberately failing test rather than decided quietly. See `tests/test_known_design_gap.py`. |

---

## The output, for reference

Produced by `python3 run.py`.

**ACC-001 (AED)** — closing balances

| Day | As believed that day | Restated at end of Day 6 |
|-----|---------------------:|-------------------------:|
| 1 | 250.00 | 250.00 |
| 2 | 250.00 | 225.00 |
| 3 | 650.00 | 625.00 |
| 4 | 465.00 | 415.00 |
| 5 | **−230.00** | 390.00 |
| 6 | 390.93 | 390.93 |

Three overdraft fees (AED 75.00), all assessed on Day 5, value-dated to Days 2,
4 and 5. Interest capitalised AED 0.93. Auth-A approved and settled; Auth-Z
rejected; Auth-B declined.

**ACC-002 (BHD)** — closes Day 6 at **BHD 10.008**: three instalments of 3.333,
3.333 and 3.334 on Day 5, plus BHD 0.008 capitalised interest. No fees.
