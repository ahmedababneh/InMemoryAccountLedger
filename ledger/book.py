"""The book: append-only storage plus the projections read off it.

Every balance in this system is a *projection* over the entry log, computed on
demand from two coordinates:

    value_date  -- the day an entry takes economic effect
    booked_day  -- the day the ledger learned the entry exists

Keeping both is what makes backdating expressible.  `closing_balance(day=2,
known_through=4)` is "what we believed Day 2 closed at, as of the end of Day 4";
`closing_balance(day=2, known_through=6)` is "what Day 2 actually closed at,
now that we know everything".  E7 makes those two numbers differ, and a design
that stored only one running balance could not represent the difference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from .money import Currency, Money
from .records import (
    AccrualRecord,
    AppendOnlyLog,
    Day,
    Decision,
    Entry,
    EntryKind,
    Event,
    FeeAssessment,
    HoldAction,
    HoldRecord,
)


@dataclass(frozen=True)
class Account:
    account_id: str
    currency: Currency
    opening_balance: Money

    def __post_init__(self) -> None:
        if self.opening_balance.currency != self.currency:
            raise ValueError(
                f"{self.account_id}: opening balance currency does not match account"
            )


@dataclass(frozen=True)
class HoldState:
    auth_id: str
    account_id: str
    amount: Money
    placed_on: Day
    released_on: Optional[Day]
    release_reason: str

    @property
    def is_active(self) -> bool:
        return self.released_on is None

    @property
    def state(self) -> str:
        if self.released_on is None:
            return "ACTIVE"
        return self.release_reason or "RELEASED"


class Book:
    """Holds every log and answers questions about them. Never mutates a record."""

    def __init__(self, accounts: Iterable[Account]) -> None:
        self.accounts: Dict[str, Account] = {a.account_id: a for a in accounts}
        self.events = AppendOnlyLog()
        self.entries = AppendOnlyLog()
        self.holds = AppendOnlyLog()
        self.accruals = AppendOnlyLog()
        self.decisions = AppendOnlyLog()
        self.fees = AppendOnlyLog()

        for account in self.accounts.values():
            # An explicit opening entry, even at zero.  It costs one row and it
            # means the balance of an account is always the sum of its entries
            # with no special case for "where did the opening figure go".
            self.entries.append(
                Entry(
                    seq=self.entries.next_seq,
                    account_id=account.account_id,
                    amount=account.opening_balance,
                    value_date=0,
                    booked_day=0,
                    kind=EntryKind.OPENING,
                    memo="opening balance",
                )
            )

    # -- account helpers --------------------------------------------------

    def account(self, account_id: str) -> Account:
        try:
            return self.accounts[account_id]
        except KeyError:
            raise KeyError(f"unknown account {account_id!r}") from None

    def currency_of(self, account_id: str) -> Currency:
        return self.account(account_id).currency

    # -- recording --------------------------------------------------------

    def record_event(self, event: Event) -> Event:
        return self.events.append(event)

    def post(
        self,
        account_id: str,
        amount: Money,
        value_date: Day,
        booked_day: Day,
        kind: EntryKind,
        source_event_id: Optional[str] = None,
        reverses_entry_seq: Optional[int] = None,
        memo: str = "",
    ) -> Entry:
        account = self.account(account_id)
        if amount.currency != account.currency:
            raise ValueError(
                f"cannot post {amount.currency.code} to {account_id} "
                f"({account.currency.code})"
            )
        return self.entries.append(
            Entry(
                seq=self.entries.next_seq,
                account_id=account_id,
                amount=amount,
                value_date=value_date,
                booked_day=booked_day,
                kind=kind,
                source_event_id=source_event_id,
                reverses_entry_seq=reverses_entry_seq,
                memo=memo,
            )
        )

    def decide(
        self, day: Day, event_id: str, account_id: str, outcome, reason: str = ""
    ) -> Decision:
        return self.decisions.append(
            Decision(
                seq=self.decisions.next_seq,
                day=day,
                event_id=event_id,
                account_id=account_id,
                outcome=outcome,
                reason=reason,
            )
        )

    def place_hold(
        self, account_id: str, auth_id: str, amount: Money, day: Day, event_id: str
    ) -> HoldRecord:
        return self.holds.append(
            HoldRecord(
                seq=self.holds.next_seq,
                account_id=account_id,
                auth_id=auth_id,
                action=HoldAction.PLACED,
                amount=amount,
                booked_day=day,
                source_event_id=event_id,
            )
        )

    def release_hold(
        self,
        account_id: str,
        auth_id: str,
        amount: Money,
        day: Day,
        event_id: str,
        memo: str = "",
    ) -> HoldRecord:
        return self.holds.append(
            HoldRecord(
                seq=self.holds.next_seq,
                account_id=account_id,
                auth_id=auth_id,
                action=HoldAction.RELEASED,
                amount=amount,
                booked_day=day,
                source_event_id=event_id,
                memo=memo,
            )
        )

    def record_fee(
        self,
        account_id: str,
        for_day: Day,
        assessed_on: Day,
        closing_balance: Money,
        amount: Money,
        entry_seq: int,
    ) -> FeeAssessment:
        return self.fees.append(
            FeeAssessment(
                seq=self.fees.next_seq,
                account_id=account_id,
                for_day=for_day,
                assessed_on=assessed_on,
                closing_balance=closing_balance,
                amount=amount,
                entry_seq=entry_seq,
            )
        )

    def record_accrual(
        self,
        account_id: str,
        accrual_day: Day,
        evaluated_on: Day,
        basis: Money,
        computed: Money,
        delta: Money,
        memo: str = "",
    ) -> AccrualRecord:
        return self.accruals.append(
            AccrualRecord(
                seq=self.accruals.next_seq,
                account_id=account_id,
                accrual_day=accrual_day,
                evaluated_on=evaluated_on,
                basis=basis,
                computed=computed,
                amount=delta,
                memo=memo,
            )
        )

    # -- projections ------------------------------------------------------

    def closing_balance(
        self, account_id: str, day: Day, known_through: Optional[Day] = None
    ) -> Money:
        """Sum of entries with value_date <= day, known as of `known_through`.

        `known_through=None` means "using everything in the book", i.e. the
        restated view. Passing a day gives the point-in-time view that the
        ledger actually held at that day's close.
        """
        total = self.currency_of(account_id).zero()
        for entry in self.entries:
            if entry.account_id != account_id:
                continue
            if entry.value_date > day:
                continue
            if known_through is not None and entry.booked_day > known_through:
                continue
            total = total + entry.amount
        return total

    def hold_states(
        self, account_id: str, known_through: Day
    ) -> tuple[HoldState, ...]:
        """Reconstruct every hold's state from the append-only hold log."""
        placed: Dict[str, HoldRecord] = {}
        released: Dict[str, HoldRecord] = {}
        for record in self.holds:
            if record.account_id != account_id:
                continue
            if record.booked_day > known_through:
                continue
            if record.action is HoldAction.PLACED:
                placed[record.auth_id] = record
            else:
                released[record.auth_id] = record

        states = []
        for auth_id, place in placed.items():
            rel = released.get(auth_id)
            states.append(
                HoldState(
                    auth_id=auth_id,
                    account_id=account_id,
                    amount=place.amount,
                    placed_on=place.booked_day,
                    released_on=rel.booked_day if rel else None,
                    release_reason=rel.memo if rel else "",
                )
            )
        return tuple(sorted(states, key=lambda s: (s.placed_on, s.auth_id)))

    def active_holds_total(self, account_id: str, known_through: Day) -> Money:
        total = self.currency_of(account_id).zero()
        for state in self.hold_states(account_id, known_through):
            if state.is_active:
                total = total + state.amount
        return total

    def available_balance(self, account_id: str, day: Day) -> Money:
        """Ledger balance minus active holds -- the authorization test's input.

        The brief: "An authorization is approved only if the account's
        available balance -- ledger balance minus active holds -- remains at or
        above zero after the hold is applied."
        """
        return self.closing_balance(
            account_id, day, known_through=day
        ) - self.active_holds_total(account_id, day)

    def fee_for_day(self, account_id: str, day: Day) -> Optional[FeeAssessment]:
        for fee in self.fees:
            if fee.account_id == account_id and fee.for_day == day:
                return fee
        return None

    def net_accrual_for_day(self, account_id: str, day: Day) -> Money:
        total = self.currency_of(account_id).zero()
        for record in self.accruals:
            if record.account_id == account_id and record.accrual_day == day:
                total = total + record.amount
        return total

    def entries_booked_on(self, day: Day, account_id: Optional[str] = None):
        return tuple(
            e
            for e in self.entries
            if e.booked_day == day and (account_id is None or e.account_id == account_id)
        )

    def entry_by_seq(self, seq: int) -> Entry:
        for entry in self.entries:
            if entry.seq == seq:
                return entry
        raise KeyError(f"no entry with seq {seq}")

    def entries_for_event(self, event_id: str) -> tuple[Entry, ...]:
        return tuple(e for e in self.entries if e.source_event_id == event_id)
