"""The six non-negotiable rules from the brief, each tested directly."""

import unittest
from decimal import Decimal

from .support import replayed
from ledger.book import Account
from ledger.engine import Engine, split_into_instalments
from ledger.money import AED, BHD
from ledger.policy import DEFAULT_POLICY, PolicyNotConfigured
from ledger.records import EntryKind, Event, EventType, Outcome


class OverdraftFeeRule(unittest.TestCase):
    """AED 25.00, once per day per account, when that day closes negative,
    value-dated to the day assessed."""

    def test_fee_amount_is_25_aed(self):
        for fee in replayed().book.fees:
            self.assertEqual(fee.amount, AED.exact("25.00"))

    def test_at_most_one_fee_per_account_per_day(self):
        seen = set()
        for fee in replayed().book.fees:
            key = (fee.account_id, fee.for_day)
            self.assertNotIn(key, seen, f"two fees for {key}")
            seen.add(key)

    def test_every_fee_is_value_dated_to_the_day_it_was_assessed_for(self):
        book = replayed().book
        for fee in book.fees:
            entry = book.entry_by_seq(fee.entry_seq)
            self.assertEqual(entry.value_date, fee.for_day)
            self.assertIs(entry.kind, EntryKind.OVERDRAFT_FEE)

    def test_a_fee_is_assessed_exactly_when_the_day_closed_negative(self):
        book = replayed().book
        for day in DEFAULT_POLICY.days:
            # The balance that triggered the decision excludes that day's own
            # fee, which is what `closing_balance` before assessment means.
            fee = book.fee_for_day("ACC-001", day)
            restated = book.closing_balance("ACC-001", day)
            if fee is not None:
                self.assertTrue(
                    fee.closing_balance.is_negative(),
                    f"day {day} charged a fee on a non-negative balance",
                )
            else:
                self.assertFalse(
                    restated.is_negative(),
                    f"day {day} closed negative at {restated} with no fee",
                )

    def test_no_fee_is_invented_for_a_currency_the_brief_never_priced(self):
        with self.assertRaises(PolicyNotConfigured):
            DEFAULT_POLICY.overdraft.fee_for(BHD)


class InterestRule(unittest.TestCase):
    """0.04% per day, positive balances only, capitalised once at end of Day 6,
    with the rounded dailies summing exactly to the capitalised total."""

    def test_rate_is_four_hundredths_of_a_percent(self):
        self.assertEqual(DEFAULT_POLICY.interest.daily_rate, Decimal("0.0004"))

    def test_negative_and_zero_balances_accrue_nothing(self):
        self.assertTrue(
            DEFAULT_POLICY.interest.accrual_for(AED.exact("-370.00")).is_zero()
        )
        self.assertTrue(DEFAULT_POLICY.interest.accrual_for(AED.exact("0.00")).is_zero())

    def test_rounded_dailies_sum_exactly_to_the_capitalised_total(self):
        # The brief's words: "The rounded daily accruals must sum exactly to
        # the capitalised total." Guaranteed by construction here, because the
        # capitalised figure IS that sum -- there is no parallel unrounded
        # total it could drift from.
        engine = replayed()
        for account_id, account in engine.book.accounts.items():
            dailies = engine.daily_accruals(account_id)
            total = account.currency.zero()
            for amount in dailies.values():
                total = total + amount
            self.assertEqual(total, engine.capitalised[account_id])

    def test_capitalisation_is_a_single_credit_on_the_last_day(self):
        book = replayed().book
        caps = [e for e in book.entries if e.kind is EntryKind.INTEREST_CAPITALISATION]
        self.assertEqual(len(caps), 2, "one capitalisation per funded account")
        for entry in caps:
            self.assertEqual(entry.value_date, 6)
            self.assertEqual(entry.booked_day, 6)
            self.assertTrue(entry.amount.is_positive())

    def test_interest_is_not_paid_on_capitalised_interest(self):
        # Day 6's basis excludes the capitalisation credit booked the same day.
        book = replayed().book
        self.assertEqual(book.interest_basis("ACC-001", 6), AED.exact("390.00"))
        self.assertEqual(book.closing_balance("ACC-001", 6), AED.exact("390.93"))

    def test_dailies_are_each_the_rounded_rate_on_that_days_restated_basis(self):
        engine = replayed()
        for account_id in engine.book.accounts:
            for day, accrued in engine.daily_accruals(account_id).items():
                basis = engine.book.interest_basis(account_id, day)
                self.assertEqual(
                    accrued, DEFAULT_POLICY.interest.accrual_for(basis), f"day {day}"
                )


class AppendOnlyRule(unittest.TestCase):
    """No event record is ever mutated or deleted."""

    def test_entry_sequence_numbers_are_dense_and_strictly_increasing(self):
        seqs = [e.seq for e in replayed().book.entries]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))

    def test_records_are_frozen(self):
        entry = replayed().book.entries[0]
        with self.assertRaises(Exception):
            entry.amount = AED.exact("1.00")

    def test_the_reversed_debit_is_still_in_the_book(self):
        book = replayed().book
        original = book.entries_for_event("E7")
        self.assertEqual(len(original), 1)
        self.assertEqual(original[0].amount, AED.exact("-620.00"))

        compensating = book.entries_for_event("E9")
        self.assertEqual(len(compensating), 1)
        self.assertEqual(compensating[0].amount, AED.exact("620.00"))
        self.assertEqual(compensating[0].reverses_entry_seq, original[0].seq)
        self.assertIs(compensating[0].kind, EntryKind.REVERSAL)

    def test_refused_events_are_recorded_rather_than_forgotten(self):
        decisions = {d.event_id: d for d in replayed().book.decisions}
        self.assertEqual(len(decisions), 10, "all ten events left a decision")
        self.assertIs(decisions["E6"].outcome, Outcome.REJECTED)
        self.assertIs(decisions["E8"].outcome, Outcome.DECLINED)

    def test_a_revised_accrual_appends_a_delta_instead_of_editing(self):
        book = replayed().book
        records = book.accrual_revisions("ACC-001", 2)
        # Day 2's accrual was written three times: 0.10 on Day 2, struck to
        # 0.00 on Day 5 when E7 landed, restored to 0.09 on Day 6 after E9.
        self.assertEqual([str(r.computed) for r in records],
                         ["AED 0.10", "AED 0.00", "AED 0.09"])
        self.assertEqual([r.evaluated_on for r in records], [2, 5, 6])
        net = book.net_accrual_for_day("ACC-001", 2)
        self.assertEqual(net, AED.exact("0.09"))


class AvailableBalanceRule(unittest.TestCase):
    """An authorization is approved only if ledger balance minus active holds
    stays at or above zero after the hold is applied."""

    def test_a_hold_never_touches_the_ledger_balance(self):
        book = replayed().book
        # Auth-A held 200.00 across Day 2 and Day 3.
        self.assertEqual(book.closing_balance("ACC-001", 2, known_through=2),
                         AED.exact("250.00"))
        self.assertEqual(book.active_holds_total("ACC-001", 2), AED.exact("200.00"))
        self.assertEqual(book.available_balance("ACC-001", 2), AED.exact("50.00"))
        # No entry anywhere came from the authorization event itself.
        self.assertEqual(book.entries_for_event("E3"), ())

    def test_an_authorization_landing_exactly_on_zero_is_approved(self):
        # "at or above zero" -- the boundary is inclusive. Auth-A could have
        # been 250.00 against a 250.00 balance and still cleared.
        events = [e for e in build_events_for_boundary()]
        engine = Engine(
            [Account("ACC-X", AED, AED.exact("0.00"))], events, DEFAULT_POLICY
        ).run()
        decisions = {d.event_id: d for d in engine.book.decisions}
        self.assertIs(decisions["B2"].outcome, Outcome.APPROVED)

    def test_one_fils_over_the_line_is_declined(self):
        events = build_events_for_boundary(hold="100.01")
        engine = Engine(
            [Account("ACC-X", AED, AED.exact("0.00"))], events, DEFAULT_POLICY
        ).run()
        decisions = {d.event_id: d for d in engine.book.decisions}
        self.assertIs(decisions["B2"].outcome, Outcome.DECLINED)


def build_events_for_boundary(hold: str = "100.00"):
    return [
        Event("B1", 1, EventType.CREDIT, "ACC-X", 1, AED.exact("100.00")),
        Event("B2", 1, EventType.AUTHORIZATION, "ACC-X", 1,
              AED.exact(hold), auth_id="Auth-Edge"),
    ]


class InstalmentSplitRule(unittest.TestCase):
    def test_a_split_always_conserves_the_total(self):
        for total, parts in (
            ("10.000", 3), ("10.000", 7), ("0.001", 3), ("100.000", 3), ("1.000", 6)
        ):
            with self.subTest(total=total, parts=parts):
                pieces = split_into_instalments(BHD.exact(total), parts)
                rebuilt = BHD.zero()
                for piece in pieces:
                    rebuilt = rebuilt + piece
                self.assertEqual(rebuilt, BHD.exact(total))

    def test_parts_differ_by_at_most_one_minor_unit(self):
        pieces = split_into_instalments(BHD.exact("10.000"), 3)
        amounts = sorted(p.amount for p in pieces)
        self.assertLessEqual(amounts[-1] - amounts[0], BHD.quantum)

    def test_ten_bhd_in_three_is_3_333_3_333_3_334(self):
        pieces = split_into_instalments(BHD.exact("10.000"), 3)
        self.assertEqual([str(p) for p in pieces],
                         ["BHD 3.333", "BHD 3.333", "BHD 3.334"])


class DeterminismAndOrdering(unittest.TestCase):
    def test_replay_is_deterministic(self):
        a = Engine(*_scenario()).run()
        b = Engine(*_scenario()).run()
        self.assertEqual(
            [(e.seq, str(e.amount), e.value_date) for e in a.book.entries],
            [(e.seq, str(e.amount), e.value_date) for e in b.book.entries],
        )

    def test_stream_order_and_booked_day_order_agree_for_this_stream(self):
        # The brief lists E10 (booked Day 5) after E9 (booked Day 6). The
        # engine groups by booked_day, so E10 is applied on Day 5. Reordering
        # the stream so E10 precedes E9 must change nothing, because the two
        # events touch different accounts. If a future stream made them touch
        # the same account this test would start failing, which is the point.
        from ledger.scenario import ACCOUNTS, build_events

        events = build_events()
        swapped = [e for e in events if e.event_id != "E10"]
        swapped.insert(
            swapped.index(next(e for e in swapped if e.event_id == "E9")),
            next(e for e in events if e.event_id == "E10"),
        )
        a = Engine(ACCOUNTS, events).run()
        b = Engine(ACCOUNTS, swapped).run()
        for account_id in a.book.accounts:
            for day in DEFAULT_POLICY.days:
                self.assertEqual(
                    a.book.closing_balance(account_id, day),
                    b.book.closing_balance(account_id, day),
                )


def _scenario():
    from ledger.scenario import ACCOUNTS, build_events

    return ACCOUNTS, build_events()


if __name__ == "__main__":
    unittest.main()
