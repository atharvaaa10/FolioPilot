"""Pure SIP scheduling, step-up calculation, and status derivation.

Adheres strictly to CONVENTIONS.md:
- Pure functions only (no database, no network, no side-effects).
- Does not raise domain exceptions; returns empty lists, booleans, or derived values.
- Exact Decimal arithmetic with single ROUND_HALF_UP quantization.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol


class PauseInterval(Protocol):
    paused_from: date
    resumed_on: date | None


def first_due_date(start_date: date, day_of_month: int) -> date:
    """Calculate the first due date on or after start_date whose day equals day_of_month.

    day_of_month must be between 1 and 28.
    """
    if start_date.day <= day_of_month:
        return date(start_date.year, start_date.month, day_of_month)

    if start_date.month == 12:
        return date(start_date.year + 1, 1, day_of_month)
    return date(start_date.year, start_date.month + 1, day_of_month)


def compute_k(origin_due_date: date, current_due_date: date) -> int:
    """Compute step-up exponent k between schedule origin due date and current due date.

    k = (whole months between FIRST due date's month and current due date's month) // 12.
    """
    months_diff = (current_due_date.year - origin_due_date.year) * 12 + (
        current_due_date.month - origin_due_date.month
    )
    return max(0, months_diff // 12)


def planned_amount(base_amount: Decimal, step_up_percent: Decimal, k: int) -> Decimal:
    """Calculate planned installment amount for step-up tier k.

    amount = base_amount * (1 + step_up_percent/100) ** k
    Computed in Decimal and quantized once to 0.01 with ROUND_HALF_UP.
    """
    if k <= 0 or step_up_percent <= Decimal("0"):
        return base_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    rate = Decimal("1") + (step_up_percent / Decimal("100"))
    factor = rate**k
    total = base_amount * factor
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def is_date_in_pauses(d: date, pauses: list[Any]) -> bool:
    """Check whether a given date falls inside any pause interval [paused_from, resumed_on)."""
    for pause in pauses:
        p_from = getattr(pause, "paused_from", None)
        p_res = getattr(pause, "resumed_on", None)
        if p_from is None:
            continue
        if p_res is None:
            if d >= p_from:
                return True
        else:
            if p_from <= d < p_res:
                return True
    return False


def validate_pauses(pauses: list[Any]) -> bool:
    """Validate that pause intervals do not overlap and at most one open pause exists.

    Returns True if valid, False otherwise.
    """
    open_pause_count = 0
    intervals: list[tuple[date, date | None]] = []

    for pause in pauses:
        p_from = getattr(pause, "paused_from", None)
        p_res = getattr(pause, "resumed_on", None)
        if p_from is None:
            return False
        if p_res is not None and p_res <= p_from:
            return False

        if p_res is None:
            open_pause_count += 1
            if open_pause_count > 1:
                return False
        intervals.append((p_from, p_res))

    # Check pairwise overlap
    n = len(intervals)
    for i in range(n):
        from_i, res_i = intervals[i]
        for j in range(i + 1, n):
            from_j, res_j = intervals[j]
            # If both are closed: [from_i, res_i) and [from_j, res_j)
            if res_i is not None and res_j is not None:
                if not (res_i <= from_j or res_j <= from_i):
                    return False
            # If i is open and j is closed: i is [from_i, inf), j is [from_j, res_j)
            elif res_i is None and res_j is not None:
                if res_j > from_i:
                    return False
            # If j is open and i is closed
            elif res_j is None and res_i is not None:
                if res_i > from_j:
                    return False
            else:
                # Both open - already checked by open_pause_count > 1
                return False

    return True


def iter_due_dates(
    start_date: date,
    day_of_month: int,
    end_date: date | None = None,
    pauses: list[Any] | None = None,
    until: date | None = None,
    max_count: int | None = None,
) -> list[date]:
    """Generate due dates starting from first_due_date, excluding pause intervals.

    Returns list of dates. Does not raise exceptions if empty (purity rule).
    """
    first_d = first_due_date(start_date, day_of_month)
    pause_list = pauses or []

    cur_year = first_d.year
    cur_month = first_d.month
    results: list[date] = []

    # Safeguard max search iterations to prevent infinite loop
    max_iterations = 1200  # up to 100 years
    iterations = 0

    while iterations < max_iterations:
        iterations += 1
        candidate = date(cur_year, cur_month, day_of_month)

        if end_date is not None and candidate > end_date:
            break
        if until is not None and candidate > until:
            break

        if not is_date_in_pauses(candidate, pause_list):
            results.append(candidate)
            if max_count is not None and len(results) >= max_count:
                break

        # Move to next month
        if cur_month == 12:
            cur_year += 1
            cur_month = 1
        else:
            cur_month += 1

    return results


def derive_status(
    start_date: date,
    end_date: date | None,
    pauses: list[Any],
    today: date,
) -> str:
    """Pure status derivation from schedule parameters, pauses, and reference date (IST).

    Returns 'ended' | 'paused' | 'scheduled' | 'active'.
    """
    if end_date is not None and end_date < today:
        return "ended"

    for pause in pauses:
        p_from = getattr(pause, "paused_from", None)
        p_res = getattr(pause, "resumed_on", None)
        if p_from is not None and p_from <= today:
            if p_res is None or today < p_res:
                return "paused"

    if start_date > today:
        return "scheduled"

    return "active"


def next_due_date(
    start_date: date,
    day_of_month: int,
    end_date: date | None,
    pauses: list[Any],
    today: date,
) -> date | None:
    """Find the next due date strictly after today, taking pauses into account.

    Returns None if ended or no upcoming due date exists before end_date.
    """
    status = derive_status(start_date, end_date, pauses, today)
    if status == "ended":
        return None

    first_d = first_due_date(start_date, day_of_month)
    cur_year = first_d.year
    cur_month = first_d.month
    pause_list = pauses or []

    max_search = 600
    for _ in range(max_search):
        candidate = date(cur_year, cur_month, day_of_month)
        if end_date is not None and candidate > end_date:
            return None

        if candidate > today and not is_date_in_pauses(candidate, pause_list):
            return candidate

        if cur_month == 12:
            cur_year += 1
            cur_month = 1
        else:
            cur_month += 1

    return None
