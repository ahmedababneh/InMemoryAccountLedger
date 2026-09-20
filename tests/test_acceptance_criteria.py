"""One test per acceptance criterion.

Four of the eight criteria are wrong. They are not silently skipped here: each
is tested against what the ledger *actually* does, with the refused claim
stated in the test name and the reasoning in REJECTED.md. A criterion that is
refused still gets a test, because "this claim is false, and here is the number
that makes it false" is worth more than an absent test.

Accepted:  1, 3, 4, and 5 (with the qualification in REJECTED.md).
Refused:   2, 6, 7, 8.
"""

import unittest

from .support import replayed
from ledger.engine import Engine
from ledger.money import AED, BHD
from ledger.policy import Policy
from ledger.records import EntryKind, Outcome
from ledger.scenario import ACCOUNTS, build_events


class Criterion1_Day2ClosesAtMinus370(unittest.TestCase):
    """ACCEPTED. "The Day 2 closing ledger balance, evaluated at end of Day 5
    and before any fee is assessed, is AED -370.00." """

    def test_day_2_evaluated_at_end_of_day_5_before_fees_is_minus_370(self):
        book = replayed().book
        # "Before any fee is assessed" is exactly the balance the fee decision
        # was taken on, so the assessment record itself is the evidence.
        fee = book.fee_for_day("ACC-001", 2)
        self.assertIsNotNone(fee)
        self.assertEqual(fee.assessed_on, 5)
        self.assertEqual(fee.closing_balance, AED.exact("-370.00"))

    def test_the_same_number_falls_out_of_the_projection_directly(self):
        book = replayed().book
        pre_fee = book.closing_balance(
            "ACC-001", day=2, known_through=5,
            exclude_kinds=(EntryKind.OVERDRAFT_FEE,),
        )
        self.assertEqual(pre_fee, AED.exact("-370.00"))  # 1200 - 950 - 620

    def test_day_2_had_read_250_until_e7_arrived(self):
        # The point of the criterion: the same day has two honest answers.
        book = replayed().book
        self.assertEqual(book.closing_balance("ACC-001", 2, known_through=2),
                         AED.exact("250.00"))


class Criterion2_RefusedOneFeeOnDay2(unittest.TestCase):
    """REFUSED. "E7 causes exactly one overdraft fee to be assessed, on Day 2."

    E7 back-values AED 620.00 into Day 2, which drags every subsequent day's
    closing balance down with it. Three days close negative, not one.
    """

    def test_e7_causes_three_fees_not_one(self):
        fees = [f for f in replayed().book.fees if f.account_id == "ACC-001"]
        self.assertEqual([f.for_day for f in fees], [2, 4, 5])
        self.assertEqual(len(fees), 3)

    def test_the_three_days_that_close_negative_are_2_4_and_5(self):
        book = replayed().book
        negatives = {
            day: book.closing_balance("ACC-001", day, known_through=5)
            for day in range(1, 6)
        }
        self.assertTrue(negatives[2].is_negative(), negatives[2])   # -395.00
        self.assertFalse(negatives[3].is_negative(), negatives[3])  #    5.00
        self.assertTrue(negatives[4].is_negative(), negatives[4])   # -205.00
        self.assertTrue(negatives[5].is_negative(), negatives[5])   # -230.00

    def test_day_3_survives_by_five_dirhams_which_is_why_it_is_three_not_four(self):
        # E4's 400.00 credit on Day 3 lifts the running total back to 5.00
        # once E7 and the Day-2 fee are both counted. Five dirhams is the
        # entire margin between three fees and four.
        book = replayed().book
        self.assertEqual(book.closing_balance("ACC-001", 3, known_through=5),
                         AED.exact("5.00"))

    def test_still_three_fees_under_the_other_reading_of_fee_value_dating(self):
        # "Booked with value_date equal to the day assessed" could mean the day
        # whose balance was negative (our default) or the day the assessment
        # ran. The criterion is wrong either way, so refusing it does not
        # depend on resolving that ambiguity.
        alternative = Engine(
            ACCOUNTS, build_events(),
            Policy(fee_value_dated_to_assessment_day=True),
        ).run()
        fees = [f for f in alternative.book.fees if f.account_id == "ACC-001"]
        self.assertEqual(len(fees), 3)
        self.assertEqual([f.for_day for f in fees], [2, 4, 5])
        self.assertEqual(
            [alternative.book.entry_by_seq(f.entry_seq).value_date for f in fees],
            [5, 5, 5],
        )


class Criterion3_AuthASettlementAccepted(unittest.TestCase):
    """ACCEPTED. "The Day 4 settlement of Auth-A must be accepted." """

    def test_e5_is_applied(self):
        decision = next(d for d in replayed().book.decisions if d.event_id == "E5")
        self.assertIs(decision.outcome, Outcome.APPLIED)

    def test_it_posts_185_and_releases_the_whole_200_hold(self):
        book = replayed().book
        entries = book.entries_for_event("E5")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].amount, AED.exact("-185.00"))
        self.assertEqual(entries[0].value_date, 4)

        state = next(s for s in book.hold_states("ACC-001", 4) if s.auth_id == "Auth-A")
        self.assertFalse(state.is_active)
        self.assertEqual(state.released_on, 4)
        # Settling for less than the hold does not strand the 15.00 remainder.
        self.assertEqual(book.active_holds_total("ACC-001", 4), AED.exact("0.00"))


class Criterion4_UnknownAuthSettlementRejected(unittest.TestCase):
    """ACCEPTED. "Any settlement referencing an authorization ID not present in
    the ledger must be rejected and the funds must not leave the account." """

    def test_e6_is_rejected(self):
        decision = next(d for d in replayed().book.decisions if d.event_id == "E6")
        self.assertIs(decision.outcome, Outcome.REJECTED)
        self.assertIn("Auth-Z", decision.reason)

    def test_no_entry_was_posted_so_no_funds_moved(self):
        book = replayed().book
        self.assertEqual(book.entries_for_event("E6"), ())

    def test_the_180_never_appears_anywhere_in_the_ledger(self):
        book = replayed().book
        self.assertNotIn(
            AED.exact("-180.00"), [e.amount for e in book.entries]
        )

    def test_day_4_closes_as_if_e6_had_not_happened(self):
        book = replayed().book
        self.assertEqual(book.closing_balance("ACC-001", 4, known_through=4),
                         AED.exact("465.00"))  # 650 - 185, not 650 - 185 - 180

    def test_the_rejection_is_still_on_the_record(self):
        # Rejecting is not forgetting: append-only means the attempt survives.
        self.assertTrue(
            any(e.event_id == "E6" for e in replayed().book.events)
        )


class Criterion5_HoldsDoNotMoveLedgerBalance(unittest.TestCase):
    """ACCEPTED AS STATED, but its condition never fires.

    "If Auth-B is approved, its hold reduces available balance but not ledger
    balance." The rule it states is correct and the engine implements it. The
    antecedent is false: Auth-B is DECLINED, because E7 lands before it on
    Day 5 and leaves available at -155.00. Anyone reading this criterion as an
    assertion that Auth-B is approved would be wrong. See REJECTED.md.
    """

    def test_auth_b_is_declined(self):
        decision = next(d for d in replayed().book.decisions if d.event_id == "E8")
        self.assertIs(decision.outcome, Outcome.DECLINED)

    def test_it_is_declined_because_available_was_already_negative(self):
        book = replayed().book
        # At the moment E8 is evaluated: E7 posted, no fees assessed yet.
        available_before = book.closing_balance(
            "ACC-001", 5, known_through=5, exclude_kinds=(EntryKind.OVERDRAFT_FEE,)
        )
        self.assertEqual(available_before, AED.exact("-155.00"))
        self.assertTrue((available_before - AED.exact("90.00")).is_negative())

    def test_a_declined_authorization_places_no_hold_and_posts_nothing(self):
        book = replayed().book
        self.assertEqual(book.entries_for_event("E8"), ())
        self.assertNotIn("Auth-B", {s.auth_id for s in book.hold_states("ACC-001", 6)})

    def test_the_rule_itself_holds_for_the_authorization_that_was_approved(self):
        # Auth-A is the working demonstration of the stated rule.
        book = replayed().book
        self.assertEqual(book.closing_balance("ACC-001", 2, known_through=2),
                         AED.exact("250.00"))   # ledger balance untouched
        self.assertEqual(book.available_balance("ACC-001", 2),
                         AED.exact("50.00"))    # available reduced by the hold

    def test_auth_b_would_have_been_approved_had_e7_not_preceded_it(self):
        # Shows the decline is caused by E7's ordering, not by the hold rule.
        without_e7 = Engine(
            ACCOUNTS, [e for e in build_events() if e.event_id not in ("E7", "E9")]
        ).run()
        decision = next(d for d in without_e7.book.decisions if d.event_id == "E8")
        self.assertIs(decision.outcome, Outcome.APPROVED)


class Criterion6_RefusedReversalRestoresEverything(unittest.TestCase):
    """REFUSED. "After E9, all balances and fees return to their pre-E7 values."

    Three independent reasons, any one of which is fatal.
    """

    def setUp(self):
        self.actual = replayed()
        self.without_e7 = Engine(
            ACCOUNTS, [e for e in build_events() if e.event_id not in ("E7", "E9")]
        ).run()

    def test_reason_1_the_three_fees_remain_on_the_book(self):
        self.assertEqual(len(list(self.actual.book.fees)), 3)
        self.assertEqual(len(list(self.without_e7.book.fees)), 0)

    def test_reason_2_final_balances_differ_by_75_10(self):
        after = self.actual.book.closing_balance("ACC-001", 6)
        pre_e7 = self.without_e7.book.closing_balance("ACC-001", 6)
        self.assertEqual(after, AED.exact("390.93"))
        self.assertEqual(pre_e7, AED.exact("466.03"))
        self.assertEqual(pre_e7 - after, AED.exact("75.10"))

    def test_reason_3_a_declined_authorization_cannot_be_un_declined(self):
        # This is the part no amount of fee-refund policy could fix. Auth-B was
        # refused on Day 5 on the strength of a balance E7 had made negative.
        # E9 arrives on Day 6. The customer's authorization stays refused;
        # a reversal cannot travel back and approve a card transaction.
        actual = next(d for d in self.actual.book.decisions if d.event_id == "E8")
        counterfactual = next(
            d for d in self.without_e7.book.decisions if d.event_id == "E8"
        )
        self.assertIs(actual.outcome, Outcome.DECLINED)
        self.assertIs(counterfactual.outcome, Outcome.APPROVED)

    def test_interest_does_not_return_either(self):
        self.assertEqual(self.actual.capitalised["ACC-001"], AED.exact("0.93"))
        self.assertEqual(self.without_e7.capitalised["ACC-001"], AED.exact("1.03"))

    def test_what_does_return_is_the_day_2_balance_net_of_fees(self):
        # Being fair to the criterion: strip the fees and the *principal* is
        # restored exactly. 225.00 + 25.00 fee = 250.00, the pre-E7 figure.
        book = self.actual.book
        ex_fees = book.closing_balance(
            "ACC-001", 2, exclude_kinds=(EntryKind.OVERDRAFT_FEE,)
        )
        self.assertEqual(ex_fees, AED.exact("250.00"))


class Criterion7_RefusedInstalmentsOf3334(unittest.TestCase):
    """REFUSED. "The three BHD instalments in E10 must each be BHD 3.334."

    3.334 x 3 = 10.002. The event credits 10.000.
    """

    def test_3334_three_times_would_credit_two_millifils_that_nobody_sent(self):
        three_of_them = BHD.exact("3.334") + BHD.exact("3.334") + BHD.exact("3.334")
        self.assertEqual(three_of_them, BHD.exact("10.002"))
        self.assertNotEqual(three_of_them, BHD.exact("10.000"))

    def test_the_actual_split_is_3_333_3_333_3_334(self):
        entries = replayed().book.entries_for_event("E10")
        self.assertEqual([str(e.amount) for e in entries],
                         ["BHD 3.333", "BHD 3.333", "BHD 3.334"])

    def test_the_instalments_sum_to_exactly_ten(self):
        entries = replayed().book.entries_for_event("E10")
        total = BHD.zero()
        for entry in entries:
            total = total + entry.amount
        self.assertEqual(total, BHD.exact("10.000"))

    def test_acc_002_closes_day_5_at_ten_not_ten_point_zero_zero_two(self):
        book = replayed().book
        self.assertEqual(book.closing_balance("ACC-002", 5), BHD.exact("10.000"))


class Criterion8_RefusedDiscardTheRemainder(unittest.TestCase):
    """REFUSED. "If the rounded daily interest accruals do not sum to the
    capitalised total, the remainder is discarded."

    It contradicts a non-negotiable rule in the same brief -- "the rounded
    daily accruals must sum exactly to the capitalised total" -- and there is
    no remainder to discard, because the capitalised total is defined as that
    sum.
    """

    def test_there_is_no_remainder_because_the_total_is_the_sum(self):
        engine = replayed()
        for account_id, account in engine.book.accounts.items():
            dailies = list(engine.daily_accruals(account_id).values())
            total = account.currency.zero()
            for amount in dailies:
                total = total + amount
            self.assertEqual(total, engine.capitalised[account_id])
            remainder = engine.capitalised[account_id] - total
            self.assertTrue(remainder.is_zero(), "nothing to discard")

    def test_the_capitalised_entry_equals_the_sum_of_the_dailies(self):
        engine = replayed()
        caps = {
            e.account_id: e.amount
            for e in engine.book.entries
            if e.kind is EntryKind.INTEREST_CAPITALISATION
        }
        self.assertEqual(caps["ACC-001"], AED.exact("0.93"))
        self.assertEqual(caps["ACC-002"], BHD.exact("0.008"))
        self.assertEqual(
            sum(int(v.amount * 100) for v in
                replayed().daily_accruals("ACC-001").values()),
            93,
        )

    def test_rounding_the_sum_instead_would_have_given_a_different_answer(self):
        # The distinction the criterion misses. Summing exact accruals and
        # rounding once gives 0.92; summing the rounded dailies gives 0.93.
        # The brief mandates the second, so the one-fils difference is the
        # bank's, not a remainder to be swept under the rug.
        from decimal import Decimal

        book = replayed().book
        exact = Decimal(0)
        for day in range(1, 7):
            exact += book.interest_basis("ACC-001", day).scaled_by(Decimal("0.0004"))
        self.assertEqual(exact, Decimal("0.918000"))
        self.assertEqual(AED.round(exact), AED.exact("0.92"))
        self.assertEqual(replayed().capitalised["ACC-001"], AED.exact("0.93"))


if __name__ == "__main__":
    unittest.main()
