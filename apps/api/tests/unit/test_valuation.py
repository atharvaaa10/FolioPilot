"""Unit tests and Hypothesis property-based tests for pure portfolio valuation."""

import uuid
from datetime import date
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.valuation import (
    FundInfo,
    assemble_fund_cash_flows,
    compute_portfolio_valuation,
)


class MockValuationTxn:
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


def test_example_b_valuation() -> None:
    """Example B: buy 2025-01-01 (10@100=1000), buy 2026-01-01 (10@100=1000).

    latest_nav 115.50 on 2027-01-01.

    Expected:
    current_value: 2310.00
    cost_basis: 2000.00
    unrealized_gain: 310.00
    unrealized_gain_pct: 15.50
    xirr rate: 0.100000
    short_period: False
    ambiguous: False
    """
    fid = uuid.uuid4()
    fund = FundInfo(
        id=fid,
        scheme_code=999101,
        name="Synthetic Valuation Fund B",
        amc="Test AMC",
        asset_class="equity",
        sub_category="flexi-cap",
        plan_type="Direct",
        option_type="Growth",
        latest_nav=Decimal("115.50000000"),
        latest_nav_date=date(2027, 1, 1),
    )
    txns = [
        MockValuationTxn(
            fund_id=fid,
            txn_type="BUY",
            txn_date=date(2025, 1, 1),
            units=Decimal("10.0000"),
            nav=Decimal("100.00000000"),
            amount=Decimal("1000.00"),
        ),
        MockValuationTxn(
            fund_id=fid,
            txn_type="BUY",
            txn_date=date(2026, 1, 1),
            units=Decimal("10.0000"),
            nav=Decimal("100.00000000"),
            amount=Decimal("1000.00"),
        ),
    ]

    res = compute_portfolio_valuation(
        transactions=txns,
        funds_by_id={fid: fund},
        today_ist=date(2027, 1, 1),
    )

    assert len(res.items) == 1
    item = res.items[0]
    assert item.current_value == Decimal("2310.00")
    assert item.cost_basis == Decimal("2000.00")
    assert item.unrealized_gain == Decimal("310.00")
    assert item.unrealized_gain_pct == Decimal("15.50")
    assert item.xirr.rate == "0.100000"
    assert item.xirr.short_period is False
    assert item.xirr.ambiguous is False

    assert res.totals.current_value == Decimal("2310.00")
    assert res.totals.cost_basis == Decimal("2000.00")
    assert res.totals.unrealized_gain == Decimal("310.00")
    assert res.totals.unrealized_gain_pct == Decimal("15.50")
    assert res.totals.xirr.rate == "0.100000"


def test_example_c_valuation_with_realized_and_unrealized() -> None:
    """Example C: buy 100@50, buy 50@60, sell 30@70, latest_nav 80.00.

    units: 120.0000
    cost_basis: 6400.00
    realized_gain: 500.00
    current_value: 9600.00
    unrealized_gain: 3200.00
    unrealized_gain_pct: 50.00
    total_gain: 3700.00
    """
    fid = uuid.uuid4()
    fund = FundInfo(
        id=fid,
        scheme_code=999102,
        name="Synthetic Valuation Fund C",
        amc="Test AMC",
        asset_class="equity",
        sub_category="flexi-cap",
        plan_type="Direct",
        option_type="Growth",
        latest_nav=Decimal("80.00000000"),
        latest_nav_date=date(2025, 3, 10),
    )
    txns = [
        MockValuationTxn(
            fund_id=fid,
            txn_type="BUY",
            txn_date=date(2025, 1, 10),
            units=Decimal("100.0000"),
            nav=Decimal("50.00000000"),
            amount=Decimal("5000.00"),
        ),
        MockValuationTxn(
            fund_id=fid,
            txn_type="BUY",
            txn_date=date(2025, 2, 10),
            units=Decimal("50.0000"),
            nav=Decimal("60.00000000"),
            amount=Decimal("3000.00"),
        ),
        MockValuationTxn(
            fund_id=fid,
            txn_type="SELL",
            txn_date=date(2025, 3, 10),
            units=Decimal("30.0000"),
            nav=Decimal("70.00000000"),
            amount=Decimal("2100.00"),
        ),
    ]

    res = compute_portfolio_valuation(
        transactions=txns,
        funds_by_id={fid: fund},
        today_ist=date(2025, 3, 10),
    )

    item = res.items[0]
    assert item.units == Decimal("120.0000")
    assert item.cost_basis == Decimal("6400.00")
    assert item.realized_gain == Decimal("500.00")
    assert item.current_value == Decimal("9600.00")
    assert item.unrealized_gain == Decimal("3200.00")
    assert item.unrealized_gain_pct == Decimal("50.00")

    assert res.totals.cost_basis == Decimal("6400.00")
    assert res.totals.current_value == Decimal("9600.00")
    assert res.totals.realized_gain == Decimal("500.00")
    assert res.totals.unrealized_gain == Decimal("3200.00")
    assert res.totals.total_gain == Decimal("3700.00")


def test_fallback_cost_and_stale_flags() -> None:
    """Position with no latest_nav falls back to average cost; stale flag set when age > 7 days."""
    fid_fallback = uuid.uuid4()
    fid_stale = uuid.uuid4()

    fund_fallback = FundInfo(
        id=fid_fallback,
        scheme_code=999103,
        name="Fallback Fund",
        amc="Test AMC",
        asset_class="debt",
        sub_category="liquid",
        plan_type="Direct",
        option_type="Growth",
        latest_nav=None,
        latest_nav_date=None,
    )
    fund_stale = FundInfo(
        id=fid_stale,
        scheme_code=999104,
        name="Stale NAV Fund",
        amc="Test AMC",
        asset_class="equity",
        sub_category="large-cap",
        plan_type="Direct",
        option_type="Growth",
        latest_nav=Decimal("100.00000000"),
        latest_nav_date=date(2026, 11, 1),  # 13 days old relative to 2026-11-14
    )

    txns = [
        MockValuationTxn(
            fund_id=fid_fallback,
            txn_type="BUY",
            txn_date=date(2026, 10, 1),
            units=Decimal("10.0000"),
            nav=Decimal("50.00000000"),
            amount=Decimal("500.00"),
        ),
        MockValuationTxn(
            fund_id=fid_stale,
            txn_type="BUY",
            txn_date=date(2026, 10, 1),
            units=Decimal("10.0000"),
            nav=Decimal("90.00000000"),
            amount=Decimal("900.00"),
        ),
    ]

    res = compute_portfolio_valuation(
        transactions=txns,
        funds_by_id={fid_fallback: fund_fallback, fid_stale: fund_stale},
        today_ist=date(2026, 11, 14),
    )

    items_by_code = {it.scheme_code: it for it in res.items}

    # Fallback checks
    fb_item = items_by_code[999103]
    assert fb_item.nav_source == "fallback_cost"
    assert fb_item.nav == Decimal("50.0000")
    assert fb_item.current_value == Decimal("500.00")
    assert fb_item.unrealized_gain == Decimal("0.00")
    assert fb_item.unrealized_gain_pct == Decimal("0.00")
    assert fb_item.xirr.reason == "NO_NAV_DATA"

    # Stale checks
    stale_item = items_by_code[999104]
    assert stale_item.nav_source == "amfi_latest"
    assert stale_item.is_stale is True
    assert stale_item.nav_age_days == 13

    # Totals count
    assert res.totals.fallback_positions == 1
    assert res.totals.stale_positions == 1
    assert res.totals.open_positions == 2
    # Portfolio XIRR excludes fallback fund
    assert res.totals.xirr.excluded_funds == 1


def test_nav_older_than_ledger_terminal_date() -> None:
    """Correction 4: When nav_older_than_ledger applies.

    Terminal date is max(latest_nav_date, last_txn_date).
    """
    fid = uuid.uuid4()
    fund = FundInfo(
        id=fid,
        scheme_code=999105,
        name="Lagging NAV Fund",
        amc="Test AMC",
        asset_class="equity",
        sub_category="flexi-cap",
        plan_type="Direct",
        option_type="Growth",
        latest_nav=Decimal("100.00000000"),
        latest_nav_date=date(2026, 1, 1),  # NAV is dated 2026-01-01
    )
    # But user bought on 2026-02-01 (later than NAV date!)
    txns = [
        MockValuationTxn(
            fund_id=fid,
            txn_type="BUY",
            txn_date=date(2026, 2, 1),
            units=Decimal("10.0000"),
            nav=Decimal("100.00000000"),
            amount=Decimal("1000.00"),
        ),
    ]

    res = compute_portfolio_valuation(
        transactions=txns,
        funds_by_id={fid: fund},
        today_ist=date(2026, 2, 10),
    )

    item = res.items[0]
    assert item.nav_older_than_ledger is True


def test_closed_positions_preserved_and_toggle() -> None:
    """Closed positions keep their realized gain; include_closed controls presence in items."""
    fid = uuid.uuid4()
    fund = FundInfo(
        id=fid,
        scheme_code=999106,
        name="Fully Exited Fund",
        amc="Test AMC",
        asset_class="equity",
        sub_category="mid-cap",
        plan_type="Direct",
        option_type="Growth",
        latest_nav=Decimal("120.00000000"),
        latest_nav_date=date(2026, 5, 1),
    )
    txns = [
        MockValuationTxn(
            fund_id=fid,
            txn_type="BUY",
            txn_date=date(2026, 1, 1),
            units=Decimal("100.0000"),
            nav=Decimal("50.00000000"),
            amount=Decimal("5000.00"),
        ),
        MockValuationTxn(
            fund_id=fid,
            txn_type="SELL",
            txn_date=date(2026, 3, 1),
            units=Decimal("100.0000"),
            nav=Decimal("60.00000000"),
            amount=Decimal("6000.00"),
        ),
    ]

    # Without include_closed: items is empty, but totals track realized gain
    res_ex = compute_portfolio_valuation(
        transactions=txns,
        funds_by_id={fid: fund},
        today_ist=date(2026, 5, 1),
        include_closed=False,
    )
    assert len(res_ex.items) == 0
    assert res_ex.totals.realized_gain == Decimal("1000.00")
    assert res_ex.totals.open_positions == 0

    # With include_closed: item is present with is_closed=True
    res_in = compute_portfolio_valuation(
        transactions=txns,
        funds_by_id={fid: fund},
        today_ist=date(2026, 5, 1),
        include_closed=True,
    )
    assert len(res_in.items) == 1
    assert res_in.items[0].is_closed is True
    assert res_in.items[0].realized_gain == Decimal("1000.00")
    assert res_in.items[0].current_value == Decimal("0.00")


def test_empty_portfolio_valuation() -> None:
    """Empty transactions return clean zeros, nulls, and NO_TRANSACTIONS."""
    res = compute_portfolio_valuation(
        transactions=[],
        funds_by_id={},
        today_ist=date(2026, 11, 14),
    )
    assert res.as_of is None
    assert len(res.items) == 0
    assert res.totals.cost_basis == Decimal("0.00")
    assert res.totals.current_value == Decimal("0.00")
    assert res.totals.unrealized_gain == Decimal("0.00")
    assert res.totals.unrealized_gain_pct is None
    assert res.totals.realized_gain == Decimal("0.00")
    assert res.totals.total_gain == Decimal("0.00")
    assert res.totals.open_positions == 0
    assert res.totals.xirr.reason == "NO_TRANSACTIONS"


def test_valuation_dividend_reinvest_cash_flow_exclusion() -> None:
    """Dividend reinvestment is NOT an external cash flow.

    Applies when DIVIDEND_REINVEST_IS_CASH_FLOW is False.
    """
    fid = uuid.uuid4()
    fund = FundInfo(
        id=fid,
        scheme_code=999105,
        name="Dividend Reinvest Fund",
        amc="Test AMC",
        asset_class="equity",
        sub_category="flexi-cap",
        plan_type="Direct",
        option_type="Growth",
        latest_nav=Decimal("110.00000000"),
        latest_nav_date=date(2026, 1, 1),
    )
    txns = [
        MockValuationTxn(
            fund_id=fid,
            txn_type="BUY",
            txn_date=date(2025, 1, 1),
            units=Decimal("100.0000"),
            nav=Decimal("100.00000000"),
            amount=Decimal("10000.00"),
        ),
        MockValuationTxn(
            fund_id=fid,
            txn_type="DIVIDEND_REINVEST",
            txn_date=date(2025, 6, 1),
            units=Decimal("5.0000"),
            nav=Decimal("100.00000000"),
            amount=Decimal("500.00"),
        ),
    ]

    flows = assemble_fund_cash_flows(
        txns=txns,
        terminal_value=Decimal("11550.00"),
        terminal_date=date(2026, 1, 1),
        is_closed=False,
    )

    # When DIVIDEND_REINVEST_IS_CASH_FLOW is False, exactly 2 flows:
    # initial buy (-10000) and terminal value (+11550).
    # If mutated to True, 3 flows are produced (-10000, -500, +11550), causing this to fail.
    assert len(flows) == 2
    assert flows[0].amount == Decimal("-10000.00")
    assert flows[1].amount == Decimal("11550.00")

    res = compute_portfolio_valuation(
        transactions=txns,
        funds_by_id={fid: fund},
        today_ist=date(2026, 1, 1),
    )
    assert len(res.items) == 1
    # When DIVIDEND_REINVEST is not a cash flow, rate is (11550 / 10000) - 1 = 15.5% (0.155000)
    assert res.items[0].xirr.rate == "0.155000"


# ==============================================================================
# Hypothesis Property-Based Tests
# ==============================================================================


@given(
    u1=st.decimals(min_value=Decimal("1.0"), max_value=Decimal("1000.0"), places=4),
    p1=st.decimals(min_value=Decimal("10.0"), max_value=Decimal("500.0"), places=4),
    u2=st.decimals(min_value=Decimal("1.0"), max_value=Decimal("1000.0"), places=4),
    p2=st.decimals(min_value=Decimal("10.0"), max_value=Decimal("500.0"), places=4),
)
@settings(max_examples=30)
def test_hypothesis_totals_equal_sum_of_rounded_positions(
    u1: Decimal, p1: Decimal, u2: Decimal, p2: Decimal
) -> None:
    """Totals are strictly SUMS of the rounded per-position values, never unrounded totals."""
    fid1 = uuid.uuid4()
    fid2 = uuid.uuid4()

    fund1 = FundInfo(
        id=fid1,
        scheme_code=999111,
        name="Fund 1",
        amc="AMC 1",
        asset_class="equity",
        sub_category="flexi-cap",
        plan_type="Direct",
        option_type="Growth",
        latest_nav=p1,
        latest_nav_date=date(2026, 11, 10),
    )
    fund2 = FundInfo(
        id=fid2,
        scheme_code=999112,
        name="Fund 2",
        amc="AMC 2",
        asset_class="debt",
        sub_category="liquid",
        plan_type="Direct",
        option_type="Growth",
        latest_nav=p2,
        latest_nav_date=date(2026, 11, 10),
    )

    cost1 = (u1 * Decimal("50.00")).quantize(Decimal("0.01"))
    cost2 = (u2 * Decimal("60.00")).quantize(Decimal("0.01"))

    txns = [
        MockValuationTxn(
            fund_id=fid1,
            txn_type="BUY",
            txn_date=date(2026, 1, 1),
            units=u1,
            nav=Decimal("50.00"),
            amount=cost1,
        ),
        MockValuationTxn(
            fund_id=fid2,
            txn_type="BUY",
            txn_date=date(2026, 1, 1),
            units=u2,
            nav=Decimal("60.00"),
            amount=cost2,
        ),
    ]

    res = compute_portfolio_valuation(
        transactions=txns,
        funds_by_id={fid1: fund1, fid2: fund2},
        today_ist=date(2026, 11, 14),
    )

    # Invariant: totals are exact sums of rounded per-position values
    assert res.totals.cost_basis == sum(it.cost_basis for it in res.items)
    assert res.totals.current_value == sum(it.current_value for it in res.items)
    assert res.totals.unrealized_gain == sum(it.unrealized_gain for it in res.items)
    assert res.totals.realized_gain == sum(it.realized_gain for it in res.items)
    assert res.totals.total_gain == res.totals.unrealized_gain + res.totals.realized_gain
