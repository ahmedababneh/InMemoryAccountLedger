"""Rendering the replay as text.

The brief asks for four things per day: closing ledger balance, fee
assessments, authorization states, and errors.  All four are printed for every
day and every account.

One addition that is not decoration.  Because entries can be back-valued, a
day has two closing balances -- the one the ledger believed at that day's
close, and the one it settled on once everything was known.  Printing only the
first hides the restatement; printing only the second hides the fact that fees
were assessed against a view that later changed.  Both are shown, and the
restated column is repeated in a final table.
"""

from __future__ import annotations

from typing import List

from .engine import Engine
from .records import Day, EntryKind, Outcome

RULE = "=" * 78
THIN = "-" * 78


def _fmt_day(day: Day) -> str:
    return f"Day {day}"


def render(engine: Engine) -> str:
    out: List[str] = []
    book = engine.book
    policy = engine.policy

    out.append(RULE)
    out.append("IN-MEMORY ACCOUNT LEDGER — six-day replay")
    out.append(RULE)
    out.append("")
    out.append("Accounts")
    for account in book.accounts.values():
        out.append(
            f"  {account.account_id}  {account.currency.code} "
            f"({account.currency.minor_units} dp)  opening {account.opening_balance}"
        )
    out.append("")
    out.append(
        f"Interest {policy.interest.daily_rate * 100:.2f}% per day on positive "
        f"closing balances, capitalised end of {_fmt_day(policy.last_day)}."
    )
    fees = ", ".join(f"{c} {m.amount}" for c, m in policy.overdraft.fees.items())
    out.append(f"Overdraft fee, once per account per day: {fees}.")
    out.append("")

    for day in policy.days:
        out.append(RULE)
        out.append(f"{_fmt_day(day)}")
        out.append(RULE)

        events = engine.events_for_day(day)
        out.append("  Events booked today")
        if not events:
            out.append("    (none)")
        for event in events:
            detail = f"    {event.event_id}  {event.type.value:<14} {event.account_id}"
            if event.amount is not None:
                detail += f"  {event.amount}"
            if event.auth_id:
                detail += f"  [{event.auth_id}]"
            if event.reverses_event_id:
                detail += f"  reverses {event.reverses_event_id}"
            detail += f"  value_date={_fmt_day(event.value_date)}"
            if event.instalments > 1:
                detail += f"  x{event.instalments} instalments"
            out.append(detail)

        for account_id in book.accounts:
            currency = book.currency_of(account_id)
            as_of = book.closing_balance(account_id, day, known_through=day)
            available = book.available_balance(account_id, day)
            held = book.active_holds_total(account_id, day)

            out.append("")
            out.append(f"  {account_id}")
            out.append(f"    Closing ledger balance .... {as_of}")
            out.append(f"    Active holds .............. {held}")
            out.append(f"    Available balance ......... {available}")

            # -- fee assessments -------------------------------------------
            assessed_today = [
                f for f in book.fees if f.account_id == account_id and f.assessed_on == day
            ]
            out.append("    Fee assessments ...........")
            if not assessed_today:
                out.append("      (none)")
            for fee in assessed_today:
                note = ""
                if fee.for_day != day:
                    note = "  <- back-valued to a day already closed"
                out.append(
                    f"      overdraft {fee.amount} value_date={_fmt_day(fee.for_day)}"
                    f" (that day closed {fee.closing_balance}){note}"
                )

            # -- authorization states --------------------------------------
            out.append("    Authorization states ......")
            states = book.hold_states(account_id, known_through=day)
            declined = [
                d
                for d in book.decisions
                if d.account_id == account_id
                and d.day <= day
                and d.outcome is Outcome.DECLINED
            ]
            if not states and not declined:
                out.append("      (none)")
            for state in states:
                line = (
                    f"      {state.auth_id:<8} {state.state:<8} hold {state.amount}"
                    f"  placed {_fmt_day(state.placed_on)}"
                )
                if state.released_on is not None:
                    line += f"  closed {_fmt_day(state.released_on)}"
                out.append(line)
            for decision in declined:
                event = next(e for e in book.events if e.event_id == decision.event_id)
                out.append(
                    f"      {event.auth_id:<8} DECLINED hold {event.amount}"
                    f"  requested {_fmt_day(decision.day)}  no hold placed"
                )

            # -- errors ----------------------------------------------------
            errors = [
                d
                for d in book.decisions
                if d.account_id == account_id and d.day == day and d.is_error
            ]
            out.append("    Errors ....................")
            if not errors:
                out.append("      (none)")
            for error in errors:
                out.append(f"      {error.event_id}  {error.outcome.value}: {error.reason}")

            # -- interest ---------------------------------------------------
            # Point-in-time: what the accrual journal held for this day at this
            # day's close.  A later back-valued entry may revise it, and the
            # reconciliation table at the bottom shows the final figure.
            accrual = book.net_accrual_for_day(account_id, day, evaluated_through=day)
            out.append(f"    Interest accrued for today  {accrual}")

            # Revisions this close made to *earlier* days' accruals.
            revisions = [
                r
                for r in book.accruals
                if r.account_id == account_id
                and r.evaluated_on == day
                and r.accrual_day < day
            ]
            if revisions:
                out.append("    Interest revised for earlier days")
                for record in revisions:
                    out.append(
                        f"      {_fmt_day(record.accrual_day):<8} -> {record.computed}"
                        f"  (delta {record.amount}, basis now {record.basis})"
                    )
        out.append("")

    # -- restatement ------------------------------------------------------
    out.append(RULE)
    out.append("RESTATED CLOSING BALANCES (every entry known, end of window)")
    out.append(RULE)
    for account_id in book.accounts:
        out.append("")
        out.append(f"  {account_id}")
        out.append(
            f"    {'day':<6}{'as-of that day':>20}{'restated':>18}{'delta':>16}"
        )
        out.append("    " + THIN[:60])
        for day in policy.days:
            as_of = book.closing_balance(account_id, day, known_through=day)
            final = book.closing_balance(account_id, day)
            delta = final - as_of
            flag = "  *" if not delta.is_zero() else ""
            out.append(
                f"    {day:<6}{str(as_of):>20}{str(final):>18}{str(delta):>16}{flag}"
            )
        out.append("    * restated after a back-valued entry arrived later")

    # -- interest reconciliation ------------------------------------------
    out.append("")
    out.append(RULE)
    out.append("INTEREST RECONCILIATION")
    out.append(RULE)
    for account_id, account in book.accounts.items():
        dailies = engine.daily_accruals(account_id)
        out.append("")
        out.append(f"  {account_id}")
        for day, amount in dailies.items():
            # The basis actually used: closing balance before capitalisation.
            basis = book.interest_basis(account_id, day)
            out.append(
                f"    {_fmt_day(day):<8} basis {str(basis):>16}"
                f"  x {policy.interest.daily_rate}  ->  {amount}"
            )
        total = account.currency.zero()
        for amount in dailies.values():
            total = total + amount
        out.append("    " + THIN[:60])
        out.append(f"    sum of rounded daily accruals .... {total}")
        out.append(f"    capitalised credit on Day {policy.last_day} ....... "
                   f"{engine.capitalised[account_id]}")
        match = "MATCH" if total == engine.capitalised[account_id] else "MISMATCH"
        out.append(f"    reconciliation ................... {match}")

    # -- final position ---------------------------------------------------
    out.append("")
    out.append(RULE)
    out.append("FINAL POSITION")
    out.append(RULE)
    for account_id in book.accounts:
        final = book.closing_balance(account_id, policy.last_day)
        fees = [f for f in book.fees if f.account_id == account_id]
        fee_total = book.currency_of(account_id).zero()
        for fee in fees:
            fee_total = fee_total + fee.amount
        out.append("")
        out.append(f"  {account_id}")
        out.append(f"    closing balance ........ {final}")
        out.append(f"    overdraft fees charged . {fee_total} across {len(fees)} day(s)")
        out.append(f"    interest capitalised ... {engine.capitalised[account_id]}")
        out.append(f"    ledger entries ......... "
                   f"{len([e for e in book.entries if e.account_id == account_id])}")

    # -- audit trail ------------------------------------------------------
    out.append("")
    out.append(RULE)
    out.append("ENTRY LOG (append-only, nothing here was ever edited or removed)")
    out.append(RULE)
    out.append(
        f"  {'seq':<5}{'acct':<10}{'booked':<8}{'value':<7}{'kind':<26}{'amount':>14}"
    )
    out.append("  " + THIN)
    for entry in book.entries:
        out.append(
            f"  {entry.seq:<5}{entry.account_id:<10}"
            f"{_fmt_day(entry.booked_day):<8}{_fmt_day(entry.value_date):<7}"
            f"{entry.kind.value:<26}{str(entry.amount):>14}"
        )
    out.append("")
    return "\n".join(out)
