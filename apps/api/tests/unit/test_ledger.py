"""Unit tests for transaction ledger ordering, validation, and average-cost derived holdings."""

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.errors import InsufficientUnitsError, LedgerInconsistentError
from app.services.ledger import (
    compute_holdings,
    compute_realized_gain,
    ledger_sort_key,
    validate_ledger,
)


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

    with pytest.raises(InsufficientUnitsError) as exc_info:
        validate_ledger([t1, t2], mutation_type="add")
    assert exc_info.value.code == "INSUFFICIENT_UNITS"
    assert exc_info.value.status_code == 409


def test_validate_ledger_detects_inconsistent_history() -> None:
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
    t2 = MockTxn(
        id=uuid.uuid4(),
        fund_id=f_id,
        txn_type="SELL",
        txn_date=date(2026, 11, 5),
        units=Decimal("10.0000"),
        nav=Decimal("60.00000000"),
        amount=Decimal("600.00"),
        created_at=datetime(2026, 11, 5, 10, 0, tzinfo=UTC),
    )
    # If editing t1 so it only bought 5 units, downstream t2 becomes inconsistent
    t1_edited = MockTxn(
        id=t1.id,
        fund_id=f_id,
        txn_type="BUY",
        txn_date=date(2026, 11, 1),
        units=Decimal("5.0000"),
        nav=Decimal("50.00000000"),
        amount=Decimal("250.00"),
        created_at=t1.created_at,
    )
    with pytest.raises(LedgerInconsistentError) as exc_info:
        validate_ledger([t1_edited, t2], mutation_type="edit", target_txn_id=str(t1.id))
    assert exc_info.value.code == "LEDGER_INCONSISTENT"
    assert exc_info.value.status_code == 409


def test_compute_holdings_and_realized_gain_worked_example() -> None:
    """Verify worked example from spec:

    BUY 100 @ 50 (5000.00) on 2025-01-10
    BUY 50 @ 60 (3000.00) on 2025-02-10
    SELL 30 @ 70 (2100.00) on 2025-03-10

    Before sell: 150 units, cost 8000.00 (avg 53.33333333)
    Sold: 30 units -> cost basis 30 * (8000/150) = 1600.00
    Realized gain: 2100.00 - 1600.00 = 500.00
    Remaining units: 120.0000
    Remaining cost basis: 6400.00
    Remaining avg cost: 53.3333
    Total bought: 8000.00
    Total sold: 2100.00
    """
    f_id = uuid.uuid4()
    t1 = MockTxn(
        id=uuid.uuid4(),
        fund_id=f_id,
        txn_type="BUY",
        txn_date=date(2025, 1, 10),
        units=Decimal("100.0000"),
        nav=Decimal("50.00000000"),
        amount=Decimal("5000.00"),
        created_at=datetime(2025, 1, 10, 10, 0, tzinfo=UTC),
    )
    t2 = MockTxn(
        id=uuid.uuid4(),
        fund_id=f_id,
        txn_type="BUY",
        txn_date=date(2025, 2, 10),
        units=Decimal("50.0000"),
        nav=Decimal("60.00000000"),
        amount=Decimal("3000.00"),
        created_at=datetime(2025, 2, 10, 10, 0, tzinfo=UTC),
    )
    t3 = MockTxn(
        id=uuid.uuid4(),
        fund_id=f_id,
        txn_type="SELL",
        txn_date=date(2025, 3, 10),
        units=Decimal("30.0000"),
        nav=Decimal("70.00000000"),
        amount=Decimal("2100.00"),
        created_at=datetime(2025, 3, 10, 10, 0, tzinfo=UTC),
    )

    txns = [t1, t2, t3]
    holdings = compute_holdings(txns)
    h = holdings[f_id]

    assert h.units == Decimal("120.0000")
    assert h.cost_basis == Decimal("6400.00")
    assert h.avg_cost == Decimal("53.3333")
    assert h.total_bought == Decimal("8000.00")
    assert h.total_sold == Decimal("2100.00")
    assert h.first_txn_date == date(2025, 1, 10)
    assert h.last_txn_date == date(2025, 3, 10)
    assert h.txn_count == 3
    assert not h.is_closed

    gain = compute_realized_gain(txns)
    assert gain == Decimal("500.00")


def test_compute_holdings_complete_sell_off() -> None:
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

    holdings = compute_holdings([t1, t2])
    h = holdings[f_id]

    assert h.units == Decimal("0.0000")
    assert h.cost_basis == Decimal("0.00")
    assert h.avg_cost == Decimal("0.0000")
    assert h.total_bought == Decimal("5000.00")
    assert h.total_sold == Decimal("5500.00")
    assert h.is_closed

    gain = compute_realized_gain([t1, t2])
    assert gain == Decimal("500.00")


# --- Hypothesis Property-Based Tests ---


@st.composite
def valid_fund_ledger_strategy(draw: st.DrawFn) -> list[MockTxn]:
    """Generates a valid sequence of transactions where running units never drop below zero."""
    fund_id = uuid.uuid4()
    num_steps = draw(st.integers(min_value=1, max_value=8))
    txns: list[MockTxn] = []
    running_units = Decimal("0")
    base_date = date(2025, 1, 1)

    for i in range(num_steps):
        txn_date = base_date + timedelta(days=i)
        is_buy = running_units == Decimal("0") or draw(st.booleans())
        nav_val = Decimal(str(draw(st.integers(min_value=10, max_value=200))))

        if is_buy:
            units_int = draw(st.integers(min_value=1, max_value=100))
            units = Decimal(f"{units_int}.0000")
            running_units += units
            amount = (units * nav_val).quantize(Decimal("0.01"))
            txns.append(
                MockTxn(
                    id=uuid.uuid4(),
                    fund_id=fund_id,
                    txn_type="BUY",
                    txn_date=txn_date,
                    units=units,
                    nav=nav_val.quantize(Decimal("0.00000001")),
                    amount=amount,
                    created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=i),
                )
            )
        else:
            max_sell = int(running_units)
            if max_sell >= 1:
                sell_int = draw(st.integers(min_value=1, max_value=max_sell))
                units = Decimal(f"{sell_int}.0000")
                running_units -= units
                amount = (units * nav_val).quantize(Decimal("0.01"))
                txns.append(
                    MockTxn(
                        id=uuid.uuid4(),
                        fund_id=fund_id,
                        txn_type="SELL",
                        txn_date=txn_date,
                        units=units,
                        nav=nav_val.quantize(Decimal("0.00000001")),
                        amount=amount,
                        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=i),
                    )
                )

    return txns


@given(txns=valid_fund_ledger_strategy())
@settings(max_examples=50)
def test_hypothesis_shuffling_invariance(txns: list[MockTxn]) -> None:
    """compute_holdings result must be identical regardless of input list permutation."""
    original_holdings = compute_holdings(txns)

    shuffled = list(txns)
    random.shuffle(shuffled)
    shuffled_holdings = compute_holdings(shuffled)

    assert original_holdings == shuffled_holdings


@given(txns=valid_fund_ledger_strategy())
@settings(max_examples=50)
def test_hypothesis_final_units_equal_buys_minus_sells(txns: list[MockTxn]) -> None:
    """Final units must exactly equal total units bought minus total units sold."""
    holdings = compute_holdings(txns)
    for fund_id, h in holdings.items():
        total_bought_units = sum(
            (t.units for t in txns if t.fund_id == fund_id and t.txn_type == "BUY"),
            start=Decimal("0.0000"),
        )
        total_sold_units = sum(
            (t.units for t in txns if t.fund_id == fund_id and t.txn_type == "SELL"),
            start=Decimal("0.0000"),
        )
        expected_units = total_bought_units - total_sold_units
        assert h.units == expected_units


@given(txns=valid_fund_ledger_strategy())
@settings(max_examples=50)
def test_hypothesis_sequence_ending_at_zero_units_has_zero_cost(txns: list[MockTxn]) -> None:
    """When all units are sold off, cost basis must be 0.00."""
    fund_id = txns[0].fund_id
    total_bought_units = sum(
        (t.units for t in txns if t.fund_id == fund_id and t.txn_type == "BUY"),
        start=Decimal("0.0000"),
    )
    total_sold_units = sum(
        (t.units for t in txns if t.fund_id == fund_id and t.txn_type == "SELL"),
        start=Decimal("0.0000"),
    )
    remaining = total_bought_units - total_sold_units

    if remaining > Decimal("0"):
        # Add a final sell off
        last_date = max(t.txn_date for t in txns) + timedelta(days=1)
        closing_sell = MockTxn(
            id=uuid.uuid4(),
            fund_id=fund_id,
            txn_type="SELL",
            txn_date=last_date,
            units=remaining,
            nav=Decimal("100.00000000"),
            amount=(remaining * Decimal("100.00")).quantize(Decimal("0.01")),
            created_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC) + timedelta(days=20),
        )
        all_txns = txns + [closing_sell]
    else:
        all_txns = txns

    holdings = compute_holdings(all_txns)
    h = holdings[fund_id]
    assert h.units == Decimal("0.0000")
    assert h.cost_basis == Decimal("0.00")
    assert h.is_closed
