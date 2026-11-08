"""Target allocation validation service."""

from decimal import Decimal

from app.core.classification_constants import VALID_ASSET_CLASSES
from app.core.constants import MAX_TARGET_ROWS
from app.core.errors import TargetsInvalidError


def validate_targets(targets: list[tuple[str, Decimal]]) -> None:
    """Validate target asset allocations for a portfolio.

    Rules:
    - Empty list is valid (unallocated portfolio).
    - If non-empty, row count cannot exceed MAX_TARGET_ROWS (5).
    - Each asset_class must be in VALID_ASSET_CLASSES.
    - Each asset_class must be unique.
    - Each target_pct must be > 0 and <= 100.
    - target_pct can have at most 2 decimal places.
    - Sum of target_pct must equal EXACTLY 100.00.
    """
    if not targets:
        return

    if len(targets) > MAX_TARGET_ROWS:
        raise TargetsInvalidError(
            f"Cannot configure more than {MAX_TARGET_ROWS} target allocations"
        )

    seen_classes: set[str] = set()
    total_pct = Decimal("0")

    for asset_class, pct in targets:
        if asset_class not in VALID_ASSET_CLASSES:
            raise TargetsInvalidError(
                f"Invalid asset class '{asset_class}'. Must be one of {sorted(VALID_ASSET_CLASSES)}"
            )

        if asset_class in seen_classes:
            raise TargetsInvalidError(f"Duplicate target asset class '{asset_class}'")
        seen_classes.add(asset_class)

        if pct <= Decimal("0") or pct > Decimal("100"):
            raise TargetsInvalidError(
                f"Target percentage for '{asset_class}' must be between 0 and 100 (got {pct})"
            )

        # Ensure at most 2 decimal places
        exp = pct.as_tuple().exponent
        if not isinstance(exp, int) or exp < -2:
            raise TargetsInvalidError(
                f"Target percentage for '{asset_class}' cannot have more than 2 decimal places"
            )

        total_pct += pct

    if total_pct != Decimal("100.00"):
        raise TargetsInvalidError(
            f"Target allocations must sum to exactly 100.00% (sum was {total_pct}%)",
            details={"sum": str(total_pct)},
        )
