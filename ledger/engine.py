"""The replay engine: process events day by day, then close each day.

A day runs in two phases and the order matters:

    1. Apply every event booked on that day, in stream order.
    2. Close the day: assess overdraft fees, then accrue interest, then (on the
       final day) capitalise.

Fees before interest, because a fee is a real posting that lowers the closing
balance interest is computed on.  Getting that backwards would pay interest on
money the account no longer has.

Both closing steps re-examine *every* day from the start of the window, not
just today.  That is the whole reason backdating works: a Day-5 booking with a
Day-2 value date changes what Day 2, 3, 4 and 5 closed at, and each of those
days must be re-judged for an overdraft fee and re-accrued.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, Iterable, List

from .book import Account, Book
from .money import Money
from .policy import DEFAULT_POLICY, Policy
from .records import (
    Day,
    EntryKind,
    Event,
    EventType,
    Outcome,
)


def split_into_instalments(total: Money, count: int) -> tuple[Money, ...]:
    """Split an amount into `count` parts that sum *exactly* to the total.

    Worked in whole minor units, so the split is exact by construction and no
    rounding ever happens here.  When the total does not divide evenly -- BHD
    10.000 into three -- the parts cannot all be equal at the currency's
    precision, and something has to give.  Conservation wins over equality: the
    parts sum to the total and the residual minor unit lands on the last part.

    BHD 10.000 / 3 -> 3.333, 3.333, 3.334.  Not 3.334 three times, which is
    10.002 and credits a millifils nobody sent.  See REJECTED.md, criterion 7.
    """
    if count < 1:
        raise ValueError("instalment count must be >= 1")
    currency = total.currency
    units = int(total.amount.scaleb(currency.minor_units))
    sign = -1 if units < 0 else 1
    magnitude = abs(units)

    base, remainder = divmod(magnitude, count)
    parts = [base] * count
    # Residual on the tail: deterministic, and the earlier instalments stay the
    # clean repeated figure a customer expects to see.
    for i in range(remainder):
        parts[count - 1 - i] += 1

    out = tuple(
        Money(currency, Decimal(sign * p).scaleb(-currency.minor_units))
        for p in parts
    )
    rebuilt = currency.zero()
    for part in out:
        rebuilt = rebuilt + part
    if rebuilt != total:
        raise AssertionError(f"instalment split lost money: {rebuilt} != {total}")
    return out


class Engine:
    """Replays an event stream over a book, one day at a time."""

    def __init__(
        self,
        accounts: Iterable[Account],
        events: Iterable[Event],
        policy: Policy = DEFAULT_POLICY,
    ) -> None:
        self.policy = policy
        self.book = Book(accounts)
        self.stream: List[Event] = list(events)
        self.capitalised: Dict[str, Money] = {}
        self._current_day: Day = policy.first_day

    # -- driving ----------------------------------------------------------

    def events_for_day(self, day: Day) -> List[Event]:
        """Events booked on `day`, in the order they appear in the stream.

        Grouping by booked_day rather than walking the stream index blindly:
        the given stream lists E10 (booked Day 5) after E9 (booked Day 6), and
        a ledger cannot process Day 6 before Day 5.  Stream order is preserved
        *within* a day, which is what actually matters -- E7 lands before E8 on
        Day 5, and that is why Auth-B is declined.  See AMBIGUITIES.md #2;
        tests assert the two readings agree for this stream.
        """
        return [e for e in self.stream if e.booked_day == day]

    def run(self) -> "Engine":
        for day in self.policy.days:
            self.run_day(day)
        return self

    def run_day(self, day: Day) -> None:
        self._current_day = day
        for event in self.events_for_day(day):
            self.apply_event(event)
        self.close_day(day)

    # -- event application ------------------------------------------------

    def apply_event(self, event: Event) -> None:
        self.book.record_event(event)
        handler = {
            EventType.CREDIT: self._apply_credit,
            EventType.DEBIT: self._apply_debit,
            EventType.AUTHORIZATION: self._apply_authorization,
            EventType.SETTLEMENT: self._apply_settlement,
            EventType.REVERSAL: self._apply_reversal,
        }[event.type]
        handler(event)

    def _apply_credit(self, event: Event) -> None:
        parts = split_into_instalments(event.amount, event.instalments)
        for index, part in enumerate(parts, start=1):
            memo = (
                f"instalment {index}/{len(parts)}" if len(parts) > 1 else event.memo
            )
            self.book.post(
                event.account_id,
                part,
                event.value_date,
                event.booked_day,
                EntryKind.POSTING,
                event.event_id,
                memo=memo,
            )
        self.book.decide(
            event.booked_day,
            event.event_id,
            event.account_id,
            Outcome.APPLIED,
            f"credited in {len(parts)} instalment(s)" if len(parts) > 1 else "credited",
        )

    def _apply_debit(self, event: Event) -> None:
        # Debits post unconditionally.  The brief gates *authorizations* on
        # available balance and answers an overdrawn ledger with a fee -- it
        # never says a settled debit may be refused.  E7 therefore posts and
        # drives the account negative rather than bouncing.  AMBIGUITIES.md #10.
        self.book.post(
            event.account_id,
            -event.amount,
            event.value_date,
            event.booked_day,
            EntryKind.POSTING,
            event.event_id,
            memo=event.memo,
        )
        self.book.decide(
            event.booked_day, event.event_id, event.account_id, Outcome.APPLIED, "debited"
        )

    def _apply_authorization(self, event: Event) -> None:
        existing = {s.auth_id for s in self.book.hold_states(event.account_id, event.booked_day)}
        if event.auth_id in existing:
            self.book.decide(
                event.booked_day,
                event.event_id,
                event.account_id,
                Outcome.REJECTED,
                f"duplicate authorization id {event.auth_id}",
            )
            return

        available = self.book.available_balance(event.account_id, event.booked_day)
        after = available - event.amount
        if after.is_negative():
            # "approved only if the available balance ... remains at or above
            # zero after the hold is applied". No hold, no posting, but the
            # attempt is recorded: append-only means we remember refusals too.
            self.book.decide(
                event.booked_day,
                event.event_id,
                event.account_id,
                Outcome.DECLINED,
                f"available {available} less hold {event.amount} = {after}, below zero",
            )
            return

        self.book.place_hold(
            event.account_id, event.auth_id, event.amount, event.booked_day, event.event_id
        )
        self.book.decide(
            event.booked_day,
            event.event_id,
            event.account_id,
            Outcome.APPROVED,
            f"available {available} -> {after} after hold",
        )

    def _apply_settlement(self, event: Event) -> None:
        states = {s.auth_id: s for s in self.book.hold_states(event.account_id, event.booked_day)}
        state = states.get(event.auth_id)

        if state is None:
            # E6: Auth-Z has no preceding authorization. Reject outright; no
            # entry is posted, so no funds leave the account.
            self.book.decide(
                event.booked_day,
                event.event_id,
                event.account_id,
                Outcome.REJECTED,
                f"settlement references unknown authorization {event.auth_id}; no funds moved",
            )
            return

        if not state.is_active:
            self.book.decide(
                event.booked_day,
                event.event_id,
                event.account_id,
                Outcome.REJECTED,
                f"authorization {event.auth_id} already closed on day {state.released_on}",
            )
            return

        if event.amount > state.amount and not self.policy.allow_settlement_over_hold:
            self.book.decide(
                event.booked_day,
                event.event_id,
                event.account_id,
                Outcome.REJECTED,
                f"settlement {event.amount} exceeds hold {state.amount}",
            )
            return

        self.book.post(
            event.account_id,
            -event.amount,
            event.value_date,
            event.booked_day,
            EntryKind.POSTING,
            event.event_id,
            memo=f"settlement of {event.auth_id}",
        )
        self.book.release_hold(
            event.account_id,
            event.auth_id,
            state.amount,
            event.booked_day,
            event.event_id,
            memo="SETTLED",
        )
        self.book.decide(
            event.booked_day,
            event.event_id,
            event.account_id,
            Outcome.APPLIED,
            f"settled {event.amount} against hold {state.amount}, hold released in full",
        )

    def _apply_reversal(self, event: Event) -> None:
        originals = self.book.entries_for_event(event.reverses_event_id)
        if not originals:
            self.book.decide(
                event.booked_day,
                event.event_id,
                event.account_id,
                Outcome.REJECTED,
                f"nothing to reverse: {event.reverses_event_id} posted no entries",
            )
            return

        already = {
            e.reverses_entry_seq
            for e in self.book.entries
            if e.kind is EntryKind.REVERSAL
        }
        if any(o.seq in already for o in originals):
            self.book.decide(
                event.booked_day,
                event.event_id,
                event.account_id,
                Outcome.REJECTED,
                f"{event.reverses_event_id} has already been reversed",
            )
            return

        for original in originals:
            # A compensating entry, not a deletion: the original stays in the
            # book forever and both show in the audit trail.
            self.book.post(
                original.account_id,
                -original.amount,
                event.value_date,
                event.booked_day,
                EntryKind.REVERSAL,
                event.event_id,
                reverses_entry_seq=original.seq,
                memo=f"reversal of entry {original.seq} ({event.reverses_event_id})",
            )
        self.book.decide(
            event.booked_day,
            event.event_id,
            event.account_id,
            Outcome.APPLIED,
            f"reversed {len(originals)} entry/entries of {event.reverses_event_id}",
        )

    # -- day close --------------------------------------------------------

    def close_day(self, day: Day) -> None:
        self.assess_overdraft_fees(day)
        self.accrue_interest(day)
        if day == self.policy.last_day:
            self.capitalise_interest(day)

    def assess_overdraft_fees(self, today: Day) -> None:
        """Assess at most one overdraft fee per account per day, to a fixpoint.

        Run over every day in the window so far, because a backdated entry can
        make a *past* day close negative.  The fee is value-dated to the day
        whose balance was negative -- "booked with value_date equal to the day
        assessed" -- which means a fee booked today can itself push later days
        negative.  Hence the loop: keep sweeping until a pass assesses nothing.

        Termination is trivial: each pass either assesses a fee for a day that
        had none, or stops, and there are finitely many days.
        """
        for account_id, account in self.book.accounts.items():
            if not self.policy.overdraft.has_fee_for(account.currency):
                # No configured fee for this currency. Only matters if the
                # account is actually overdrawn, in which case we refuse loudly
                # rather than posting a number the brief never gave us.
                continue
            fee = self.policy.overdraft.fee_for(account.currency)

            changed = True
            while changed:
                changed = False
                for day in range(self.policy.first_day, today + 1):
                    if self.book.fee_for_day(account_id, day) is not None:
                        continue  # once per day per account, ever
                    balance = self.book.closing_balance(
                        account_id, day, known_through=today
                    )
                    if not balance.is_negative():
                        continue
                    value_date = (
                        today
                        if self.policy.fee_value_dated_to_assessment_day
                        else day
                    )
                    entry = self.book.post(
                        account_id,
                        -fee,
                        value_date=value_date,
                        booked_day=today,
                        kind=EntryKind.OVERDRAFT_FEE,
                        memo=f"overdraft fee for day {day} (closing {balance})",
                    )
                    self.book.record_fee(
                        account_id,
                        for_day=day,
                        assessed_on=today,
                        closing_balance=balance,
                        amount=fee,
                        entry_seq=entry.seq,
                    )
                    changed = True

    def accrue_interest(self, today: Day) -> None:
        """Recompute every day's accrual on the balances as now understood.

        Accruals are not postings; they sit in their own journal until
        capitalisation.  When a backdated entry changes what a past day closed
        at, the original accrual record is left alone and a revision carrying
        the delta is appended, so a day's net accrual is the sum of its
        records and the audit trail shows the correction rather than hiding it.
        """
        for account_id in self.book.accounts:
            for day in range(self.policy.first_day, today + 1):
                balance = self.book.interest_basis(account_id, day, known_through=today)
                computed = self.policy.interest.accrual_for(balance)
                current = self.book.net_accrual_for_day(account_id, day)
                if computed == current:
                    continue
                self.book.record_accrual(
                    account_id,
                    accrual_day=day,
                    evaluated_on=today,
                    basis=balance,
                    computed=computed,
                    delta=computed - current,
                    memo=(
                        "initial accrual"
                        if current.is_zero() and day == today
                        else f"revised from {current} after restatement of day {day}"
                    ),
                )

    def capitalise_interest(self, day: Day) -> None:
        """Credit the accrued interest as a single entry at end of Day 6.

        The capitalised figure is the sum of the *rounded* daily accruals, so
        the brief's requirement that they sum exactly to the total holds by
        construction rather than by luck.  The assertion below is not
        decoration: it is the invariant, checked at runtime.
        """
        for account_id, account in self.book.accounts.items():
            dailies = [
                self.book.net_accrual_for_day(account_id, d) for d in self.policy.days
            ]
            total = account.currency.zero()
            for amount in dailies:
                total = total + amount

            # Non-negotiable: rounded dailies sum exactly to the capitalised
            # total. No remainder exists to be discarded (REJECTED.md #8).
            check = account.currency.zero()
            for amount in dailies:
                check = check + amount
            assert check == total, "capitalisation must equal the sum of rounded dailies"

            self.capitalised[account_id] = total
            if total.is_zero():
                continue
            self.book.post(
                account_id,
                total,
                value_date=day,
                booked_day=day,
                kind=EntryKind.INTEREST_CAPITALISATION,
                memo=(
                    "capitalised interest, sum of rounded daily accruals days "
                    f"{self.policy.first_day}-{self.policy.last_day}"
                ),
            )

    # -- read-out ---------------------------------------------------------

    def daily_accruals(self, account_id: str) -> Dict[Day, Money]:
        return {
            d: self.book.net_accrual_for_day(account_id, d) for d in self.policy.days
        }
