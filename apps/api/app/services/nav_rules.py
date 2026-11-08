"""Pure business rules for NAV updates and sync sanity guards."""

from datetime import date


def should_update_latest(
    stored_date: date | None,
    incoming_date: date | None,
) -> bool:
    """Determine whether incoming NAV date should update the stored latest NAV.

    Latest NAV never moves backwards: update only when incoming_date >= stored_date.
    If incoming_date is None, returns False.
    If stored_date is None and incoming_date is present, returns True.
    """
    if incoming_date is None:
        return False
    if stored_date is None:
        return True
    return incoming_date >= stored_date


def evaluate_sanity_guard(
    parsed_count: int,
    active_count: int,
    min_schemes: int = 5000,
    is_valid_format: bool = True,
) -> tuple[bool, str | None]:
    """Evaluate whether a parsed AMFI payload meets the safety criteria to apply.

    Returns (is_sane, abort_reason).
    """
    if not is_valid_format:
        return False, "Response is not in the expected AMFI format or is invalid HTML."

    if parsed_count < min_schemes:
        return (
            False,
            f"Parsed schemes count ({parsed_count}) is below minimum threshold ({min_schemes}).",
        )

    if active_count > 0 and parsed_count < int(0.70 * active_count):
        threshold = int(0.70 * active_count)
        return (
            False,
            f"Parsed schemes count ({parsed_count}) is below 70% of active funds "
            f"({active_count}, required at least {threshold}).",
        )

    return True, None
