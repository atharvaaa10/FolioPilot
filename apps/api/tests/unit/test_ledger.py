"""Unit tests for transaction ledger ordering, validation, and average-cost positions."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core.errors import InsufficientUnitsError
from app.services.ledger import compute_positions, ledger_sort_key, validate_ledger


@dataclass
class MockTxn:
    id: uuid.UUID
    fund_id: uuid.UUID
    txn_type: str
    txn_date: date
    units: Decimal
    nav: Decimal
    amount: Decimal
    created_at: datetime


def test_ledger_sort_key_buy_before_sell_on_same_date() -> None:
    f_id = uuid.uuid4()
    t_sell = MockTxn(
        id=uuid.uuid4(),
        fund_id=f_id,
        txn_type="SELL",
        txn_date=date(2026, 11, 1),
        units=Decimal("10.0000"),
        nav=Decimal("100.00000000"),
        amount=Decimal("1000.00"),
        created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
    )
    t_buy = MockTxn(
        id=uuid.uuid4(),
        fund_id=f_id,
        txn_type="BUY",
        txn_date=date(2026, 11, 1),
        units=Decimal("10.0000"),
        nav=Decimal("100.00000000"),
        amount=Decimal("1000.00"),
        created_at=datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
    )

    # Sort key puts BUY (rank 0) before SELL (rank 1) even though SELL was created earlier
    assert ledger_sort_key(t_buy) < ledger_sort_key(t_sell)

    # validate_ledger succeeds because BUY processes first
    validate_ledger([t_sell, t_buy])


def test_validate_ledger_rejects_oversell() -> None:
    f_id = uuid.uuid4()
    t1 = MockTxn(
        id=uuid.uuid4(),
        fund_id=f_id,
        txn_type="BUY",
        txn_date=date(2026, 11, 1),
        units=Decimal("10.0000"),
        nav=Decimal("50.00000000"),
        amount=Decimal("500.00"),
        created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
    )
    # Attempting to sell 15 units when only 10 are available
    t2 = MockTxn(
        id=uuid.uuid4(),
        fund_id=f_id,
        txn_type="SELL",
        txn_date=date(2026, 11, 2),
        units=Decimal("15.0000"),
        nav=Decimal("60.00000000"),
        amount=Decimal("900.00"),
        created_at=datetime(2026, 11, 2, 10, 0, tzinfo=UTC),
    )

    with pytest.raises(InsufficientUnitsError, match="Insufficient units"):
        validate_ledger([t1, t2])


def test_compute_positions_worked_example() -> None:
    """Verify average-cost calculation:

    Buy 100 @ 10 -> 1000
    Buy 100 @ 20 -> 2000 (total units 200, total invested 3000, avg NAV 15)
    Sell 50 @ 25 -> 1250 (gain = 500, units 150, invested 2250, avg NAV 15)
    """
    f_id = uuid.uuid4()
    t1 = MockTxn(
        id=uuid.uuid4(),
        fund_id=f_id,
        txn_type="BUY",
        txn_date=date(2026, 11, 1),
        units=Decimal("100.0000"),
        nav=Decimal("10.00000000"),
        amount=Decimal("1000.00"),
        created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
    )
    t2 = MockTxn(
        id=uuid.uuid4(),
        fund_id=f_id,
        txn_type="BUY",
        txn_date=date(2026, 11, 2),
        units=Decimal("100.0000"),
        nav=Decimal("20.00000000"),
        amount=Decimal("2000.00"),
        created_at=datetime(2026, 11, 2, 10, 0, tzinfo=UTC),
    )
    t3 = MockTxn(
        id=uuid.uuid4(),
        fund_id=f_id,
        txn_type="SELL",
        txn_date=date(2026, 11, 3),
        units=Decimal("50.0000"),
        nav=Decimal("25.00000000"),
        amount=Decimal("1250.00"),
        created_at=datetime(2026, 11, 3, 10, 0, tzinfo=UTC),
    )

    positions = compute_positions([t1, t2, t3])
    pos = positions[f_id]

    assert pos.units == Decimal("150.0000")
    assert pos.total_invested == Decimal("2250.00")
    assert pos.avg_nav == Decimal("15.00000000")
    assert pos.realized_gain == Decimal("500.00")


def test_compute_positions_complete_sell_off() -> None:
    f_id = uuid.uuid4()
    t1 = MockTxn(
        id=uuid.uuid4(),
        fund_id=f_id,
        txn_type="BUY",
        txn_date=date(2026, 11, 1),
        units=Decimal("50.0000"),
        nav=Decimal("100.00000000"),
        amount=Decimal("5000.00"),
        created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
    )
    t2 = MockTxn(
        id=uuid.uuid4(),
        fund_id=f_id,
        txn_type="SELL",
        txn_date=date(2026, 11, 2),
        units=Decimal("50.0000"),
        nav=Decimal("110.00000000"),
        amount=Decimal("5500.00"),
        created_at=datetime(2026, 11, 2, 10, 0, tzinfo=UTC),
    )

    positions = compute_positions([t1, t2])
    pos = positions[f_id]

    assert pos.units == Decimal("0.0000")
    assert pos.total_invested == Decimal("0.00")
    assert pos.avg_nav == Decimal("0.00000000")
    assert pos.realized_gain == Decimal("500.00")
