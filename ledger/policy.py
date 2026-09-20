"""Every configurable number in the system, in one place.

Nothing in the engine hardcodes a rate, a fee, a precision or a day count.
NUMBERS.md explains each value, why it is that value, and what visibly changes
if you halve it.  The overdraft fee in particular is keyed *by currency*: the
brief gives a fee for AED and none for BHD, and silently posting an AED-shaped
number into a 3dp BHD account would be a real bug hiding behind a default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Optional

from .money import AED, Currency, Money


class PolicyNotConfigured(Exception):
    """Raised when policy is asked for a value the brief never supplied."""


@dataclass(frozen=True)
class InterestPolicy:
    """Daily simple interest, credit balances only, capitalised once."""

    # 0.04% per day, expressed as a decimal fraction. Exact, not a float.
    daily_rate: Decimal = Decimal("0.0004")

    # "positive balances only" -- a negative closing balance accrues nothing.
    # Zero is not positive, so a flat account accrues nothing either.
    credit_only: bool = True

    def accrual_for(self, closing_balance: Money) -> Money:
        """Rounded accrual for one day on one closing balance.

        Rounded here, once, to the account's own precision.  The brief requires
        that the rounded dailies sum exactly to the capitalised total, so the
        rounded daily figure is the unit of account -- there is no parallel
        unrounded running total that the capitalisation could be taken from.
        """
        currency = closing_balance.currency
        if self.credit_only and not closing_balance.is_positive():
            return currency.zero()
        return currency.round(closing_balance.scaled_by(self.daily_rate))


@dataclass(frozen=True)
class OverdraftPolicy:
    """A flat fee, at most once per account per day, per currency."""

    fees: Dict[str, Money] = field(
        default_factory=lambda: {
            "AED": AED.exact("25.00"),
            # BHD intentionally absent: the brief specifies no BHD overdraft
            # fee.  An overdrawn BHD account therefore raises rather than
            # guessing a number.  See AMBIGUITIES.md #12.
        }
    )

    def fee_for(self, currency: Currency) -> Money:
        try:
            return self.fees[currency.code]
        except KeyError:
            raise PolicyNotConfigured(
                f"no overdraft fee configured for {currency.code}; refusing to "
                f"invent one"
            ) from None

    def has_fee_for(self, currency: Currency) -> bool:
        return currency.code in self.fees


@dataclass(frozen=True)
class Policy:
    interest: InterestPolicy = field(default_factory=InterestPolicy)
    overdraft: OverdraftPolicy = field(default_factory=OverdraftPolicy)

    # The replay window. Day 1 .. Day 6 inclusive; capitalisation lands on
    # last_day.
    first_day: int = 1
    last_day: int = 6

    # Where an overdraft fee lands when a back-valued entry makes a *past* day
    # close negative. False (the default) reads "booked with value_date equal
    # to the day assessed" as the day whose balance was negative, so a Day-2
    # overdraft discovered on Day 5 is value-dated to Day 2. True reads it as
    # the day the assessment ran. The alternative exists so that REJECTED.md's
    # claim -- that acceptance criterion 2 is wrong under *either* reading --
    # is a test rather than an assertion. AMBIGUITIES.md #3.
    fee_value_dated_to_assessment_day: bool = False

    # A settlement closes its authorization outright, releasing the whole
    # remaining hold even when it settles for less (E5: 185.00 against a
    # 200.00 hold). AMBIGUITIES.md #8.
    settlement_releases_full_hold: bool = True

    # A settlement may exceed the hold it closes; card schemes permit overage
    # and the funds have already been authorised. Does not arise in this
    # stream. AMBIGUITIES.md #9.
    allow_settlement_over_hold: bool = True

    # Holds do not expire inside a six-day window; the brief gives no expiry
    # period, so Auth-B would stay active to Day 6 had it been approved.
    # AMBIGUITIES.md #11.
    hold_expiry_days: Optional[int] = None

    # A reversal never refunds a fee that a prior state of the ledger had
    # already made true. This is the single most consequential policy choice in
    # the build; it is what acceptance criterion 6 gets wrong, and it is also
    # the thing the deliberately-failing test attacks.
    # AMBIGUITIES.md #5, REJECTED.md criterion 6, tests/test_known_design_gap.py
    reversal_refunds_consequential_fees: bool = False

    # ------------------------------------------------------------------
    # Three of the settings above record a decision but have no alternative
    # implementation behind them: `settlement_releases_full_hold`,
    # `hold_expiry_days` and `reversal_refunds_consequential_fees`. They are
    # here because the decision needed a name and a place to be cited from,
    # not because the other branch exists.
    #
    # A flag that looks like configuration and silently does nothing when
    # flipped is worse than no flag: it invites someone to change it, watch the
    # output stay identical, and conclude the setting does not matter. So
    # setting one away from its documented default raises here, naming where
    # the decision is written up and what implementing it would involve.
    # ------------------------------------------------------------------

    _UNIMPLEMENTED = {
        "settlement_releases_full_hold": (
            True,
            "a settlement would have to release only the amount it settles and "
            "leave the remainder held, which in turn needs the hold-expiry "
            "policy of #11 to ever clear it. AMBIGUITIES.md #8.",
        ),
        "hold_expiry_days": (
            None,
            "holds would have to be released automatically N days after being "
            "placed, and the brief specifies no N. AMBIGUITIES.md #11.",
        ),
        "reversal_refunds_consequential_fees": (
            False,
            "deliberately not implemented. See tests/test_known_design_gap.py, "
            "which fails on purpose to keep this decision visible, and "
            "AMBIGUITIES.md #5.",
        ),
    }

    def __post_init__(self) -> None:
        for name, (default, note) in self._UNIMPLEMENTED.items():
            if getattr(self, name) != default:
                raise PolicyNotConfigured(
                    f"{name}={getattr(self, name)!r} is not implemented; the "
                    f"only supported value is {default!r}. To change it, "
                    f"{note}"
                )
        if self.last_day < self.first_day:
            raise ValueError("last_day must not precede first_day")

    @property
    def days(self) -> range:
        return range(self.first_day, self.last_day + 1)


DEFAULT_POLICY = Policy()
