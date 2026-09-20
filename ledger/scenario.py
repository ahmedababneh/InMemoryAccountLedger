"""The six-day event stream from the brief, transcribed verbatim.

Deliberately data, not code: nothing here decides anything, so the engine has
nowhere to hide a special case.  The `booked_day` / `value_date` split is the
load-bearing detail -- note E7, booked on Day 5 but value-dated to Day 2.
"""

from __future__ import annotations

from .book import Account
from .money import AED, BHD
from .records import Event, EventType

ACC_001 = Account("ACC-001", AED, AED.exact("0.00"))
ACC_002 = Account("ACC-002", BHD, BHD.exact("0.000"))

ACCOUNTS = (ACC_001, ACC_002)


def build_events() -> list[Event]:
    return [
        Event(
            event_id="E1",
            booked_day=1,
            type=EventType.CREDIT,
            account_id="ACC-001",
            value_date=1,
            amount=AED.exact("1200.00"),
            memo="opening funding credit",
        ),
        Event(
            event_id="E2",
            booked_day=1,
            type=EventType.DEBIT,
            account_id="ACC-001",
            value_date=1,
            amount=AED.exact("950.00"),
        ),
        Event(
            event_id="E3",
            booked_day=2,
            type=EventType.AUTHORIZATION,
            account_id="ACC-001",
            value_date=2,
            amount=AED.exact("200.00"),
            auth_id="Auth-A",
        ),
        Event(
            event_id="E4",
            booked_day=3,
            type=EventType.CREDIT,
            account_id="ACC-001",
            value_date=3,
            amount=AED.exact("400.00"),
        ),
        Event(
            event_id="E5",
            booked_day=4,
            type=EventType.SETTLEMENT,
            account_id="ACC-001",
            value_date=4,
            amount=AED.exact("185.00"),
            auth_id="Auth-A",
        ),
        Event(
            event_id="E6",
            booked_day=4,
            type=EventType.SETTLEMENT,
            account_id="ACC-001",
            value_date=4,
            amount=AED.exact("180.00"),
            auth_id="Auth-Z",
            memo="no preceding authorization exists for Auth-Z",
        ),
        # The pivot of the whole exercise: booked on Day 5, effective Day 2.
        Event(
            event_id="E7",
            booked_day=5,
            type=EventType.DEBIT,
            account_id="ACC-001",
            value_date=2,
            amount=AED.exact("620.00"),
            memo="back-valued debit",
        ),
        Event(
            event_id="E8",
            booked_day=5,
            type=EventType.AUTHORIZATION,
            account_id="ACC-001",
            value_date=5,
            amount=AED.exact("90.00"),
            auth_id="Auth-B",
            memo="never settled inside the window",
        ),
        Event(
            event_id="E9",
            booked_day=6,
            type=EventType.REVERSAL,
            account_id="ACC-001",
            value_date=2,
            reverses_event_id="E7",
        ),
        Event(
            event_id="E10",
            booked_day=5,
            type=EventType.CREDIT,
            account_id="ACC-002",
            value_date=5,
            amount=BHD.exact("10.000"),
            instalments=3,
            memo="posted as three equal instalments",
        ),
    ]
