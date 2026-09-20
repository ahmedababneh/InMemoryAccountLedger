"""Money: a currency-tagged decimal amount that knows its own precision.

Two rules from the brief drive every design choice in this module:

  * "AED is 2 decimal places, BHD is 3."
  * "Amounts stored and rounded to their own precision."

So precision is a property of the *currency*, never a global constant, and a
Money value is only constructible at its currency's exact precision.  Rounding
is therefore never implicit: callers that hold a more precise Decimal (an
interest computation, an instalment split) must say so by calling
``Currency.round`` explicitly.  Every rounding site in this codebase is thus
greppable, which is the point -- a rounding you cannot find is a rounding you
cannot audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


class CurrencyMismatch(Exception):
    """Raised when two amounts in different currencies are combined."""


class PrecisionError(Exception):
    """Raised when an amount carries more precision than its currency allows."""


@dataclass(frozen=True)
class Currency:
    """An ISO 4217 currency and its minor-unit count."""

    code: str
    minor_units: int

    @property
    def quantum(self) -> Decimal:
        """The smallest representable amount, e.g. Decimal('0.01') for AED."""
        return Decimal(1).scaleb(-self.minor_units)

    def round(self, value: Decimal) -> "Money":
        """Explicitly round an arbitrary-precision Decimal into this currency.

        ROUND_HALF_UP, not Python's default banker's rounding: see NUMBERS.md
        for why a retail ledger wants ties to move away from zero.
        """
        return Money(self, value.quantize(self.quantum, rounding=ROUND_HALF_UP))

    def exact(self, literal: str) -> "Money":
        """Build a Money from a literal that must already be at full precision."""
        return Money(self, Decimal(literal))

    def zero(self) -> "Money":
        return Money(self, Decimal(0).quantize(self.quantum))


AED = Currency("AED", 2)
BHD = Currency("BHD", 3)

CURRENCIES = {c.code: c for c in (AED, BHD)}


@dataclass(frozen=True, order=False)
class Money:
    """An immutable amount, exact at its currency's precision.

    Construction *rejects* over-precise input rather than silently rounding it.
    Under-precise input (Decimal('5') for AED) is normalised to '5.00', which
    changes no value and keeps string output stable.
    """

    currency: Currency
    amount: Decimal

    def __post_init__(self) -> None:
        exponent = self.amount.as_tuple().exponent
        if not isinstance(exponent, int):
            raise PrecisionError(f"non-finite amount {self.amount!r}")
        if -exponent > self.currency.minor_units:
            raise PrecisionError(
                f"{self.amount} has {-exponent} dp, {self.currency.code} allows "
                f"{self.currency.minor_units}; use Currency.round() to round explicitly"
            )
        # Normalise the exponent so equality and str() are stable.
        object.__setattr__(
            self, "amount", self.amount.quantize(self.currency.quantum)
        )

    # -- arithmetic -------------------------------------------------------
    # Addition and subtraction are closed over a currency's representable
    # amounts, so neither can ever need to round.  Multiplication is not, so it
    # deliberately returns a raw Decimal and forces the caller to round.

    def _check(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise CurrencyMismatch(
                f"cannot combine {self.currency.code} with {other.currency.code}"
            )

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.currency, self.amount + other.amount)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.currency, self.amount - other.amount)

    def __neg__(self) -> "Money":
        return Money(self.currency, -self.amount)

    def scaled_by(self, factor: Decimal) -> Decimal:
        """Multiply, returning an unrounded Decimal on purpose.

        The caller must pass the result through ``Currency.round`` to get a
        storable amount.  This is what stops a rate multiplication from
        quietly inventing precision.
        """
        return self.amount * factor

    # -- comparison -------------------------------------------------------

    def __lt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount >= other.amount

    def is_negative(self) -> bool:
        return self.amount < 0

    def is_positive(self) -> bool:
        return self.amount > 0

    def is_zero(self) -> bool:
        return self.amount == 0

    # -- rendering --------------------------------------------------------

    def __str__(self) -> str:
        return f"{self.currency.code} {self.amount:,.{self.currency.minor_units}f}"

    def __repr__(self) -> str:
        return f"Money({self.currency.code}, {self.amount})"


def zero_like(m: Money) -> Money:
    return m.currency.zero()
