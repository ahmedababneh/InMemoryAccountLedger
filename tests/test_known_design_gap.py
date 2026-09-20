"""THE ONE FAILING TEST. It is supposed to fail. Do not "fix" it.

`python3 -m unittest discover tests` reports 64 passes and this single
failure. It is not a broken assertion left behind by accident; it is the
deliverable the brief asks for -- a test written against my own design that
the design does not satisfy, kept in the suite so the gap cannot be forgotten.

It is annotated inline. The short version: this ledger charges AED 75.00 of
overdraft fees for an overdraft that, by the end of the window, the ledger
itself says never happened.

Run just this file:

    python3 -m unittest tests.test_known_design_gap -v
"""

import unittest

from .support import replayed
from ledger.money import AED


class ReversalDoesNotUnwindConsequentialFees(unittest.TestCase):

    def test_fees_caused_solely_by_an_entry_that_was_reversed_are_not_refunded(self):
        book = replayed().book

        # ---- Setup: establish that E7 is the sole cause of every fee --------
        #
        # E7 is a DEBIT of AED 620.00 booked on Day 5 and value-dated back to
        # Day 2. Before it arrived, no day in the window had closed negative:
        # Day 1 250.00, Day 2 250.00, Day 3 650.00, Day 4 465.00. The account
        # had never been overdrawn and no fee had ever been assessed.
        self.assertEqual(len(list(book.fees)), 3)  # all three, and all assessed on Day 5
        self.assertEqual({f.assessed_on for f in book.fees}, {5})

        # E9, booked Day 6, reverses E7 in full and at the same value date
        # (Day 2). It is a complete, exact, same-day-valued reversal -- not a
        # partial refund, not a correction with a different effective date.
        original = book.entries_for_event("E7")[0]
        compensating = book.entries_for_event("E9")[0]
        self.assertEqual(compensating.amount, -original.amount)
        self.assertEqual(compensating.value_date, original.value_date)

        # ---- The state the ledger ends in -----------------------------------
        #
        # With both entries present, NO day in the window closes negative.
        # Every one of the three days that was charged a fee is, in the
        # ledger's own final account of itself, a day the customer was in
        # credit. Days 2, 4 and 5 restate to 225.00, 415.00 and 390.00 --
        # except those figures are already NET of the fees, so the ledger is
        # only in credit on those days because... it is in credit on those
        # days. The overdraft it was punished for is gone.
        for day, fee in ((2, True), (3, False), (4, True), (5, True)):
            restated = book.closing_balance("ACC-001", day)
            self.assertFalse(
                restated.is_negative(),
                f"Day {day} restates to {restated}, not negative",
            )
            self.assertEqual(book.fee_for_day("ACC-001", day) is not None, fee)

        # ---- What this design does about that: nothing ----------------------
        #
        # Policy.reversal_refunds_consequential_fees is False. The three fees
        # stand. The customer pays AED 75.00 for a Day-2 overdraft that the
        # ledger's final state says did not occur, caused entirely by an entry
        # that was withdrawn.
        fees_charged = AED.zero()
        for fee in book.fees:
            fees_charged = fees_charged + fee.amount

        # ---- The assertion, and why it is the right one to write ------------
        #
        # A fee is a charge levied on a customer for a fact about their
        # account. When the only entry supporting that fact is withdrawn, the
        # charge is no longer supported by anything. I can defend not
        # *deleting* the fee -- the ledger is append-only, and the fee was
        # correctly assessed on Day 5 against everything then known. I cannot
        # defend the customer still being AED 75.00 down on Day 6. Those are
        # different claims, and this design conflates them: it treats "the
        # record is immutable" as though it implied "the money stays taken".
        #
        # Append-only does not force this outcome. The correct fix is a
        # compensating FEE_REVERSAL entry -- exactly the mechanism E9 already
        # uses for E7 -- posted when a restatement leaves a fee's triggering
        # day non-negative. Both the fee and its reversal would remain in the
        # book forever. The audit trail would be strictly richer, not poorer.
        #
        # This assertion therefore states what the ledger should do, and fails.
        self.assertEqual(
            fees_charged, AED.exact("0.00"),
            "\n\n"
            "    WHAT THIS FAILURE REVEALS\n"
            "    -------------------------\n"
            "    A reversal unwinds its own entry and nothing that entry caused.\n"
            "    E9 gives back the 620.00 but not the 75.00 of overdraft fees\n"
            "    that only E7 could have triggered, so the customer ends the\n"
            "    window 75.00 poorer for a transaction that was withdrawn and a\n"
            "    negative balance that, on the ledger's own final numbers,\n"
            "    never existed.\n"
            "\n"
            "    This is a policy gap, not an arithmetic bug. Every individual\n"
            "    step is defensible: the fees were correct when assessed on\n"
            "    Day 5, and append-only correctly forbids deleting them. The\n"
            "    gap is that nothing re-examines a fee after the facts beneath\n"
            "    it change. The engine re-sweeps every past day to ADD fees a\n"
            "    backdated entry newly justifies (that is why there are three)\n"
            "    but the sweep is one-directional: it never asks whether a fee\n"
            "    it already booked has lost its justification.\n"
            "\n"
            "    Why it is not fixed: refunding requires answering a question\n"
            "    the brief does not answer -- whether a fee assessed correctly\n"
            "    on the information available at the time survives a later\n"
            "    restatement. Real banks differ, and it is a commercial policy\n"
            "    decision rather than a ledger-mechanics one. Guessing would\n"
            "    hide the choice; failing here makes someone make it. The hook\n"
            "    is already in place: Policy.reversal_refunds_consequential_fees.\n"
            "\n"
            "    What the fix would cost: assess_overdraft_fees() gains a second\n"
            "    pass that posts a FEE_REVERSAL for any assessed fee whose\n"
            "    triggering day no longer closes negative once its own fee is\n"
            "    excluded. It needs care -- reversing the Day-2 fee lifts Days\n"
            "    3, 4 and 5, which may unjustify their fees in turn -- so it is\n"
            "    a second fixpoint loop running in the opposite direction, and\n"
            "    the two together can oscillate unless the 'once per day' rule\n"
            "    is read as 'once ever', not 'once currently in force'.\n"
            "\n"
            "    What it does NOT reveal: any disagreement with acceptance\n"
            "    criterion 6. That criterion claims balances and fees return to\n"
            "    their pre-E7 values, and it is still wrong even if this gap is\n"
            "    closed, because Auth-B's Day-5 decline is permanent no matter\n"
            "    what happens to the fees. See REJECTED.md.\n"
        )


if __name__ == "__main__":
    unittest.main()
