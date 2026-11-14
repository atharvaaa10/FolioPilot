"""Unit tests and Hypothesis property-based tests for pure value-over-time series."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.ledger import compute_holdings
from app.services.value_series import (
    PricePoint,
    sample_dates,
    value_series,
)


class MockSeriesTxn:
    def __init__(
        self,
        fund_id: uuid.UUID,
        txn_type: str,
        txn_date: date,
        units: Decimal,
        nav: Decimal,
        amount: Decimal,
    ) -> None:
        self.id = uuid.uuid4()
        self.fund_id = fund_id
        self.txn_type = txn_type
        self.txn_date = txn_date
        self.units = units
        self.nav = nav
        self.amount = amount


def test_example_d_series() -> None:
    """Example D:
    Buy 2025-01-10: 100@50 (5000)
    Buy 2025-02-10: 50@60 (3000)
    Sell 2025-03-10: 30@70 (2100)
    On 2025-02-15: value 9000.00, cost_basis 8000.00
    On 2025-03-10: value 8400.00, cost_basis 6400.00
    With official NAV 69.00 on 2025-03-10: value 8280.00 (official wins on equal dates)
    With official NAV 72.00 on 2025-03-20: value 8640.00 on 2025-03-20
    Dates before first transaction produce no point.
    """
    fid = uuid.uuid4()
    txns = [
        MockSeriesTxn(
            fund_id=fid,
            txn_type="BUY",
            txn_date=date(2025, 1, 10),
            units=Decimal("100.0000"),
            nav=Decimal("50.00000000"),
            amount=Decimal("5000.00"),
        ),
        MockSeriesTxn(
            fund_id=fid,
            txn_type="BUY",
            txn_date=date(2025, 2, 10),
            units=Decimal("50.0000"),
            nav=Decimal("60.00000000"),
            amount=Decimal("3000.00"),
        ),
        MockSeriesTxn(
            fund_id=fid,
            txn_type="SELL",
            txn_date=date(2025, 3, 10),
            units=Decimal("30.0000"),
            nav=Decimal("70.00000000"),
            amount=Decimal("2100.00"),
        ),
    ]

    dates_test_1 = [date(2025, 1, 1), date(2025, 2, 15), date(2025, 3, 10)]
    pts_1 = value_series(transactions=txns, price_points=[], dates=dates_test_1)

    # Date before first transaction (2025-01-01) produces no point
    assert len(pts_1) == 2
    assert pts_1[0].date == "2025-02-15"
    assert pts_1[0].value == "9000.00"
    assert pts_1[0].cost_basis == "8000.00"

    assert pts_1[1].date == "2025-03-10"
    assert pts_1[1].value == "8400.00"
    assert pts_1[1].cost_basis == "6400.00"

    # Now add official NAV of 69.00 on 2025-03-10 (official wins on equal dates)
    # and official NAV of 72.00 on 2025-03-20
    official_prices = [
        PricePoint(
            fund_id=fid,
            nav_date=date(2025, 3, 10),
            nav=Decimal("69.00000000"),
            is_official=True,
        ),
        PricePoint(
            fund_id=fid,
            nav_date=date(2025, 3, 20),
            nav=Decimal("72.00000000"),
            is_official=True,
        ),
    ]
    dates_test_2 = [date(2025, 3, 10), date(2025, 3, 20)]
    pts_2 = value_series(transactions=txns, price_points=official_prices, dates=dates_test_2)

    assert len(pts_2) == 2
    assert pts_2[0].date == "2025-03-10"
    assert pts_2[0].value == "8280.00"  # 120 * 69.00
    assert pts_2[0].cost_basis == "6400.00"

    assert pts_2[1].date == "2025-03-20"
    assert pts_2[1].value == "8640.00"  # 120 * 72.00
    assert pts_2[1].cost_basis == "6400.00"


def test_sample_dates_ranges_and_caps() -> None:
    """Verify sample steps per range and MAX_SERIES_POINTS cap, with last date always included."""
    today = date(2026, 11, 14)

    # 1m daily
    d_1m = sample_dates("1m", first_txn_date=date(2025, 1, 1), today_ist=today)
    assert d_1m[-1] == today
    assert (d_1m[1] - d_1m[0]).days == 1

    # 1y weekly
    d_1y = sample_dates("1y", first_txn_date=date(2025, 1, 1), today_ist=today)
    assert d_1y[-1] == today
    assert (d_1y[1] - d_1y[0]).days == 7

    # Start date constrained by first_txn_date if later than range start
    d_late = sample_dates("1y", first_txn_date=date(2026, 11, 1), today_ist=today)
    assert d_late[0] == date(2026, 11, 1)
    assert d_late[-1] == today

    # Points capped at MAX_SERIES_POINTS
    d_long = sample_dates("max", first_txn_date=date(1990, 1, 1), today_ist=today)
    assert len(d_long) <= 400
    assert d_long[-1] == today


# ==============================================================================
# Hypothesis Property-Based Tests
# ==============================================================================


@given(
    days_held=st.integers(min_value=1, max_value=200),
    units=st.decimals(min_value=Decimal("1.0"), max_value=Decimal("500.0"), places=4),
    price=st.decimals(min_value=Decimal("10.0"), max_value=Decimal("200.0"), places=4),
)
@settings(max_examples=30)
def test_hypothesis_sweep_versus_compute_positions_parity(
    days_held: int, units: Decimal, price: Decimal
) -> None:
    """value_series at any date equals point-in-time holdings and cost basis."""
    fid = uuid.uuid4()
    start_d = date(2025, 1, 1)
    target_d = start_d + timedelta(days=days_held)

    cost = (units * Decimal("50.00")).quantize(Decimal("0.01"))
    txn = MockSeriesTxn(
        fund_id=fid,
        txn_type="BUY",
        txn_date=start_d,
        units=units,
        nav=Decimal("50.00"),
        amount=cost,
    )

    p_point = PricePoint(
        fund_id=fid,
        nav_date=target_d,
        nav=price,
        is_official=True,
    )

    pts = value_series(
        transactions=[txn],
        price_points=[p_point],
        dates=[target_d],
    )
    assert len(pts) == 1
    pt = pts[0]

    # Compare with point-in-time compute_holdings
    h = compute_holdings([txn])[fid]
    expected_cost = str(h.cost_basis)
    expected_value = str((h.units * price).quantize(Decimal("0.01")))

    assert pt.cost_basis == expected_cost
    assert pt.value == expected_value
