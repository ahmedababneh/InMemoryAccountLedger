"""Money and per-currency precision.

"AED is 2 decimal places, BHD is 3. Amounts stored and rounded to their own
precision."
"""

import unittest
from decimal import Decimal

from .support import replayed  # noqa: F401  (keeps sys.path setup in one place)
from ledger.money import (
    AED,
    BHD,
    CurrencyMismatch,
    Money,
    PrecisionError,
)


class PrecisionIsPerCurrency(unittest.TestCase):
    def test_each_currency_carries_its_own_minor_units(self):
        self.assertEqual(AED.minor_units, 2)
        self.assertEqual(BHD.minor_units, 3)
        self.assertEqual(AED.quantum, Decimal("0.01"))
        self.assertEqual(BHD.quantum, Decimal("0.001"))

    def test_over_precise_construction_is_rejected_not_silently_rounded(self):
        # The failure mode this guards against: a fils-level amount slipping
        # into an AED account and being rounded away by whichever operation
        # happens to touch it next.
        with self.assertRaises(PrecisionError):
            Money(AED, Decimal("0.005"))
        with self.assertRaises(PrecisionError):
            Money(BHD, Decimal("0.0005"))

    def test_under_precise_construction_is_normalised(self):
        self.assertEqual(str(Money(AED, Decimal("5"))), "AED 5.00")
        self.assertEqual(str(Money(BHD, Decimal("5"))), "BHD 5.000")

    def test_bhd_holds_three_places_that_aed_would_lose(self):
        self.assertEqual(str(BHD.exact("3.334")), "BHD 3.334")
        with self.assertRaises(PrecisionError):
            AED.exact("3.334")


class RoundingIsAlwaysExplicit(unittest.TestCase):
    def test_multiplication_returns_an_unrounded_decimal(self):
        # Money * rate deliberately does not return Money: the caller must
        # round, so every rounding site is visible in the source.
        raw = AED.exact("465.00").scaled_by(Decimal("0.0004"))
        self.assertIsInstance(raw, Decimal)
        self.assertEqual(raw, Decimal("0.186000"))

    def test_half_up_moves_ties_away_from_zero(self):
        # Python's built-in round() is half-to-even and would give 0.16 here.
        self.assertEqual(AED.round(Decimal("0.165")).amount, Decimal("0.17"))
        self.assertEqual(AED.round(Decimal("0.175")).amount, Decimal("0.18"))
        self.assertEqual(round(0.165, 2), 0.17)  # float, for contrast
        self.assertEqual(AED.round(Decimal("0.186")).amount, Decimal("0.19"))

    def test_decimal_beats_float_at_a_balance_close_to_this_scenario(self):
        # AED 462.50 is five dirhams from this scenario's real Day 4 balance.
        # float+round() gives 0.18; the correct half-up answer is 0.19.
        self.assertEqual(round(float(Decimal("462.50")) * 0.0004, 2), 0.18)
        self.assertEqual(
            AED.round(AED.exact("462.50").scaled_by(Decimal("0.0004"))).amount,
            Decimal("0.19"),
        )


class CurrenciesDoNotMix(unittest.TestCase):
    def test_adding_across_currencies_raises(self):
        with self.assertRaises(CurrencyMismatch):
            AED.exact("1.00") + BHD.exact("1.000")

    def test_comparing_across_currencies_raises(self):
        with self.assertRaises(CurrencyMismatch):
            _ = AED.exact("1.00") < BHD.exact("1.000")


if __name__ == "__main__":
    unittest.main()
