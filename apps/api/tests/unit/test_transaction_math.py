"""Unit and property tests for transaction math, scales, derivations, and tolerance."""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.errors import AmountMismatchError, ValidationError
from app.services.transaction_math import resolve_transaction_amounts, validate_scales


def test_validate_scales_limits() -> None:
    # Valid scales
    validate_scales(
        units=Decimal("123.4567"),
        nav=Decimal("123.12345678"),
        amount=Decimal("12345.67"),
    )

    # Units > 4 decimals rejected
    with pytest.raises(ValidationError, match="Units cannot exceed 4 decimal places"):
        validate_scales(units=Decimal("12.34567"))

    # NAV > 8 decimals rejected
    with pytest.raises(ValidationError, match="NAV cannot exceed 8 decimal places"):
        validate_scales(nav=Decimal("12.123456789"))

    # Amount > 2 decimals rejected
    with pytest.raises(ValidationError, match="Amount cannot exceed 2 decimal places"):
        validate_scales(amount=Decimal("100.555"))

    # Non-positive values rejected
    with pytest.raises(ValidationError, match="greater than zero"):
        validate_scales(units=Decimal("0"))

    with pytest.raises(ValidationError, match="greater than zero"):
        validate_scales(amount=Decimal("-10.00"))


def test_resolve_transaction_amounts_derivations() -> None:
    # 1. Units and NAV provided -> derives amount
    u, n, a = resolve_transaction_amounts(
        units=Decimal("10.5000"),
        nav=Decimal("50.25000000"),
        amount=None,
    )
    assert u == Decimal("10.5000")
    assert n == Decimal("50.25000000")
    assert a == Decimal("527.63")  # 10.5 * 50.25 = 527.625 -> 527.63

    # 2. Amount and NAV provided -> derives units
    u, n, a = resolve_transaction_amounts(
        units=None,
        nav=Decimal("100.00000000"),
        amount=Decimal("1000.00"),
    )
    assert u == Decimal("10.0000")
    assert n == Decimal("100.00000000")
    assert a == Decimal("1000.00")

    # 3. Units and Amount provided -> derives NAV
    u, n, a = resolve_transaction_amounts(
        units=Decimal("10.0000"),
        nav=None,
        amount=Decimal("1000.00"),
    )
    assert u == Decimal("10.0000")
    assert n == Decimal("100.00000000")
    assert a == Decimal("1000.00")

    # Fewer than 2 provided
    with pytest.raises(ValidationError, match="at least two"):
        resolve_transaction_amounts(units=Decimal("10"), nav=None, amount=None)


def test_resolve_transaction_amounts_tolerance_matching() -> None:
    units = Decimal("100.0000")
    nav = Decimal("10.00000000")
    # Expected amount = 1000.00
    # Tolerance = max(1.00, 1000 * 0.002 = 2.00) = 2.00

    # Within tolerance: 1001.50 -> diff 1.50 <= 2.00 -> OK
    u, n, a = resolve_transaction_amounts(units=units, nav=nav, amount=Decimal("1001.50"))
    assert a == Decimal("1001.50")

    # Within tolerance: 998.00 -> diff 2.00 <= 2.00 -> OK
    u, n, a = resolve_transaction_amounts(units=units, nav=nav, amount=Decimal("998.00"))
    assert a == Decimal("998.00")

    # Outside tolerance: 1002.50 -> diff 2.50 > 2.00 -> AmountMismatchError
    with pytest.raises(AmountMismatchError, match="exceeding allowable tolerance"):
        resolve_transaction_amounts(units=units, nav=nav, amount=Decimal("1002.50"))


# Property-based tests via Hypothesis
@given(
    units=st.decimals(
        min_value=Decimal("0.0100"),
        max_value=Decimal("10000.0000"),
        places=4,
    ),
    nav=st.decimals(
        min_value=Decimal("1.00000000"),
        max_value=Decimal("50000.00000000"),
        places=8,
    ),
)
@settings(max_examples=50)
def test_hypothesis_derivation_roundtrip(units: Decimal, nav: Decimal) -> None:
    """Deriving amount from (units, nav) always passes tolerance checks."""
    u_out, n_out, derived_amount = resolve_transaction_amounts(units=units, nav=nav, amount=None)
    assert u_out == units
    assert n_out == nav
    assert derived_amount > Decimal("0")

    # Passing all three with the derived amount must never raise AmountMismatchError
    u_chk, n_chk, a_chk = resolve_transaction_amounts(units=units, nav=nav, amount=derived_amount)
    assert u_chk == units
    assert n_chk == nav
    assert a_chk == derived_amount
