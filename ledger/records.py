"""The append-only record types.

"The ledger is append-only. No event record is ever mutated or deleted."

That rule is enforced structurally rather than by convention: every record here
is a frozen dataclass, and the only mutation the ledger offers is `append`.
Consequences that fall out of it, and that shaped the rest of the design:

  * A reversal is a *new compensating entry*, not the removal of the original.
    Both E7 and its reversal E9 sit in the ledger forever.
  * A rejected or declined event is still a recorded fact.  It produces a
    Decision with no Entry, so the ledger remembers that someone tried.
  * A hold is never decremented in place.  Placing and releasing a hold are two
    separate HoldRecords, and "what is held right now" is a *projection* over
    that log rather than a mutable number.
  * An interest accrual that a backdated entry invalidates is not edited.  A
    further AccrualRecord carrying the delta is appended, and the day's net
    accrual is the sum of its records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .money import Money


# Days are plain ordinals 1..6.  There is no clock, no timezone and no
# intraday time: the brief's window is "Day 1 through Day 6" and inventing
# timestamps would invent a cutover policy nobody specified (AMBIGUITIES.md #1).
Day = int

OPENING_DAY: Day = 0  # value_date for opening balances: before the window starts


class EventType(str, Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    AUTHORIZATION = "AUTHORIZATION"
    SETTLEMENT = "SETTLEMENT"
    REVERSAL = "REVERSAL"


class Outcome(str, Enum):
    APPLIED = "APPLIED"        # posted to the ledger
    APPROVED = "APPROVED"      # authorization accepted, hold placed
    DECLINED = "DECLINED"      # authorization refused on available balance
    REJECTED = "REJECTED"      # event could not be applied at all


class EntryKind(str, Enum):
    OPENING = "OPENING"
    POSTING = "POSTING"                  # from a CREDIT/DEBIT/SETTLEMENT event
    REVERSAL = "REVERSAL"                # compensating entry for a prior entry
    OVERDRAFT_FEE = "OVERDRAFT_FEE"
    INTEREST_CAPITALISATION = "INTEREST_CAPITALISATION"


class HoldAction(str, Enum):
    PLACED = "PLACED"
    RELEASED = "RELEASED"


@dataclass(frozen=True)
class Event:
    """An inbound instruction, exactly as it arrived. Never edited."""

    event_id: str
    booked_day: Day          # the day the instruction reaches the ledger
    type: EventType
    account_id: str
    value_date: Day          # the day it takes economic effect
    amount: Optional[Money] = None
    auth_id: Optional[str] = None
    reverses_event_id: Optional[str] = None
    instalments: int = 1
    memo: str = ""

    def __post_init__(self) -> None:
        if self.value_date > self.booked_day:
            # Forward-valued entries would need an accrual-vs-availability
            # policy the brief does not define; none appear in the stream, so
            # reject rather than guess (AMBIGUITIES.md #14).
            raise ValueError(
                f"{self.event_id}: value_date {self.value_date} is after "
                f"booked_day {self.booked_day}; forward value-dating is not supported"
            )
        if self.instalments < 1:
            raise ValueError(f"{self.event_id}: instalments must be >= 1")


@dataclass(frozen=True)
class Entry:
    """A posting that moves the ledger balance. Append-only."""

    seq: int
    account_id: str
    amount: Money            # signed: credits positive, debits negative
    value_date: Day          # drives every balance in this system
    booked_day: Day          # when the ledger learned about it
    kind: EntryKind
    source_event_id: Optional[str] = None
    reverses_entry_seq: Optional[int] = None
    memo: str = ""


@dataclass(frozen=True)
class HoldRecord:
    """One state transition of an authorization hold. Append-only."""

    seq: int
    account_id: str
    auth_id: str
    action: HoldAction
    amount: Money
    booked_day: Day
    source_event_id: str
    memo: str = ""


@dataclass(frozen=True)
class AccrualRecord:
    """A daily interest accrual, or a revision to one.

    `amount` is the *delta* applied to the day's running accrual, so a day's
    net accrual is the sum of its records.  `computed` is the full recomputed
    value for the day, kept for the audit trail.  A backdated entry that
    changes a past day's closing balance appends a revision here; it never
    edits the original record.
    """

    seq: int
    account_id: str
    accrual_day: Day         # the day the interest is earned for
    evaluated_on: Day        # the EOD run that produced this record
    basis: Money             # closing balance used
    computed: Money          # rounded accrual for accrual_day as now understood
    amount: Money            # delta vs the previously recorded net
    memo: str = ""


@dataclass(frozen=True)
class Decision:
    """The outcome of processing one event, including refusals."""

    seq: int
    day: Day
    event_id: str
    account_id: str
    outcome: Outcome
    reason: str = ""

    @property
    def is_error(self) -> bool:
        return self.outcome in (Outcome.REJECTED, Outcome.DECLINED)


@dataclass(frozen=True)
class FeeAssessment:
    """Record that an overdraft fee was assessed for a given day.

    Kept alongside the fee Entry so that "once per day per account" can be
    checked without re-deriving intent from entry metadata.
    """

    seq: int
    account_id: str
    for_day: Day             # the day whose closing balance was negative
    assessed_on: Day         # the EOD run that noticed
    closing_balance: Money   # the balance that triggered it, before the fee
    amount: Money
    entry_seq: int


class AppendOnlyLog:
    """A list that only grows, handing out read-only views.

    Deliberately not a plain list: the ledger passes these around, and a bare
    list invites `log[3] = ...` or `log.pop()` from a future caller who has not
    read the brief.
    """

    __slots__ = ("_items",)

    def __init__(self) -> None:
        self._items: list = []

    def append(self, item):
        self._items.append(item)
        return item

    def __iter__(self):
        return iter(tuple(self._items))

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index):
        return tuple(self._items)[index]

    @property
    def next_seq(self) -> int:
        return len(self._items) + 1

    def all(self) -> tuple:
        return tuple(self._items)
