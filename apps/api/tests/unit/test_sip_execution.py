"""Unit tests for pure SIP execution logic: pick_nav and unit calculation."""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.services.ledger import compute_holdings
from app.services.sip_execution import build_installment_buy_params, pick_nav


class MockTxn:
    def __init__(
        self,
        fund_id: Any,
        txn_type: str,
        txn_date: date,
        units: Decimal,
        nav: Decimal,
        amount: Decimal,
    ) -> None:
        self.fund_id = fund_id
        self.txn_type = txn_type
        self.txn_date = txn_date
        self.units = units
        self.nav = nav
        self.amount = amount
        self.id = uuid4()


def test_pick_nav_exact_match() -> None:
    points = [
        (date(2025, 1, 9), Decimal("49.00")),
        (date(2025, 1, 10), Decimal("50.00")),
        (date(2025, 1, 11), Decimal("51.00")),
    ]
    today = date(2025, 1, 20)
    res = pick_nav(date(2025, 1, 10), today, points)
    assert res == (date(2025, 1, 10), Decimal("50.00"))


def test_pick_nav_weekend_gap() -> None:
    # Due date is Saturday 2025-05-10
    # NAV points available: Friday 2025-05-09 and Monday 2025-05-12
    points = [
        (date(2025, 5, 9), Decimal("64.00")),
        (date(2025, 5, 12), Decimal("65.00")),
        (date(2025, 5, 13), Decimal("65.50")),
    ]
    today = date(2025, 5, 20)
    res = pick_nav(date(2025, 5, 10), today, points)
    assert res == (date(2025, 5, 12), Decimal("65.00"))


def test_pick_nav_future_date_ignored() -> None:
    # NAV point exists on 2025-05-15, but today is 2025-05-12
    points = [
        (date(2025, 5, 15), Decimal("66.00")),
    ]
    today = date(2025, 5, 12)
    res = pick_nav(date(2025, 5, 10), today, points)
    assert res is None


def test_pick_nav_no_points_available() -> None:
    points: list[tuple[date, Decimal]] = []
    today = date(2025, 5, 20)
    res = pick_nav(date(2025, 5, 10), today, points)
    assert res is None


def test_worked_example_execution_math() -> None:
    """Validate worked example numbers with exact precision."""
    synthetic_nav = [
        (date(2025, 1, 10), Decimal("50.0000")),
        (date(2025, 2, 10), Decimal("55.0000")),
        (date(2025, 3, 10), Decimal("60.0000")),
        (date(2025, 4, 10), Decimal("62.5000")),
        (date(2025, 5, 12), Decimal("65.0000")),  # weekend rollover from May 10
        (date(2025, 6, 10), Decimal("70.0000")),
    ]
    due_dates = [
        date(2025, 1, 10),
        date(2025, 2, 10),
        date(2025, 3, 10),
        date(2025, 4, 10),
        date(2025, 5, 10),
        date(2025, 6, 10),
    ]
    planned_amt = Decimal("5000.00")
    today = date(2025, 6, 20)
    fund_id = uuid4()
    portfolio_id = uuid4()

    txns: list[Any] = []
    expected_units = [
        Decimal("100.0000"),
        Decimal("90.9091"),
        Decimal("83.3333"),
        Decimal("80.0000"),
        Decimal("76.9231"),
        Decimal("71.4286"),
    ]

    for i, due_d in enumerate(due_dates):
        picked = pick_nav(due_d, today, synthetic_nav)
        assert picked is not None
        nav_date, nav = picked
        params = build_installment_buy_params(
            installment_id=uuid4(),
            portfolio_id=portfolio_id,
            fund_id=fund_id,
            planned_amount=planned_amt,
            nav_date=nav_date,
            nav=nav,
        )
        assert params["units"] == expected_units[i]
        assert params["amount"] == planned_amt
        txns.append(
            MockTxn(
                fund_id=fund_id,
                txn_type="buy",
                txn_date=nav_date,
                units=params["units"],
                nav=nav,
                amount=planned_amt,
            )
        )

    # Validate derived holdings
    holdings = compute_holdings(txns)
    fund_holding = holdings[fund_id]

    assert fund_holding.units == Decimal("502.5941")
    assert fund_holding.cost_basis == Decimal("30000.00")
    assert fund_holding.total_bought == Decimal("30000.00")
    assert fund_holding.avg_cost == Decimal("59.6903")
    assert fund_holding.txn_count == 6
