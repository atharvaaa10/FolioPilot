"""Unit and property tests for pure SIP scheduling, step-up, and status derivation."""

from datetime import date
from decimal import Decimal
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from app.services.ledger import validate_ledger
from app.services.sip_schedule import (
    compute_k,
    derive_status,
    first_due_date,
    iter_due_dates,
    next_due_date,
    planned_amount,
    validate_pauses,
)


class MockPause:
    def __init__(self, paused_from: date, resumed_on: date | None = None) -> None:
        self.paused_from = paused_from
        self.resumed_on = resumed_on


class MockTxn:
    def __init__(self, fund_id: Any, txn_type: str, txn_date: date, units: Decimal) -> None:
        self.fund_id = fund_id
        self.txn_type = txn_type
        self.txn_date = txn_date
        self.units = units
        self.id = "mock"


# ==============================================================================
# 1. first_due_date rules
# ==============================================================================
def test_first_due_date_start_before_day() -> None:
    # Start: Jan 5, Day: 10 -> Jan 10
    assert first_due_date(date(2025, 1, 5), 10) == date(2025, 1, 10)


def test_first_due_date_start_on_day() -> None:
    # Start: Jan 10, Day: 10 -> Jan 10
    assert first_due_date(date(2025, 1, 10), 10) == date(2025, 1, 10)


def test_first_due_date_start_after_day() -> None:
    # Start: Jan 15, Day: 10 -> Feb 10
    assert first_due_date(date(2025, 1, 15), 10) == date(2025, 2, 10)


def test_first_due_date_december_rollover() -> None:
    # Start: Dec 20, Day: 5 -> Jan 5 next year
    assert first_due_date(date(2024, 12, 20), 5) == date(2025, 1, 5)


# ==============================================================================
# 2. Step-up planned_amount & compute_k
# ==============================================================================
def test_planned_amount_tiers() -> None:
    base = Decimal("5000.00")
    step_up = Decimal("10")

    # k = 0: Year 1
    assert planned_amount(base, step_up, 0) == Decimal("5000.00")
    # k = 1: Year 2 (13th installment, 2026-01-10) -> 5500.00
    assert planned_amount(base, step_up, 1) == Decimal("5500.00")
    # k = 2: Year 3 (25th installment, 2027-01-10) -> 6050.00
    assert planned_amount(base, step_up, 2) == Decimal("6050.00")


def test_step_up_rounding_half_up() -> None:
    base = Decimal("333.33")
    step_up = Decimal("5.55")
    # k = 1: 333.33 * 1.0555 = 351.829815 -> 351.83
    assert planned_amount(base, step_up, 1) == Decimal("351.83")


def test_step_up_with_pause_covering_first_due_date() -> None:
    """Correction 6: k is counted from FIRST due date of schedule without pauses,

    even when that first due date falls inside a pause.
    """
    start = date(2025, 1, 5)
    day = 10
    # First due date without pauses is 2025-01-10
    origin = first_due_date(start, day)
    assert origin == date(2025, 1, 10)

    # Pause from 2025-01-01 to 2025-04-01 covers 2025-01-10
    pauses = [MockPause(date(2025, 1, 1), date(2025, 4, 1))]
    due_dates = iter_due_dates(start, day, pauses=pauses, max_count=20)

    # First generated due date is April 10, 2025
    assert due_dates[0] == date(2025, 4, 10)
    k_first = compute_k(origin, due_dates[0])
    assert k_first == 0  # 3 months diff // 12 = 0
    assert planned_amount(Decimal("5000.00"), Decimal("10"), k_first) == Decimal("5000.00")

    # Due date on 2026-01-10 is exactly 12 months from 2025-01-10
    jan_2026 = next(d for d in due_dates if d == date(2026, 1, 10))
    k_jan_2026 = compute_k(origin, jan_2026)
    assert k_jan_2026 == 1  # 12 months diff // 12 = 1
    assert planned_amount(Decimal("5000.00"), Decimal("10"), k_jan_2026) == Decimal("5500.00")


# ==============================================================================
# 3. iter_due_dates & pause filtering
# ==============================================================================
def test_iter_due_dates_worked_example_pause() -> None:
    # Worked example pause: pause from 2025-03-01 to 2025-05-01
    start = date(2025, 1, 5)
    day = 10
    pauses = [MockPause(date(2025, 3, 1), date(2025, 5, 1))]
    dates = iter_due_dates(start, day, pauses=pauses, until=date(2025, 6, 20))

    expected = [
        date(2025, 1, 10),
        date(2025, 2, 10),
        # 2025-03-10 skipped
        # 2025-04-10 skipped
        date(2025, 5, 10),
        date(2025, 6, 10),
    ]
    assert dates == expected


def test_iter_due_dates_end_date_inclusive() -> None:
    start = date(2025, 1, 10)
    day = 10
    end = date(2025, 3, 10)
    dates = iter_due_dates(start, day, end_date=end)
    assert dates == [date(2025, 1, 10), date(2025, 2, 10), date(2025, 3, 10)]


def test_iter_due_dates_open_pause() -> None:
    start = date(2025, 1, 10)
    day = 10
    pauses = [MockPause(date(2025, 3, 1), None)]  # open pause from March 1
    dates = iter_due_dates(start, day, pauses=pauses, until=date(2025, 6, 10))
    assert dates == [date(2025, 1, 10), date(2025, 2, 10)]


# ==============================================================================
# 4. validate_pauses
# ==============================================================================
def test_validate_pauses_valid() -> None:
    pauses = [
        MockPause(date(2025, 2, 1), date(2025, 3, 1)),
        MockPause(date(2025, 4, 1), date(2025, 5, 1)),
    ]
    assert validate_pauses(pauses) is True


def test_validate_pauses_overlapping_closed() -> None:
    pauses = [
        MockPause(date(2025, 2, 1), date(2025, 3, 15)),
        MockPause(date(2025, 3, 1), date(2025, 4, 1)),
    ]
    assert validate_pauses(pauses) is False


def test_validate_pauses_two_open_pauses() -> None:
    pauses = [
        MockPause(date(2025, 2, 1), None),
        MockPause(date(2025, 4, 1), None),
    ]
    assert validate_pauses(pauses) is False


def test_validate_pauses_open_overlapping_closed() -> None:
    pauses = [
        MockPause(date(2025, 3, 1), None),
        MockPause(date(2025, 2, 1), date(2025, 3, 15)),
    ]
    assert validate_pauses(pauses) is False


# ==============================================================================
# 5. derive_status
# ==============================================================================
def test_derive_status_ended() -> None:
    today = date(2025, 6, 20)
    assert derive_status(date(2025, 1, 1), date(2025, 6, 19), [], today) == "ended"


def test_derive_status_scheduled() -> None:
    today = date(2025, 6, 20)
    assert derive_status(date(2025, 6, 21), None, [], today) == "scheduled"


def test_derive_status_active() -> None:
    today = date(2025, 6, 20)
    assert derive_status(date(2025, 1, 1), None, [], today) == "active"
    assert derive_status(date(2025, 6, 20), None, [], today) == "active"


def test_derive_status_paused_open() -> None:
    today = date(2025, 6, 20)
    pauses = [MockPause(date(2025, 6, 15), None)]
    assert derive_status(date(2025, 1, 1), None, pauses, today) == "paused"


def test_derive_status_paused_closed() -> None:
    today = date(2025, 6, 20)
    # Today is inside [June 15, June 25)
    pauses = [MockPause(date(2025, 6, 15), date(2025, 6, 25))]
    assert derive_status(date(2025, 1, 1), None, pauses, today) == "paused"

    # Today is on or after resumed_on -> active
    pauses_resumed = [MockPause(date(2025, 6, 10), date(2025, 6, 20))]
    assert derive_status(date(2025, 1, 1), None, pauses_resumed, today) == "active"


# ==============================================================================
# 6. next_due_date
# ==============================================================================
def test_next_due_date_calculation() -> None:
    today = date(2025, 6, 20)
    # Day 10: next due date after June 20 is July 10, 2025
    assert next_due_date(date(2025, 1, 1), 10, None, [], today) == date(2025, 7, 10)

    # If July 10 is paused, advances to August 10
    pauses = [MockPause(date(2025, 7, 1), date(2025, 7, 20))]
    assert next_due_date(date(2025, 1, 1), 10, None, pauses, today) == date(2025, 8, 10)

    # If end_date is before next due date -> None
    assert next_due_date(date(2025, 1, 1), 10, date(2025, 6, 30), [], today) is None


# ==============================================================================
# 7. Hypothesis Property-Based Tests
# ==============================================================================
@given(
    start_year=st.integers(min_value=2020, max_value=2028),
    start_month=st.integers(min_value=1, max_value=12),
    start_day=st.integers(min_value=1, max_value=28),
    day_of_month=st.integers(min_value=1, max_value=28),
    months_span=st.integers(min_value=1, max_value=36),
)
def test_property_due_dates_strictly_increasing_and_match_day(
    start_year: int,
    start_month: int,
    start_day: int,
    day_of_month: int,
    months_span: int,
) -> None:
    start = date(start_year, start_month, start_day)
    due_dates = iter_due_dates(start, day_of_month, max_count=months_span)

    assert len(due_dates) <= months_span
    for i, d in enumerate(due_dates):
        assert d.day == day_of_month
        assert d >= start
        if i > 0:
            assert d > due_dates[i - 1]


@given(
    base=st.decimals(
        min_value=Decimal("100"), max_value=Decimal("100000"), places=2, allow_nan=False
    ),
    step_up=st.decimals(min_value=Decimal("0"), max_value=Decimal("50"), places=2, allow_nan=False),
    k1=st.integers(min_value=0, max_value=10),
    k2=st.integers(min_value=11, max_value=20),
)
def test_property_planned_amounts_never_decrease_with_non_negative_step_up(
    base: Decimal,
    step_up: Decimal,
    k1: int,
    k2: int,
) -> None:
    amt1 = planned_amount(base, step_up, k1)
    amt2 = planned_amount(base, step_up, k2)
    assert amt2 >= amt1


@given(
    num_buys=st.integers(min_value=1, max_value=15),
    units_per_buy=st.decimals(
        min_value=Decimal("1"), max_value=Decimal("1000"), places=4, allow_nan=False
    ),
)
def test_property_generated_buys_never_violate_ledger(
    num_buys: int,
    units_per_buy: Decimal,
) -> None:
    txns = []
    fund_id = "00000000-0000-0000-0000-000000000001"
    cur_date = date(2025, 1, 10)

    for i in range(num_buys):
        m = (cur_date.month + i - 1) % 12 + 1
        y = cur_date.year + (cur_date.month + i - 1) // 12
        txns.append(
            MockTxn(
                fund_id=fund_id,
                txn_type="buy",
                txn_date=date(y, m, 10),
                units=units_per_buy,
            )
        )

    # validate_ledger must never raise for sequential buys
    validate_ledger(txns)
