"""Unit tests for target allocation validation."""

from decimal import Decimal

import pytest

from app.core.errors import TargetsInvalidError
from app.services.target_allocation import validate_targets


def test_validate_targets_empty_is_valid() -> None:
    """Empty target allocation (unallocated portfolio) is valid."""
    validate_targets([])


def test_validate_targets_exact_100_percent_valid() -> None:
    """Valid target allocations summing to exactly 100.00%."""
    targets = [
        ("equity", Decimal("60.00")),
        ("debt", Decimal("30.00")),
        ("gold", Decimal("10.00")),
    ]
    validate_targets(targets)

    # All 5 canonical asset classes
    five_targets = [
        ("equity", Decimal("50.00")),
        ("debt", Decimal("20.00")),
        ("hybrid", Decimal("15.00")),
        ("gold", Decimal("10.00")),
        ("other", Decimal("5.00")),
    ]
    validate_targets(five_targets)


def test_validate_targets_rejects_sum_not_100() -> None:
    """Allocations summing to anything other than 100.00% are rejected."""
    # Sum 99.99
    with pytest.raises(TargetsInvalidError, match="must sum to exactly 100.00%"):
        validate_targets(
            [
                ("equity", Decimal("33.33")),
                ("debt", Decimal("33.33")),
                ("gold", Decimal("33.33")),
            ]
        )

    # Sum 100.01
    with pytest.raises(TargetsInvalidError, match="must sum to exactly 100.00%"):
        validate_targets(
            [
                ("equity", Decimal("60.01")),
                ("debt", Decimal("40.00")),
            ]
        )


def test_validate_targets_rejects_invalid_asset_class() -> None:
    """Reject non-canonical asset class."""
    with pytest.raises(TargetsInvalidError, match="Invalid asset class 'crypto'"):
        validate_targets(
            [
                ("crypto", Decimal("50.00")),
                ("equity", Decimal("50.00")),
            ]
        )


def test_validate_targets_rejects_duplicates() -> None:
    """Reject duplicate asset class entries."""
    with pytest.raises(TargetsInvalidError, match="Duplicate target asset class 'equity'"):
        validate_targets(
            [
                ("equity", Decimal("60.00")),
                ("equity", Decimal("40.00")),
            ]
        )


def test_validate_targets_rejects_zero_or_negative_or_exceeding_100() -> None:
    """Reject target_pct <= 0 or > 100."""
    with pytest.raises(TargetsInvalidError, match="between 0 and 100"):
        validate_targets([("equity", Decimal("0.00")), ("debt", Decimal("100.00"))])

    with pytest.raises(TargetsInvalidError, match="between 0 and 100"):
        validate_targets([("equity", Decimal("-10.00")), ("debt", Decimal("110.00"))])

    with pytest.raises(TargetsInvalidError, match="between 0 and 100"):
        validate_targets([("equity", Decimal("105.00"))])


def test_validate_targets_rejects_more_than_two_decimal_places() -> None:
    """Percentages cannot exceed 2 decimal places."""
    with pytest.raises(TargetsInvalidError, match="cannot have more than 2 decimal places"):
        validate_targets(
            [
                ("equity", Decimal("33.333")),
                ("debt", Decimal("66.667")),
            ]
        )


def test_validate_targets_rejects_more_than_max_rows() -> None:
    """Cannot exceed 5 rows."""
    with pytest.raises(TargetsInvalidError, match="Cannot configure more than 5"):
        validate_targets(
            [
                ("equity", Decimal("20.00")),
                ("debt", Decimal("20.00")),
                ("hybrid", Decimal("20.00")),
                ("gold", Decimal("20.00")),
                ("other", Decimal("10.00")),
                ("equity", Decimal("10.00")),  # 6th row
            ]
        )
