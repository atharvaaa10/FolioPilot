"""Transaction amount derivation, scale validation, and tolerance checks."""

from decimal import ROUND_HALF_UP, Decimal

from app.core.constants import AMOUNT_TOLERANCE_ABSOLUTE, AMOUNT_TOLERANCE_RELATIVE
from app.core.errors import AmountMismatchError, ValidationError

UNITS_QUANT = Decimal("0.0001")
NAV_QUANT = Decimal("0.00000001")
AMOUNT_QUANT = Decimal("0.01")

UNITS_SCALE: int = abs(int(UNITS_QUANT.as_tuple().exponent))
NAV_SCALE: int = abs(int(NAV_QUANT.as_tuple().exponent))
AMOUNT_SCALE: int = abs(int(AMOUNT_QUANT.as_tuple().exponent))


def validate_scales(
    units: Decimal | None = None,
    nav: Decimal | None = None,
    amount: Decimal | None = None,
) -> None:
    """Validate decimal scale limits for transaction inputs."""
    if units is not None:
        if not units.is_finite():
            raise ValidationError("Units must be a finite number")
        if units <= Decimal("0"):
            raise ValidationError("Units must be greater than zero")
        exp = units.as_tuple().exponent
        if not isinstance(exp, int) or exp < -UNITS_SCALE:
            raise ValidationError(f"Units cannot exceed {UNITS_SCALE} decimal places")

    if nav is not None:
        if not nav.is_finite():
            raise ValidationError("NAV must be a finite number")
        if nav <= Decimal("0"):
            raise ValidationError("NAV must be greater than zero")
        exp = nav.as_tuple().exponent
        if not isinstance(exp, int) or exp < -NAV_SCALE:
            raise ValidationError(f"NAV cannot exceed {NAV_SCALE} decimal places")

    if amount is not None:
        if not amount.is_finite():
            raise ValidationError("Amount must be a finite number")
        if amount <= Decimal("0"):
            raise ValidationError("Amount must be greater than zero")
        exp = amount.as_tuple().exponent
        if not isinstance(exp, int) or exp < -AMOUNT_SCALE:
            raise ValidationError(f"Amount cannot exceed {AMOUNT_SCALE} decimal places")


def resolve_transaction_amounts(
    units: Decimal | None,
    nav: Decimal | None,
    amount: Decimal | None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Resolve any two of {units, nav, amount} or validate all three within tolerance.

    Returns (resolved_units, resolved_nav, resolved_amount).
    """
    validate_scales(units=units, nav=nav, amount=amount)

    provided = [v is not None for v in (units, nav, amount)]
    if sum(provided) < 2:
        raise ValidationError("Must provide at least two of units, nav, and amount")

    # Case 1: All three provided -> validate amount within tolerance
    if units is not None and nav is not None and amount is not None:
        expected_amount = (units * nav).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
        rel_tol = (expected_amount * AMOUNT_TOLERANCE_RELATIVE).quantize(
            AMOUNT_QUANT, rounding=ROUND_HALF_UP
        )
        tolerance = max(AMOUNT_TOLERANCE_ABSOLUTE, rel_tol)
        diff = abs(amount - expected_amount)

        if diff > tolerance:
            raise AmountMismatchError(
                f"Provided amount ₹{amount} differs from units * NAV (₹{expected_amount}) "
                f"by ₹{diff}, exceeding allowable tolerance of ₹{tolerance}",
                details={"expected": str(expected_amount), "given": str(amount)},
            )
        return units, nav, amount

    # Case 2: units and nav provided -> derive amount
    if units is not None and nav is not None and amount is None:
        derived_amount = (units * nav).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
        if derived_amount <= Decimal("0"):
            raise ValidationError("Derived amount must be greater than zero")
        return units, nav, derived_amount

    # Case 3: amount and nav provided -> derive units
    if amount is not None and nav is not None and units is None:
        derived_units = (amount / nav).quantize(UNITS_QUANT, rounding=ROUND_HALF_UP)
        if derived_units <= Decimal("0"):
            raise ValidationError("Derived units must be greater than zero")
        return derived_units, nav, amount

    # Case 4: units and amount provided -> derive nav
    if units is not None and amount is not None and nav is None:
        derived_nav = (amount / units).quantize(NAV_QUANT, rounding=ROUND_HALF_UP)
        if derived_nav <= Decimal("0"):
            raise ValidationError("Derived NAV must be greater than zero")
        return units, derived_nav, amount

    raise ValidationError("Invalid combination of units, nav, and amount")
